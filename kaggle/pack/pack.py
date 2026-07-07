"""Pack the completed core run's logs into ONE downloadable tarball.
Mounts contactshahdhruvil/poisoned-tools-core output via kernel_sources; no GPU.
"""
import shutil, tarfile
from pathlib import Path
inp = Path("/kaggle/input")
runs = next((c for c in inp.rglob("core_v1") if c.is_dir()), None)
assert runs, f"core_v1 not found; /kaggle/input has {[p.name for p in inp.glob('*')]}"
out = Path("/kaggle/working")
n = sum(1 for _ in runs.rglob("*.json"))
with tarfile.open(out / "runs.tar.gz", "w:gz") as t:
    t.add(runs, arcname="core_v1")
for name in ("DIAG.txt", "matrix_summary.json"):
    hits = list(inp.rglob(name))
    if hits:
        shutil.copy(hits[0], out / name)
print(f"packed {n} json logs into runs.tar.gz")
