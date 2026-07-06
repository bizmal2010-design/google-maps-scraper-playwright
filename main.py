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
MAX_SCROLL_ATTEMPTS = 5
OUTPUT_DIR = "." 


def parse_rating_and_reviews(text):
    rating = "N/A"
    reviews = "N/A"
    if not text:
        return rating, reviews
    
    text = text.strip().replace(",", "")
    # Standard English maps format: "4.5 stars 120 reviews" or "4.5(120)"
    match = re.search(r"([\d.]+)\s*\(([\d]+)\)", text)
    if not match:
        match = re.search(r"([\d.]+)\s*stars?\s*([\d]+)", text, re.IGNORECASE)
        
    if match:
        rating = match.group(1)
        reviews = match.group(2)
    return rating, reviews


def clean_phone(raw):
    # Cleans and formats UAE numbers to international format (+971)
    digits = re.sub(r'[^\d]', '', raw)
    if digits.startswith('971'):
        return '+' + digits
    elif digits.startswith('0'):
        return '+971' + digits[1:]
    else:
        return '+971' + digits
    
def short_url(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except:
        return url

def save_excel(results, filepath):
    wb = Workbook()
    ws = wb.active
    ws.title = "Dubai Medical Leads"

    # Header style - English Professional
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

        # Numbering
        c = ws.cell(row=row_idx, column=1, value=row_idx - 1)
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        # Business Name
        c = ws.cell(row=row_idx, column=2, value=item['Business Name'])
        c.font = normal_font
        c.alignment = left_align
        c.fill = row_fill
        c.border = thin_border

        # Phone
        c = ws.cell(row=row_idx, column=3, value=item['Phone'])
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        # Rating
        c = ws.cell(row=row_idx, column=4, value=item['Rating'])
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        # Reviews
        c = ws.cell(row=row_idx, column=5, value=item['Reviews'])
        c.font = normal_font
        c.alignment = center_align
        c.fill = row_fill
        c.border = thin_border

        # Maps URL
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

        # Website
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

async def scrape_google_maps(search_query, total_results_needed=150):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print(f"[*] Searching for: {search_query}")
        query = search_query.replace(" ", "+")
        
        # --- Forced English UI (?hl=en) to match cloud proxies natively ---
        await page.goto(f"https://www.google.com/maps/search/{query}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()
        scroll_attempts = 0
        duplicate_count = 0
        empty_name_count = 0
        last_cards_count = 0

        print("[*] Progress: Collecting listings and reviews natively...")

        while len(results) < total_results_needed:
            if scroll_attempts >= MAX_SCROLL_ATTEMPTS:
                print("[!] Max scroll reached")
                break

            cards = await page.query_selector_all('div[role="article"]')
            new_cards = cards[last_cards_count:]
            print(f"Cards found: {len(cards)} (+{len(new_cards)} new)")

            for card in cards[last_cards_count:]:
                if len(results) >= total_results_needed:
                    break
                try:
                    # Business Name
                    link_el = await card.query_selector("a.hfpxzc")
                    name = "N/A"
                    if link_el:
                        name = await link_el.get_attribute("aria-label")
                    
                    if not name or name == "N/A":
                        empty_name_count += 1
                        continue
                        
                    if name in seen:
                        duplicate_count += 1
                        continue

                    if await card.query_selector('h1.kpih0e'):
                        continue

                    # Rating & Reviews directly from English interface
                    rating = "N/A"
                    reviews = "N/A"
                    
                    review_container = await card.query_selector('span.AJ76f')
                    if review_container:
                        raw_text = await review_container.get_attribute('aria-label')
                        rating, reviews = parse_rating_and_reviews(raw_text)
                    else:
                        stars_el = await card.query_selector('span.MW4etd')
                        if stars_el:
                            rating = (await stars_el.text_content()).strip()
                        reviews_el = await card.query_selector('span.UY7F9')
                        if reviews_el:
                            reviews = (await reviews_el.text_content()).strip("()").strip()

                    # URL
                    url = await link_el.get_attribute("href") if link_el else "N/A"

                    # Phone
                    phone = "N/A"
                    phone_el = await card.query_selector('span.UsdlK span[dir="ltr"]')
                    if phone_el:
                        phone = clean_phone(await phone_el.inner_text())

                    # Website
                    website = "N/A"
                    website_el = await card.query_selector('a.lcr4fd')
                    if website_el:
                        website = await website_el.get_attribute('href')

                    seen.add(name)
                    results.append({
                        "Business Name": name,
                        "Maps URL": url,
                        "Phone": phone,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Website": website
                    })
                    print(f"[+] {len(results)}. {name} | {phone} | Rating: {rating} | Reviews: {reviews}")
                except Exception as e:
                    print("[!] Error inside card parser:", e)
            
            last_cards_count = len(cards)
            current_cards = len(await page.query_selector_all('div[role="article"]'))
            feed = await page.query_selector('div[role="feed"]')
            if feed:
                await feed.evaluate("(el) => el.scrollBy(0, 4000)")
            await page.wait_for_timeout(2500)

            try:
                await page.wait_for_function(
                    "(count) => document.querySelectorAll('div[role=\"article\"]').length > count",
                    arg=current_cards,
                    timeout=4000
                )
            except:
                pass

            new_cards_check = len(await page.query_selector_all('div[role=\"article\"]'))
            if new_cards_check == current_cards:
                scroll_attempts += 1
            else:
                scroll_attempts = 0

        await browser.close()

        # Save outputs
        csv_path = os.path.join(OUTPUT_DIR, "cleaned_medical_leads.csv")
        excel_path = os.path.join(OUTPUT_DIR, "cleaned_medical_leads.xlsx")

        print("\n[*] Data Quality Report:")
        print(f"    Cards loaded       : {current_cards}")
        print(f"    Total records      : {len(results)}")
        print(f"    With Phone         : {sum(1 for r in results if r['Phone'] != 'N/A')}")
        print(f"    With Website       : {sum(1 for r in results if r['Website'] != 'N/A')}")

        if results:
            df = pd.DataFrame(results)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            save_excel(results, excel_path)
            print(f"\n[+] Done successfully!")
            print(f"[+] CSV saved to: {csv_path}")
            print(f"[+] Excel saved to: {excel_path}")
        else:
            print("[!] No data collected.")

# Targeted Query for High Demand Market (Dental Clinics in Dubai)
asyncio.run(scrape_google_maps("Dental Clinics in Dubai", total_results_needed=150))
