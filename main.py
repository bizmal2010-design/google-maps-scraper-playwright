# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')


async def extract_name(card):
    # الطريقة الأولى: من العنصر المخصص للاسم
    name_el = await card.query_selector('div.qBF1Pd')
    if name_el:
        text = (await name_el.inner_text()).strip()
        if text:
            return text
    # الطريقة الثانية، احتياطية: من aria-label الخاص برابط الكارد الرئيسي
    link_el = await card.query_selector('a.hfpxzc')
    if link_el:
        label = await link_el.get_attribute('aria-label')
        if label:
            return label.strip()
    return "N/A"


async def extract_rating_and_reviews(card):
    # الطريقة الأولى: aria-label واحدة تحتوي التقييم وعدد المراجعات معاً
    wrapper = await card.query_selector('span.ZkP5Je')
    if wrapper:
        label = await wrapper.get_attribute('aria-label')
        if label:
            match = re.search(r'([\d.]+)\s*stars?\s*([\d,]+)\s*Reviews?', label, re.IGNORECASE)
            if match:
                return match.group(1), match.group(2).replace(',', '')

    # الطريقة الثانية، احتياطية: من الكلاسات المنفصلة
    rating_el = await card.query_selector('span.MW4etd')
    reviews_el = await card.query_selector('span.UY7F9')
    rating = (await rating_el.inner_text()).strip() if rating_el else "N/A"
    reviews = "N/A"
    if reviews_el:
        raw = await reviews_el.inner_text()
        reviews = raw.replace('(', '').replace(')', '').replace(',', '').strip()
    return rating, reviews


async def extract_phone(card):
    # موجود مباشرة داخل الكارد، لا حاجة إطلاقاً لفتح لوحة التفاصيل
    phone_el = await card.query_selector('span.UsdlK')
    if phone_el:
        return (await phone_el.inner_text()).strip()
    return "N/A"


async def extract_website(card):
    # يظهر فقط إذا كانت العيادة تملك موقعاً إلكترونياً
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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1600, "height": 900}
        )
        page = await context.new_page()

        print(f"[*] البحث عن: {search_query}")
        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()
        stagnant_rounds = 0

        while len(results) < total_results:
            cards = await page.query_selector_all('div[role="article"]')
            new_in_this_round = 0

            for card in cards:
                if len(results) >= total_results:
                    break
                try:
                    place_url = await extract_place_url(card)
                    name = await extract_name(card)
                    key = place_url if place_url != "N/A" else name

                    if key in seen or name == "N/A":
                        continue

                    rating, reviews = await extract_rating_and_reviews(card)
                    phone = await extract_phone(card)
                    website = await extract_website(card)

                    results.append({
                        "Name": name,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Phone": phone,
                        "Website": website,
                        "MapURL": place_url
                    })
                    print(f"[+] تم استخراج: {name} | الهاتف: {phone} | التقييم: {rating} ({reviews})")
                    seen.add(key)
                    new_in_this_round += 1

                except Exception:
                    continue

            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2000)

            if new_in_this_round == 0:
                stagnant_rounds += 1
                if stagnant_rounds >= 3:
                    print("[!] لا توجد نتائج جديدة بعد عدة محاولات تمرير، تم إيقاف البحث.")
                    break
            else:
                stagnant_rounds = 0

        print(f"[*] تمت المهمة بنجاح. إجمالي النتائج: {len(results)}")
        await browser.close()
        return results


if __name__ == "__main__":
    data = asyncio.run(scrape_google_maps("Dental Clinics in Dubai"))
    # هنا يمكنك إضافة كود حفظ البيانات في ملف Excel باستخدام openpyxl
