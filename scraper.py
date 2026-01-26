"""
Scraper Template
================
Simple template for building scrapers with GCS upload.
Replace the example scraping logic with your own.
"""
import os
import json
import re
import requests
import pandas as pd
import time
import random
from datetime import datetime
from typing import Any, Dict
from fake_useragent import UserAgent
from dlg import send_slack_notification, save_to_gcs

# === CONFIG (auto-set by CI/CD from repo name) ===
PLATFORM_ID = os.environ.get("PLATFORM_ID", "imbt")

# === IMBT CONFIG ===
BASE_URL = "https://itmustbetime.com"
COLLECTION_URL = f"{BASE_URL}/products.json"
PAGE_LIMIT = 250  # Max 250 per page as per API

EXCLUDE_KEYWORDS = tuple(
    kw.strip().lower()
    for kw in os.environ.get(
        "EXCLUDE_KEYWORDS",
        "band,bracelet,accessory,accessories,case,bag,william henry",
    ).split(",")
    if kw.strip()
)

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

def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()

def _is_watch_product(product: Dict[str, Any]) -> bool:
    title = (product.get("title") or "").lower()
    product_type = (product.get("product_type") or "").lower()
    tags = " ".join(t.lower() for t in product.get("tags") or [])
    vendor = (product.get("vendor") or "").lower()

    # Exclude accessory-only items
    haystack = f"{title} {product_type} {tags} {vendor}"
    if any(kw in haystack for kw in EXCLUDE_KEYWORDS):
        return False

    return True

def map_product_to_parsed_row(product: Dict[str, Any], extraction_date: str) -> Dict[str, Any]:
    handle = (product.get("handle") or "").strip()
    product_url = f"{BASE_URL}/products/{handle}" if handle else ""
    product_id = str(product.get("id") or "")
    product_name = (product.get("title") or "").strip()
    brand = (product.get("vendor") or "").strip()

    variants = product.get("variants") or []
    any_available = any(bool(v.get("available")) for v in variants) if variants else bool(product.get("available"))
    availability = "in stock" if any_available else "out of stock"

    # Pricing: uses compare_at_price to show "full price" (higher) vs discounted.
    price = ""
    full_price = ""
    if variants:
        # We only look at the first variant for pricing as all the products contains only 1 variant
        v0 = variants[0]
        p0 = v0.get("price")
        c0 = v0.get("compare_at_price")
        price = str(p0).strip() if p0 is not None else ""
        full_price = str(c0).strip() if c0 is not None else ""
        # If no discount, keep full_price empty
        if full_price and price and full_price == price:
            full_price = ""

    # Images
    images = product.get("images") or []
    main_image = images[0].get("src") if images else ""
    secondary_images = [img.get("src") for img in images[1:] if img.get("src")]

    reference_number = variants[0].get("sku") if variants else ""
    description = _strip_html(product.get("body_html") or "")

    # Seller: platform-sold store (no individual sellers)
    seller_name = "It Must Be Time"
    seller_id = PLATFORM_ID
    seller_url = BASE_URL

    # Collect extra specs in JSON bucket
    product_specifications = {
        "tags": product.get("tags") or [],
        "product_type": product.get("product_type") or "",
    }

    return {
        # --- Basic fields ---
        "platform_id": PLATFORM_ID,
        "product_id": product_id,
        "product_name": product_name,
        "description": description,
        "product_url": product_url,
        "availability": availability,
        "brand": brand,
        "extraction_date": extraction_date,
        "main_image": main_image,
        "secondary_images": json.dumps(secondary_images, ensure_ascii=False) if secondary_images else "",
        "item_location_country": "",

        # --- Seller ---
        "seller_name": seller_name,
        "seller_id": seller_id,
        "seller_url": seller_url,

        # --- Prices ---
        "price": price,
        "full_price": full_price,
        "tax_free_price": "",
        "tax_full_price": "",

        # --- Specs / IDs ---
        "reference_number": reference_number,
        "collection": (product.get("product_type") or "").strip(),
        "case_material": "",
        "bracelet_material": "",
        "bezel_material": "",
        "caliber_size": "",
        "case_diameter": "",
        "dial_color": "",
        "water_resistance": "",
        "year_of_production": "",
        "number_of_jewels": "",
        "complication": "",

        # --- Condition / delivery ---
        "condition_detail": "",
        "scope_of_delivery": "",

        # --- Text fields ---
        "detail_of_the_exceptional_piece": "",

        # --- JSON bucket per parsing rules ---
        "product_specifications": json.dumps(product_specifications, ensure_ascii=False),
    }

# =============================================================================
# SCRAPING LOGIC (IMBT - Watch collection JSON)
# =============================================================================
def fetch_page(url, page=1, delay_range=(0.2, 0.5)):
    """
    Fetch a single page of products for the collection URL.
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            params={"limit": PAGE_LIMIT, "page": page},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        page_products = data.get("products") or []
        total_pages = page if len(page_products) < PAGE_LIMIT else page + 1
        return {"items": page_products, "total_pages": total_pages}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page {page}: {e}")
        return None
    finally:
        time.sleep(random.uniform(*delay_range))


def fetch_all_data(base_url, delay_range=(0.2, 0.5)):
    """
    Fetch all pages from the given collection URL and map to parsed rows.
    """
    all_items = []
    raw_items = []
    page = 1
    extraction_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    while True:
        print(f"Fetching page {page}...")
        data = fetch_page(base_url, page=page, delay_range=delay_range)

        if not data or not data.get("items"):
            break

        for p in data["items"]:
            if not _is_watch_product(p):
                continue
            all_items.append(map_product_to_parsed_row(p, extraction_date))
            # Raw data
            handle = (p.get("handle") or "").strip()
            raw_items.append({
                "platform_id": PLATFORM_ID,
                "extraction_date": extraction_date,
                "product_id": str(p.get("id") or ""),
                "product_url": f"{BASE_URL}/products/{handle}" if handle else "",
                "raw_json": json.dumps(p, ensure_ascii=False),
            })

        if page >= data.get("total_pages", 1):
            break

        page += 1

    return pd.DataFrame(raw_items), pd.DataFrame(all_items)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def run_scraper(delay_range=(0.2, 0.5)):
    """Main scraper logic - returns dict with status code and message"""

    try:
        # As per README **Two CSV outputs** - raw (all fields) + parsed (schema-compliant)
        raw_df, parsed_df = fetch_all_data(
            COLLECTION_URL,
            delay_range=delay_range,
        )

        if parsed_df.empty:
            result = {"status": 204, "message": "No data found", "rows": 0}
            print(f"Response: {result}")
            return result

        raw_local_file = "/tmp/raw.csv"
        parsed_local_file = "/tmp/parsed.csv"
        raw_df.to_csv(raw_local_file, index=False)
        parsed_df.to_csv(parsed_local_file, index=False)

        raw_gcs_path = save_to_gcs(raw_local_file, prefix="raw")
        parsed_gcs_path = save_to_gcs(parsed_local_file)

        result = {
            "status": 200,
            "message": "Success",
            "rows": len(parsed_df),
            "columns": len(parsed_df.columns),
            "raw_gcs_path": raw_gcs_path,
            "gcs_path": parsed_gcs_path,
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
