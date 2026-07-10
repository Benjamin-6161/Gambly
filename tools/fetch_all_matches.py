import re
from datetime import datetime, date
from playwright.sync_api import sync_playwright
from helpers.db import save_matches

# (category, league) -> (flashscore country slug, flashscore league slug)
#
# NOTE: The 2026 World Cup finals run at ("world", "world-championship"),
# which flashscore keeps at a stable slug across cycles. European World
# Cup *qualifying* is a separate competition at ("europe", "world-cup") -
# deliberately left out below since that campaign finished in March 2026
# and won't resume until the next cycle (~2028). Add it back in then:
#   ("EUROPE", "WORLD CUP QUALIFICATION"): ("europe", "world-cup"),
TARGET_LEAGUES = {
    ("ENGLAND", "PREMIER LEAGUE"): ("england", "premier-league"),
    ("ENGLAND", "FA CUP"): ("england", "fa-cup"),
    ("SPAIN", "LALIGA"): ("spain", "laliga"),
    ("SPAIN", "COPA DEL REY"): ("spain", "copa-del-rey"),
    ("ITALY", "SERIE A"): ("italy", "serie-a"),
    ("ITALY", "COPPA ITALIA"): ("italy", "coppa-italia"),
    ("GERMANY", "BUNDESLIGA"): ("germany", "bundesliga"),
    ("GERMANY", "DFB POKAL"): ("germany", "dfb-pokal"),
    ("FRANCE", "LIGUE 1"): ("france", "ligue-1"),
    ("FRANCE", "COUPE DE FRANCE"): ("france", "coupe-de-france"),
    ("EUROPE", "CHAMPIONS LEAGUE"): ("europe", "champions-league"),
    ("EUROPE", "EUROPA LEAGUE"): ("europe", "europa-league"),
    ("EUROPE", "UEFA NATIONS LEAGUE - LEAGUE C/D - RELEGATION"): ("europe", "uefa-nations-league"),
    ("WORLD", "WORLD CHAMPIONSHIP"): ("world", "world-championship"),
}

TODAY_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
DATED_TIME_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.\s*(\d{1,2}:\d{2})?")

# How far ahead (and slightly behind, to absorb timezone slop between the
# scraping browser and the real world) a match can be and still be picked
# up. Change these two numbers if you want a wider/narrower lookahead.
DAY_WINDOW_BACK = 1
DAY_WINDOW_FORWARD = 3

FINISHED_MARKERS = {"FT", "AET", "AP", "PEN.", "POSTP.", "CANCL.", "ABN.", "AWRD."}


def _match_date(time_text: str):
    """Resolve the actual calendar date a row's time text refers to, or
    None if unparseable. Bare 'HH:MM' means the page's implicit 'today'
    convention; 'DD.MM.[ HH:MM]' is parsed against the closest real
    calendar date (handles a Dec/Jan year boundary)."""
    time_text = time_text.strip()
    if TODAY_TIME_RE.match(time_text):
        return datetime.now().date()

    m = DATED_TIME_RE.match(time_text)
    if not m:
        return None

    day, month = int(m.group(1)), int(m.group(2))
    today = datetime.now().date()
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - today).days))


def _is_within_window(match_date) -> bool:
    if match_date is None:
        return False
    offset = (match_date - datetime.now().date()).days
    return -DAY_WINDOW_BACK <= offset <= DAY_WINDOW_FORWARD


def _clock_portion(time_text: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2})\s*$", time_text.strip())
    return m.group(1) if m else time_text.strip()


def _extract_matches_from_page(page, category, league):
    matches = []
    rows = page.query_selector_all("div[id^='g_1_']")

    for row in rows:
        try:
            row_id = row.get_attribute("id") or ""
            match_id = row_id.split("_")[-1]
            if not match_id:
                continue
            
            time_el = row.query_selector(".event__stageTime")
            if not time_el:
                continue
            if time_el.get_attribute("data-live") == "true":
                continue  # belt-and-suspenders alongside the score check above

            time_text = time_el.inner_text().strip()
            # Finished-match markers (FT, AET, Pen, etc.) can appear as a
            # second line alongside the date/time rather than as the only
            # content (confirmed: "03.07. 22:00\nAET"), so check each line
            # rather than the whole string.
            if any(line.strip().upper() in FINISHED_MARKERS for line in time_text.splitlines()):
                continue
            if time_text.upper() in FINISHED_MARKERS:
                continue

            match_date = _match_date(time_text)
            if not _is_within_window(match_date):
                continue

            home_el = (row.query_selector(".event__participant--home")
                       or row.query_selector(".event__homeParticipant"))
            away_el = (row.query_selector(".event__participant--away")
                       or row.query_selector(".event__awayParticipant"))
            home = home_el.inner_text().strip() if home_el else None
            away = away_el.inner_text().strip() if away_el else None
            
            score_home_el = row.query_selector(".event__score--home")
            score_away_el = row.query_selector(".event__score--away")
            # A not-yet-started match shows literal "-" for both scores;
            # any real digits mean it's live or finished (confirmed: "-"
            # for upcoming, "3"/"2" for played, "1\n(2)" for penalties).
            if score_home_el and score_home_el.inner_text().strip() not in ("", "-"):
                continue
            if score_away_el and score_away_el.inner_text().strip() not in ("", "-"):
                continue
            
            if not home or not away:
                continue

            matches.append({
                "fixture": f"{home} vs {away}",
                "category": category,
                "league": league,
                "date": f"{match_date.strftime('%Y-%m-%d')} {_clock_portion(time_text)}",
                "match_url": f"https://www.flashscore.com/match/football/{match_id}/#/match-summary",
                "match_id": match_id,
            })
        except Exception as e:
            print(f"[flashscore] Failed to parse a match row: {e}")
            continue

    return matches


def fetch_matches(*args, **kwargs):
    """
    Scrape fixtures from flashscore.com, today through DAY_WINDOW_FORWARD
    days ahead, for the configured top-5-European-leagues + major-
    competitions set. Replaces the Apify actor previously used here.
    """
    all_matches = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for (category, league), (country_slug, league_slug) in TARGET_LEAGUES.items():
            url = f"https://www.flashscore.com/football/{country_slug}/{league_slug}/"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector("div[id^='g_1_']", state="attached", timeout=15000)

                for _ in range(3):
                    more_button = page.query_selector("a.event__more, .wclButton--more")
                    if not more_button:
                        break
                    more_button.click()
                    page.wait_for_timeout(1000)

                found = _extract_matches_from_page(page, category, league)
                all_matches.extend(found)
                print(f"[flashscore] {category}/{league}: {len(found)} match(es) in window")

            except Exception as e:
                print(f"[flashscore] Skipped {category}/{league} ({url}): {e}")
                continue

        browser.close()

    if not all_matches:
        return "No Available Matches"

    save_matches(all_matches)
    return all_matches


if __name__ == "__main__":
    fetch_matches()