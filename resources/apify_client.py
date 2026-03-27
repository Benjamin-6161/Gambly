import requests
import json


class ApifyClient:
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.session = requests.Session()

    def start_actor_run(self, actor_id: str, input_data: dict) -> dict:
        print("[ApifyClient] Starting actor run")

        url = f"{self.BASE_URL}/acts/{actor_id}/runs"
        params = {"token": self.api_token}

        try:
            body = json.dumps(input_data)
        except Exception as e:
            raise RuntimeError("Failed to serialize Apify input") from e

        #print(f"Using actor id: {actor_id}")
        #print(f"Apify input: {body}")

        try:
            response = self.session.post(
                url,
                params=params,
                data=body,
                headers={"Content-Type": "application/json"},
            )

            response_body = response.text

            if not response.ok:
                print(f"[Apify] Apify call failed with response: {response_body} and code: {response.status_code}")
                raise RuntimeError(f"Failed to start Apify actor {response_body}")

            #print(f"[Apify] Scraper successfully started with response: {response_body}")
            return response.json()

        except requests.RequestException as e:
            raise RuntimeError("Apify actor start failed") from e

    def get_run_status(self, run_id: str) -> dict:
        #print("[ApifyClient] Get run status method hit")

        url = f"{self.BASE_URL}/actor-runs/{run_id}"
        params = {"token": self.api_token}

        try:
            response = self.session.get(url, params=params)
            response_body = response.text

            if not response.ok:
                print(f"[Apify] Apify status call failed with response: {response_body}")
                raise RuntimeError("Failed to get run status")

            return response.json()

        except requests.RequestException as e:
            raise RuntimeError("Failed to fetch Apify run status") from e

    def fetch_dataset_items(self, dataset_id: str) -> str:
        #print("[ApifyClient] Fetch dataset items hit")

        url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        params = {"token": self.api_token}

        try:
            response = self.session.get(url, params=params)
            response_body = response.text

            if not response.ok:
                print(f"[Apify] Apify dataset fetch failed with response: {response_body}")
                raise RuntimeError("Failed to fetch Apify dataset")

            print("[ApifyClient] Fetched dataset items successfully")
            return response_body

        except requests.RequestException as e:
            raise RuntimeError("Failed to fetch Apify dataset") from e

    def fetch_dataset_info(self, dataset_id: str) -> dict:
        #print(f"[ApifyClient] Fetch dataset info hit with id: {dataset_id}")

        url = f"{self.BASE_URL}/datasets/{dataset_id}"
        params = {"token": self.api_token}

        try:
            response = self.session.get(url, params=params)
            response_body = response.text

            if not response.ok:
                print(f"[Apify] Dataset info fetch failed with response: {response_body}")
                raise RuntimeError("Failed to fetch Apify dataset info")

            return response.json()

        except requests.RequestException as e:
            raise RuntimeError("Failed to fetch Apify dataset info") from e

    def fetch_dataset_items_paginated(self, dataset_id: str, offset: int, limit: int) -> str:
        url = f"{self.BASE_URL}/datasets/{dataset_id}/items"
        params = {
            "token": self.api_token,
            "offset": offset,
            "limit": limit,
            "clean": "true",
            "format": "json",
        }

        try:
            response = self.session.get(url, params=params)
            response_body = response.text

            if not response.ok:
                print(f"[Apify] Paginated dataset fetch failed with response: {response_body}")
                raise RuntimeError("Failed to fetch Apify dataset page")

            return response_body

        except requests.RequestException as e:
            raise RuntimeError("Failed to fetch Apify dataset page") from e