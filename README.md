# l1c-ga4-reporter

Multi-property GA4 reporting across Layer One Capital portfolio companies.

## How it works

1. **GitHub Actions** runs on cron (daily Mon–Sat, weekly Sunday, both at 11:00 UTC / 7:00 ET).
2. The workflow calls `scripts/fetch_ga4.py`, which reads `properties.yaml`, queries the GA4 Data API for each configured property, and writes JSON to `data/<property_key>/`.
3. Committed data files are consumed by a **Claude Code scheduled agent** (separate from this repo) that reads the latest JSON, writes narrative commentary, and posts to each property's configured Slack channel via the Slack MCP connector.

## Adding a property

Edit `properties.yaml`:

```yaml
properties:
  <key>:
    property_id: "<GA4 property id>"
    name: "<Display name>"
    domain: "<root domain>"
    slack_channel: "#<channel>"
```

The service account referenced by `GA4_SERVICE_ACCOUNT_JSON` must have Viewer access on the GA4 property.

## Secrets

- `GA4_SERVICE_ACCOUNT_JSON` — full service-account JSON (stringified), set via `gh secret set GA4_SERVICE_ACCOUNT_JSON < ~/.config/gcloud/ga4-key.json`.

## Local testing

```bash
export GA4_SERVICE_ACCOUNT_JSON="$(cat ~/.config/gcloud/ga4-key.json)"
pip install -r requirements.txt
python scripts/fetch_ga4.py --mode daily
python scripts/fetch_ga4.py --mode weekly
```
