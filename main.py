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
    
    # Method 1: Try finding the aria-label inside the outer card
    wrapper = await card.query_selector('span[role="img"]')
    if wrapper:
        label = await wrapper.get_attribute('aria-label')
        if label:
            # Better Regex to match "4.9 stars 1,107 Reviews"
            match = re.search(r'([\d.]+)\s*stars?\s*([\d,]+)\s*Reviews?', label, re.IGNORECASE)
            if match:
                rating = match.group(1)
                reviews = match.group(2).replace(',', '')
                return rating, reviews

    # Method 2: Fallback to specific spans in the outer card
    rating_el = await card.query_selector('span.MW4etd')
    reviews_el = await card.query_selector('span.UY7F9')
    
    if rating_el:
        text = await rating_el.inner_text()
        rating = text.strip()
        
    if reviews_el:
        raw = await reviews_el.inner_text()
        # Remove all non-numeric characters (brackets, commas, etc.)
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

        print(f"[*] Starting search for: {search_query}")
        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}?hl=en")
        await page.wait_for_timeout(5000)

        results = []
        seen = set()
        stagnant_rounds = 0

        while len(results) < total_results:
            cards = await page.query_selector_all('div[role="article"]')
            new_in_this_round = 0

            for i in range(len(cards)):
                if len(results) >= total_results:
                    break
                
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
                    phone = await extract_phone_from_card(card)
                    website = await extract_website_from_card(card)

                    # Condition to click: missing phone, website, OR reviews
                    if phone == "N/A" or website == "N/A" or reviews == "N/A":
                        link_to_click = await card.query_selector('a.hfpxzc')
                        if link_to_click:
                            await link_to_click.click()
                            
                            # VITAL FIX: Wait for the sidebar Title to match the current clinic name.
                            # This prevents scraping the old clinic's data while the new one is loading!
                            try:
                                # Escape quotes in name to prevent selector errors
                                safe_name = name.replace('"', '\\"')
                                await page.wait_for_selector(f'h1.DUwDvf:has-text("{safe_name}")', timeout=5000)
                            except Exception:
                                # Fallback wait if exact name match fails
                                await page.wait_for_timeout(3000)
                            
                            # Extract Reviews from inner sidebar if still missing
                            if reviews == "N/A":
                                rev_el = await page.query_selector('div.F7nice span[role="img"]')
                                if rev_el:
                                    lbl = await rev_el.get_attribute('aria-label')
                                    if lbl:
                                        match = re.search(r'([\d,]+)\s*reviews?', lbl, re.IGNORECASE)
                                        if match:
                                            reviews = match.group(1).replace(',', '')

                            # Extract Phone from sidebar
                            if phone == "N/A":
                                phone_btn = await page.query_selector('button[data-item-id^="phone:tel:"]')
                                if phone_btn:
                                    phone_data = await phone_btn.get_attribute('data-item-id')
                                    phone = phone_data.replace('phone:tel:', '')
                            
                            # Extract Website from sidebar
                            if website == "N/A":
                                web_btn = await page.query_selector('a[data-item-id="authority"]')
                                if web_btn:
                                    website = await web_btn.get_attribute('href')

                            # Go back to the list
                            back_btn = await page.query_selector('button[aria-label="Back"], button[aria-label="رجوع"]')
                            if back_btn:
                                await back_btn.click()
                                await page.wait_for_timeout(1500)

                    results.append({
                        "Name": name,
                        "Rating": rating,
                        "Reviews": reviews,
                        "Phone": phone,
                        "Website": website,
                        "MapURL": place_url
                    })
                    
                    print(f"[+] Extracted: {name} | Phone: {phone} | Rating: {rating} | Reviews: {reviews} | Website: {website} | MapURL: {place_url}")
                    seen.add(key)
                    new_in_this_round += 1

                except Exception as e:
                    print(f"[-] Error extracting data for a clinic: {e}")
                    back_btn = await page.query_selector('button[aria-label="Back"], button[aria-label="رجوع"]')
                    if back_btn:
                        await back_btn.click()
                        await page.wait_for_timeout(1000)
                    continue

            # Scroll to load more
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(3000)

            if new_in_this_round == 0:
                stagnant_rounds += 1
                if stagnant_rounds >= 3:
                    print("[!] No new results found after several scroll attempts. Stopping search.")
                    break
            else:
                stagnant_rounds = 0

        print(f"[*] Task completed successfully. Total results: {len(results)}")
        await browser.close()
        return results

if __name__ == "__main__":
    data = asyncio.run(scrape_google_maps("Dental Clinics in Dubai"))
