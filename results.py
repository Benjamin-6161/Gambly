from tools.send_telegram_message import send_telegram_message
from helpers.db import get_predictions_awaiting_results, save_result
from helpers.fetch_match_results import get_match_details
from helpers.generate_message import generate_results_message

matches = get_predictions_awaiting_results()
results = []

for match in matches:
    match_id = match.get('match_id')
    fixture = match.get('fixture')

    try:
        details = get_match_details(match_id)
    except Exception as e:
        print(f"[results] Failed to fetch details for {fixture} ({match_id}): {e}")
        details = {}

    if not details.get("ft_score"):
        print(f"[results] {fixture} not finished yet, skipping for now")
        continue

    save_result(match_id, fixture, details)

    results.append({
        "match": fixture,
        "details": details,
    })

print(results)
message = generate_results_message(results)
send_telegram_message(message, False)