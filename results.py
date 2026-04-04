import requests
from tools.send_telegram_message import send_telegram_message
from helpers.db import get_matches
from helpers.fetch_match_results import get_match_score
from helpers.generate_message import generate_message

matches = get_matches()
results = []

for match in matches:
  url = match.get('match_url')
  scoreline = get_match_score(url)
  
  results.append({
    "match":match.get('fixture'),
    "scoreline":scoreline
  })

print(results)
message = generate_message(results)
send_telegram_message(message, False)