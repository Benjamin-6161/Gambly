import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from helpers.fetch_match_results import get_match_details

# Edit this to a flashscore match_id for a match that has ALREADY BEEN
# PLAYED - grab one from test_fetch_all_matches.py output a few days after
# the fact, or any finished match_id you have handy.
MATCH_ID = "bodsDyte"  # placeholder - swap for a real finished match_id

if __name__ == "__main__":
    print(f"Fetching match details for match_id={MATCH_ID}...\n")
    details = get_match_details(MATCH_ID)

    print("Raw result:")
    for key, value in details.items():
        print(f"  {key}: {value}")

    if details.get("ft_score") is None:
        print("\nNo FT score found. Either this match hasn't finished yet, or "
              "this file's selectors are stale - it was written BEFORE we "
              "discovered flashscore's markup redesign (.event__time -> "
              ".event__stageTime, dated timestamps always shown, etc.) while "
              "fixing fetch_all_matches.py, and has never been re-verified "
              "against a real finished match since. If this comes back empty "
              "for a match you know has finished, that redesign is the first "
              "thing to check.")