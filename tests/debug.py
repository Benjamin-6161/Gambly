# tests/debug_mobi_stats_page.py — temporary
from playwright.sync_api import sync_playwright

MATCH_ID = "bodsDyte"  # Argentina vs Egypt, same finished match as before
URL = f"https://www.flashscore.mobi/match/{MATCH_ID}/?t=stats"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1000)

    print("Full page inner_text:\n")
    print(page.inner_text("body"))

    browser.close()