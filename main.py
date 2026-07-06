# -*- coding: utf-8 -*-

import asyncio
import sys
import re
import os
import pandas as pd
from playwright.async_api import async_playwright
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding='utf-8')
MAX_SCROLL_ATTEMPTS = 6
OUTPUT_DIR = "." 


def parse_rating_and_reviews(text):
    rating = "N/A"
    reviews = "N/A"
    if not text:
        return rating, reviews
    
    text = text.strip().replace(",", "")
    match = re.search(r"([\d.]+)\s*\(([\d]+)\)", text)
    if not match:
        match = re.search(r"([\d.]+)\s*stars?\s*([\d]+)", text, re.IGNORECASE)
        
    if match:
        rating = match.group(1)
        reviews = match.group(2)
    return rating, reviews


def clean_phone(raw):
    digits = re.sub(r'[^\d+]', '', raw)
    if digits.startswith('971'):
        return '+' + digits
    elif digits.startswith('0'):
        return '+971' + digits[1:]
    elif digits.startswith('+'):
        return digits
    else:
        return '+971' + digits
    
def short_url(url):
    if not url or url == "N/A":
        return "N/A"
    try:
        return urlparse(url).netloc.replace("www.", "")
    except:
        return url

def save_excel(results, filepath):
    wb = Workbook()
    ws = wb.active
    ws.title = "Dubai Medical Leads"

    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill('solid', start_color='1F4E79')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

    headers = ['#', 'Business Name', 'Phone', 'Rating', 'Reviews', 'Maps URL', 'Website']
    col_widths = [5, 40, 20, 10, 10, 25, 30]

    for col, (header, width) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.row_dimensions[1].height = 30

    link_font = Font(name='Arial', color='0563C1', underline='single', size=10)
    normal_font = Font(name='Arial', size=10)
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center', wrap_text=True)

    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    for row_idx, item in enumerate(results, 2):
        row_fill = PatternFill('solid', start_color='EBF3FB') if row_idx % 2 == 0 else PatternFill('solid', start_color='FFFFFF')

        c = ws.cell(row=row_idx, column=1, value=row_idx - 1)
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        c = ws.cell(row=row_idx, column=2, value=item['Business Name'])
        c.font = normal_font
        c.alignment = left_align
        c.fill = row_fill
        c.border = thin_border

        c = ws.cell(row=row_idx, column=3, value=item['Phone'])
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        c = ws.cell(row=row_idx, column=4, value=item['Rating'])
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        c = ws.cell(row=row_idx, column=5, value=item['Reviews'])
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        maps_url = item['Maps URL']
        if maps_url and maps_url != 'N/A':
            c = ws.cell(row=row_idx, column=6, value='Open Map')
            c.hyperlink = maps_url
            c.font = link_font
        else:
            c = ws.cell(row=row_idx, column=6, value='N/A')
            c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        website = item['Website']
        if website and website != 'N/A':
            c = ws.cell(row=row_idx, column=7, value=short_url(website))
            c.hyperlink = website
            c.font = link_font
        else:
            c = ws.cell(row=row_idx, column=7, value='N/A')
            c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        ws.row_dimensions[row_idx].height = 40

    ws.freeze_panes = 'A2'
    wb.save(filepath)

async def scrape_google_maps(search_query, total_results_needed=80):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print(f"[*] Searching for: {search_query}")
        query = search_query.replace(" ", "+")
        
        await page.goto(f"https://www.google.com/maps/search/{query}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()
        scroll_attempts = 0
        last_cards_count = 0

        print("[*] Progress: Extracting unique cards and matching details...")

        while len(results) < total_results_needed:
            if scroll_attempts >= MAX_SCROLL_ATTEMPTS:
                print("[!] Max scroll reached")
                break

            cards = await page.query_selector_all('div[role="article"]')
            new_cards_count = len(cards) - last_cards_count
            print(f"Cards found: {len(cards)} (+{new_cards_count} new)")

            if new_cards_count == 0 and len(cards) > 0:
                scroll_attempts += 1
            else:
                scroll_attempts = 0

            for card in cards[last_cards_count:]:
                if len(results) >= total_results_needed:
                    break
                try:
                    link_el = await card.query_selector("a.hfpxzc")
                    name = "N/A"
                    if link_el:
                        name = await link_el.get_attribute("aria-label")
                    
                    if not name or name == "N/A" or name in seen:
                        continue

                    if await card.query_selector('h1.kpih0e'):
                        continue

                    # جلب التقييمات فوراً من واجهة الكرت
                    rating = "N/A"
                    reviews = "N/A"
                    review_container = await card.query_selector('span.AJ76f')
                    if review_container:
                        raw_text = await review_container.get_attribute('aria-label')
                        rating, reviews = parse_rating_and_reviews(raw_text)

                    url = await link_el.get_attribute("href") if link_el else "N/A"

                    phone = "N/A"
                    website = "N/A"
                    
                    if link_el:
                        await link_el.click()
                        
                        # --- الأمان الذكي: ننتظر حتى يتغير عنوان اللوحة الجانبية ليطابق اسم العيادة الفعلي ---
                        matched = False
                        for _ in range(10): # محاولة الانتظار لمدة تصل لـ 2 ثانية كحد أقصى
                            panel_title_el = await page.query_selector('h1.DUwDvf')
                            if panel_title_el:
                                panel_title = await panel_title_el.inner_text()
                                if name.strip() in panel_title.strip() or panel_title.strip() in name.strip():
                                    matched = True
                                    break
                            await page.wait_for_timeout(200)

                        if matched:
                            # 1. جلب رقم الهاتف المحدث بدقة
                            phone_button = await page.query_selector('button[data-item-id^="phone:tel:"]')
                            if phone_button:
                                phone_raw = await phone_button.get_attribute('data-item-id')
                                phone = clean_phone(phone_raw.replace("phone:tel:", "").strip())
                            
                            # 2. جلب الموقع الإلكتروني بدقة
                            web_button = await page.query_selector('a[data-item-id="authority"]')
                            if web_button:
                                website = await web_button.get_attribute('href')
                            else:
                                backup_web = await page.query_selector('a[aria-label*="Website:"]')
                                if backup_web:
                                    website = await backup_web.get_attribute('href')

                    seen.add(name)
                    results.append({
                        "Business Name": name,
                        "Maps URL": url,
                        "Phone": phone,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Website": website if website else "N/A"
                    })
                    print(f"[+] {len(results)}. {name} | Phone: {phone} | Rating: {rating} | Reviews: {reviews} | Website: {short_url(website) if website else 'N/A'}")
                except Exception as e:
                    pass
            
            last_cards_count = len(cards)
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("(el) => el.scrollBy(0, 3500)")
            await page.wait_for_timeout(2500)

        await browser.close()

        csv_path = os.path.join(OUTPUT_DIR, "cleaned_medical_leads.csv")
        excel_path = os.path.join(OUTPUT_DIR, "cleaned_medical_leads.xlsx")

        if results:
            df = pd.DataFrame(results)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            save_excel(results, excel_path)
            print(f"\n[+] Extraction successfully completed!")
        else:
            print("[!] No data collected.")

asyncio.run(scrape_google_maps("Dental Clinics in Dubai", total_results_needed=80))
