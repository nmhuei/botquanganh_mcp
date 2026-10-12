"""Profile exact breakdown of workspace_context(bind) latency."""

import os
import shutil
import time
from pathlib import Path

BENCHMARK_DIR = Path("/home/light/Downloads/bqa-trash/benchmarks_profile")
if BENCHMARK_DIR.exists():
    shutil.rmtree(BENCHMARK_DIR)
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)

os.environ["ATTRIBUTION_MODE"] = "enforce"
os.environ["HOST_CHAT_WORKSPACES"] = "true"
os.environ["HOST_CHAT_ROOT"] = str(BENCHMARK_DIR / "workspaces")
os.environ["HOST_DEFAULT_DIR"] = str(BENCHMARK_DIR)
os.environ["HOST_WORKSPACE_DIR"] = str(BENCHMARK_DIR)

import app.config
app.config.ATTRIBUTION_MODE = "enforce"
app.config.HOST_CHAT_WORKSPACES = True
app.config.HOST_CHAT_ROOT = str(BENCHMARK_DIR / "workspaces")
app.config.HOST_DEFAULT_DIR = BENCHMARK_DIR
app.config.HOST_WORKSPACE_DIR = BENCHMARK_DIR

from app.chat_workspace import WorkspaceManager
from app.tools.workspace_context import workspace_context

# Measure component by component
t0 = time.perf_counter()
mgr = WorkspaceManager(Path(app.config.HOST_CHAT_ROOT))
t_mgr = time.perf_counter()

# Root dir check
mgr.root.mkdir(parents=True, exist_ok=True)
t_mkdir = time.perf_counter()

# Disk usage check
stat = shutil.disk_usage(mgr.root)
t_statvfs = time.perf_counter()

# Enforce capacity (iterdir)
list(mgr.root.iterdir())
t_iterdir = time.perf_counter()

# Actual bind call
res_bind = workspace_context(action="bind", chat_id="perf-profile-01")
t_end = time.perf_counter()

print(f"Setup WorkspaceManager: {(t_mgr - t0)*1000:.3f} ms")
print(f"mkdir root: {(t_mkdir - t_mgr)*1000:.3f} ms")
print(f"disk_usage (statvfs): {(t_statvfs - t_mkdir)*1000:.3f} ms")
print(f"iterdir capacity scan: {(t_iterdir - t_statvfs)*1000:.3f} ms")
print(f"Total workspace_context(bind) call: {(t_end - t_iterdir)*1000:.3f} ms")
