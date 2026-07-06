# -*- coding: utf-8 -*-
import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def scrape_google_maps(search_query, total_results=80):
    async with async_playwright() as p:
        # 1. إعداد المتصفح بلغة إنجليزية ثابتة لتجنب تضارب الكلاسات
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = await context.new_page()
        
        print(f"[*] البحث عن: {search_query}")
        # إجبار جوجل على عرض النتائج بالإنجليزية
        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()

        while len(results) < total_results:
            # استخراج كروت النتائج
            cards = await page.query_selector_all('div[role="article"]')
            
            for card in cards:
                if len(results) >= total_results: break
                
                try:
                    # استخراج الاسم بدقة
                    name_el = await card.query_selector('div.qBF1Pd')
                    name = await name_el.inner_text() if name_el else "N/A"
                    if name in seen or name == "N/A": continue
                    
                    # استخراج التقييم والمراجعات من الكلاسات المباشرة (الأكثر ثباتاً)
                    rating_el = await card.query_selector('span.MW4etd')
                    reviews_el = await card.query_selector('span.UY7F9')
                    rating = await rating_el.inner_text() if rating_el else "N/A"
                    reviews = (await reviews_el.inner_text()).replace('(', '').replace(')', '').replace(',', '') if reviews_el else "N/A"

                    # الدخول للوحة التفاصيل لاستخراج الهاتف والموقع
                    await card.click()
                    await page.wait_for_timeout(2500)
                    
                    phone = "N/A"
                    website = "N/A"
                    
                    # البحث عن زر الهاتف والموقع باستخدام الـ Tooltips البرمجية
                    phone_btn = await page.query_selector('button[data-tooltip="Copy phone number"]')
                    if phone_btn:
                        phone = await phone_btn.get_attribute('aria-label')
                        phone = phone.replace("Phone: ", "")

                    web_btn = await page.query_selector('a[data-tooltip="Open website"]')
                    if web_btn:
                        website = await web_btn.get_attribute('href')

                    # تسجيل النتيجة
                    results.append({"Name": name, "Rating": rating, "Reviews": reviews, "Phone": phone, "Website": website})
                    print(f"[+] تم استخراج: {name} | الهاتف: {phone}")
                    seen.add(name)
                    
                    # الخروج من اللوحة للعودة للقائمة الرئيسية
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    
                except Exception:
                    await page.keyboard.press("Escape")
                    continue
            
            # التمرير لأسفل للحصول على نتائج إضافية
            await page.keyboard.press("PageDown")
            await page.wait_for_timeout(2000)

        print("[*] تمت المهمة بنجاح.")
        await browser.close()
        return results

# تشغيل السكربت
if __name__ == "__main__":
    data = asyncio.run(scrape_google_maps("Dental Clinics in Dubai"))
    # هنا يمكنك إضافة كود حفظ البيانات في ملف CSV أو Excel
