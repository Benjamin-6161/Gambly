import sqlite3
import os
import re
from datetime import datetime, timezone


def get_db_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "../resources/db/matches.db")
    db_path = os.path.abspath(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path


def _connect():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    """Create all tables if they don't already exist. Safe to call repeatedly."""
    conn = _connect()
    cur = conn.cursor()

    # Today's queue of matches - wiped and repopulated on every run of
    # daily_parlay.yml. This table is intentionally NOT a history store.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture TEXT,
        category TEXT,
        league TEXT,
        date TEXT,
        match_url TEXT,
        match_id TEXT
    )
    """)

    # Every prediction the agent has ever made. Append-only - this is the
    # memory the feedback loop reads from.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        fixture TEXT,
        category TEXT,
        league TEXT,
        market TEXT,
        predicted_outcome TEXT,
        reasoning TEXT,
        whispers_opinion TEXT,
        created_at TEXT
    )
    """)

    # Every result the results workflow has ever fetched. Append-only.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT,
        fixture TEXT,
        ht_score TEXT,
        ft_score TEXT,
        home_corners INTEGER,
        away_corners INTEGER,
        home_cards INTEGER,
        away_cards INTEGER,
        home_shots INTEGER,
        away_shots INTEGER,
        home_sot INTEGER,
        away_sot INTEGER,
        graded_correct INTEGER,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Daily matches queue (unchanged behaviour from the original implementation)
# ---------------------------------------------------------------------------

def save_matches(matches):
    init_db()
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM matches")
    conn.commit()

    for item in matches:
        cursor.execute("""
        INSERT INTO matches (fixture, category, league, date, match_url, match_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (item["fixture"], item["category"], item["league"], item["date"],
              item["match_url"], item["match_id"]))

    conn.commit()
    conn.close()


def get_matches():
    init_db()
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Predictions (persistent)
# ---------------------------------------------------------------------------

def save_prediction(pred: dict):
    """pred keys: match_id, fixture, category, league, market,
    predicted_outcome, reasoning, whispers_opinion (optional)"""
    init_db()
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO predictions
        (match_id, fixture, category, league, market, predicted_outcome,
         reasoning, whispers_opinion, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pred.get("match_id"), pred.get("fixture"), pred.get("category"),
        pred.get("league"), pred.get("market"), pred.get("predicted_outcome"),
        pred.get("reasoning"), pred.get("whispers_opinion", ""), _now()
    ))
    conn.commit()
    conn.close()


def get_latest_prediction(match_id: str):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM predictions WHERE match_id = ?
        ORDER BY id DESC LIMIT 1
    """, (match_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
    
def get_predictions_awaiting_results(since_days: int = 14):
    """Every (match_id, fixture) that has a prediction but no result row
    yet - this is what results.py should scrape, instead of relying on
    the `matches` table, which now gets wiped every 3 days by the predict
    run and can no longer be trusted to still contain a match by the time
    its result is ready to fetch. Bounded to recent predictions so a
    postponed/abandoned match doesn't get retried forever."""
    init_db()
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT p.match_id, p.fixture
        FROM predictions p
        LEFT JOIN results r ON p.match_id = r.match_id
        WHERE r.id IS NULL
          AND p.created_at >= datetime('now', ?)
    """, (f"-{since_days} days",))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Grading - best-effort correctness check for common market types. Anything
# we can't confidently grade is left as NULL (ungraded) rather than guessed.
# ---------------------------------------------------------------------------

def grade_prediction(predicted_outcome: str, ft_score: str):
    if not predicted_outcome or not ft_score:
        return None

    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", ft_score)
    if not m:
        return None
    home, away = int(m.group(1)), int(m.group(2))
    total = home + away
    pred = predicted_outcome.strip().lower()

    if "home win" in pred:
        return int(home > away)
    if "away win" in pred:
        return int(home < away)
    if pred == "draw" or pred.endswith(" draw"):
        return int(home == away)
    if "win or draw" in pred:
        if pred.startswith("home"):
            return int(home >= away)
        if pred.startswith("away"):
            return int(away >= home)

    over_under = re.search(r"(over|under)\s*(\d+(\.\d+)?)\s*goals", pred)
    if over_under:
        direction, threshold = over_under.group(1), float(over_under.group(2))
        return int(total > threshold) if direction == "over" else int(total < threshold)

    if "both teams to score" in pred or "btts" in pred:
        both_scored = home > 0 and away > 0
        if "yes" in pred:
            return int(both_scored)
        if "no" in pred:
            return int(not both_scored)

    if "draw no bet" in pred or re.search(r"\bdnb\b", pred):
        if home == away:
            return None  # stake refunded - neither correct nor incorrect
        if pred.startswith("home"):
            return int(home > away)
        if pred.startswith("away"):
            return int(home < away)

    if re.search(r"\bodd\b", pred) or re.search(r"\beven\b", pred):
        if "home" in pred and "team" in pred:
            n = home
        elif "away" in pred and "team" in pred:
            n = away
        else:
            n = total
        # the pick is whichever word comes last ('Odd' / 'Even'); a bare
        # 'Odd' or 'Even' outcome counts as that pick
        has_odd = bool(re.search(r"\bodd\b", pred))
        has_even = bool(re.search(r"\beven\b", pred))
        pick_odd = has_odd and (not has_even or pred.rfind("odd") > pred.rfind("even"))
        return int((n % 2 == 1) == pick_odd)

    if "clean sheet" in pred:
        if "home" in pred:
            cs = away == 0
        elif "away" in pred:
            cs = home == 0
        else:
            return None
        if "yes" in pred:
            return int(cs)
        if "no" in pred:
            return int(not cs)

    if "win to nil" in pred:
        if "home" in pred:
            hit = home > away and away == 0
        elif "away" in pred:
            hit = away > home and home == 0
        else:
            return None
        if "yes" in pred:
            return int(hit)
        if "no" in pred:
            return int(not hit)

    only_home = ("only home" in pred)
    only_away = ("only away" in pred)
    if only_home or only_away or "neither" in pred or "none" in pred:
        if only_home:
            return int(home > 0 and away == 0)
        if only_away:
            return int(away > 0 and home == 0)
        return int(home == 0 and away == 0)

    exact_goals = re.search(r"(?:exact(?:ly)?\s*)?(\d+)\s*goals?\s*$", pred)
    if exact_goals and "over" not in pred and "under" not in pred:
        return int(total == int(exact_goals.group(1)))

    score_match = re.search(r"(\d+)\s*-\s*(\d+)", pred)
    if score_match:
        return int(int(score_match.group(1)) == home and int(score_match.group(2)) == away)

    return None


def save_result(match_id: str, fixture: str, details: dict):
    """details: ht_score, ft_score, home_corners, away_corners, home_cards,
    away_cards, home_shots, away_shots, home_sot, away_sot"""
    init_db()

    graded = None
    prediction = get_latest_prediction(match_id)
    if prediction:
        graded = grade_prediction(prediction.get("predicted_outcome"), details.get("ft_score"))

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO results
        (match_id, fixture, ht_score, ft_score, home_corners, away_corners,
         home_cards, away_cards, home_shots, away_shots, home_sot, away_sot,
         graded_correct, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        match_id, fixture, details.get("ht_score"), details.get("ft_score"),
        details.get("home_corners"), details.get("away_corners"),
        details.get("home_cards"), details.get("away_cards"),
        details.get("home_shots"), details.get("away_shots"),
        details.get("home_sot"), details.get("away_sot"),
        graded, _now()
    ))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Feedback loop: give the agent a compact summary of past performance
# ---------------------------------------------------------------------------

def get_history_context(limit: int = 30) -> str:
    """Returns a plain-text summary of recent predictions vs results plus
    accuracy-by-market, suitable for dropping straight into an LLM prompt."""
    init_db()
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT p.fixture, p.market, p.predicted_outcome, r.ft_score, r.graded_correct
        FROM predictions p
        JOIN results r ON p.match_id = r.match_id
        ORDER BY r.id DESC
        LIMIT ?
    """, (limit,))
    recent = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT p.market,
               SUM(CASE WHEN r.graded_correct = 1 THEN 1 ELSE 0 END) as correct,
               COUNT(r.graded_correct) as graded_total
        FROM predictions p
        JOIN results r ON p.match_id = r.match_id
        WHERE r.graded_correct IS NOT NULL
        GROUP BY p.market
    """)
    accuracy_rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not recent and not accuracy_rows:
        return "No prediction history yet - this is effectively a cold start."

    lines = ["Accuracy by market (graded predictions only):"]
    for row in accuracy_rows:
        total = row["graded_total"] or 0
        correct = row["correct"] or 0
        pct = (correct / total * 100) if total else 0
        lines.append(f"- {row['market']}: {correct}/{total} correct ({pct:.0f}%)")

    lines.append("\nMost recent graded predictions:")
    for row in recent:
        outcome = "✅" if row["graded_correct"] == 1 else ("❌" if row["graded_correct"] == 0 else "?")
        lines.append(f"- {row['fixture']}: predicted '{row['predicted_outcome']}' "
                      f"({row['market']}), actual {row['ft_score']} {outcome}")

    return "\n".join(lines)
