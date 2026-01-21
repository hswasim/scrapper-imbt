"""
Scraper Template
================
Simple template for building scrapers with GCS upload.
Replace the example scraping logic with your own.
"""
import os
import json
import requests
import pandas as pd
import time
import random
from datetime import datetime
from fake_useragent import UserAgent
from dlg import send_slack_notification, save_to_gcs

# === CONFIG (auto-set by CI/CD from repo name) ===
PLATFORM_ID = os.environ.get("PLATFORM_ID", "example")

# === SETUP ===
ua = UserAgent(platforms='desktop')
HEADERS = {
    "user-agent": ua.random,
    "accept": "application/json",
}
print(f"Using User-Agent: {HEADERS['user-agent']}")


def notify_error(error_type: str, detail: str, status_code: int):
    """Send Slack notification for errors"""
    send_slack_notification(
        message=f"Scraper failed: {error_type}",
        status="error",
        details={
            "Platform": PLATFORM_ID,
            "Status": status_code,
            "Error": detail[:500]
        }
    )


# =============================================================================
# SCRAPING LOGIC (replace with your own)
# =============================================================================
def fetch_page(url, page=1, delay_range=(0.2, 0.5)):
    """
    Example: Fetch a single page of results
    Replace with your actual API/scraping logic
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params={"page": page},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page {page}: {e}")
        return None
    finally:
        time.sleep(random.uniform(*delay_range))


def fetch_all_data(base_url, delay_range=(0.2, 0.5)):
    """
    Example: Fetch all pages
    Replace with your actual pagination logic
    """
    all_items = []
    page = 1

    while True:
        print(f"Fetching page {page}...")
        data = fetch_page(base_url, page=page, delay_range=delay_range)

        if not data or not data.get("items"):
            break

        all_items.extend(data["items"])

        if page >= data.get("total_pages", 1):
            break

        page += 1

    return pd.DataFrame(all_items)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def run_scraper(delay_range=(0.2, 0.5)):
    """Main scraper logic - returns dict with status code and message"""

    try:
        # === REPLACE THIS WITH YOUR SCRAPING LOGIC ===
        # Example: df = fetch_all_data("https://api.example.com/items", delay_range)

        # Placeholder - remove and add your logic
        print("TODO: Add your scraping logic here")
        df = pd.DataFrame({"example": ["replace", "with", "real", "data"]})
        # === END REPLACE ===

        if df.empty:
            result = {"status": 204, "message": "No data found", "rows": 0}
            print(f"Response: {result}")
            return result

        # Save to /tmp then upload to GCS
        local_file = "/tmp/data.csv"
        df.to_csv(local_file, index=False)
        gcs_path = save_to_gcs(local_file)

        result = {
            "status": 200,
            "message": "Success",
            "rows": len(df),
            "columns": len(df.columns),
            "gcs_path": gcs_path
        }
        print(f"Response: {result}")
        return result

    except requests.exceptions.Timeout as e:
        result = {"status": 504, "error": "Gateway Timeout", "detail": str(e)}
        print(f"Response: {result}")
        notify_error("Gateway Timeout", str(e), 504)
        return result

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 500
        result = {"status": status_code, "error": "HTTP Error", "detail": str(e)}
        print(f"Response: {result}")
        notify_error("HTTP Error", str(e), status_code)
        return result

    except requests.exceptions.ConnectionError as e:
        result = {"status": 503, "error": "Service Unavailable", "detail": str(e)}
        print(f"Response: {result}")
        notify_error("Service Unavailable", str(e), 503)
        return result

    except json.JSONDecodeError as e:
        result = {"status": 502, "error": "Bad Gateway - Invalid JSON", "detail": str(e)}
        print(f"Response: {result}")
        notify_error("Bad Gateway - Invalid JSON", str(e), 502)
        return result

    except Exception as e:
        result = {"status": 500, "error": "Internal Server Error", "detail": str(e)}
        print(f"Response: {result}")
        notify_error("Internal Server Error", str(e), 500)
        return result


if __name__ == "__main__":
    run_scraper(delay_range=(0.2, 0.5))
