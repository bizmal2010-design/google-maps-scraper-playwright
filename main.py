# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def get_phone_from_sidebar(page):
    phone_btn = await page.query_selector('button[data-item-id^="phone:tel:"]')
    if phone_btn:
        phone_data = await phone_btn.get_attribute('data-item-id')
        if phone_data:
            return phone_data.replace('phone:tel:', '')
    return "N/A"

async def extract_name(card):
    name_el = await card.query_selector('div.qBF1Pd')
    if name_el:
        text = await name_el.inner_text()
        if text.strip():
            return text.strip()
    link_el = await card.query_selector('a.hfpxzc')
    if link_el:
        label = await link_el.get_attribute('aria-label')
        if label:
            return label.split(' · Visited link')[0].strip()
    return "N/A"

async def extract_rating_and_reviews(card):
    rating = "N/A"
    reviews = "N/A"
    wrapper = await card.query_selector('span.ZkP5Je')
    if wrapper:
        label = await wrapper.get_attribute('aria-label')
        if label:
            match = re.search(r'([\d.]+)\s*stars?\s*([\d,]+)\s*Reviews?', label, re.IGNORECASE)
            if match:
                rating = match.group(1)
                reviews = match.group(2).replace(',', '')
                return rating, reviews
    rating_el = await card.query_selector('span.MW4etd')
    reviews_el = await card.query_selector('span.UY7F9')
    if rating_el:
        text = await rating_el.inner_text()
        rating = text.strip()
    if reviews_el:
        raw = await reviews_el.inner_text()
        reviews = re.sub(r'[^\d]', '', raw)
    return rating, reviews

async def extract_place_url(card):
    link_el = await card.query_selector('a.hfpxzc')
    if link_el:
        href = await link_el.get_attribute('href')
        if href:
            return href
    return "N/A"

async def wait_for_panel_ready(page, expected_name, timeout=8000):
    # شرط مستقل عن اللغة: بعض العيادات تفتح لوحتها بالإنجليزية وبعضها بالعربية
    # (Information for ... / معلومات عن ...)، لذلك نعتمد على الكلاسات الثابتة
    # بدل نص العنوان، ونتحقق فقط أن اسم العيادة موجود بداخله
    try:
        await page.wait_for_function(
            """(expectedName) => {
                const panels = document.querySelectorAll('div.m6QErb.XiKgde[role="region"]');
                for (const panel of panels) {
                    const label = panel.getAttribute('aria-label') || '';
                    if (label.includes(expectedName)) return true;
                }
                return false;
            }""",
            arg=expected_name,
            timeout=timeout
        )
        return True
    except Exception:
        return False

async def scrape_google_maps(search_query, total_results=80):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--lang=en-US',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-gpu'
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1600, "height": 900}
        )
        page = await context.new_page()
        print(f"[*] Starting search for: {search_query}")

        await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font", "stylesheet"] else route.continue_())

        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()
        stagnant_rounds = 0
        current_index = 0

        try:
            while len(results) < total_results:
                cards_locator = page.locator('div[role="article"]')
                count = await cards_locator.count()

                if current_index >= count:
                    if count > 0:
                        last_card = cards_locator.nth(count - 1)
                        await last_card.hover()
                    await page.mouse.wheel(0, 3000)
                    await page.wait_for_timeout(3000)

                    new_count = await cards_locator.count()
                    if new_count == count:
                        stagnant_rounds += 1
                        if stagnant_rounds >= 3:
                            print("[!] No new results found after several scroll attempts. Stopping search.")
                            break
                    else:
                        stagnant_rounds = 0
                    continue

                card_handle = await cards_locator.nth(current_index).element_handle()
                if not card_handle:
                    current_index += 1
                    continue

                try:
                    place_url = await extract_place_url(card_handle)
                    name = await extract_name(card_handle)
                    key = place_url if place_url != "N/A" else name

                    if key in seen or name == "N/A":
                        await card_handle.dispose()
                        current_index += 1
                        continue

                    rating, reviews = await extract_rating_and_reviews(card_handle)
                    phone = "N/A"
                    website = "N/A"

                    # نضغط على كل عيادة دائماً، ونأخذ الهاتف والموقع مباشرة من اللوحة
                    link_to_click = await card_handle.query_selector('a.hfpxzc')
                    if link_to_click:
                        await link_to_click.click()
                        panel_ready = await wait_for_panel_ready(page, name)

                        if panel_ready:
                            phone = await get_phone_from_sidebar(page)

                            web_btn = await page.query_selector('a[data-item-id="authority"]')
                            if web_btn:
                                website = await web_btn.get_attribute('href') or "N/A"

                            if reviews == "N/A":
                                rev_el = await page.query_selector('div.F7nice span[role="img"]')
                                if rev_el:
                                    lbl = await rev_el.get_attribute('aria-label')
                                    if lbl:
                                        match = re.search(r'([\d,]+)', lbl)
                                        if match:
                                            reviews = match.group(1).replace(',', '')

                        back_btn = page.locator('button[aria-label="Back"], button[aria-label="رجوع"]')
                        if await back_btn.count() > 0:
                            await back_btn.first.click()
                            await page.wait_for_timeout(1500)

                    results.append({
                        "Name": name,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Phone": phone,
                        "Website": website,
                        "MapURL": place_url
                    })

                    print(f"[+] Extracted: {name} | Phone: {phone} | Rating: {rating} | Reviews: {reviews} | Website: {website}")
                    seen.add(key)

                except Exception as e:
                    print(f"[-] Error extracting data for a clinic: {e}")
                    try:
                        back_btn = page.locator('button[aria-label="Back"], button[aria-label="رجوع"]')
                        if await back_btn.count() > 0:
                            await back_btn.first.click()
                            await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                await card_handle.dispose()
                current_index += 1
        except Exception as e:
            print(f"[!] Scraping stopped due to an unexpected error, but all {len(results)} results collected so far are preserved: {e}")

        print(f"[*] Task completed. Total results: {len(results)}")
        await browser.close()
        return results

if __name__ == "__main__":
    data = asyncio.run(scrape_google_maps("Dental Clinics in Dubai"))
    for i, item in enumerate(data, 1):
        print(f"{i}. {item['Name']} | Phone: {item['Phone']} | Rating: {item['Rating']} | Reviews: {item['Reviews']} | Website: {item['Website']}")
