# -*- coding: utf-8 -*-
import asyncio
import sys
from playwright.async_api import async_playwright

# لضمان ظهور النصوص العربية بشكل صحيح في سجلات النظام
sys.stdout.reconfigure(encoding='utf-8')

async def scrape_google_maps(search_query, total_results=80):
    async with async_playwright() as p:
        # 1. إعداد المتصفح: استخدام locale و hl=en يضمن استقرار الكلاسات البرمجية
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = await context.new_page()
        
        print(f"[*] بدء البحث عن: {search_query}")
        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
        await page.wait_for_timeout(6000)

        results = []
        seen = set()

        while len(results) < total_results:
            cards = await page.query_selector_all('div[role="article"]')
            
            for card in cards:
                if len(results) >= total_results: break
                
                try:
                    # 2. استخراج الاسم
                    name_el = await card.query_selector('div.qBF1Pd')
                    name = await name_el.inner_text() if name_el else "N/A"
                    if name in seen or name == "N/A": continue
                    
                    # 3. استخدام Evaluate لجلب التقييم والمراجعات مباشرة من الـ DOM
                    data = await card.evaluate("""(element) => {
                        const r = element.querySelector('span.MW4etd');
                        const rev = element.querySelector('span.UY7F9');
                        return {
                            rating: r ? r.innerText : 'N/A',
                            reviews: rev ? rev.innerText.replace(/[()]/g, '').replace(',', '') : 'N/A'
                        };
                    }""")
                    
                    # 4. الدخول للوحة التفاصيل لجلب الهاتف والموقع
                    await card.click()
                    await page.wait_for_timeout(3000)
                    
                    phone = "N/A"
                    website = "N/A"
                    
                    # البحث عن الهاتف (مع محاولة ثانية ذكية)
                    phone_btn = await page.query_selector('button[data-tooltip="Copy phone number"]')
                    if phone_btn:
                        phone = (await phone_btn.get_attribute('aria-label')).replace("Phone: ", "").strip()

                    # البحث عن الموقع الإلكتروني
                    web_btn = await page.query_selector('a[data-tooltip="Open website"]')
                    if web_btn:
                        website = await web_btn.get_attribute('href')

                    results.append({"Name": name, "Rating": data['rating'], "Reviews": data['reviews'], "Phone": phone, "Website": website})
                    print(f"[+] تم استخراج: {name} | المراجعات: {data['reviews']} | الهاتف: {phone}")
                    seen.add(name)
                    
                    # العودة للقائمة
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    
                except Exception:
                    await page.keyboard.press("Escape")
                    continue
            
            # التمرير للأسفل
            await page.keyboard.press("PageDown")
            await page.wait_for_timeout(2500)

        await browser.close()
        print("[*] تمت العملية بنجاح.")
        return results

if __name__ == "__main__":
    # تشغيل الدالة
    asyncio.run(scrape_google_maps("Dental Clinics in Dubai"))
