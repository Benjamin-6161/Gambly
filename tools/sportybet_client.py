import re
import time
import requests

SEARCH_URL = "https://www.sportybet.com/api/ng/factsCenter/event/firstSearch"
EVENT_URL = "https://www.sportybet.com/api/ng/factsCenter/event"
SHARE_URL = "https://www.sportybet.com/api/ng/orders/share"
HEADERS = {"User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36"}

PLACEHOLDER_STAKE = 1000000

# Markets verified live against the real factsCenter/event payload
# (Italy vs Belgium, sr:match:68931470) plus the sportybet.com match page
# (All/Main/Goals/Half/Bookings/Corners/Specials/Players tabs). Outcome IDs
# below are stable platform-wide; specifiers are matched live per event.
OU_12_OVER = "12"
OU_13_UNDER = "13"
YES_74 = "74"
NO_76 = "76"
ODD_70 = "70"
EVEN_72 = "72"


def _normalize(name: str) -> str:
    """Lowercase, strip country-disambiguator suffixes like ' (Aze)',
    women's ' W', age-group tags and punctuation for fuzzy matching."""
    n = re.sub(r"\s*\([^)]*\)\s*$", "", (name or "")).strip()
    n = re.sub(r"\s+(W|Women|U\d+|U-\d+)$", "", n, flags=re.IGNORECASE).strip()
    return re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()


def _tokens(name: str):
    return [t for t in _normalize(name).split() if len(t) > 2]


SKIP_CATEGORY_RE = re.compile(
    r"simulated reality|esports|efootball|ebasketball|virtual|instant virtual",
    re.IGNORECASE,
)


class SportyBetSession:
    """
    Drives two confirmed-live, no-login SportyBet endpoints:

    1. `firstSearch` - finds candidate events for a team-name query.
    2. `factsCenter/event?eventId=` - full event payload with ALL ~1200+
       markets/outcomes (1X2, DC, DNB, handicaps, totals, team totals,
       HT/FT, exact score, odd/even, BTTS, 1st/2nd-half splits, 1st/last
       goal, corners, bookings/cards, shots, offsides, fouls, player
       props). Confirmed live against Italy vs Belgium.
    3. `orders/share` - POST selections, get back shareCode/shareURL.
       No login, no cookie, no charge - "stake" is required by the
       payload but never actually debited.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # -- event lookup ----------------------------------------------------

    def _search(self, query):
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
            return []
        return (data.get("data", {}).get("live", []) +
                data.get("data", {}).get("preMatch", []))

    @staticmethod
    def _is_real_football(event) -> bool:
        category = (event.get("sport", {}).get("category", {}).get("name") or "")
        tourn = (event.get("sport", {}).get("tournament", {}).get("name") or "")
        if SKIP_CATEGORY_RE.search(f"{category} {tourn}"):
            return False
        sport_name = (event.get("sport", {}).get("name") or "").lower()
        if sport_name and sport_name != "football":
            return False
        return True

    @classmethod
    def _score_event(cls, event, home_team, away_team) -> int:
        """Token-overlap score so 'Man City' matches 'Manchester City',
        either search order works, and exact matches outrank partials."""
        home_t, away_t = set(_tokens(home_team)), set(_tokens(away_team))
        ev_home, ev_away = set(_tokens(event.get("homeTeamName") or "")), set(
            _tokens(event.get("awayTeamName") or ""))
        if not home_t or not away_t or not ev_home or not ev_away:
            return -1
        straight = len(home_t & ev_home) + len(away_t & ev_away)
        swapped = len(home_t & ev_away) + len(away_t & ev_home)
        best = max(straight, swapped)
        if best == 0:
            return -1
        # bonus when every query token is covered (exact-ish match)
        if straight == len(home_t) + len(away_t):
            best += 5
        return best

    def find_event(self, home_team, away_team):
        """Best-scoring real-football event across both team queries."""
        clean_home = re.sub(r"\s*\([^)]*\)\s*$", "", home_team).strip()
        clean_away = re.sub(r"\s*\([^)]*\)\s*$", "", away_team).strip()

        best, best_score = None, -1
        for query in (clean_home, clean_away):
            for event in self._search(query):
                if not self._is_real_football(event):
                    continue
                score = self._score_event(event, clean_home, clean_away)
                if score > best_score:
                    best, best_score = event, score

        if best is None:
            print(f"[SportyBet] find_event: no match for '{home_team}' vs '{away_team}'")
            return None
        return best

    def get_event_details(self, event_id: str):
        """Full market catalogue for one event. Returns None on failure
        (callers fall back to the slimmer firstSearch payload)."""
        try:
            resp = self.session.get(
                EVENT_URL,
                params={"eventId": event_id, "_t": int(time.time() * 1000)},
                timeout=25,
            )
            resp.raise_for_status()
            return resp.json().get("data")
        except (requests.RequestException, ValueError) as e:
            print(f"[SportyBet] event details failed for {event_id}: {e}")
            return None

    def find_event_with_markets(self, home_team, away_team):
        """find_event + full market catalogue in one call."""
        event = self.find_event(home_team, away_team)
        if not event:
            return None
        details = self.get_event_details(event["eventId"])
        if details and details.get("markets"):
            event = {**event, "markets": details["markets"]}
        return event

    # -- market helpers --------------------------------------------------

    @staticmethod
    def _iter_markets(event, *market_ids):
        want = {str(m) for m in market_ids}
        for market in event.get("markets", []):
            if str(market.get("id")) in want:
                yield market

    @staticmethod
    def _pick(event_id, market, outcome_id):
        return {"eventId": event_id, "marketId": str(market.get("id")),
                "specifier": market.get("specifier"), "outcomeId": str(outcome_id)}

    @classmethod
    def _ou(cls, event, market_ids, direction, line):
        want_spec = f"total={line}"
        oid = OU_12_OVER if direction == "over" else OU_13_UNDER
        for market in cls._iter_markets(event, *market_ids):
            if (market.get("specifier") or "").strip() != want_spec:
                continue
            oids = {str(o.get("id")) for o in market.get("outcomes", [])}
            if oid in oids:
                return cls._pick(event["eventId"], market, oid)
        return None

    @classmethod
    def _named_outcome(cls, event, market_ids, outcome_descs,
                       specifier=None, spec_contains=None):
        """First market (optionally filtered by specifier) containing one
        of the outcome descs (case-insensitive exact match)."""
        if isinstance(outcome_descs, str):
            outcome_descs = [outcome_descs]
        want = {d.lower() for d in outcome_descs}
        for market in cls._iter_markets(event, *market_ids):
            spec = (market.get("specifier") or "")
            if specifier is not None and spec.strip() != specifier:
                continue
            if spec_contains and spec_contains not in spec:
                continue
            for o in market.get("outcomes", []):
                if str(o.get("desc", "")).lower() in want:
                    return cls._pick(event["eventId"], market, o["id"])
        return None

    @staticmethod
    def resolve_home_draw_away(event: dict, outcome: str):
        """outcome: 'home', 'draw', or 'away'. Reads straight off the
        market-1 (1X2) block already present in the search result."""
        desc = {"home": "Home", "draw": "Draw", "away": "Away"}.get(outcome)
        if not desc:
            return None
        return SportyBetSession._named_outcome(event, ["1"], desc)

    @staticmethod
    def resolve_known_market(event: dict, market_text: str, outcome_text: str):
        """
        Resolve a selection from the live market catalogue using confirmed
        SportyBet market/outcome IDs (verified against a real
        factsCenter/event capture + the sportybet.com match page, which
        exposes All/Main/Goals/Half/Bookings/Corners/Specials/Players tabs).

        market_text and outcome_text are checked separately so e.g.
        "Home Goals Over/Under" routes to market 19, not 18.
        Returns None for anything with no live equivalent (player props
        for a player not in the squad list, out-of-range lines, compound
        picks combining two markets in one string).
        """
        market = (market_text or "").lower()
        outcome = (outcome_text or "").lower()
        combined = f"{market} {outcome}"
        R = SportyBetSession._named_outcome
        OU = SportyBetSession._ou

        def ou_direction():
            m = re.search(r"(over|under)\s*(\d+(?:\.\d+)?)", outcome)
            return (m.group(1), m.group(2)) if m else (None, None)

        half = "1st half" in combined or "first half" in combined or " ht " in f" {combined} "
        second_half = "2nd half" in combined or "second half" in combined
        is_half = half or second_half

        # --- Half-time / full-half Match Result (1X2) ---
        if is_half and ("1x2" in combined or "match result" in combined or "result" in market):
            mids = ["60"] if half else ["83"]
            if outcome.strip() == "draw" or outcome == "draw":
                return R(event, mids, "Draw")
            if "home win" in outcome or outcome.strip() == "home":
                return R(event, mids, "Home")
            if "away win" in outcome or outcome.strip() == "away":
                return R(event, mids, "Away")

        # --- Full-time Match Result (1X2, market 1) ---
        if not is_half and ("1x2" in market or "match result" in market
                            or market.strip() in ("", "result", "ft result")):
            if outcome == "draw":
                return R(event, ["1"], "Draw")
            if "home win" in outcome:
                return R(event, ["1"], "Home")
            if "away win" in outcome:
                return R(event, ["1"], "Away")

        # --- Double chance (incl. 1H/2H) ---
        if "double chance" in combined or "win or draw" in combined or "or draw" in combined:
            mids = ["63"] if half else (["85"] if second_half else ["10"])
            if "home" in combined and "draw" in combined:
                return R(event, mids, "Home or Draw")
            if "home" in combined and "away" in combined and "draw" not in combined:
                return R(event, mids, "Home or Away")
            if "draw" in combined and "away" in combined:
                return R(event, mids, "Draw or Away")

        # --- Draw-no-bet family ---
        if "draw no bet" in combined or re.search(r"\bdnb\b", combined):
            mids = ["64"] if half else (["86"] if second_half else ["11"])
            if "home" in outcome:
                return R(event, mids, "Home")
            if "away" in outcome:
                return R(event, mids, "Away")
            return None
        # --- Home/Away No Bet (markets 12/13) ---
        if "home no bet" in combined:
            if "draw" in outcome:
                return R(event, ["12"], "Draw")
            if "away" in outcome:
                return R(event, ["12"], "Away")
            return None
        if "away no bet" in combined:
            if "home" in outcome:
                return R(event, ["13"], "Home")
            if "draw" in outcome:
                return R(event, ["13"], "Draw")
            return None

        # --- BTTS / GG-NG (incl. halves) ---
        if ("both teams to score" in combined or "btts" in combined
                or re.search(r"\bgg\b", combined) or "gg/ng" in combined):
            mids = ["75"] if half else (["95"] if second_half else ["29"])
            if "yes" in combined:
                return R(event, mids, "Yes")
            if "no" in combined:
                return R(event, mids, "No")

        # --- Exact score ---
        m = re.search(r"(\d+)\s*-\s*(\d+)", outcome)
        if ("correct score" in combined or "exact score" in combined or "scoreline" in combined
                or ("score" in market and m)):
            if m:
                return R(event, ["45"], f"{int(m.group(1))}:{int(m.group(2))}") or \
                    R(event, ["45"], "Other")
            return None

        # --- Half-time / Full-time ---
        if "half time" in combined and "full time" in combined or "ht/ft" in combined.replace(" ", ""):
            norm = outcome.replace("-", "/")
            parts = [p.strip().capitalize() for p in norm.split("/") if p.strip()]
            if len(parts) == 2:
                return R(event, ["47"], f"{parts[0]}/{parts[1]}")
            return None

        # --- Odd / Even goals ---
        if "odd" in combined and "even" in combined or re.search(r"\bodd/even\b", combined) \
                or ("odd" in outcome and "even" in market) or ("even" in outcome and "odd" in market):
            mids = ["27"] if "home" in market and "team" in market else (
                ["28"] if "away" in market and "team" in market else ["26"])
            if "odd" in outcome:
                return R(event, mids, "Odd")
            if "even" in outcome:
                return R(event, mids, "Even")

        # --- Clean sheet / win to nil / teams to score ---
        if "clean sheet" in combined:
            mids = ["31"] if "home" in combined else (["32"] if "away" in combined else ["31", "32"])
            if "yes" in combined:
                return R(event, mids, "Yes")
            if "no" in combined:
                return R(event, mids, "No")
        if "win to nil" in combined:
            mids = ["33"] if "home" in combined else ["34"]
            if "yes" in combined:
                return R(event, mids, "Yes")
            if "no" in combined:
                return R(event, mids, "No")
        if "teams to score" in combined and "both" not in combined:
            if "only home" in combined:
                return R(event, ["30"], "Only Home")
            if "only away" in combined:
                return R(event, ["30"], "Only Away")
            if "none" in combined or "neither" in combined:
                return R(event, ["30"], "None")
            if "both" in combined:
                return R(event, ["30"], "Both teams")

        # --- Goal range / exact goals / team exact goals ---
        if "goal range" in combined or re.search(r"\d+\s*-\s*\d+\s*goals", combined):
            m = re.search(r"(\d+\s*-\s*\d+\+?)", outcome)
            if m:
                return R(event, ["25"], m.group(1).replace(" ", ""))
            return None
        if "exact goals" in combined or re.match(r"^\s*\d+\+?\s*(goals?)?\s*$", outcome):
            m = re.search(r"(\d+\+?)", outcome)
            if m:
                return R(event, ["21"], m.group(1))
            return None

        # --- Handicap (3-way, market 14) ---
        if "handicap" in combined and "asian" not in combined:
            hm = re.search(r"(\d+)\s*:\s*(\d+)", combined)
            if hm:
                spec = f"hcp={hm.group(1)}:{hm.group(2)}"
                for pick in ("Home", "Draw", "Away"):
                    if pick.lower() in outcome:
                        # outcome descs look like "Home (1:0)"
                        sel = R(event, ["14"],
                                [f"{pick} ({hm.group(1)}:{hm.group(2)})"],
                                specifier=spec)
                        if sel:
                            return sel
                return None

        # --- Asian handicap (market 16) ---
        if "asian handicap" in combined:
            hm = re.search(r"([+-]?\d+(?:\.\d+)?)", outcome)
            if hm:
                val = float(hm.group(1))
                side = "home" if "home" in combined else ("away" if "away" in combined else None)
                if side is None:
                    return None
                for mkt in SportyBetSession._iter_markets(event, "16"):
                    spec = (mkt.get("specifier") or "")
                    sm = re.search(r"hcp=([+-]?\d+(?:\.\d+)?)", spec)
                    if not sm or abs(float(sm.group(1))) != abs(val):
                        continue
                    for o in mkt.get("outcomes", []):
                        d = str(o.get("desc", "")).lower()
                        if side in d and str(abs(val)) in d:
                            return SportyBetSession._pick(
                                event["eventId"], mkt, o["id"])
                return None

        # --- 1st / last goal ---
        if "1st goal" in combined or "first goal" in combined or "first scorer" in combined:
            mids = ["62"] if half else (["84"] if second_half else ["8"])
            if "home" in combined:
                return R(event, mids, "Home")
            if "away" in combined:
                return R(event, mids, "Away")
            if "no" in combined and "goal" in combined:
                return R(event, mids, "None")
        if "last goal" in combined or "last scorer" in combined:
            if "home" in combined:
                return R(event, ["9"], "Home")
            if "away" in combined:
                return R(event, ["9"], "Away")
            if "no" in combined:
                return R(event, ["9"], "None")

        # --- Anytime / player props: match player surname to live list ---
        if "scorer" in combined or "goalscorer" in combined or "to score" in combined \
                or "player to be carded" in combined or "carded" in combined:
            for mkt in event.get("markets", []):
                if str(mkt.get("id")) not in ("38", "39", "40", "800296"):
                    continue
                for o in mkt.get("outcomes", []):
                    if _normalize(outcome_text) and _normalize(outcome_text) in _normalize(str(o.get("desc", ""))):
                        return SportyBetSession._pick(
                            event["eventId"], mkt, o["id"])
            return None

        # --- Over/Under: route by market family, then exact line ---
        direction, line = ou_direction()
        if direction and line and ("goal" in combined or "corner" in combined
                                   or "booking" in combined or "card" in combined
                                   or "point" in combined):
            norm_line = line if "." in line else line
            if "corner" in combined:
                if "home" in market:
                    return OU(event, ["900300", "900302"], direction, norm_line)
                if "away" in market:
                    return OU(event, ["900301", "900303"], direction, norm_line)
                mids = ["177"] if is_half else ["166"]
                return OU(event, mids, direction, norm_line)
            if "booking" in combined or "card" in combined or "booking point" in combined:
                if "point" in combined:
                    mids = ["151"] if half else ["138"]
                    return OU(event, mids, direction, norm_line)
                if "home" in market:
                    return OU(event, ["900304", "900306"], direction, norm_line)
                if "away" in market:
                    return OU(event, ["900305", "900307"], direction, norm_line)
                mids = ["152"] if half else ["139"]
                return OU(event, mids, direction, norm_line)
            if "home" in market and "goal" in market:
                mids = ["69"] if half else ["19"]
                return OU(event, mids, direction, norm_line)
            if "away" in market and "goal" in market:
                mids = ["70"] if half else ["20"]
                return OU(event, mids, direction, norm_line)
            if "1st half" in combined or half:
                return OU(event, ["68"], direction, norm_line)
            if "2nd half" in combined or second_half:
                return OU(event, ["90"], direction, norm_line)
            if "home" not in market and "away" not in market:
                return OU(event, ["18"], direction, norm_line)
            return None  # ambiguous, don't guess

        # --- Corners / bookings 1X2 ---
        if "corner" in combined and ("1x2" in combined or "most corners" in combined
                                     or outcome in ("home", "draw", "away")):
            mids = ["173"] if half else ["162"]
            cap = outcome.capitalize()
            if cap in ("Home", "Draw", "Away"):
                return R(event, mids, cap)
        if ("booking" in combined or "card" in combined) and "1x2" in combined:
            mids = ["149"] if half else ["136"]
            cap = outcome.capitalize()
            if cap in ("Home", "Draw", "Away"):
                return R(event, mids, cap)

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
