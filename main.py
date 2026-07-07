# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from playwright.async_api import async_playwright
from apify import Actor  # استيراد مكتبة Apify لحفظ البيانات برمجياً

sys.stdout.reconfigure(encoding='utf-8')

async def get_phone_from_sidebar(page):
    phone_btn = await page.query_selector('button[data-item-id^="phone:tel:"]')
    if phone_btn:
        phone_data = await phone_btn.get_attribute('data-item-id')
        if phone_data:
            return phone_data.replace('phone:tel:', '').strip()
    
    elements = await page.query_selector_all('button[aria-label^="Phone:"]')
    for el in elements:
        label = await el.get_attribute('aria-label')
        if label:
            return label.replace('Phone:', '').strip()
            
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
    
    wrapper = await card.query_selector('span[aria-label*="stars" i]')
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

async def fetch_details_in_new_tab(context, place_url, timeout=20000):
    detail_page = await context.new_page()
    phone, website, reviews = "N/A", "N/A", "N/A"
    try:
        await detail_page.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_()
        )
        await detail_page.goto(place_url, timeout=timeout)
        await detail_page.wait_for_selector('h1.DUwDvf', timeout=timeout)

        phone = await get_phone_from_sidebar(detail_page)

        web_btn = await detail_page.query_selector('a[data-item-id="authority"]')
        if web_btn:
            website = await web_btn.get_attribute('href') or "N/A"

        f7nice_el = await detail_page.query_selector('div.F7nice')
        if f7nice_el:
            f7_text = await f7nice_el.inner_text()
            paren_match = re.search(r'\(([\d,]+)\)', f7_text)
            if paren_match:
                reviews = paren_match.group(1).replace(',', '')
                        
    except Exception:
        pass
    finally:
        await detail_page.close()

    return phone, website, reviews

async def main():
    # بدء تشغيل أداة Apify
    async with Actor:
        # يمكنك جلب الكلمات البحثية من الـ Input الخاص بالمنصة أو كتابتها مباشرة هنا
        actor_input = await Actor.get_input() or {}
        search_query = actor_input.get("search_query", "Dental Clinics in Dubai")
        total_results = actor_input.get("total_results", 80)

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

            await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())

            await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
            await page.wait_for_timeout(5000)

            results_count = 0
            seen = set()
            stagnant_rounds = 0
            current_index = 0

            try:
                while results_count < total_results:
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
                                print("[!] No new results found. Stopping search.")
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

                        if place_url != "N/A":
                            phone, website, fallback_reviews = await fetch_details_in_new_tab(context, place_url)
                            if reviews == "N/A" or reviews == "":
                                reviews = fallback_reviews
                        else:
                            phone, website = "N/A", "N/A"

                        clinic_data = {
                            "Name": name,
                            "Rating": rating,
                            "Reviews": reviews,
                            "Phone": phone,
                            "Website": website,
                            "MapURL": place_url
                        }

                        # السطر السحري: دفع البيانات مباشرة إلى مخزن Apify لكي تظهر في الـ Dataset فوراً
                        await Actor.push_data(clinic_data)

                        print(f"[+] Extracted & Saved: {name} | Phone: {phone}")
                        seen.add(key)
                        results_count += 1

                    except Exception as e:
                        print(f"[-] Error: {e}")

                    await card_handle.dispose()
                    current_index += 1
            except Exception as e:
                print(f"[!] Scraping stopped: {e}")

            print(f"[*] Task completed. Total saved results: {results_count}")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
