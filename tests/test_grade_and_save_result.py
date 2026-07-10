import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from helpers.db import save_prediction, save_result, get_latest_prediction, grade_prediction

# NOTE: this writes to the REAL resources/db/matches.db - the same file the
# live pipeline uses - so the feedback loop can be inspected end-to-end.
# Uses an obviously-fake match_id so it's easy to find and remove afterward.
TEST_MATCH_ID = "TEST_MATCH_0001"
TEST_FIXTURE = "Test FC vs Placeholder United"

# Edit these to whatever prediction + "actual result" combo you want to
# stress-test the grading logic against (e.g. try predicted_outcome values
# for over/under, BTTS, or double chance markets, not just match result).
FAKE_PREDICTION = {
    "match_id": TEST_MATCH_ID,
    "fixture": TEST_FIXTURE,
    "category": "TEST",
    "league": "TEST LEAGUE",
    "market": "Match Result",
    "predicted_outcome": "Home win",
    "reasoning": "Test reasoning.",
    "whispers_opinion": "",
}

FAKE_MATCH_DETAILS = {
    "ht_score": "1-0",
    "ft_score": "2-1",  # home win - should grade correct against "Home win"
    "home_corners": 6,
    "away_corners": 4,
    "home_cards": 2,
    "away_cards": 3,
    "home_shots": 12,
    "away_shots": 9,
    "home_sot": 5,
    "away_sot": 3,
}

if __name__ == "__main__":
    print(f"Saving fake prediction for {TEST_FIXTURE} ({TEST_MATCH_ID})...")
    save_prediction(FAKE_PREDICTION)

    print(f"Saving fake result: ft_score={FAKE_MATCH_DETAILS['ft_score']}...")
    save_result(TEST_MATCH_ID, TEST_FIXTURE, FAKE_MATCH_DETAILS)

    print("\nDirect grade_prediction() check:")
    graded = grade_prediction(FAKE_PREDICTION["predicted_outcome"], FAKE_MATCH_DETAILS["ft_score"])
    print(f"  grade_prediction('{FAKE_PREDICTION['predicted_outcome']}', "
          f"'{FAKE_MATCH_DETAILS['ft_score']}') -> {graded}")
    print("  (1 = correct, 0 = incorrect, None = couldn't grade this market type)")

    print("\nLatest prediction row (from db):")
    print(get_latest_prediction(TEST_MATCH_ID))

    print(f"\nDone. This wrote real rows into resources/db/matches.db under "
          f"match_id='{TEST_MATCH_ID}'. To clean up: "
          f"sqlite3 resources/db/matches.db "
          f"\"DELETE FROM predictions WHERE match_id='{TEST_MATCH_ID}'; "
          f"DELETE FROM results WHERE match_id='{TEST_MATCH_ID}';\"")