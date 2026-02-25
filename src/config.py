"""
Central configuration loaded from environment variables / .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── HubSpot ────────────────────────────────────────────────────────────────
    HUBSPOT_ACCESS_TOKEN: str = os.environ["HUBSPOT_ACCESS_TOKEN"]

    # Deal pipeline IDs that determine contact category.
    # Each is a set of pipeline IDs (comma-separated in env).
    CREATOR_PIPELINE_IDS: set[str] = set(
        os.getenv("CREATOR_PIPELINE_IDS", "678993585,696988058").split(",")
    )
    AGENCY_PIPELINE_IDS: set[str] = set(
        os.getenv("AGENCY_PIPELINE_IDS", "678993586").split(",")
    )
    AFFILIATE_PIPELINE_IDS: set[str] = set(
        os.getenv("AFFILIATE_PIPELINE_IDS", "679087972").split(",")
    )

    # ── Google Sheets ──────────────────────────────────────────────────────────
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json"
    )
    GOOGLE_SPREADSHEET_ID: str = os.environ["GOOGLE_SPREADSHEET_ID"]
    GOOGLE_WORKSHEET_NAME: str = os.getenv("GOOGLE_WORKSHEET_NAME", "BizDev")

    # ── Slack ──────────────────────────────────────────────────────────────────
    # Optional — if not set, Slack posting is skipped
    SLACK_BOT_TOKEN: str | None = os.getenv("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET: str | None = os.getenv("SLACK_SIGNING_SECRET")
    SLACK_REPORT_CHANNEL: str = os.getenv("SLACK_REPORT_CHANNEL", "#creator-reporting")

    # ── Reporting window ───────────────────────────────────────────────────────
    LOOKBACK_HOURS: int = int(os.getenv("LOOKBACK_HOURS", "24"))

    # ── Manual counts file ─────────────────────────────────────────────────────
    MANUAL_COUNTS_FILE: str = os.getenv(
        "MANUAL_COUNTS_FILE", "data/manual_counts.json"
    )


cfg = Config()
