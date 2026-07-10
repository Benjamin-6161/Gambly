import re
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.flashscore.mobi/match"

# Labels as they actually appear on the ?t=stats page - confirmed against
# a real finished match. Each stat is rendered as three consecutive lines:
# home value, label, away value (e.g. "19\nTotal shots\n5"). Each stat
# block appears twice on the page (once under "Top stats", once in the
# detailed breakdown further down) with identical values both times, so
# matching the first occurrence is safe.
STAT_LABELS = {
    "home_corners": "Corner kicks",
    "away_corners": "Corner kicks",
    "home_cards": "Yellow cards",
    "away_cards": "Yellow cards",
    "home_shots": "Total shots",
    "away_shots": "Total shots",
    "home_sot": "Shots on target",
    "away_sot": "Shots on target",
}


def get_match_details(match_id: str) -> dict:
    """
    Scrape full-time/half-time score plus corners, cards, shots and shots
    on target for both teams from flashscore.mobi.

    VERIFIED against a real finished match (Argentina 3-2 Egypt):
    - Summary page score line reads "3-2 (0-1,3-1)" - i.e. FT score,
      then (HT score, 2nd-half score) in parentheses. The old version of
      this file grabbed the first "\\d+-\\d+" anywhere on the page, which
      risked matching all sorts of unrelated numbers (goal-scorer minute
      lists, odds, etc.) rather than the actual score - this regex is
      now anchored to the real format instead.
    - Stats live on a separate page at {match_url}?t=stats (a real query
      param, not a JS tab switch), with each stat as three plain-text
      lines: home value, label, away value.
    """
    url = f"{BASE_URL}/{match_id}/"
    details = {
        "ht_score": None, "ft_score": None,
        "home_corners": None, "away_corners": None,
        "home_cards": None, "away_cards": None,
        "home_shots": None, "away_shots": None,
        "home_sot": None, "away_sot": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            summary_text = page.inner_text("body")

            page.goto(f"{url}?t=stats", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            stats_text = page.inner_text("body")
        finally:
            browser.close()

    # --- Score ---
    score_match = re.search(r"(\d+)-(\d+)\s*\((\d+)-(\d+)", summary_text)
    if score_match:
        details["ft_score"] = f"{score_match.group(1)}-{score_match.group(2)}"
        details["ht_score"] = f"{score_match.group(3)}-{score_match.group(4)}"

    # --- Stats ---
    lines = [l.strip() for l in stats_text.splitlines() if l.strip()]

    def _find_stat(label):
        for i, line in enumerate(lines):
            if line.lower() == label.lower() and 0 < i < len(lines) - 1:
                home_num = re.search(r"\d+", lines[i - 1])
                away_num = re.search(r"\d+", lines[i + 1])
                if home_num and away_num:
                    return int(home_num.group()), int(away_num.group())
        return None, None

    details["home_corners"], details["away_corners"] = _find_stat("Corner kicks")
    details["home_cards"], details["away_cards"] = _find_stat("Yellow cards")
    details["home_shots"], details["away_shots"] = _find_stat("Total shots")
    details["home_sot"], details["away_sot"] = _find_stat("Shots on target")

    return details


# Kept for backwards compatibility with anything still calling the old
# single-value scoreline function.
def get_match_score(match_id_or_url: str) -> str:
    match_id = match_id_or_url.rstrip("/").split("/")[-1]
    details = get_match_details(match_id)
    return details.get("ft_score") or "-"