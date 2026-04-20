"""Fetch GA4 data for configured properties and write JSON to data/.

Reads properties.yaml, runs daily or weekly GA4 reports, writes timestamped
and latest-<mode>.json files under data/<property_key>/. Credentials come
from the GA4_SERVICE_ACCOUNT_JSON env var (the full service-account JSON
as a string).
"""

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

import yaml
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)
from google.oauth2 import service_account


DAILY_METRICS = [
    "totalUsers",
    "newUsers",
    "sessions",
    "screenPageViews",
    "engagementRate",
    "bounceRate",
]


def load_client() -> BetaAnalyticsDataClient:
    raw = os.environ.get("GA4_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError("GA4_SERVICE_ACCOUNT_JSON env var not set")
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info)
    return BetaAnalyticsDataClient(credentials=creds)


def run_report(client, property_id, start, end, dimensions, metrics, limit=None):
    req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        limit=limit or 10000,
    )
    resp = client.run_report(req)
    rows = []
    for row in resp.rows:
        entry = {}
        for i, d in enumerate(dimensions):
            entry[d] = row.dimension_values[i].value
        for i, m in enumerate(metrics):
            entry[m] = row.metric_values[i].value
        rows.append(entry)
    return rows


def daily_report(client, property_id):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    totals = run_report(client, property_id, yesterday, yesterday, [], DAILY_METRICS)
    by_channel = run_report(
        client, property_id, yesterday, yesterday,
        ["sessionDefaultChannelGroup"], ["totalUsers", "sessions", "engagementRate"],
    )
    by_source = run_report(
        client, property_id, yesterday, yesterday,
        ["sessionSource", "sessionMedium"], ["totalUsers", "sessions"],
    )
    top_pages = run_report(
        client, property_id, yesterday, yesterday,
        ["pagePath"], ["screenPageViews", "totalUsers"], limit=20,
    )
    return {
        "mode": "daily",
        "date": yesterday,
        "totals": totals[0] if totals else {},
        "by_channel": by_channel,
        "by_source": by_source,
        "top_pages": top_pages,
    }


def weekly_report(client, property_id):
    end = (date.today() - timedelta(days=1)).isoformat()
    start = (date.today() - timedelta(days=7)).isoformat()
    prev_end = (date.today() - timedelta(days=8)).isoformat()
    prev_start = (date.today() - timedelta(days=14)).isoformat()

    totals = run_report(client, property_id, start, end, [], DAILY_METRICS)
    prev_totals = run_report(client, property_id, prev_start, prev_end, [], DAILY_METRICS)
    by_day = run_report(
        client, property_id, start, end,
        ["date"], ["totalUsers", "sessions"],
    )
    by_channel = run_report(
        client, property_id, start, end,
        ["sessionDefaultChannelGroup"], ["totalUsers", "sessions", "engagementRate"],
    )
    by_source = run_report(
        client, property_id, start, end,
        ["sessionSource", "sessionMedium"], ["totalUsers", "sessions"],
    )
    top_pages = run_report(
        client, property_id, start, end,
        ["pagePath"], ["screenPageViews", "totalUsers"], limit=25,
    )
    return {
        "mode": "weekly",
        "period": {"start": start, "end": end},
        "prev_period": {"start": prev_start, "end": prev_end},
        "totals": totals[0] if totals else {},
        "prev_totals": prev_totals[0] if prev_totals else {},
        "by_day": by_day,
        "by_channel": by_channel,
        "by_source": by_source,
        "top_pages": top_pages,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--config", default="properties.yaml")
    parser.add_argument("--output-dir", default="data")
    parser.add_argument("--only", help="Comma-separated property keys to fetch")
    args = parser.parse_args()

    client = load_client()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    only = set(args.only.split(",")) if args.only else None
    out_dir = Path(args.output_dir)

    for key, prop in config["properties"].items():
        if only and key not in only:
            continue
        print(f"Fetching {args.mode} report for {key} (property {prop['property_id']})...")
        if args.mode == "daily":
            report = daily_report(client, prop["property_id"])
        else:
            report = weekly_report(client, prop["property_id"])

        report["property"] = {
            "key": key,
            "name": prop["name"],
            "domain": prop["domain"],
            "slack_channel": prop["slack_channel"],
        }

        prop_dir = out_dir / key
        prop_dir.mkdir(parents=True, exist_ok=True)

        stamp = report.get("date") or report["period"]["end"]
        timestamped = prop_dir / f"{args.mode}-{stamp}.json"
        latest = prop_dir / f"latest-{args.mode}.json"

        for path in (timestamped, latest):
            with open(path, "w") as f:
                json.dump(report, f, indent=2)

        print(f"  -> {timestamped}")
        print(f"  -> {latest}")


if __name__ == "__main__":
    main()
