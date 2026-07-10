def generate_ticket_message(predictions, booking_result=None, bookie_site="sportybet.com"):
    """
    Build a Telegram-friendly summary of today's selections. If
    `booking_result` (from tools.book_ticket.book_parlay) is provided and
    produced a code, it's included up top - along with a direct share
    link that loads the whole parlay on SportyBet in one tap. Any legs
    that couldn't be auto-booked are called out separately so they aren't
    silently missing from the slip.

    predictions: list of dicts with keys: fixture, market, predicted_outcome,
    reasoning (optional), whispers_opinion (optional)
    """
    if not predictions:
        return "No High priority matches available today😓."

    lines = [f"🎟️ Today's Parlay Ticket ({len(predictions)} legs)"]

    if booking_result and booking_result.get("booking_code"):
        lines.append(f"Booking code ({bookie_site}): {booking_result['booking_code']}")
        if booking_result.get("share_url"):
            lines.append(f"Load it directly: {booking_result['share_url']}")
    else:
        lines.append(f"Book manually on {bookie_site} - no code was generated for this run.")

    unbooked_fixtures = set()
    if booking_result:
        unbooked_fixtures = {p.get("fixture") for p in booking_result.get("unbooked", [])}

    lines.append("")
    for i, p in enumerate(predictions, start=1):
        flag = " (add manually - not in the code above)" if p.get("fixture") in unbooked_fixtures else ""
        lines.append(f"{i}. {p['fixture']} — {p['market']}: {p['predicted_outcome']}{flag}")
        if p.get("reasoning"):
            lines.append(f"   ↳ {p['reasoning']}")
        if p.get("whispers_opinion"):
            lines.append(f"   ↳ Whispers: {p['whispers_opinion']}")

    return "\n".join(lines)