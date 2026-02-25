# Outreach Reporter

Automates Evan's daily outreach metrics routine:

- Pulls engagement counts from **HubSpot** (WhatsApp, SmartLead email replies, LinkedIn notes)
- Adds a row to the **BizDev Google Sheet**
- Posts a formatted daily summary to **#creator-reporting** on Slack
- Provides a `/log-social` **Slack slash command** for Evan to enter Telegram / Signal counts in 2 seconds instead of checking the apps

---

## Architecture

```
main.py
  ├── src/hubspot_client.py   — fetch & categorise engagements
  ├── src/sheets_client.py    — append row to BizDev sheet
  ├── src/slack_client.py     — post summary to Slack
  └── src/manual_counts.py    — read/write data/manual_counts.json

slack_app.py  (FastAPI)
  ├── POST /slack/commands/log-social   — slash command handler
  ├── POST /slack/trigger-report        — on-demand run
  ├── GET  /healthz                     — health check
  └── APScheduler → main.run_daily_report() at configured hour
```

**Two deployment options — pick one:**

| Option | Best for | Slash command support |
|--------|----------|-----------------------|
| **FastAPI server** (Railway / Render / Fly) | Slash command + auto-schedule | ✅ Yes |
| **GitHub Actions** (cron) | Simplest, no server cost | ❌ No (manual counts only via JSON file) |

---

## Setup

### 1. HubSpot — Create a Private App

1. HubSpot → Settings → Integrations → Private Apps → **Create a private app**
2. Name it "Outreach Reporter"
3. Under **Scopes**, enable:
   - `crm.objects.contacts.read`
   - `crm.objects.communications.read`
   - `crm.objects.emails.read`
   - `crm.objects.notes.read`
4. Click **Create app** → copy the **Access Token**

> **How to refresh the HubSpot Access Token**
> Private App tokens do **not expire** unless you rotate them manually.
> To rotate: Settings → Private Apps → your app → **Rotate token**.
> Update `HUBSPOT_ACCESS_TOKEN` in your `.env` / GitHub Secrets immediately after rotating.

#### Find your lead_type property name

1. HubSpot → Settings → Properties → **Contact properties**
2. Search for the property that stores Creator / Agency / Affiliate
3. Copy the **Internal name** (e.g., `lead_type`, `hs_lead_status`, `contact_category`)
4. Set `HUBSPOT_LEAD_TYPE_PROPERTY=<internal_name>` in `.env`

#### Confirm WhatsApp channel type value

HubSpot's API value for WhatsApp is `WHATS_APP` (with underscore).
If your account uses a different value, update `hubspot_client.py:fetch_whatsapp_contact_ids`.
To verify, run:
```bash
python - <<'EOF'
from src.hubspot_client import _post
results = _post("/crm/v3/objects/communications/search", {
    "filterGroups": [], "properties": ["hs_communication_channel_type"], "limit": 5
})
for r in results.get("results", []):
    print(r["properties"].get("hs_communication_channel_type"))
EOF
```

---

### 2. Google Sheets — Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com) → create or select a project
2. Enable **Google Sheets API** and **Google Drive API**
3. IAM & Admin → Service Accounts → **Create Service Account**
4. Create a JSON key → download as `service_account.json` → place it in the project root
5. Copy the service account email (e.g., `reporter@project.iam.gserviceaccount.com`)
6. Open your Google Sheet → Share → paste the service account email → **Editor**
7. Copy the spreadsheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/**<SPREADSHEET_ID>**/edit`

---

### 3. Slack — Bot Token + Slash Command

#### Create the Slack App
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From Scratch**
2. Name it "Outreach Reporter"

#### Bot Token
1. OAuth & Permissions → add scopes: `chat:write`, `chat:write.public`
2. Install app to workspace → copy **Bot User OAuth Token** (`xoxb-…`)

#### Slash Command (requires FastAPI deployment first)
1. Slash Commands → **Create New Command**
2. Command: `/log-social`
3. Request URL: `https://<your-app-url>/slack/commands/log-social`
4. Short description: `Log manual outreach counts (Telegram, Signal)`
5. Save → reinstall app

#### Signing Secret
1. Basic Information → App Credentials → copy **Signing Secret**

---

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with all your credentials
```

---

## Running locally

```bash
pip install -r requirements.txt

# Test the full pipeline (no Sheets/Slack writes)
python main.py --dry-run

# Run for real
python main.py

# Start the FastAPI server (includes scheduler + slash command)
uvicorn slack_app:app --reload --port 8000
```

---

## Deployment — FastAPI on Railway

1. Push this repo to GitHub
2. New project on [Railway](https://railway.app) → Deploy from GitHub repo
3. Set all environment variables from `.env.example` in Railway's dashboard
4. Paste the `service_account.json` contents as a single-line JSON string in `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` (you'll need to update `config.py` to write it to a temp file — see note below)
5. Set start command: `uvicorn slack_app:app --host 0.0.0.0 --port $PORT`
6. Copy the Railway public URL → update Slack slash command Request URL

---

## Deployment — GitHub Actions (no server)

1. Push repo to GitHub
2. Settings → Secrets and Variables → Actions → add all secrets:
   - `HUBSPOT_ACCESS_TOKEN`
   - `GOOGLE_SPREADSHEET_ID`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` ← paste the **entire JSON file contents**
   - `SLACK_BOT_TOKEN`
   - `SLACK_SIGNING_SECRET`
   - `SLACK_REPORT_CHANNEL`
3. The workflow at `.github/workflows/daily_report.yml` runs Monday–Friday at 09:00 UTC
4. To change the time, edit the `cron` expression in the workflow file

**Manual counts with GitHub Actions:**
Since there's no server, Evan logs counts by editing `data/manual_counts.json` directly
and committing it, OR you can open `Issues` in the repo and parse the body — but the
FastAPI server option is recommended for Slack slash command support.

---

## Google Sheets column mapping

| Column | Source |
|--------|--------|
| Date | Today's date |
| Total Creators | HubSpot contacts with `lead_type = creator` |
| LinkedIn | HubSpot notes tagged "linkedin" + `/log-social linkedin N` |
| WhatsApp | HubSpot Communications (`hs_communication_channel_type = WHATS_APP`) |
| Telegram | `/log-social telegram N` (manual) |
| Agencies | HubSpot contacts with `lead_type = agency` |
| Affiliates | HubSpot contacts with `lead_type = affiliate` |

---

## Slack slash command reference

```
/log-social                → show today's manual counts
/log-social telegram 3     → set Telegram count to 3 for today
/log-social signal 1       → set Signal count to 1 for today
/log-social linkedin 5     → add 5 LinkedIn contacts (manual supplement)
```

---

## Customisation

**Add a new contact category** (e.g., "Influencer"):
1. Add the HubSpot property values to `INFLUENCER_VALUES` in `.env`
2. Add a branch in `src/hubspot_client.py:_classify()`
3. Add a field to `CategoryCounts` in `src/models.py`

**Add a new channel** (e.g., Instagram DMs if synced to HubSpot):
1. Add a fetcher function in `src/hubspot_client.py`
2. Add the count to `ChannelCounts` in `src/models.py`
3. Update `sheets_row()` and `slack_summary()` in `src/models.py`

---

## Project structure

```
outreach-reporter/
├── .github/workflows/daily_report.yml   GitHub Actions cron
├── src/
│   ├── config.py           Environment variables
│   ├── models.py           Data classes (ChannelCounts, DailyReport, etc.)
│   ├── hubspot_client.py   HubSpot API — fetch engagements + categorise contacts
│   ├── sheets_client.py    Google Sheets — append BizDev row
│   ├── slack_client.py     Slack — post daily summary
│   └── manual_counts.py    Read/write data/manual_counts.json
├── slack_app.py            FastAPI server (slash command + scheduler)
├── main.py                 Orchestrator (also CLI entry point)
├── requirements.txt
├── .env.example
├── service_account.json    ← create from Google Cloud, do NOT commit
└── data/
    └── manual_counts.json  ← auto-created; safe to commit
```
