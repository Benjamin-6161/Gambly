def generate_message(items):
    """Simple fixture/scoreline formatter, kept for backwards compatibility."""
    message_lines = []
    for i in items:
        line = f"*{i.get('match')}*\n{i.get('scoreline')}"
        message_lines.append(line)
    return "\n\n".join(message_lines)


def generate_results_message(items, pending=0):
    """Detailed results formatter: FT/HT score, corners, cards, shots and
    shots on target for both teams, per match.

    items: list of {"match": str, "details": dict} where details comes from
    helpers.fetch_match_results.get_match_details
    pending: number of predicted matches not finished yet (reported in the
    header so an empty finished-list is still informative instead of
    looking like a silent failure).
    """
    header = ""
    if pending:
        header = (f"_{pending} other predicted match{'es' if pending != 1 else ''} "
                  f"not finished yet._\n\n")

    if not items:
        if pending:
            return header + "No finished results to report yet - check back tomorrow."
        return "No results to report today."

    blocks = []
    for item in items:
        d = item.get("details") or {}
        fixture = item.get("match", "Unknown fixture")

        lines = [f"⚽ *{fixture}*"]

        ft = d.get("ft_score") or "unavailable"
        ht_suffix = f" (HT: {d.get('ht_score')})" if d.get("ht_score") else ""
        lines.append(f"FT: {ft}{ht_suffix}")

        stat_bits = []
        if d.get("home_corners") is not None:
            stat_bits.append(f"Corners: {d['home_corners']}-{d['away_corners']}")
        if d.get("home_cards") is not None:
            stat_bits.append(f"Cards: {d['home_cards']}-{d['away_cards']}")
        if stat_bits:
            lines.append(" | ".join(stat_bits))

        if d.get("home_shots") is not None:
            shots_line = f"Shots: {d['home_shots']}-{d['away_shots']}"
            if d.get("home_sot") is not None:
                shots_line += f" (on target {d['home_sot']}-{d['away_sot']})"
            lines.append(shots_line)

        blocks.append("\n".join(lines))

    return header + "\n\n".join(blocks)