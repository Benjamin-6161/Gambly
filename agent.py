import os
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
from helpers.db import save_prediction, get_history_context
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

class BuildTicketInput(BaseModel):
    predictions: List[MatchPick] = Field(description="Every pick made this run, one entry per match")


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

class SendTelegramMessageTool(BaseTool):
    name: str = "send_telegram_message"
    description: str = "Useful for when you need to send a telegram message."
    args_schema: Type[BaseModel] = SendTelegramMessageInput

    def _run(self, message: str) -> str:
        return send_telegram_message(message)

class BuildTicketTool(BaseTool):
    name: str = "build_ticket"
    description: str = (
        "Call this exactly once, after you've decided a pick for every match "
        "and saved each one with save_prediction. Pass every pick you made. "
        "This tries to book each leg on SportyBet (no login, no stake - just "
        "generating a shareable slip code) and returns the finished ticket "
        "message text, ready to send exactly as-is via send_telegram_message. "
        "Legs that couldn't be auto-booked are already flagged in the "
        "returned text as needing a manual add - don't try to fix those "
        "yourself, just send the message as returned."
    )
    args_schema: Type[BaseModel] = BuildTicketInput

    def _run(self, predictions: List[MatchPick]) -> str:
        pred_dicts = [p.model_dump() for p in predictions]
        booking_result = book_parlay(pred_dicts)
        return generate_ticket_message(pred_dicts, booking_result=booking_result)

def get_all_matches(*args, **kwargs):
    return fetch_matches()

def get_history(*args, **kwargs):
    return get_history_context(limit=30)

tools = [
    FetchMatchDetailsTool(),
    FetchWhispersTool(),
    SavePredictionTool(),
    BuildTicketTool(),
    SendTelegramMessageTool(),
     StructuredTool.from_function(
        func=lambda: fetch_matches(),
        name="GetAllMatches",
        description="Get all available matches for the day",
        args_schema=NoArgs,
    ),
   StructuredTool.from_function(
        func=lambda: get_history_context(limit=30),
        name="GetHistoryContext",
        description="Get a summary of past predictions vs actual results...",
        args_schema=NoArgs,
    ),
]

if os.getenv("ENVIRONMENT") == "production":
    #gemini
    llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite")
    agent = create_react_agent(llm, tools)
else:
    #ollama (for dev)
    llm = ChatOllama(model="qwen2.5-coder-7b-local", temperature=0, num_ctx=16384)
    agent = create_react_agent(llm, tools)


SYSTEM_PROMPT = """You are an expert soccer punter helping produce a daily parlay ticket.

Rules:
1. Call GetHistoryContext once at the start and keep it in mind throughout.
2. Call GetAllMatches to get today's matches.
3. For each match: call fetch_match_overview for stats/news/H2H, and call
   fetch_whispers_prediction for an outside opinion. Treat the whispers
   opinion as one more input to weigh, not a rule to follow - your own
   reasoning over the match overview, stats and history context should
   dominate the final call.
4. Decide a single best market + pick per match. Valid outcomes include
   things like: 'Home/Away win', 'Draw', 'Home/Away win or draw',
   'Total goals over/under X', 'Home/Away goals over/under X',
   'Both teams to score - Yes/No', match stats (cards, corners over/under),
   player stats (goals, assists), or an exact scoreline. Each leg must be
   ONE clean market only - never combine two picks into one outcome (e.g.
   not 'Home win and under 2.5 goals', not 'BTTS and over 2.5' - pick
   whichever single one you have more conviction in instead).
5. Call save_prediction for every match you make a pick on.
6. Once you've gone through all matches, call build_ticket exactly once
   with every pick you made (fixture, home_team, away_team, market,
   predicted_outcome, reasoning, whispers_opinion). It will attempt to
   book each leg on SportyBet as a shareable slip code - no login, no
   stake, nothing placed - and return the finished message text.
7. Send that returned text via send_telegram_message exactly as given,
   without editing it. If there were no matches available at all, skip
   build_ticket and just send 'No High priority matches available today😓.'
8. Make sure to return a prediction for every match in fetch_matches no matter the number.
"""

response = agent.invoke({
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Run today's full prediction pipeline and send the ticket."},
    ]
})
print(f"Response: {response['messages'][-1].content}")
