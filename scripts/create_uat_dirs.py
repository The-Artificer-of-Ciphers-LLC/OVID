import sys
import os
import shutil

# Add ovid-client/src to path
sys.path.insert(0, os.path.abspath('ovid-client/src'))
sys.path.insert(0, os.path.abspath('ovid-client/tests'))

from conftest_bd import make_mpls_file

# Clean up any previous test dirs
if os.path.exists("uat_dirs"):
    shutil.rmtree("uat_dirs")
os.makedirs("uat_dirs")

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)

# Test 1: BD Fingerprint from Folder (Tier 2 — no AACS)
t1 = "uat_dirs/t1_bd2"
write_file(f"{t1}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))

# Test 2: BD Fingerprint from Folder (Tier 1 — with AACS)
t2 = "uat_dirs/t2_bd1"
write_file(f"{t2}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))
write_file(f"{t2}/AACS/Unit_Key_RO.inf", b"dummy_aacs_data_for_tier1")

# Test 3: UHD Fingerprint Detection
t3 = "uat_dirs/t3_uhd"
write_file(f"{t3}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0300", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))
t3_aacs = "uat_dirs/t3_uhd_aacs"
write_file(f"{t3_aacs}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0300", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))
write_file(f"{t3_aacs}/AACS/Unit_Key_RO.inf", b"dummy_aacs_data")

# Test 5 & 7: DVD
t5 = "uat_dirs/t5_dvd"
write_file(f"{t5}/VIDEO_TS/VIDEO_TS.IFO", b"DVDVIDEO-VMG" + b"\x00"*2000)
write_file(f"{t5}/VIDEO_TS/VTS_01_0.IFO", b"DVDVIDEO-VTS" + b"\x00"*2000)

# Test 8: AACS Tier 1 Fallback to Tier 2 (AACS dir present but empty/no Unit_Key_RO.inf)
t8 = "uat_dirs/t8_fallback"
write_file(f"{t8}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))
os.makedirs(f"{t8}/AACS", exist_ok=True)

# Test 9: Obfuscation Playlist Filtering (one 90 min, several 30 sec)
t9 = "uat_dirs/t9_obfuscation"
write_file(f"{t9}/BDMV/PLAYLIST/00000.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00000", "in_time": 0.0, "out_time": 5400.0}])) # 90 mins
write_file(f"{t9}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 30.0}]))
write_file(f"{t9}/BDMV/PLAYLIST/00002.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00002", "in_time": 0.0, "out_time": 30.0}]))

# Test 10: All Playlists Under 60 Seconds
t10 = "uat_dirs/t10_all_under_60"
write_file(f"{t10}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 59.0}]))
write_file(f"{t10}/BDMV/PLAYLIST/00002.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00002", "in_time": 0.0, "out_time": 30.0}]))

# Edge Case: Exactly 60-second playlist
edge_60 = "uat_dirs/edge_60s"
write_file(f"{edge_60}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 60.0}]))

# Edge Case: Mixed valid and malformed
edge_mixed = "uat_dirs/edge_mixed"
write_file(f"{edge_mixed}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))
write_file(f"{edge_mixed}/BDMV/PLAYLIST/00002.mpls", b"invalid_binary_data")

# Edge Case: BD and DVD directories coexist
edge_coexist = "uat_dirs/edge_coexist"
write_file(f"{edge_coexist}/BDMV/PLAYLIST/00001.mpls", make_mpls_file(version="0200", play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 70.0}]))
write_file(f"{edge_coexist}/VIDEO_TS/VIDEO_TS.IFO", b"DVDVIDEO-VMG" + b"\x00"*2000)
write_file(f"{edge_coexist}/VIDEO_TS/VTS_01_0.IFO", b"DVDVIDEO-VTS" + b"\x00"*2000)

print("Created UAT directories.")
