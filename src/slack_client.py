"""
Slack client — posts the daily summary to #creator-reporting.

Uses the slack_sdk WebClient (Bot Token / OAuth).
Docs: https://slack.dev/python-slack-sdk/web/index.html
"""

import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import cfg
from src.models import DailyReport

logger = logging.getLogger(__name__)

_client: WebClient | None = None


def _get_client() -> WebClient:
    global _client
    if _client is None:
        _client = WebClient(token=cfg.SLACK_BOT_TOKEN)
    return _client


def post_daily_report(report: DailyReport) -> None:
    """Post the formatted daily summary to the configured Slack channel."""
    client = _get_client()
    text = report.slack_summary()

    try:
        resp = client.chat_postMessage(
            channel=cfg.SLACK_REPORT_CHANNEL,
            text=text,
            mrkdwn=True,
        )
        logger.info(
            "Posted to %s (ts=%s)", cfg.SLACK_REPORT_CHANNEL, resp["ts"]
        )
    except SlackApiError as exc:
        logger.error("Slack post failed: %s", exc.response["error"])
        raise


def post_ephemeral(channel: str, user: str, text: str) -> None:
    """Send a private reply visible only to the user (used by slash command)."""
    client = _get_client()
    try:
        client.chat_postEphemeral(channel=channel, user=user, text=text)
    except SlackApiError as exc:
        logger.error("Ephemeral post failed: %s", exc.response["error"])
