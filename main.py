"""
Daily report orchestrator.

Can be run three ways:
  1. python main.py                    — run the full report right now
  2. python main.py --dry-run          — fetch data, print output, skip posting
  3. Invoked by slack_app.py scheduler — runs daily at the configured hour
"""

import argparse
import logging
import sys
from datetime import date

from src.config import cfg
from src.hubspot_client import build_channel_and_category_counts
from src.manual_counts import get_counts
from src.models import DailyReport
from src.sheets_client import append_daily_row
from src.slack_client import post_daily_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_daily_report(dry_run: bool = False) -> DailyReport:
    logger.info("=== Daily Outreach Report (%s) ===", date.today())

    # 1. Pull manual counts (Telegram, Signal, LinkedIn supplement)
    manual = get_counts()
    telegram = manual.get("telegram", 0)
    signal = manual.get("signal", 0)
    linkedin_manual = manual.get("linkedin", 0)
    logger.info("Manual counts — telegram:%d  signal:%d  linkedin_supplement:%d",
                telegram, signal, linkedin_manual)

    # 2. Fetch HubSpot engagement data
    logger.info("Fetching HubSpot engagement data…")
    channels, categories, all_contact_ids = build_channel_and_category_counts(
        manual_telegram=telegram,
        manual_signal=signal,
        manual_linkedin=linkedin_manual,
    )

    # 3. Build the report object
    report = DailyReport(
        report_date=date.today(),
        channels=channels,
        categories=categories,
        unique_contact_ids=all_contact_ids,
    )

    logger.info(
        "Summary — total:%d  creators:%d  agencies:%d  affiliates:%d  unknown:%d",
        report.total_outreach,
        report.categories.creators,
        report.categories.agencies,
        report.categories.affiliates,
        report.categories.unknown,
    )

    if dry_run:
        print("\n" + "─" * 60)
        print("DRY RUN — nothing will be written to Sheets or Slack")
        print("─" * 60)
        print("\nSlack message preview:\n")
        print(report.slack_summary())
        print("\nSheets row:", report.sheets_row())
        return report

    # 4. Append to Google Sheets
    logger.info("Appending row to Google Sheets…")
    try:
        append_daily_row(report)
        logger.info("Sheets updated successfully.")
    except Exception as exc:
        logger.error("Failed to update Sheets: %s", exc)

    # 5. Post to Slack (skipped if SLACK_BOT_TOKEN is not configured)
    if cfg.SLACK_BOT_TOKEN:
        logger.info("Posting to Slack…")
        try:
            post_daily_report(report)
            logger.info("Slack message posted.")
        except Exception as exc:
            logger.error("Failed to post to Slack: %s", exc)
    else:
        logger.info("SLACK_BOT_TOKEN not set — skipping Slack post.")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the daily outreach report")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write to Sheets or post to Slack",
    )
    args = parser.parse_args()

    try:
        run_daily_report(dry_run=args.dry_run)
    except KeyboardInterrupt:
        sys.exit(0)
