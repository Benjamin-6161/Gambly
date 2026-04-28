import os
from dotenv import load_dotenv
from datetime import datetime
import time
import json
from resources.apify_client import ApifyClient  
from helpers.db import save_matches

load_dotenv()

apify_key = os.environ.get('APIFY_KEY')

apify = ApifyClient(apify_key)

def fetch_matches(*args, **kwargs):
  """Fetch all matches for today"""

  if not apify_key:
    raise ValueError("APIFY_KEY is not set")

  leagues  = {
      "ENGLAND", 
      "SPAIN", 
      "ITALY", 
      "FRANCE", 
      "GERMANY", 
      "EUROPE"
      }
  competitions = {
      "PREMIER LEAGUE", 
      "LIGUE 1", 
      "BUNDESLIGA", 
      "SERIE A", 
      "LALIGA", 
      "FA CUP",
      "CHAMPIONS LEAGUE - PLAY OFFS",
      "EUROPA LEAGUE - PLAY OFFS",
      "CHAMPIONS LEAGUE - QUARTER FINALS",
      "EUROPA LEAGUE - QUARTER FINALS",
      "CHAMPIONS LEAGUE - SEMI FINALS",
      "EUROPA LEAGUE - SEMI FINALS",
      "CHAMPIONS LEAGUE - FINALS", 
      "EUROPA LEAGUE - FINALS",
      "WORLD CUP - QUALIFICATION - PROMOTION",
      "UEFA NATIONS LEAGUE - LEAGUE C/D - RELEGATION"
      }

  today = datetime.now().strftime("%Y-%m-%d")
  actor = "dataizi-srl~flashscore-data-extractor"

  apify_input = {
    "endpoint":"getMatches", 
    "sports":["football"],
    "dayOffsets":["0"],
    "matchStatuses":["scheduled"]
  }
  run = apify.start_actor_run(actor, apify_input)
  wait_for_completion(run["data"]["id"])

  dataset_id = run["data"]["defaultDatasetId"]
  dataset_info = apify.fetch_dataset_info(dataset_id)
  total_items =  dataset_info["data"]["itemCount"]
  target = min(total_items, 10000)
  m_offset = 0
  fetched = 0

  filtered_matches = []
  #Pagination logic
  while fetched < target:
    m_limit = min(100, target-fetched)
    matches = apify.fetch_dataset_items_paginated(dataset_id, m_offset, m_limit)

    try:
      matches = json.loads(matches)
    except json.JSONDecodeError:
      print("Failed to decode Apify response")
      break

    if not matches:
      break

    #Verify that the object returned by Apify is a list
    if not isinstance(matches, list):
      print("Incorrect data type returned from Apify")
      break
    print(f"First Match returned by Apify:\n{matches[0]}")
    #Only fetch matches from Europe top 5 leagues and European competitions

    for match in matches:
      home = match['home_team_name']
      away = match['away_team_name']
      category = match["category_name"].upper().strip()
      league = match["tournament_name"].upper().strip()
      date = match["match_date"]
      match_url = match["match_url"]
      match_id = match["match_id"]

      if not home or not away or not category or not league or not date or not match_url or not match_id:
        print("Incomplete details for a match")
        continue
      fixture = f"{home} vs {away}"
      #filter
      if  category not in leagues or league not in competitions:
        continue

      details = {
        "fixture":fixture,
        "category":category,
        "league":league,
        "date":date,
        "match_url":match_url,
        "match_id":match_id
      }
      filtered_matches.append(details)

    fetched += len(matches)
    m_offset += m_limit

  if not filtered_matches:
      #return matches[0:11]
      return "No Available Matches"
  save_matches(filtered_matches)
  return filtered_matches









def wait_for_completion(run_id: str):
    print("[Apify] Wait for completion hit")

    start = time.time()
    timeout = 10 * 60  # 10 minutes

    while (time.time() - start) < timeout:

        response = apify.get_run_status(run_id)
        status = response.get("data", {}).get("status")

        print(f"[Apify] Actor status: {status}")

        if status == "SUCCEEDED":
            return

        if status in ("FAILED", "ABORTED"):
            raise RuntimeError("Apify matches scrape failed")

        try:
            time.sleep(5)  # 5 seconds
        except KeyboardInterrupt:
            raise RuntimeError("Waiting interrupted")
    raise RuntimeError("Timeout while waiting for Apify run to complete")


if __name__ == "__main__":
    fetch_matches()