import sys
import os
import json

# tools/ and helpers/ live one level up from tests/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.book_ticket import book_parlay
from helpers.generate_ticket import generate_ticket_message

# ---------------------------------------------------------------------------
# EDIT THIS: paste in whatever predictions you want to test, in the exact
# shape build_ticket receives from the agent (see MatchPick in agent.py).
# home_team/away_team/market/predicted_outcome are what book_parlay() uses
# to actually resolve and book each leg. fixture/reasoning/whispers_opinion
# aren't used for booking but ARE used by generate_ticket_message, so fill
# them in too if you want to see the real final Telegram text.
# ---------------------------------------------------------------------------
"""PREDICTIONS = [
    {
        "fixture": "France vs Morocco",
        "home_team": "France",
        "away_team": "Morocco",
        "market": "Match Result",
        "predicted_outcome": "Home win",
        "reasoning": "Test reasoning for France win.",
        "whispers_opinion": "",
    },
    {
        "fixture": "Spain vs Belgium",
        "home_team": "Spain",
        "away_team": "Belgium",
        "market": "Total Goals",
        "predicted_outcome": "Over 2.5 goals",
        "reasoning": "Test reasoning for over 2.5.",
        "whispers_opinion": "",
    },
]"""
PREDICTIONS = [
    {
        "fixture": "Spain vs Belgium",
        "home_team": "Spain",
        "away_team": "Belgium",
        "market": "Match Result",
        "predicted_outcome": "Draw",
        "reasoning": "Test reasoning for draw.",
        "whispers_opinion": "",
    },
    {
        "fixture": "Norway vs England",
        "home_team": "Norway",
        "away_team": "England",
        "market": "Match Result",
        "predicted_outcome": "Away win",
        "reasoning": "Test reasoning for away win.",
        "whispers_opinion": "",
    },
    {
        "fixture": "France vs Morocco",
        "home_team": "France",
        "away_team": "Morocco",
        "market": "Double Chance",
        "predicted_outcome": "Home or Draw",
        "reasoning": "Test reasoning for double chance.",
        "whispers_opinion": "",
    },
    {
        "fixture": "Spain vs Belgium",
        "home_team": "Spain",
        "away_team": "Belgium",
        "market": "Both Teams To Score",
        "predicted_outcome": "Both Teams To Score - Yes",
        "reasoning": "Test reasoning for BTTS.",
        "whispers_opinion": "",
    },
]

if __name__ == "__main__":
    print(f"Testing book_parlay() with {len(PREDICTIONS)} prediction(s)...\n")

    booking_result = book_parlay(PREDICTIONS)

    print("\n=== book_parlay() result ===")
    print(json.dumps(booking_result, indent=2, default=str))

    print("\n=== Final ticket message (generate_ticket_message) ===")
    message = generate_ticket_message(PREDICTIONS, booking_result=booking_result)
    print(message)