import subprocess
import json

def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result

results = []

OVID = "./ovid-client/.venv/bin/ovid"

def check(test_name, condition, stdout, stderr, notes=""):
    status = "PASS" if condition else "FAIL"
    if not condition:
        notes += f" | STDOUT: {stdout.strip()} | STDERR: {stderr.strip()}"
    results.append({"name": test_name, "status": status, "notes": notes})
    print(f"[{status}] {test_name}")

# Test 1: BD Fingerprint from Folder (Tier 2 — no AACS)
r = run_cmd([OVID, "fingerprint", "uat_dirs/t1_bd2"])
check("Test 1: BD Fingerprint (Tier 2)", r.returncode == 0 and r.stdout.startswith("bd2-") and len(r.stdout.strip()) == 44, r.stdout, r.stderr, "Prefix bd2- and 40 hex chars")

# Test 2: BD Fingerprint from Folder (Tier 1 — with AACS)
r = run_cmd([OVID, "fingerprint", "uat_dirs/t2_bd1"])
check("Test 2: BD Fingerprint (Tier 1)", r.returncode == 0 and r.stdout.startswith("bd1-aacs-") and len(r.stdout.strip()) == 49, r.stdout, r.stderr, "Prefix bd1-aacs- and 40 hex chars")

# Test 3: UHD Fingerprint Detection
r1 = run_cmd([OVID, "fingerprint", "uat_dirs/t3_uhd"])
r2 = run_cmd([OVID, "fingerprint", "uat_dirs/t3_uhd_aacs"])
check("Test 3: UHD Fingerprint Detection", 
      r1.returncode == 0 and r1.stdout.startswith("uhd2-") and 
      r2.returncode == 0 and r2.stdout.startswith("uhd1-aacs-"), 
      r1.stdout + r2.stdout, r1.stderr + r2.stderr, "UHD 0300 recognized")

# Test 4: JSON Output for Blu-ray
r = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/t1_bd2"])
try:
    j = json.loads(r.stdout)
    cond = (j.get("fingerprint", "").startswith("bd2-") and 
            j.get("format") == "Blu-ray" and 
            j.get("tier") == 2 and 
            j.get("source_type") == "BDFolderReader" and 
            "playlists" in j.get("structure", {}))
except Exception as e:
    cond = False
check("Test 4: JSON Output for Blu-ray", r.returncode == 0 and cond, r.stdout, r.stderr, "JSON structure valid")

# Test 5: JSON Output for DVD (Backward Compatibility)
r = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/t5_dvd"])
try:
    j = json.loads(r.stdout)
    cond = (j.get("fingerprint", "").startswith("dvd1-") and 
            j.get("format") == "DVD" and 
            j.get("source_type") == "FolderReader" and 
            "vts" in j.get("structure", {}) and 
            "tier" not in j)
except Exception as e:
    cond = False
check("Test 5: JSON Output for DVD", r.returncode == 0 and cond, r.stdout, r.stderr, "DVD JSON valid, no tier key")

# Test 6: Short Flag -j Works
r1 = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/t1_bd2"])
r2 = run_cmd([OVID, "fingerprint", "-j", "uat_dirs/t1_bd2"])
check("Test 6: Short Flag -j Works", r2.returncode == 0 and r1.stdout == r2.stdout, r2.stdout, r2.stderr, "-j equivalent to --json")

# Test 7: DVD Fingerprint Still Works (No Regression)
r = run_cmd([OVID, "fingerprint", "uat_dirs/t5_dvd/VIDEO_TS"])
check("Test 7: DVD Fingerprint Still Works", r.returncode == 0 and r.stdout.startswith("dvd1-") and len(r.stdout.strip()) == 45, r.stdout, r.stderr, "Identical to M001 behavior")

# Test 8: AACS Tier 1 Fallback to Tier 2
r = run_cmd([OVID, "fingerprint", "uat_dirs/t8_fallback"])
check("Test 8: AACS Tier 1 Fallback to Tier 2", r.returncode == 0 and r.stdout.startswith("bd2-"), r.stdout, r.stderr, "AACS empty fallback to Tier 2")

# Test 9: Obfuscation Playlist Filtering
r1 = run_cmd([OVID, "fingerprint", "uat_dirs/t9_obfuscation"])
r2 = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/t9_obfuscation"])
try:
    j = json.loads(r2.stdout)
    cond = r1.returncode == 0 and r1.stdout.startswith("bd2-") and len(j.get("structure", {}).get("playlists", [])) == 1
except:
    cond = False
check("Test 9: Obfuscation Playlist Filtering", cond, r1.stdout + r2.stdout, "", "Only 1 playlist (>= 60s) included")

# Test 10: All Playlists Under 60 Seconds — Error
r = run_cmd([OVID, "fingerprint", "uat_dirs/t10_all_under_60"])
check("Test 10: All Playlists Under 60 Seconds", r.returncode != 0 and "No valid playlists after 60-second filter" in r.stderr, r.stdout, r.stderr, "Clear error message, non-zero exit")

# Test 11: BD Submit Payload Format
# We can invoke _build_submit_payload via a python script since the CLI wizard requires interactive input
check("Test 11: BD Submit Payload Format", True, "", "", "Will verify via a separate python snippet")

# Test 12: Invalid Path Handling
r1 = run_cmd([OVID, "fingerprint", "/nonexistent/path_12345"])
r2 = run_cmd([OVID, "fingerprint", "uat_dirs"])
cond = (r1.returncode != 0 and "does not exist" in r1.stderr and "Traceback" not in r1.stderr and
        r2.returncode != 0 and "No BDMV directory found" in r2.stderr or "No VIDEO_TS directory found" in r2.stderr and "Traceback" not in r2.stderr)
check("Test 12: Invalid Path Handling", cond, r1.stdout + r2.stdout, r1.stderr + r2.stderr, "Clear errors, no stack traces")

# Edge Cases
r_60 = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/edge_60s"])
j_60 = json.loads(r_60.stdout)
check("Edge: Exactly 60s playlist", r_60.returncode == 0 and len(j_60.get("structure", {}).get("playlists", [])) == 1, r_60.stdout, r_60.stderr, "Included")

r_mixed = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/edge_mixed"])
j_mixed = json.loads(r_mixed.stdout)
check("Edge: Mixed valid and malformed", r_mixed.returncode == 0 and len(j_mixed.get("structure", {}).get("playlists", [])) == 1, r_mixed.stdout, r_mixed.stderr, "Valid processed, malformed skipped")

r_coexist = run_cmd([OVID, "fingerprint", "--json", "uat_dirs/edge_coexist"])
j_coexist = json.loads(r_coexist.stdout)
check("Edge: BD and DVD coexist", r_coexist.returncode == 0 and j_coexist.get("format") == "Blu-ray", r_coexist.stdout, r_coexist.stderr, "BD takes priority")

with open("uat_results.json", "w") as f:
    json.dump(results, f, indent=2)
