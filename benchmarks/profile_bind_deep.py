"""Deep line-by-line profiling of create_or_bind and _initialize."""

import os
import shutil
import time
from pathlib import Path

BENCHMARK_DIR = Path("/home/light/Downloads/bqa-trash/benchmarks_profile_deep")
if BENCHMARK_DIR.exists():
    shutil.rmtree(BENCHMARK_DIR)
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

import app.config
app.config.ATTRIBUTION_MODE = "enforce"
app.config.HOST_CHAT_WORKSPACES = True
app.config.HOST_CHAT_ROOT = str(BENCHMARK_DIR / "workspaces")

from app.chat_workspace import (
    WorkspaceManager,
    _atomic_write,
    _json_line_bytes,
    rebuild_state,
    generate_session_token,
    META_NAME,
    NOTES_NAME,
    JOURNAL_NAME,
)

ws_dir = BENCHMARK_DIR / "workspaces" / "profile-deep-01"
ws_dir.mkdir(parents=True, exist_ok=True)

# Test individual operations
t0 = time.perf_counter()
(ws_dir / NOTES_NAME).mkdir(exist_ok=True)
t1 = time.perf_counter()

raw_token, token_hash = generate_session_token()
t2 = time.perf_counter()

meta = {
    "chat_id": "profile-deep-01",
    "created_at": "2026-10-07T12:00:00Z",
    "schema": 1,
    "token_hash": token_hash,
    "next_seq": 1,
}
meta_path = ws_dir / META_NAME
desc = os.open(meta_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(desc, _json_line_bytes(meta))
t3 = time.perf_counter()

# Fsync meta
os.fsync(desc)
os.close(desc)
t4 = time.perf_counter()

(ws_dir / JOURNAL_NAME).touch(mode=0o600)
t5 = time.perf_counter()

# Rebuild state (includes _atomic_write with fsync)
rebuild_state(ws_dir)
t6 = time.perf_counter()

# Write resume card (atomic write with fsync)
mgr = WorkspaceManager(BENCHMARK_DIR / "workspaces")
mgr._write_resume_card(ws_dir, "profile-deep-01", raw_token)
t7 = time.perf_counter()

# Record last session (atomic write with fsync)
mgr._record_last_session("profile-deep-01")
t8 = time.perf_counter()

print("--- Breakdown of I/O within create_or_bind ---")
print(f"mkdir notes: {(t1 - t0)*1000:.3f} ms")
print(f"generate token: {(t2 - t1)*1000:.3f} ms")
print(f"open + write meta.json: {(t3 - t2)*1000:.3f} ms")
print(f"os.fsync meta.json: {(t4 - t3)*1000:.3f} ms  <-- PHYSICAL FSYNC #1")
print(f"touch journal.jsonl: {(t5 - t4)*1000:.3f} ms")
print(f"rebuild_state (STATE.md atomic write + fsync): {(t6 - t5)*1000:.3f} ms  <-- PHYSICAL FSYNC #2")
print(f"_write_resume_card (RESUME_CARD.md atomic write + fsync): {(t7 - t6)*1000:.3f} ms  <-- PHYSICAL FSYNC #3")
print(f"_record_last_session (.last_session atomic write + fsync): {(t8 - t7)*1000:.3f} ms  <-- PHYSICAL FSYNC #4")
print(f"Total _initialize time: {(t8 - t0)*1000:.3f} ms")
