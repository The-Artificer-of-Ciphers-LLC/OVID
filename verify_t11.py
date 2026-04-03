import sys
import os
import json

sys.path.insert(0, os.path.abspath('ovid-client/src'))

from ovid.bd_disc import BDDisc
from ovid.cli import _build_bd_submit_payload

try:
    disc = BDDisc.from_path("uat_dirs/t1_bd2")
    payload = _build_bd_submit_payload(
        bd_disc=disc,
        title="Test Movie",
        year=2026,
        tmdb_id=123,
        imdb_id="tt123",
        edition_name="Director's Cut",
        disc_number=1,
        total_discs=1
    )
    
    cond = (
        payload.get("format") == "Blu-ray" and
        payload.get("fingerprint", "").startswith("bd2-") and
        "titles" in payload and
        len(payload["titles"]) == 1 and
        payload["titles"][0].get("is_main_feature") is True
    )
    status = "PASS" if cond else "FAIL"
    
    with open("uat_results.json", "r") as f:
        results = json.load(f)
    
    for r in results:
        if r["name"] == "Test 11: BD Submit Payload Format":
            r["status"] = status
            r["notes"] = f"Payload verified: {cond}"
            
    with open("uat_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"[{status}] Test 11: BD Submit Payload Format")

except Exception as e:
    print(f"[FAIL] Test 11: Exception {e}")
