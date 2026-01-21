# Scraper Template

Simple template for building scrapers deployed to GCP Cloud Run.

## Quick Start

1. Clone this repo
2. Edit your files:
   - `scraper.py` - your scraping logic
   - `requirements.txt` - add/remove dependencies
   - `Dockerfile` - customize container (e.g., add browsers)
   - `.gitlab-ci.yml` - **only variables:** `CLOUD_RUN_MEMORY`, `CLOUD_RUN_CPU`, `CLOUD_RUN_TIMEOUT`
3. Push to a **feature branch** and create a **Merge Request**

## How to Submit Your Work

```bash
# 1. Create a feature branch
git checkout -b feature/my-scraper

# 2. Make your changes

# 3. Commit and push
git add .
git commit -m "Implement scraper for [platform]"
git push -u origin feature/my-scraper

# 4. Go to GitLab and create a Merge Request to main
# 5. Wait for review and approval - pipeline runs after merge
```

**Important:** Do NOT push directly to `main` (it's protected)

## Naming Convention

Use the **platform_id** (lowercase) for repository name and output files:

| Element | Format | Example |
|---------|--------|---------|
| Repository | `scraper-{platform_id}` | `scraper-kaki` |
| GCS folder | `gs://market-place-dev/{platform_id}/` | `gs://market-place-dev/kaki/` |

**Two files are uploaded each run (naming is auto handle with dlg.save_to_gcs):**

| File | Purpose | Example |
|------|---------|---------|
| `raw_{platform_id}_{date}.csv` | (optional) Raw data (all fields from API) | `raw_kaki_20260106_143052.csv` |
| `{platform_id}_{date}.csv` | Parsed data (schema-compliant) | `kaki_20260106_143052.csv` |
| `{platform_id}_latest.csv` | Latest version (overwritten) | `kaki_latest.csv` |

> **Why this matters:** The `platform_id` drives all automation:
> - CI/CD deploys to `scraper-{platform_id}` Cloud Run job
> - Logs are isolated to `bucket-scraper-{platform_id}`
> - GCP permissions are scoped to your specific job
> - GCS folder structure for data organization
>
> **Using incorrect naming will break the pipeline and permissions.**

## Files

```
scraper-{platform_id}/
├── scraper.py          # Your scraping logic
├── dlg.py              # Data/Logging/GCS utilities (don't modify)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container config
├── .gitlab-ci.yml      # CI/CD pipeline + Cloud Run settings
└── README.md
```

## Cloud Run Settings

Edit these directly in `.gitlab-ci.yml`:

```yaml
variables:
  CLOUD_RUN_MEMORY: "512Mi"    # Options: 512Mi, 1Gi, 2Gi, 4Gi
  CLOUD_RUN_CPU: "1"           # Options: 1, 2, 4
  CLOUD_RUN_TIMEOUT: "300"     # Seconds (max 86400 for jobs)
  DEPLOY_MODE: "job"           # "job" (24h max) or "service" (1h max)
```

## Configuration (Auto)

**Zero config required.** The CI/CD pipeline auto-extracts settings from your repository name:

```
scraper-kaki      → PLATFORM_ID=kaki, GCS_FOLDER=kaki
scraper-ch24  → PLATFORM_ID=ch24, GCS_FOLDER=ch24
scraper-1std   → PLATFORM_ID=1std, GCS_FOLDER=1std
```

Output files will be:
- `gs://market-place-dev/{platform_id}/raw_{platform_id}_20260106_143052.csv` (raw)
- `gs://market-place-dev/{platform_id}/{platform_id}_20260106_143052.csv` (parsed)
- `gs://market-place-dev/{platform_id}/{platform_id}_latest.csv` (latest)

> **Using the repo's name setup by the owner** (`scraper-{platform_id}`) and everything is configured automatically.

## Data Extraction Requirements

### Extraction Priority

**Priority 1: Use API Endpoints**
- Find REST APIs, GraphQL, AJAX calls, product feeds using browser DevTools
- Use Playwright only if needed to capture auth tokens/headers
- Save complete raw API responses

**Priority 2: HTML Parsing (if no API exists)**
- Document why (e.g., server-side rendering, no APIs found)

### Anti-Detection
- No hardcoded tokens, user agents, or credentials
- Random sleep between requests
- Smart user agent rotation (if many requests)
- Use proxies (ScraperAPI, Zyte, Browserbase) when needed

## Required Outputs

### Field Schema
**Source of Truth:** [LuxuryIQ Crawling Brief](https://docs.google.com/presentation/d/1hB8A4TdCFOw45H2j7lM0qJaRUJTvVnUF7HQGgNG4NRQ)

Refer to the Crawling Brief for complete field specifications, priorities, and examples.

### Key Fields to Include
- **Must have:** read the Source of Truth
- **Nice to have:** read the Source of Truth

### CSV Outputs

**1. Raw Data CSV (optional):** `raw_{platform_id}_{YYYYMMDD}.csv`
- All fields from API/source, unprocessed
- Complete API responses preserved

**2. Parsed Data CSV:** `{platform_id}_{YYYYMMDD}.csv`
- Follow [LuxuryIQ Crawling Brief](https://docs.google.com/presentation/d/1hB8A4TdCFOw45H2j7lM0qJaRUJTvVnUF7HQGgNG4NRQ) schema
- Keep values as they appear on the website (e.g., price: "1036.25 USD")
- The data pipeline will handle ISO standardization downstream

## Run the Job

```bash
gcloud run jobs execute scraper-{platform_id} --region=us-central1
```

## Playwright (Browser Automation)

For sites requiring JavaScript rendering:

1. In `Dockerfile`, comment Option 1 and uncomment Option 2
2. In `requirements.txt`, uncomment `playwright`
3. In `.gitlab-ci.yml`, set `CLOUD_RUN_MEMORY: "2Gi"` and `CLOUD_RUN_CPU: "2"`

---

## Error Handling

Your scraper **must** return proper status codes and messages. This allows us to monitor issues in logs.

As in the `scraper.py` template, the `run_scraper()` function returns a dict with:

| Status | Meaning | When to use |
|--------|---------|-------------|
| `200` | Success | Scraping completed, data uploaded |
| `204` | No Content | Scraping completed but no data found |
| `500` | Internal Error | Unexpected exception |
| `502` | Bad Gateway | Invalid JSON response from target |
| `503` | Service Unavailable | Connection error to target |
| `504` | Gateway Timeout | Request timeout |

### Response Format (Cloud Run Logs)

These responses are printed to Cloud Run logs for monitoring:

```python
# Success
{"status": 200, "message": "Success", "rows": 150, "gcs_path": "gs://..."}

# No data
{"status": 204, "message": "No data found", "rows": 0}

# Error
{"status": 500, "error": "Internal Server Error", "detail": "error message"}
```

**Slack notifications** are sent only for errors (exceptions in try/except blocks). Success and "no data" responses are logged but do NOT trigger Slack alerts.

### Example Implementation

```python
from dlg import save_to_gcs, send_slack_notification

def run_scraper():
    try:
        # Your scraping logic
        df = scrape_data()

        if df.empty:
            result = {"status": 204, "message": "No data found", "rows": 0}
            print(f"Response: {result}")
            return result

        # Save to /tmp then upload to GCS
        df.to_csv("/tmp/data.csv", index=False)
        gcs_path = save_to_gcs("/tmp/data.csv")

        result = {"status": 200, "message": "Success", "rows": len(df), "gcs_path": gcs_path}
        print(f"Response: {result}")
        return result

    except requests.exceptions.Timeout as e:
        result = {"status": 504, "error": "Gateway Timeout", "detail": str(e)}
        print(f"Response: {result}")
        send_slack_notification("Gateway Timeout", status="error", details={"Error": str(e)})
        return result

    except Exception as e:
        result = {"status": 500, "error": "Internal Server Error", "detail": str(e)}
        print(f"Response: {result}")
        send_slack_notification(f"{type(e).__name__}", status="error", details={"Error": str(e)})
        return result
```

See `scraper.py` for the complete error handling implementation.

## DLG Utilities (dlg.py)

The `dlg.py` module provides two functions:

### save_to_gcs(file_path, prefix=None, extension="csv")

Upload a local file to GCS with auto-naming:

```python
from dlg import save_to_gcs

# Save DataFrame to /tmp, then upload
df.to_csv("/tmp/data.csv", index=False)
gcs_path = save_to_gcs("/tmp/data.csv")                       # → kaki/kaki_20260114_143052.csv
gcs_path = save_to_gcs("/tmp/data.csv", prefix="raw")         # → kaki/raw_kaki_20260114_143052.csv
gcs_path = save_to_gcs("/tmp/data.json", extension="json")    # → kaki/kaki_20260114_143052.json
```

### send_slack_notification(message, status, details)

Send Slack alerts (auto-triggered on errors):

```python
from dlg import send_slack_notification

send_slack_notification(
    message="Something went wrong",
    status="error",  # info, success, warning, error
    details={"Error": str(e)}
)
```

## Slack Notifications

Any exception automatically sends a Slack alert. No configuration needed.

**How it works:**
- `SLACK_WEBHOOK_URL` is set at **GitLab Group level** (masked variable)
- `PLATFORM_ID` is auto-extracted from repo name during deployment
- All exceptions trigger notifications
- 204 "no data" does NOT alert (it will handle by the China pipeline)

**What you get in Slack:**
```
❌ kaki - ERROR
Scraper failed: Gateway Timeout

Platform: kaki
Status: 504
Error: Connection timed out after 30s
```

## Technical Requirements

1. **Dynamic credential capture** - no hardcoded values
2. **Error handling** - retry logic, proper HTTP codes, diagnostic info
3. **Data validation** - validate required fields, handle nulls
4. **Clean code** - maintainable, not over-engineered
5. **Two CSV outputs** - raw (all fields) + parsed (schema-compliant)

## Important Notes

- **API-first approach** - use browser DevTools to find endpoints
- **Playwright when needed** - only for auth token capture
- **Two CSV outputs** - raw (all fields) + parsed (schema-compliant)
- **Keep it simple** - focus on stability and maintainability
- **Watches only** - exclude accessories and straps
- **Field schema** - always refer to [LuxuryIQ Crawling Brief](https://docs.google.com/presentation/d/1hB8A4TdCFOw45H2j7lM0qJaRUJTvVnUF7HQGgNG4NRQ) as source of truth

## Workflow

1. A GitLab ticket will be opened for each new website to crawl
2. Create feature branch for your scraper
3. Implement scraper following this template
4. Create Merge Request for review
5. Pipeline deploys after merge approval
6. Ping Charlotte to ask for QC
7. Quality control successful and validated -> payment requested from Tancredi
