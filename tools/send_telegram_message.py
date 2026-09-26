import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

today = datetime.now()
formatted_date = today.strftime("%d %B, %Y")

# Telegram caps a single message at 4096 characters - anything longer is
# rejected with HTTP 400 'message is too long' (seen live when the results
# job tried to send 45 finished matches at once). Stay safely under it.
MAX_CHUNK_LEN = 4000


def _split_message(text: str, limit: int = MAX_CHUNK_LEN):
    """Split on blank-line boundaries so no match block is torn in half.
    A single oversized block is hard-split as a last resort."""
    chunks, current = [], ""
    for block in text.split("\n\n"):
        piece = block if not current else current + "\n\n" + block
        if len(piece) <= limit:
            current = piece
        else:
            if current:
                chunks.append(current)
            if len(block) > limit:
                for i in range(0, len(block), limit):
                    chunks.append(block[i:i + limit])
                current = ""
            else:
                current = block
    if current:
        chunks.append(current)
    return chunks or [""]


def _send_chunk(url: str, text: str):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
      }
    response = requests.post(url, json=payload, timeout=15)
    return response


def send_telegram_message(message: str, from_ai=True) -> str:

  if not BOT_TOKEN or not CHAT_ID:
    print("[Telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set")
    return "Message not sent - missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"

  url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

  header = f"🚨 *Predictions for {formatted_date}*"

  if not from_ai:
    header = "⚽ *Results for Yesterday's Matches*"

  chunks = _split_message(message)
  total = len(chunks)

  try:
    for i, chunk in enumerate(chunks, 1):
      part = f" ({i}/{total})" if total > 1 else ""
      text = f"{header}{part}\n\n{chunk}" if i == 1 else f"{header} (cont. {i}/{total})\n\n{chunk}"
      response = _send_chunk(url, text)
      data = response.json()

      if not response.ok or not data.get("ok"):
        print(f"[Telegram] Rejected chunk {i}/{total}: HTTP {response.status_code} - {data}")
        return f"Message not sent - Telegram error: {data.get('description', 'unknown')}"

    return f"Message Sent successfully ({total} part{'s' if total != 1 else ''})"
  except Exception as e:
    print(f"Telegram message failed with error {e}")
    return "Message not sent successfully. Please try again"
