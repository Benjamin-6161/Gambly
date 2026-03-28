import os
import requests
from datetime import datetime

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

today = datetime.now()
formatted_date = today.strftime("%d %B, %Y")

def send_telegram_message(message: str, from_ai=True) -> str: 

  url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

  final_message = f"🚨Predictions for {formatted_date}\n\n{message}"
  
  if not from_ai:
    final_message = f"⚽Results for Yesterday's Matches\n\n{message}"
    
  payload = {
      "chat_id": CHAT_ID,
      "text": final_message
    }
    
  try:
    response = requests.post(url, json=payload)
    return "Message Sent successfully"
  except:
    print(f"Telegram message failed with error {response.body}")
    return "Message not sent successfully. Please try again"
    

