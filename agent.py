import os
import re
from typing import Type, Optional, List
from dotenv import load_dotenv
load_dotenv()

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import BaseTool, Tool, StructuredTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from tools.fetch_match_overview import fetch_match_overview
from tools.fetch_all_matches import fetch_matches
from tools.fetch_whispers_prediction import find_whispers_article
from tools.send_telegram_message import send_telegram_message
from tools.book_ticket import book_parlay
from helpers.db import (
    save_prediction,
    get_history_context,
    get_latest_prediction,
)
from helpers.generate_ticket import generate_ticket_message



# ---------------------------------------------------------------------------
# Tool argument schemas
# ---------------------------------------------------------------------------

class NoArgs(BaseModel):
    pass

class FetchMatchDetailsInput(BaseModel):
    url: str = Field(description="should be a url for a match")

class WhispersInput(BaseModel):
    home_team: str = Field(description="home team name")
    away_team: str = Field(description="away team name")

class SavePredictionInput(BaseModel):
    match_id: str = Field(description="the match_id for this fixture")
    fixture: str = Field(description="e.g. 'Team A vs Team B'")
    category: str = Field(description="country/category, e.g. 'ENGLAND'")
    league: str = Field(description="competition name, e.g. 'PREMIER LEAGUE'")
    market: str = Field(description="betting market, e.g. 'Match Result', 'Total Goals', 'BTTS'")
    predicted_outcome: str = Field(description="the specific pick, e.g. 'Home win', 'Over 2.5 goals'")
    reasoning: str = Field(description="one or two sentence reasoning behind the pick")
    whispers_opinion: Optional[str] = Field(
        default="",
        description=(
            "footballwhispers.com's tip in just a few words - e.g. "
            "'BTTS - Yes' or 'Spain to win 2-0' - not the full article "
            "summary. This gets shown directly in the Telegram message, "
            "so keep it short."
        ),
    )

class SendTelegramMessageInput(BaseModel):
    message: str = Field(description="should be a string of the telegram message to send")

class MatchPick(BaseModel):
    fixture: str = Field(description="e.g. 'Team A vs Team B'")
    home_team: str
    away_team: str
    market: str
    predicted_outcome: str
    reasoning: Optional[str] = ""
    whispers_opinion: Optional[str] = ""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class FetchMatchDetailsTool(BaseTool):
    name: str = "fetch_match_overview"
    description: str = "Useful for when you need details on a single match (news, stats, H2H) from flashscore.com."
    args_schema: Type[BaseModel] = FetchMatchDetailsInput

    def _run(self, url: str) -> str:
        return fetch_match_overview(url)

class FetchWhispersTool(BaseTool):
    name: str = "fetch_whispers_prediction"
    description: str = (
        "Get footballwhispers.com's prediction/opinion for a given home vs away "
        "matchup, as one extra input alongside your own reasoning. Returns null "
        "if no matching article is found - that's fine, just proceed without it."
    )
    args_schema: Type[BaseModel] = WhispersInput

    def _run(self, home_team: str, away_team: str):
        return find_whispers_article(home_team, away_team)

class SavePredictionTool(BaseTool):
    name: str = "save_prediction"
    description: str = (
        "Persist your final prediction for a match to the database. Call this "
        "exactly once per match, after you've decided on your pick, so future "
        "runs can learn from how it turns out."
    )
    args_schema: Type[BaseModel] = SavePredictionInput

    def _run(self, **kwargs) -> str:
        save_prediction(kwargs)
        return "Saved"


def get_history(*args, **kwargs):
    return get_history_context(limit=30)

per_match_tools = [
    FetchMatchDetailsTool(),
    FetchWhispersTool(),
    SavePredictionTool(),
]


def _make_llm():
    if os.getenv("ENVIRONMENT") == "production":
        #gemini
        return ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite")
    #ollama (for dev)
    return ChatOllama(model="qwen2.5-coder-7b-local", temperature=0, num_ctx=16384)


# Bookable markets only - every option here resolves to a real SportyBet
# market ID in tools/sportybet_client.py. Do NOT pick anything else
# (no compound picks like 'Home win and over 2.5', no markets outside
# this list) or the leg can't go into the booking code.
BOOKABLE_MARKETS = """- Match Result (1X2): 'Home win', 'Draw', 'Away win'
- Double Chance: 'Home win or draw', 'Home win or Away win', 'Away win or draw'
- Draw No Bet: 'Home (Draw No Bet)', 'Away (Draw No Bet)'
- Total Goals Over/Under: 'Over X goals' / 'Under X goals' (X = 0.5/1.5/2.5/3.5/4.5/5.5)
- Home Team Goals Over/Under / Away Team Goals Over/Under (same lines)
- 1st Half: Match Result, Over/Under, Double Chance, Draw No Bet, BTTS
- 2nd Half: Match Result, Over/Under, Double Chance, Draw No Bet, BTTS
- Both Teams To Score: 'Yes' / 'No'
- Odd/Even Goals: 'Odd' / 'Even' (match, home team, or away team)
- Exact Score: e.g. '2-1' / '1-1'
- Half Time / Full Time: e.g. 'Home/Home', 'Draw/Away'
- Handicap (3-way): e.g. 'Home (1:0)', 'Draw (0:1)', 'Away (0:2)'
- Asian Handicap: e.g. 'Home -1.5', 'Away +0.5'
- 1st Goal / Last Goal: 'Home', 'Away', 'No goal'
- Corners: Total Over/Under (7.5/8.5/9.5/10.5/11.5), Corners 1X2
- Bookings/Cards: Total Over/Under (1.5/2.5/3.5/4.5), Bookings 1X2
- Clean Sheet / Win To Nil: 'Yes' / 'No'"""

PER_MATCH_SYSTEM = f"""You are an expert soccer punter. You analyse ONE match and save ONE pick - or skip it.

Steps for this match:
1. Call fetch_match_overview with the given match_url for stats/news/H2H.
2. Call fetch_whispers_prediction with the home/away team names. A null
   result is fine - treat it as one extra input, not a rule. Your own
   reasoning over the overview, stats and history context dominates.
3. If you have genuine conviction, call save_prediction EXACTLY ONCE with
   the given match_id/fixture/category/league plus your chosen market,
   predicted_outcome, one-or-two-sentence reasoning and short
   whispers_opinion ("" if none). Use the market/outcome wording below.
4. If you have NO conviction (missing data, derby chaos, nothing stands
   out), do NOT call save_prediction - just reply SKIP. Skipping is
   allowed: only high-confidence picks make the ticket.

Valid markets/outcomes (bookable on SportyBet - pick nothing else, and
each leg must be ONE clean market, never a combo like 'Home win and
under 2.5'):
{BOOKABLE_MARKETS}
"""


def _split_fixture(fixture: str):
    parts = fixture.split(" vs ")
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return fixture.strip(), ""


def run_per_match(agent, match: dict, history: str) -> Optional[dict]:
    """Invoke the agent for a single match. Returns the saved prediction
    row (or None when the agent skipped / failed). Picks are read back
    from the DB so the ticket can only ever contain what was persisted -
    fixing the old bug where the agent analysed N matches but only
    returned picks for ~3 of them."""
    home, away = _split_fixture(match.get("fixture", ""))
    user_msg = (
        f"Analyse this ONE match and save (or skip) a pick:\n"
        f"- fixture: {match.get('fixture')}\n"
        f"- home_team: {home}\n"
        f"- away_team: {away}\n"
        f"- match_id: {match.get('match_id')}\n"
        f"- category: {match.get('category')}\n"
        f"- league: {match.get('league')}\n"
        f"- date: {match.get('date')}\n"
        f"- match_url: {match.get('match_url')}\n\n"
        f"Past performance context (keep in mind):\n{history}"
    )
    try:
        agent.invoke({
            "messages": [
                {"role": "system", "content": PER_MATCH_SYSTEM},
                {"role": "user", "content": user_msg},
            ]
        })
    except Exception as e:
        print(f"[agent] match {match.get('fixture')} failed: {e}")
        return None

    row = get_latest_prediction(match.get("match_id", ""))
    if not row:
        print(f"[agent] SKIP (no conviction): {match.get('fixture')}")
        return None
    return row


def main():
    llm = _make_llm()
    agent = create_react_agent(llm, per_match_tools)

    history = get_history_context(limit=30)

    matches = fetch_matches()
    if isinstance(matches, str) or not matches:
        msg = "No High priority matches available today\U0001f613."
        print(f"[agent] {msg} (fetcher returned: {matches!r})")
        send_telegram_message(msg)
        return

    print(f"[agent] Fetched {len(matches)} match(es); analysing each in turn...")
    saved_rows = []
    for i, match in enumerate(matches, 1):
        print(f"[agent] ({i}/{len(matches)}) {match.get('fixture')} ...")
        row = run_per_match(agent, match, history)
        if row:
            saved_rows.append(row)

    if not saved_rows:
        msg = "No High priority matches available today\U0001f613."
        print(f"[agent] No confident picks from {len(matches)} matches.")
        send_telegram_message(msg)
        return

    # Build booking picks from what was actually persisted.
    booking_picks = []
    for row in saved_rows:
        home, away = _split_fixture(row.get("fixture", ""))
        booking_picks.append({
            "fixture": row.get("fixture"),
            "home_team": home,
            "away_team": away,
            "market": row.get("market", ""),
            "predicted_outcome": row.get("predicted_outcome", ""),
            "reasoning": row.get("reasoning", ""),
            "whispers_opinion": row.get("whispers_opinion", ""),
        })

    booking_result = book_parlay(booking_picks)
    code = (booking_result or {}).get("booking_code")
    print(f"[agent] Picks: {len(booking_picks)}, booking code: {code or 'NONE'}")
    if not code:
        unbooked = [p.get("fixture") for p in (booking_result or {}).get("unbooked", [])]
        print(f"[agent] Unbooked legs: {unbooked}")

    message = generate_ticket_message(booking_picks, booking_result=booking_result)
    result = send_telegram_message(message)
    print(f"[agent] Telegram: {result}")


if __name__ == "__main__":
    main()
