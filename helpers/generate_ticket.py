import re


def _shorten_whispers(text: str, max_len: int = 80) -> str:
    """Keep just the headline tip, not a full paragraph. Prefers cutting
    at the first sentence boundary within max_len; falls back to a clean
    word-boundary truncation."""
    text = text.strip()
    if not text:
        return text

    m = re.match(r"^.{1,%d}?[.!?](?=\s|$)" % max_len, text)
    if m:
        return m.group(0).strip()

    if len(text) <= max_len:
        return text

    return text[:max_len].rsplit(" ", 1)[0].strip() + "…"


def generate_ticket_message(predictions, booking_result=None, bookie_site="sportybet.com"):
    """
    Build a Telegram-friendly (Markdown) summary of today's selections.
    Each leg shows a checkmark if it made it into the SportyBet booking
    code, or an X if it needs to be added manually. Reasoning is
    intentionally omitted here - it's still saved to the db via
    save_prediction for the feedback loop, just not shown in the message.

    predictions: list of dicts with keys: fixture, market, predicted_outcome,
    whispers_opinion (optional). reasoning is accepted but not displayed.
    """
    if not predictions:
        return "No High priority matches available today😓."

    n = len(predictions)
    lines = [f"🎟️ *Today's Parlay Ticket* ({n} game{'s' if n != 1 else ''})"]

    if booking_result and booking_result.get("booking_code"):
        lines.append(f"Code: `{booking_result['booking_code']}`")
    else:
        lines.append(f"Code: not generated - book manually on {bookie_site}")

    lines.append("")

    unbooked_fixtures = set()
    if booking_result:
        unbooked_fixtures = {p.get("fixture") for p in booking_result.get("unbooked", [])}

    for p in predictions:
        in_code = p.get("fixture") not in unbooked_fixtures
        check = "✅" if in_code else "❌"

        lines.append(f"• *{p['fixture']}*")
        lines.append(f"Prediction: {p['predicted_outcome']} {check}")
        if p.get("whispers_opinion"):
            lines.append(f"Whispers: {_shorten_whispers(p['whispers_opinion'])}")
        lines.append("")

    return "\n".join(lines).rstrip()