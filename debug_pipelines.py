"""
List all deal pipelines and their stages.
  python debug_pipelines.py

Use this output to tell Claude which pipeline/stage = Creator, Agency, Affiliate.
"""
import json, requests
from dotenv import load_dotenv
load_dotenv()
from src.config import cfg

BASE = "https://api.hubapi.com"
HEADERS = {"Authorization": f"Bearer {cfg.HUBSPOT_ACCESS_TOKEN}"}

r = requests.get(f"{BASE}/crm/v3/pipelines/deals", headers=HEADERS, timeout=15)
r.raise_for_status()

for pipeline in r.json().get("results", []):
    print(f"\nPipeline: {pipeline['label']!r}  (id: {pipeline['id']})")
    for stage in pipeline.get("stages", []):
        print(f"  Stage: {stage['label']!r}  (id: {stage['id']})")
