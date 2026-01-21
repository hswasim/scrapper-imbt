"""
DLG - Data, Logging, GCS utilities for scrapers.

Provides:
- save_to_gcs(): Upload local file to GCS with auto-naming
- send_slack_notification(): Send Slack alerts

Environment variables (auto-set by CI/CD):
- PLATFORM_ID: Auto-extracted from repo name (scraper-kaki → kaki)
- GCS_FOLDER: Same as PLATFORM_ID
- GCS_BUCKET: Default "market-place-dev"
- SLACK_WEBHOOK_URL: Set at GitLab Group level

Usage:
------
from dlg import save_to_gcs, send_slack_notification

# Save file to GCS (returns gcs_path)
df.to_csv("/tmp/data.csv", index=False)
gcs_path = save_to_gcs("/tmp/data.csv")                       # → kaki/kaki_20260114_143052.csv
gcs_path = save_to_gcs("/tmp/data.csv", prefix="raw")         # → kaki/raw_kaki_20260114_143052.csv
gcs_path = save_to_gcs("/tmp/data.json", extension="json")    # → kaki/kaki_20260114_143052.json

# Send Slack notification
send_slack_notification("Scraper failed", status="error", details={"Error": str(e)})
"""
import os
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from google.cloud import storage


# === CONFIG (auto-set by CI/CD from repo name) ===
PLATFORM_ID = os.environ.get("PLATFORM_ID", "example")
GCS_FOLDER = os.environ.get("GCS_FOLDER", "example")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "market-place-dev")


# =============================================================================
# GCS UPLOAD
# =============================================================================
def save_to_gcs(
    file_path: str,
    prefix: Optional[str] = None,
    extension: str = "csv",
    save_latest: bool = True
) -> str:
    """
    Upload a local file to GCS with auto-generated filename.

    Args:
        file_path: Path to the local file to upload
        prefix: Optional prefix for filename (e.g., "raw" → raw_kaki_20260114.csv)
        extension: File extension (default: "csv")
        save_latest: Also save as {prefix_}latest.{ext} (default: True)

    Returns:
        str: GCS path of timestamped file (gs://bucket/folder/file.ext)

    Example:
        save_to_gcs("/tmp/data.csv")                        → kaki/kaki_20260114_143052.csv
        save_to_gcs("/tmp/data.csv", prefix="raw")          → kaki/raw_kaki_20260114_143052.csv
        save_to_gcs("/tmp/data.json", extension="json")     → kaki/kaki_20260114_143052.json
    """
    import os

    # Validate file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"Not a file: {file_path}")

    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Build filename with optional prefix
    if prefix:
        filename = f"{prefix}_{PLATFORM_ID}_{date_str}.{extension}"
        latest_filename = f"{prefix}_{PLATFORM_ID}_latest.{extension}"
    else:
        filename = f"{PLATFORM_ID}_{date_str}.{extension}"
        latest_filename = f"{PLATFORM_ID}_latest.{extension}"

    # GCS client
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    # Upload timestamped version
    gcs_path = f"{GCS_FOLDER}/{filename}"
    print(f"Uploading to gs://{GCS_BUCKET}/{gcs_path}")
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(file_path)
    print(f"Uploaded: gs://{GCS_BUCKET}/{gcs_path}")

    # Upload latest version
    if save_latest:
        latest_path = f"{GCS_FOLDER}/{latest_filename}"
        print(f"Uploading to gs://{GCS_BUCKET}/{latest_path}")
        blob_latest = bucket.blob(latest_path)
        blob_latest.upload_from_filename(file_path)
        print(f"Uploaded: gs://{GCS_BUCKET}/{latest_path}")

    return f"gs://{GCS_BUCKET}/{gcs_path}"


# =============================================================================
# SLACK NOTIFICATIONS
# =============================================================================
def send_slack_notification(
    message: str,
    status: str = "info",
    details: Optional[Dict[str, Any]] = None,
    webhook_url: Optional[str] = None
) -> bool:
    """
    Send notification to Slack.

    Args:
        message:     Main message text
        status:      "info", "success", "warning", or "error"
        details:     Dict of key-value pairs to display as fields
        webhook_url: Slack webhook URL (defaults to SLACK_WEBHOOK_URL env var)

    Returns:
        True if sent successfully, False otherwise

    Example:
        try:
            result = do_something()
        except Exception as e:
            send_slack_notification(
                message="Scraper failed",
                status="error",
                details={
                    "Error": str(e),
                    "Type": type(e).__name__
                }
            )
            raise
    """
    webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print("SLACK_WEBHOOK_URL not configured - skipping notification")
        return False

    colors = {
        "success": "#36a64f",
        "warning": "#ff9800",
        "error": "#ff0000",
        "info": "#2196f3"
    }

    emojis = {
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "info": "ℹ️"
    }

    attachment = {
        "color": colors.get(status, colors["info"]),
        "title": f"{emojis.get(status, '')} {PLATFORM_ID} - {status.upper()}",
        "text": message,
        "ts": int(datetime.now().timestamp()),
        "fields": []
    }

    if details:
        for key, value in details.items():
            attachment["fields"].append({
                "title": key,
                "value": str(value),
                "short": len(str(value)) < 30
            })

    payload = {"attachments": [attachment]}

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Slack notification sent: {status}")
        return True
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")
        return False
