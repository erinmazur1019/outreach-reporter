"""
HubSpot API client.

Data sources:
  - WhatsApp messages  → Conversations API v3 (inbox threads)
  - SmartLead replies  → Engagements API v1 (email engagements)
  - Contact categories → Deal pipeline lookup (contacts → deals → pipeline)

Required Private App scopes:
  - crm.objects.contacts.read
  - crm.objects.deals.read
  - conversations.read          (for WhatsApp inbox threads)
  - sales-email-read            (for email engagement history)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.config import cfg
from src.models import CategoryCounts, ChannelCounts

logger = logging.getLogger(__name__)

BASE = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {cfg.HUBSPOT_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict) -> dict:
    resp = requests.post(f"{BASE}{path}", headers=HEADERS, json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _since_ms() -> int:
    """Unix epoch milliseconds for (now - LOOKBACK_HOURS)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.LOOKBACK_HOURS)
    return int(cutoff.timestamp() * 1000)


def _since_iso() -> str:
    """ISO-8601 timestamp for (now - LOOKBACK_HOURS), used by Conversations API."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.LOOKBACK_HOURS)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Deal pipeline classification ──────────────────────────────────────────────

def _classify_contacts_by_pipeline(contact_ids: set[str]) -> dict[str, str]:
    """
    For each contact ID, look up their associated deals, read the deal's
    pipelineId, and map it to 'creator' | 'agency' | 'affiliate' | 'unknown'.

    Steps:
      1. Batch-get deal IDs associated with each contact
      2. Batch-read deal pipelineId properties
      3. Map pipeline → category (first match wins if contact has multiple deals)

    Requires scopes: crm.objects.contacts.read, crm.objects.deals.read
    """
    if not contact_ids:
        return {}

    ids = list(contact_ids)

    # Step 1: batch-fetch contact → deal associations
    contact_to_deal_ids: dict[str, list[str]] = {cid: [] for cid in ids}

    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        try:
            data = _post(
                "/crm/v4/associations/contacts/deals/batch/read",
                {"inputs": [{"id": cid} for cid in chunk]},
            )
            for result in data.get("results", []):
                contact_id = str(result.get("from", {}).get("id", ""))
                deal_ids = [str(r["toObjectId"]) for r in result.get("to", [])]
                if contact_id in contact_to_deal_ids:
                    contact_to_deal_ids[contact_id] = deal_ids
        except requests.HTTPError as exc:
            logger.warning("Contact→deal association batch failed: %s", exc)

    # Step 2: collect all unique deal IDs and batch-read their pipelineId
    all_deal_ids: set[str] = set()
    for deal_ids in contact_to_deal_ids.values():
        all_deal_ids.update(deal_ids)

    deal_pipeline: dict[str, str] = {}  # deal_id → pipeline_id
    deal_ids_list = list(all_deal_ids)
    for i in range(0, len(deal_ids_list), 100):
        chunk = deal_ids_list[i : i + 100]
        try:
            data = _post(
                "/crm/v3/objects/deals/batch/read",
                {"inputs": [{"id": did} for did in chunk], "properties": ["pipeline"]},
            )
            for record in data.get("results", []):
                pipeline_id = record.get("properties", {}).get("pipeline", "")
                deal_pipeline[record["id"]] = pipeline_id
        except requests.HTTPError as exc:
            logger.warning("Deal batch read failed: %s", exc)

    # Step 3: map each contact to a category via their deals' pipelines
    contact_category: dict[str, str] = {}
    for contact_id, deal_ids in contact_to_deal_ids.items():
        category = "unknown"
        for did in deal_ids:
            pipeline_id = deal_pipeline.get(did, "")
            if pipeline_id in cfg.CREATOR_PIPELINE_IDS:
                category = "creator"
                break
            elif pipeline_id in cfg.AGENCY_PIPELINE_IDS:
                category = "agency"
                break
            elif pipeline_id in cfg.AFFILIATE_PIPELINE_IDS:
                category = "affiliate"
                break
        contact_category[contact_id] = category

    return contact_category


# ── WhatsApp via CRM Activity object type 0-18 ────────────────────────────────

def fetch_whatsapp_contact_ids() -> set[str]:
    """
    Query HubSpot's native WhatsApp Messages activity object (type 0-18) for
    messages logged in the last LOOKBACK_HOURS hours, then return the unique
    contact IDs associated with those activities.

    This uses the CRM Search API with a server-side timestamp filter, so it
    only pages through records actually within the time window — no runaway loop.

    Requires scope: crm.objects.contacts.read  (activities inherit contact scope)
    If you get a 403, also try adding: crm.objects.custom.read
    """
    activity_ids: list[str] = []
    after: str | None = None
    since_ms = _since_ms()

    while True:
        body: dict[str, Any] = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "hs_timestamp",
                    "operator": "GTE",
                    "value": str(since_ms),
                }]
            }],
            "properties": ["hs_timestamp"],
            "limit": 100,
        }
        if after:
            body["after"] = after

        try:
            data = _post("/crm/v3/objects/0-18/search", body)
        except requests.HTTPError as exc:
            if exc.response.status_code == 403:
                logger.warning(
                    "WhatsApp (0-18) fetch: 403 Forbidden. "
                    "Ensure crm.objects.contacts.read scope is set on your Private App."
                )
            else:
                logger.error("WhatsApp activity fetch failed: %s", exc)
            break

        results = data.get("results", [])
        activity_ids.extend(r["id"] for r in results)
        logger.info("WhatsApp activities fetched so far: %d", len(activity_ids))

        paging = data.get("paging", {})
        after = paging.get("next", {}).get("after")
        if not after:
            break

    if not activity_ids:
        return set()

    # Batch-read associations: WhatsApp activity (0-18) → contacts
    contact_ids: set[str] = set()
    for i in range(0, len(activity_ids), 100):
        chunk = activity_ids[i : i + 100]
        try:
            data = _post(
                "/crm/v4/associations/0-18/contacts/batch/read",
                {"inputs": [{"id": aid} for aid in chunk]},
            )
            for result in data.get("results", []):
                for assoc in result.get("to", []):
                    contact_ids.add(str(assoc["toObjectId"]))
        except requests.HTTPError as exc:
            logger.warning("WhatsApp→contact association batch failed: %s", exc)

    logger.info("WhatsApp unique contacts in last %dh: %d", cfg.LOOKBACK_HOURS, len(contact_ids))
    return contact_ids


# ── SmartLead replies via Engagements API v1 ──────────────────────────────────

def fetch_smartlead_reply_contact_ids() -> set[str]:
    """
    Pull inbound email engagements (replies) from the last LOOKBACK_HOURS hours.
    SmartLead syncs replies into HubSpot as EMAIL type engagements.

    Requires scope: sales-email-read
    """
    contact_ids: set[str] = set()
    cutoff_ms = _since_ms()
    offset = 0

    while True:
        try:
            data = _get(
                "/engagements/v1/engagements/recent/modified",
                params={
                    "count": 100,
                    "offset": offset,
                    "since": cutoff_ms,
                },
            )
        except requests.HTTPError as exc:
            if exc.response.status_code == 403:
                logger.warning(
                    "SmartLead email fetch: 403 Forbidden. "
                    "Add 'sales-email-read' scope to your HubSpot Private App."
                )
            else:
                logger.error("SmartLead email fetch failed: %s", exc)
            break

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            engagement = item.get("engagement", {})
            metadata = item.get("metadata", {})
            associations = item.get("associations", {})

            # Only count inbound email replies
            if engagement.get("type") != "EMAIL":
                continue
            if metadata.get("direction") not in ("INCOMING_EMAIL", None, ""):
                continue

            for cid in associations.get("contactIds", []):
                contact_ids.add(str(cid))

        if not data.get("hasMore", False):
            break
        offset = data.get("offset", offset + 100)

    logger.info("SmartLead reply contacts found: %d", len(contact_ids))
    return contact_ids


# ── Main entry point ──────────────────────────────────────────────────────────

def build_channel_and_category_counts(
    manual_telegram: int = 0,
    manual_signal: int = 0,
    manual_linkedin: int = 0,
) -> tuple[ChannelCounts, CategoryCounts, set[str]]:
    """
    Fetch all HubSpot data and return:
      - ChannelCounts  (contacts per channel)
      - CategoryCounts (creators / agencies / affiliates)
      - set of all unique contact IDs touched
    """
    whatsapp_ids = fetch_whatsapp_contact_ids()
    smartlead_ids = fetch_smartlead_reply_contact_ids()

    all_ids: set[str] = whatsapp_ids | smartlead_ids

    channels = ChannelCounts(
        whatsapp=len(whatsapp_ids),
        smartlead_email=len(smartlead_ids),
        linkedin=manual_linkedin,
        telegram=manual_telegram,
        signal=manual_signal,
    )

    # Classify every unique contact via their deal pipeline
    logger.info("Classifying %d contacts via deal pipelines…", len(all_ids))
    contact_category = _classify_contacts_by_pipeline(all_ids)

    categories = CategoryCounts()
    for cid in all_ids:
        bucket = contact_category.get(cid, "unknown")
        if bucket == "creator":
            categories.creators += 1
        elif bucket == "agency":
            categories.agencies += 1
        elif bucket == "affiliate":
            categories.affiliates += 1
        else:
            categories.unknown += 1

    return channels, categories, all_ids
