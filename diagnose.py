"""
Run this first to find out exactly where the hang is.
  python diagnose.py
Each step has a 10-second timeout and will tell you pass/fail.
"""
import sys
import signal
import requests
from datetime import datetime, timedelta, timezone

# ── load env ──────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()
from src.config import cfg

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {cfg.HUBSPOT_ACCESS_TOKEN}"}


def check(label, fn):
    print(f"\n{'─'*50}\n🔍 {label}")
    try:
        result = fn()
        print(f"   ✅ OK — {result}")
    except requests.HTTPError as e:
        print(f"   ❌ HTTP {e.response.status_code}: {e.response.text[:200]}")
    except requests.Timeout:
        print("   ❌ TIMED OUT after 10s")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")


# ── 1. Basic auth check ───────────────────────────────────────────────────────
def test_auth():
    r = requests.get(f"{BASE}/crm/v3/objects/contacts?limit=1",
                     headers=HEADERS, timeout=10)
    r.raise_for_status()
    return f"contacts endpoint reachable, got {len(r.json().get('results', []))} result(s)"

# ── 2. Conversations API (WhatsApp) ───────────────────────────────────────────
def test_conversations():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(
        f"{BASE}/conversations/v3/conversations/threads",
        headers=HEADERS,
        params={"limit": 5, "latestMessageTimestampAfter": since},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return f"{len(data.get('results', []))} thread(s) in last 24h"

# ── 3. Conversations — WhatsApp filter ────────────────────────────────────────
def test_whatsapp_filter():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(
        f"{BASE}/conversations/v3/conversations/threads",
        headers=HEADERS,
        params={
            "limit": 5,
            "channelAccountType": "WHATS_APP",
            "latestMessageTimestampAfter": since,
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return f"{len(data.get('results', []))} WhatsApp thread(s) in last 24h"

# ── 4. Engagements API (SmartLead emails) ─────────────────────────────────────
def test_engagements():
    since_ms = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
    r = requests.get(
        f"{BASE}/engagements/v1/engagements/recent/modified",
        headers=HEADERS,
        params={"count": 5, "offset": 0, "since": since_ms},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    types = [r.get("engagement", {}).get("type") for r in results]
    return f"{len(results)} engagement(s): {types}"

# ── 5. Google Sheets ──────────────────────────────────────────────────────────
def test_sheets():
    import gspread
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file(
        cfg.GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    client = gspread.authorize(creds)
    ss = client.open_by_key(cfg.GOOGLE_SPREADSHEET_ID)
    tabs = [ws.title for ws in ss.worksheets()]
    print(f"   📋 Available tabs: {tabs}")
    ws = ss.worksheet(cfg.GOOGLE_WORKSHEET_NAME)
    return f"Tab '{cfg.GOOGLE_WORKSHEET_NAME}' opened, {ws.row_count} rows"


# ── Run all ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("Outreach Reporter — Diagnostics")
    print("=" * 50)

    check("HubSpot auth + contacts scope", test_auth)
    check("Conversations API (any threads)", test_conversations)
    check("Conversations API (WhatsApp filter)", test_whatsapp_filter)
    check("Engagements API (SmartLead emails)", test_engagements)
    check("Google Sheets access", test_sheets)

    print(f"\n{'='*50}\nDone. Fix any ❌ above before running main.py\n")
