import requests
import re
import json

def fetch_match_overview(arg):
  """Fetch Match Overview and Stats using match url"""

  if isinstance(arg, dict):
      url = arg.get("url")
  elif isinstance(arg, str):
      url = arg
  else:
      return "Incorrect arg type passed. Pass in a matcb url as a string or in a dictionary with the key 'query'"

  try:
      response = requests.get(url, timeout=20)
      response.raise_for_status()
  except requests.RequestException as e:
      print(f"[flashscore] Failed to fetch match overview for {url}: {e}")
      return "No relevant details found (network error - proceed without an overview for this match)"

  html = response.text

  # Regex to grab the content of "eventPreview"
  match = re.search(r'"eventPreview"\s*:\s*({.*?})\s*,\s*"', html, re.DOTALL)
  if match:
      try:
          json_str = match.group(1)

          # Clean it up to be proper JSON
          json_str = json_str.replace('\\V', '')  # remove weird escape sequences
          json_str = json_str.replace('\xa0', ' ')  # non-breaking spaces
          json_str = re.sub(r'\[\\?p\]', '', json_str)  # remove [\p] markers etc.

          data = json.loads(json_str)
          content = data.get("contentParsed", "")
          plain_text = re.sub(r'\[.*?\]', '', content)  # removes all [p], [b], [a href=...] etc.
          plain_text = plain_text.replace('\n', ' ').strip()
          return plain_text
      except (json.JSONDecodeError, AttributeError) as e:
          print(f"[flashscore] Failed to parse match overview for {url}: {e}")
          return "No relevant details found (couldn't parse the page - proceed without an overview for this match)"
  else:
      return "No relevant details found"