import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.fetch_whispers_prediction import find_whispers_article

# Edit these to whatever fixture you want to test against footballwhispers.com
HOME_TEAM = "France"
AWAY_TEAM = "Morocco"

if __name__ == "__main__":
    print(f"Searching footballwhispers.com for '{HOME_TEAM} vs {AWAY_TEAM}'...\n")
    result = find_whispers_article(HOME_TEAM, AWAY_TEAM)

    if result is None:
        print("No article found. This is a VALID outcome, not necessarily a bug - "
              "footballwhispers might just not have a preview up for this fixture "
              "yet. Try a bigger/more mainstream fixture if you want to confirm "
              "the happy path actually works before trusting a null result.")
    else:
        print("Found:")
        print(f"  source:  {result['source']}")
        print(f"  url:     {result['url']}")
        print(f"  summary: {result['summary']}")