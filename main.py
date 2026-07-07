# -*- coding: utf-8 -*-
import asyncio
import re
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def extract_name(card):
    name_el = await card.query_selector('div.qBF1Pd')
    if name_el:
        text = (await name_el.inner_text()).strip()
        if text:
            return text
    link_el = await card.query_selector('a.hfpxzc')
    if link_el:
        label = await link_el.get_attribute('aria-label')
        if label:
            return label.strip()
    return "N/A"

async def extract_rating_and_reviews(card):
    # استخدام الكلاسات المباشرة لتجنب مشكلة اختلاف اللغات (عربي/إنجليزي)
    rating_el = await card.query_selector('span.MW4etd')
    reviews_el = await card.query_selector('span.UY7F9')
    
    rating = "N/A"
    reviews = "N/A"
    
    if rating_el:
        rating = (await rating_el.inner_text()).strip()
    
    if reviews_el:
        raw = await reviews_el.inner_text()
        # إزالة الأقواس والمسافات سواء كانت بالعربي أو الإنجليزي
        reviews = raw.replace('(', '').replace(')', '').replace(',', '').replace('٬', '').strip()
        
    return rating, reviews

async def extract_phone_from_card(card):
    phone_el = await card.query_selector('span.UsdlK')
    if phone_el:
        return (await phone_el.inner_text()).strip()
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
        # إضافة إعدادات لإجبار المتصفح على اللغة الإنجليزية لتجنب التضارب
        browser = await p.chromium.launch(
            headless=True,
            args=['--lang=en-US', '--disable-blink-features=AutomationControlled']
        )
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
            # جلب كل الكروت في القائمة
            cards = await page.query_selector_all('div[role="article"]')
            new_in_this_round = 0

            for i in range(len(cards)):
                if len(results) >= total_results:
                    break
                
                # تحديث الكارت في كل دورة لتجنب فقدان العنصر من الذاكرة (Stale Element)
                current_cards = await page.query_selector_all('div[role="article"]')
                if i >= len(current_cards):
                    break
                card = current_cards[i]

                try:
                    place_url = await extract_place_url(card)
                    name = await extract_name(card)
                    key = place_url if place_url != "N/A" else name

                    if key in seen or name == "N/A":
                        continue

                    rating, reviews = await extract_rating_and_reviews(card)
                    
                    # محاولة استخراج الهاتف والموقع من الكارت الخارجي أولاً
                    phone = await extract_phone_from_card(card)
                    website = await extract_website_from_card(card)

                    # الشرط الذكي: إذا كان الهاتف أو الموقع غير موجودين (حالة الصورة المصغرة)
                    if phone == "N/A" or website == "N/A":
                        # الضغط على الكارت لفتح التفاصيل
                        await card.click()
                        await page.wait_for_timeout(2500) # انتظار تحميل البيانات الجانبية
                        
                        # استخراج الهاتف من اللوحة الجانبية
                        if phone == "N/A":
                            # نبحث عن الزر الذي يحتوي على خاصية data-item-id تبدأ بـ phone:tel:
                            phone_btn = await page.query_selector('button[data-item-id^="phone:tel:"]')
                            if phone_btn:
                                phone_data = await phone_btn.get_attribute('data-item-id')
                                phone = phone_data.replace('phone:tel:', '')
                        
                        # استخراج الموقع من اللوحة الجانبية
                        if website == "N/A":
                            # نبحث عن الرابط الخاص بالموقع
                            web_btn = await page.query_selector('a[data-item-id="authority"]')
                            if web_btn:
                                website = await web_btn.get_attribute('href')

                        # الضغط على زر الرجوع للعودة إلى القائمة (ندعم زر الرجوع باللغتين)
                        back_btn = await page.query_selector('button[aria-label="Back"], button[aria-label="رجوع"]')
                        if back_btn:
                            await back_btn.click()
                            await page.wait_for_timeout(1500) # انتظار العودة للقائمة

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

                except Exception as e:
                    print(f"[-] خطأ أثناء استخراج بيانات عيادة: {e}")
                    # في حال حدث خطأ أثناء فتح عيادة، نضمن العودة للقائمة
                    back_btn = await page.query_selector('button[aria-label="Back"], button[aria-label="رجوع"]')
                    if back_btn:
                        await back_btn.click()
                        await page.wait_for_timeout(1000)
                    continue

            # التمرير لأسفل لجلب المزيد من النتائج
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2500)

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
    # البيانات متوفرة الآن في المتغير data
