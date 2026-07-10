from tools.sportybet_client import SportyBetSession


def book_parlay(predictions):
    sb = SportyBetSession()
    booked, unbooked = [], []
    selections = []

    for pred in predictions:
        home, away = pred["home_team"], pred["away_team"]
        market_text = pred.get("market", "").strip()
        outcome_text = pred["predicted_outcome"].strip()
        outcome = outcome_text.lower()

        event = sb.find_event(home, away)
        if not event:
            unbooked.append(pred)
            continue
        print(f"[SportyBet] find_event OK for {home} vs {away} -> {event['eventId']}")

        selection = None
        if outcome == "draw":
            selection = sb.resolve_home_draw_away(event, "draw")
        elif "home win" in outcome:
            selection = sb.resolve_home_draw_away(event, "home")
        elif "away win" in outcome:
            selection = sb.resolve_home_draw_away(event, "away")

        if not selection:
            # Combine market + predicted_outcome so a bare "No"/"Yes" or
            # "Over 2.5" still carries its market context (confirmed
            # failing without this: predicted_outcome alone was sometimes
            # just "No", with "Both Teams To Score" only present in the
            # separate market field, which resolve_known_market never saw).
        if not selection:
          selection = sb.resolve_known_market(event, market_text, outcome_text)

        if selection:
            print(f"[SportyBet] resolved '{outcome_text}' -> {selection}")
            selections.append(selection)
            booked.append(pred)
        else:
            print(f"[SportyBet] could NOT resolve '{outcome_text}' (market: '{market_text}') for {home} vs {away}")
            unbooked.append(pred)

    booking_code, share_url = None, None
    if selections:
        try:
            result = sb.get_booking_code(selections)
            if result:
                booking_code = result.get("share_code")
                share_url = result.get("share_url")
            else:
                print("[SportyBet] get_booking_code returned no result")
        except Exception as e:
            print(f"[SportyBet] get_booking_code raised: {e}")

    return {
        "booking_code": booking_code,
        "share_url": share_url,
        "booked": booked,
        "unbooked": unbooked,
    }