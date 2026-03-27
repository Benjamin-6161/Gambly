from playwright.sync_api import sync_playwright


def get_match_score(url):
    with sync_playwright() as p:
      browser = p.chromium.launch(headless=True)

      page = browser.new_page()

      # Open the match page
      page.goto(url, timeout=60000)

      # Wait for score to load
      page.wait_for_selector("div.detailScore__wrapper", timeout=15000)

      # Extract full score (e.g. "1 - 0")
      score_text = page.query_selector("div.detailScore__wrapper").inner_text().strip()

      # Extract home and away separately
      home = page.query_selector(
        "div.detailScore__wrapper span:nth-child(1)"
      ).inner_text()

      away = page.query_selector(
        "div.detailScore__wrapper span:nth-child(3)"
      ).inner_text()

      browser.close()

      return score_text#, home, away

