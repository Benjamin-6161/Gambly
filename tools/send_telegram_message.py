import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

today = datetime.now()
formatted_date = today.strftime("%d %B, %Y")

def send_telegram_message(message: str, from_ai=True) -> str:

  if not BOT_TOKEN or not CHAT_ID:
    print("[Telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set")
    return "Message not sent - missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"

  url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

  final_message = f"🚨 *Predictions for {formatted_date}*\n\n{message}"

  if not from_ai:
    final_message = f"⚽ *Results for Yesterday's Matches*\n\n{message}"

  payload = {
      "chat_id": CHAT_ID,
      "text": final_message,
      "parse_mode": "Markdown",
    }

  try:
    response = requests.post(url, json=payload, timeout=15)
    data = response.json()

    if not response.ok or not data.get("ok"):
      print(f"[Telegram] Rejected: HTTP {response.status_code} - {data}")
      return f"Message not sent - Telegram error: {data.get('description', 'unknown')}"

    return "Message Sent successfully"
  except Exception as e:
    print(f"Telegram message failed with error {e}")
    return "Message not sent successfully. Please try again"