# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

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
            return label.strip()
    return "N/A"

async def extract_rating_and_reviews(card):
    rating = "N/A"
    reviews = "N/A"
    
    wrapper = await card.query_selector('span[role="img"]')
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

async def extract_phone_from_card(card):
    phone_el = await card.query_selector('span.UsdlK')
    if phone_el:
        text = await phone_el.inner_text()
        return text.strip()
    return "N/A"

async def extract_website_from_card(card):
    web_el = await card.query_selector('a.lcr4fd[data-value="Website"]')
    if web_el:
        href = await web_el.get_attribute('href')
        if href:
            return href
    return "N/A"

async def extract_place_url(card):
    link_el = await card.query_selector('a.hfpxzc')
    if link_el:
        href = await link_el.get_attribute('href')
        if href:
            return href
    return "N/A"

async def scrape_google_maps(search_query, total_results=80):
    async with async_playwright() as p:
        # إضافة إعدادات لمنع انهيار الذاكرة
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--lang=en-US', 
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage' # يحمي المتصفح من الانهيار عند امتلاء الذاكرة
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1600, "height": 900}
        )
        page = await context.new_page()
        print(f"[*] Starting search for: {search_query}")
        
        # حظر الصور لتسريع الكشط ومنع الانهيار
        await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font", "stylesheet"] else route.continue_())
        
        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()
        stagnant_rounds = 0
        current_index = 0 # تعقب مكاننا في القائمة بدلاً من حلقة for الكبيرة

        while len(results) < total_results:
            cards_locator = page.locator('div[role="article"]')
            count = await cards_locator.count()

            # إذا وصلنا لنهاية القائمة المحملة، نقوم بالتمرير لأسفل
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

            # استخراج عيادة واحدة فقط في كل مرة للحفاظ على الذاكرة
            card_handle = await cards_locator.nth(current_index).element_handle()
            if not card_handle:
                current_index += 1
                continue

            try:
                place_url = await extract_place_url(card_handle)
                name = await extract_name(card_handle)
                key = place_url if place_url != "N/A" else name

                if key in seen or name == "N/A":
                    await card_handle.dispose() # تفريغ الذاكرة
                    current_index += 1
                    continue

                rating, reviews = await extract_rating_and_reviews(card_handle)
                phone = await extract_phone_from_card(card_handle)
                website = await extract_website_from_card(card_handle)

                # النقر على العيادة إذا احتجنا بيانات إضافية
                if phone == "N/A" or website == "N/A" or reviews == "N/A":
                    link_to_click = await card_handle.query_selector('a.hfpxzc')
                    if link_to_click:
                        await link_to_click.click()
                        
                        # [الحل الأساسي لتضارب البيانات] الانتظار حتى يتغير اسم العيادة في اللوحة الجانبية
                        try:
                            escaped_name = re.escape(name)
                            # ننتظر ظهور اسم العيادة الجديدة في العنوان الرئيسي
                            await page.locator('h1.DUwDvf').filter(has_text=re.compile(escaped_name, re.IGNORECASE)).wait_for(state="visible", timeout=6000)
                            # نعطي واجهة المتصفح نصف ثانية لتفريغ البيانات القديمة (رقم الهاتف) وعرض الجديدة
                            await page.wait_for_timeout(500)
                        except Exception:
                            # في حال فشل التطابق الدقيق، نعتمد على انتظار ثابت قصير كبديل
                            await page.wait_for_timeout(2500)
                        
                        # كشط المراجعات من اللوحة الجانبية
                        if reviews == "N/A":
                            rev_el = await page.query_selector('div.F7nice span[role="img"]')
                            if rev_el:
                                lbl = await rev_el.get_attribute('aria-label')
                                if lbl:
                                    match = re.search(r'([\d,]+)\s*reviews?', lbl, re.IGNORECASE)
                                    if match:
                                        reviews = match.group(1).replace(',', '')

                        # كشط رقم الهاتف من اللوحة الجانبية
                        if phone == "N/A":
                            phone_btn = await page.query_selector('button[data-item-id^="phone:tel:"]')
                            if phone_btn:
                                phone_data = await phone_btn.get_attribute('data-item-id')
                                phone = phone_data.replace('phone:tel:', '')
                        
                        # كشط الموقع من اللوحة الجانبية
                        if website == "N/A":
                            web_btn = await page.query_selector('a[data-item-id="authority"]')
                            if web_btn:
                                website = await web_btn.get_attribute('href')

                        # العودة للقائمة
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
                
                print(f"[+] Extracted: {name} | Phone: {phone} | Rating: {rating} | Reviews: {reviews}")
                seen.add(key)

            except Exception as e:
                print(f"[-] Error extracting data for a clinic: {e}")
                # محاولة الرجوع إذا حدث خطأ لضمان استمرار الكشط للعيادة التالية
                try:
                    back_btn = page.locator('button[aria-label="Back"], button[aria-label="رجوع"]')
                    if await back_btn.count() > 0:
                        await back_btn.first.click()
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass
            
            # خطوة هامة جداً: حذف العنصر من الذاكرة لمنع الانهيار (Target Crashed)
            await card_handle.dispose()
            current_index += 1

        print(f"[*] Task completed successfully. Total results: {len(results)}")
        await browser.close()
        return results

if __name__ == "__main__":
    data = asyncio.run(scrape_google_maps("Dental Clinics in Dubai"))
