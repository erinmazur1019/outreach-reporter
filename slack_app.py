"""
FastAPI application serving two purposes:

1. Slack Slash Commands
   /log-social telegram 3        → log 3 Telegram contacts for today
   /log-social signal 1          → log 1 Signal contact for today
   /log-social linkedin 5        → add 5 LinkedIn contacts (manual supplement)
   /log-social                   → show current manual counts for today

2. Scheduled daily report (via APScheduler)
   Runs main.run_daily_report() every day at the configured time.

Deploy to Railway / Render / Fly.io and expose the public URL to Slack
as your slash command Request URL:
   https://<your-app>.railway.app/slack/commands/log-social

Slack must verify requests using SLACK_SIGNING_SECRET.
"""

import hashlib
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, Response, HTTPException

import main as report_main
from src.config import cfg
from src.manual_counts import get_counts, set_count
from src.slack_client import post_ephemeral

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cron schedule for the daily report (server local time / UTC)
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "9"))   # 09:00
REPORT_MINUTE = int(os.getenv("REPORT_MINUTE", "0"))


# ── Slack request signature verification ──────────────────────────────────────

def _verify_slack_signature(body: bytes, headers: dict) -> None:
    """Raise HTTPException 403 if the Slack signature is invalid."""
    ts = headers.get("x-slack-request-timestamp", "")
    sig = headers.get("x-slack-signature", "")

    # Reject replays older than 5 minutes
    if abs(time.time() - int(ts)) > 300:
        raise HTTPException(status_code=403, detail="Request too old")

    base = f"v0:{ts}:{body.decode()}"
    expected = (
        "v0="
        + hmac.new(
            cfg.SLACK_SIGNING_SECRET.encode(),
            base.encode(),
            hashlib.sha256,
        ).hexdigest()
    )
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")


# ── Lifespan (scheduler) ──────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        report_main.run_daily_report,
        CronTrigger(hour=REPORT_HOUR, minute=REPORT_MINUTE),
        id="daily_report",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — daily report at %02d:%02d", REPORT_HOUR, REPORT_MINUTE
    )
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.post("/slack/commands/log-social")
async def log_social(request: Request):
    """
    Handle /log-social Slack slash command.

    Usage:
      /log-social                   → show today's manual counts
      /log-social telegram 3        → set Telegram count to 3
      /log-social signal 1          → set Signal count to 1
      /log-social linkedin 5        → set LinkedIn supplement to 5
    """
    body = await request.body()
    _verify_slack_signature(body, dict(request.headers))

    # Slack sends form-encoded body
    params = parse_qs(body.decode())
    text = params.get("text", [""])[0].strip()
    user_id = params.get("user_id", [""])[0]
    channel_id = params.get("channel_id", [""])[0]

    VALID_CHANNELS = {"telegram", "signal", "linkedin"}

    if not text:
        counts = get_counts()
        reply = (
            f"📋 *Today's manual counts:*\n"
            f"  Telegram: `{counts.get('telegram', 0)}`\n"
            f"  Signal:   `{counts.get('signal', 0)}`\n"
            f"  LinkedIn: `{counts.get('linkedin', 0)}`\n\n"
            f"_Use `/log-social telegram 3` to update._"
        )
    else:
        parts = text.split()
        if len(parts) != 2:
            return Response(
                content="Usage: `/log-social <channel> <count>`  e.g. `/log-social telegram 3`",
                media_type="text/plain",
            )
        channel_name, count_str = parts
        channel_name = channel_name.lower()

        if channel_name not in VALID_CHANNELS:
            return Response(
                content=f"Unknown channel `{channel_name}`. Valid: telegram, signal, linkedin",
                media_type="text/plain",
            )
        try:
            count = int(count_str)
            if count < 0:
                raise ValueError
        except ValueError:
            return Response(
                content=f"`{count_str}` is not a valid non-negative integer.",
                media_type="text/plain",
            )

        set_count(channel_name, count)
        reply = f"✅ Logged `{count}` {channel_name} contacts for today."

    # Return immediate response (Slack expects < 3 s)
    return Response(content=reply, media_type="text/plain")


@app.post("/slack/trigger-report")
async def trigger_report(request: Request):
    """
    Manual trigger for the daily report.
    POST to this endpoint from Slack or internally to run the report immediately.
    """
    body = await request.body()
    _verify_slack_signature(body, dict(request.headers))

    import asyncio
    asyncio.create_task(_run_report_async())
    return Response(content="⏳ Running report now — results in #creator-reporting shortly.", media_type="text/plain")


async def _run_report_async():
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, report_main.run_daily_report)
