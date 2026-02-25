"""
Inspect the raw HubSpot API response structure so we can fix the field mappings.
  python debug_structure.py
"""
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
load_dotenv()
from src.config import cfg

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {cfg.HUBSPOT_ACCESS_TOKEN}"}

print("\n" + "="*60)
print("1. RAW STRUCTURE OF FIRST WHATSAPP THREAD")
print("="*60)
r = requests.get(
    f"{BASE}/conversations/v3/conversations/threads",
    headers=HEADERS,
    params={"limit": 1, "channelAccountType": "WHATS_APP"},
    timeout=15,
)
r.raise_for_status()
threads = r.json().get("results", [])
if threads:
    print(json.dumps(threads[0], indent=2))
else:
    print("No WhatsApp threads found")

print("\n" + "="*60)
print("2. RAW PROPERTIES OF ONE 'UNKNOWN' CONTACT")
print("   (from SmartLead replies — shows what properties exist)")
print("="*60)
since_ms = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)
r2 = requests.get(
    f"{BASE}/engagements/v1/engagements/recent/modified",
    headers=HEADERS,
    params={"count": 10, "offset": 0, "since": since_ms},
    timeout=15,
)
r2.raise_for_status()
results = r2.json().get("results", [])

# Find first EMAIL engagement with a contact
contact_id = None
for item in results:
    if item.get("engagement", {}).get("type") == "EMAIL":
        ids = item.get("associations", {}).get("contactIds", [])
        if ids:
            contact_id = str(ids[0])
            break

if contact_id:
    print(f"Contact ID: {contact_id}")
    # Fetch ALL properties so we can see what's actually set
    r3 = requests.get(
        f"{BASE}/crm/v3/objects/contacts/{contact_id}",
        headers=HEADERS,
        params={"properties": "lifecyclestage,lead_type,hs_lead_status,jobtitle,type"},
        timeout=15,
    )
    r3.raise_for_status()
    props = r3.json().get("properties", {})
    print("Key properties on this contact:")
    for k, v in sorted(props.items()):
        if v:  # only show non-empty
            print(f"  {k}: {v!r}")
    print("\nFull property dump (non-null):")
    print(json.dumps({k: v for k, v in props.items() if v}, indent=2))
else:
    print("No email engagements with contacts found in last 24h")
