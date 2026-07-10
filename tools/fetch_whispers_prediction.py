import re
import requests
from bs4 import BeautifulSoup

SITE = "https://footballwhispers.com/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GamblyBot/1.0)"}


def _tokens(team_name: str):
    cleaned = re.sub(r"[^a-z0-9]+", " ", team_name.lower()).strip()
    # drop very short/common tokens that would match almost anything
    return [t for t in cleaned.split() if len(t) > 2]


def find_whispers_article(home_team: str, away_team: str):
    """
    Search footballwhispers.com for a prediction article covering this
    fixture and return its extracted prediction summary.

    footballwhispers.com is a standard WordPress blog with on-site search at
    '/?s=<query>'. There's no official API, so this matches article titles
    against both team names. Returns None (not an error) if nothing is
    found - a missing whispers opinion should never block a prediction,
    just mean the agent reasons without that extra input.
    """
    query = f"{home_team} vs {away_team} prediction"
    try:
        resp = requests.get(SITE, params={"s": query}, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[Whispers] search failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    home_tokens = _tokens(home_team)
    away_tokens = _tokens(away_team)

    candidate_url = None
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True).lower()
        if not title or "prediction" not in title:
            continue
        if any(t in title for t in home_tokens) and any(t in title for t in away_tokens):
            candidate_url = a["href"]
            break

    if not candidate_url:
        return None

    return fetch_whispers_article(candidate_url)


def fetch_whispers_article(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[Whispers] article fetch failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    article = soup.find("article") or soup
    text = article.get_text("\n", strip=True)

    score_match = re.search(r"(predicting[^.\n]+\.)", text, re.IGNORECASE)
    tip_match = re.search(r"(top tip[:\-][^\n]+)", text, re.IGNORECASE)

    parts = [m.group(1) for m in (score_match, tip_match) if m]

    if not parts:
        # Fall back to the first couple of sentences of the article body
        sentences = re.split(r"(?<=[.!?])\s+", text)
        parts = [s for s in sentences[:4] if s]

    return {
        "source": "footballwhispers",
        "url": url,
        "summary": " ".join(parts).strip()[:600],
    }
