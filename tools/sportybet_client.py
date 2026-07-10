import re
import time
import requests

SEARCH_URL = "https://www.sportybet.com/api/ng/factsCenter/event/firstSearch"
SHARE_URL = "https://www.sportybet.com/api/ng/orders/share"
HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"}

PLACEHOLDER_STAKE = 1000000


class SportyBetSession:
    """
    Drives two confirmed-live, no-login SportyBet endpoints:

    1. `firstSearch` - a real search API (not HTML scraping) that returns
       full match + market + outcome data for a team-name query in one
       shot. Confirmed live against "morocco": correctly found the actual
       World Cup fixture (sr:match:53452525) with every market/outcome ID
       already resolved - no day-listing pagination limits, no HTML
       parsing. This replaced an earlier, much more fragile approach that
       scraped SportyBet's day-by-day HTML listing page, which turned out
       not to carry marquee tournaments like the World Cup at all.
    2. `orders/share` - confirmed live: POST a list of selections, get
       back a shareCode/shareURL. No login, no cookie, no charge - "stake"
       is required by the payload but never actually debited.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def find_event(self, home_team, away_team):
        """..."""
        # flashscore fixture names carry a " (Xxx)" country-disambiguator
        # suffix (e.g. "Qarabag (Aze)") that SportyBet's real team names
        # don't have - confirmed causing every search to come back empty
        # for a batch of Europa League fixtures. Strip it before searching.
        clean_home = re.sub(r"\s*\([^)]*\)\s*$", "", home_team).strip()
        clean_away = re.sub(r"\s*\([^)]*\)\s*$", "", away_team).strip()

        for query in (clean_home, clean_away):
            try:
                resp = self.session.get(SEARCH_URL, params={
                    "keyword": query,
                    "offset": 0,
                    "pageSize": 20,
                    "withOneUpMarket": "true",
                    "withTwoUpMarket": "true",
                    "_t": int(time.time() * 1000),
                }, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError) as e:
                print(f"[SportyBet] firstSearch failed for '{query}': {e}")
                continue

            all_events = (data.get("data", {}).get("live", []) +
                          data.get("data", {}).get("preMatch", []))

            home_key = clean_home.lower().split()[0]
            away_key = clean_away.lower().split()[0]

            for event in all_events:
                home_name = (event.get("homeTeamName") or "")
                away_name = (event.get("awayTeamName") or "")

                category_name = (event.get("sport", {}).get("category", {}).get("name") or "").lower()
                if "simulated reality" in category_name:
                    continue

                if home_key in home_name.lower() and away_key in away_name.lower():
                    return event

        print(f"[SportyBet] find_event: no match for '{home_team}' vs '{away_team}'")
        return None

    @staticmethod
    def resolve_home_draw_away(event: dict, outcome: str):
        """outcome: 'home', 'draw', or 'away'. Reads straight off the
        market-1 (1X2) block already present in the search result."""
        desc = {"home": "Home", "draw": "Draw", "away": "Away"}.get(outcome)
        if not desc:
            return None
        for market in event.get("markets", []):
            if market.get("id") == "1":  # 1X2, confirmed
                for o in market.get("outcomes", []):
                    if o.get("desc") == desc:
                        return {"eventId": event["eventId"], "marketId": "1",
                                "specifier": None, "outcomeId": o["id"]}
        return None

    @staticmethod
    def resolve_known_market(self, event: dict, market_text: str, outcome_text: str):
        """
        Resolves a selection from confirmed SportyBet market/outcome IDs.
        market_text and outcome_text are checked separately (rather than
        one combined string) so a market label like "Home Goals Over/Under"
        can correctly route to market 19 instead of being misread as the
        total-goals market (18) just because "goals" appears in it.

        IDs confirmed against real /orders/share and firstSearch captures:
          - market 18 (Total goals O/U): outcomeId 12 = Over, 13 = Under.
          - market 19 (Home team goals O/U): same outcome IDs as 18.
          - market 20 (Away team goals O/U): same outcome IDs as 18.
          - market 29 (BTTS/GG-NG): outcomeId 74 = Yes, 76 = No.
          - market 10 (Double Chance): outcomeId 9 = 1X, 10 = 12, 11 = X2.
        Anything else (handicaps, exact score, corners/cards, player
        props, or a compound pick combining two markets in one string)
        returns None.
        """
        market = market_text.lower()
        outcome = outcome_text.lower()
        combined = f"{market} {outcome}"

        if "double chance" in combined or "win or draw" in combined or "or draw" in combined or "or away" in combined:
            if "home" in combined and "draw" in combined:
                return {"eventId": event["event_id"], "marketId": "10",
                        "specifier": None, "outcomeId": "9"}
            if "home" in combined and "away" in combined:
                return {"eventId": event["event_id"], "marketId": "10",
                        "specifier": None, "outcomeId": "10"}
            if "draw" in combined and "away" in combined:
                return {"eventId": event["event_id"], "marketId": "10",
                        "specifier": None, "outcomeId": "11"}

        if ("both teams to score" in combined or "btts" in combined or " gg" in combined) and "team" not in combined.split("both")[0]:
            if "yes" in combined:
                return {"eventId": event["event_id"], "marketId": "29",
                        "specifier": None, "outcomeId": "74"}
            if "no" in combined:
                return {"eventId": event["event_id"], "marketId": "29",
                        "specifier": None, "outcomeId": "76"}

        over_under = re.search(r"(over|under)\s*(\d+(?:\.\d+)?)", outcome)
        if over_under and "goal" in combined:
            direction, line = over_under.group(1), over_under.group(2)
            outcome_id = "12" if direction == "over" else "13"

            if "home" in market and "goal" in market:
                market_id = "19"
            elif "away" in market and "goal" in market:
                market_id = "20"
            elif "home" not in market and "away" not in market:
                market_id = "18"
            else:
                return None  # ambiguous, don't guess

            return {"eventId": event["event_id"], "marketId": market_id,
                    "specifier": f"total={line}", "outcomeId": outcome_id}

        return None

    def get_booking_code(self, selections: list):
        """VERIFIED live: see earlier capture. No login, no cookie, no
        debit - stake is required by the payload but never charged.

        NOTE: the plain /orders/share path (no /api prefix) started
        getting redirected to a dead /ng/m/orders/share route and 404ing -
        confirmed via a fresh manual capture that the live path now needs
        the /api prefix, plus three headers (clientid/platform/operid)
        identifying the request as coming from the wap client. Without
        these the request appears to get misrouted rather than rejected
        outright, which is a nastier failure mode than a clean error -
        worth re-checking these headers again if this endpoint acts up
        in the future.
        """
        if not selections:
            return None

        payload = {
            "selections": [
                {
                    "eventId": s["eventId"],
                    "marketId": s["marketId"],
                    "specifier": s.get("specifier"),
                    "outcomeId": s["outcomeId"],
                    "stake": PLACEHOLDER_STAKE,
                }
                for s in selections
            ],
            "orderType": 2,
            "betType": "MULTIPLE",
        }

        resp = self.session.post(
            SHARE_URL,
            params={"throwInvalidEvent": "true"},
            json=payload,
            headers={
                "clientid": "wap",
                "platform": "wap",
                "operid": "2",
                "content-type": "application/json;charset=UTF-8",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("isAvailable") or "data" not in data:
            return None

        return {
            "share_code": data["data"].get("shareCode"),
            "share_url": data["data"].get("shareURL"),
        }