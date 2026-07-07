"""Kaggle kernel for the Poisoned Tools core matrix (design §6).

Self-gating: setup -> pull+verify the five Q8_0 tags -> run all check gates ->
timed PILOT on real GPU -> extrapolate full runtime, proceed only if <= budget
-> full matrix (resumable). Logs to /kaggle/working/runs/.

Writes a running /kaggle/working/DIAG.txt (fetched reliably via `kernels output`)
so failures are diagnosable even when Kaggle's own log endpoint is flaky.
"""

import json
import shutil
import subprocess
import time
import traceback
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

WORK = "/kaggle/working"
REPO = f"{WORK}/poisoned-tools"
DIAG = f"{WORK}/DIAG.txt"
MODELS = ["qwen2.5:1.5b-instruct-q8_0", "qwen2.5:3b-instruct-q8_0",
          "qwen2.5:7b-instruct-q8_0", "llama3.2:1b",
          "llama3.2:3b-instruct-q8_0"]
BUDGET_GPU_H = 22.0
PILOT_TASK = "t02"


def diag(msg):
    with open(DIAG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")
    print(msg, flush=True)


def sh(cmd, check=True, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    tail = (r.stdout or "")[-1200:] + (("\nSTDERR:" + (r.stderr or "")[-800:])
                                       if r.stderr else "")
    diag(f"$ {cmd}\n  rc={r.returncode}  {tail}")
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {cmd}")
    return r


def wait_ollama():
    for _ in range(120):
        try:
            urllib.request.urlopen("http://localhost:11434/api/version", timeout=5)
            return True
        except Exception:
            time.sleep(1)
    return False


def mean_wall_by_model(run_dir):
    walls = defaultdict(list)
    for p in Path(run_dir).glob("*/*.json"):
        ep = json.loads(p.read_text(encoding="utf-8"))
        walls[ep["model"]].append(ep.get("wall_s", 0.0))
    return {m: sum(v) / len(v) for m, v in walls.items() if v}


def main():
    open(DIAG, "w").close()
    diag("=== STEP 0: gpu ===")
    sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", check=False)

    diag("=== STEP 1: locate + extract code ===")
    if Path(REPO).exists():
        shutil.rmtree(REPO)
    Path(REPO).mkdir(parents=True)
    inp = Path("/kaggle/input")
    diag(f"  /kaggle/input contents: {[p.name for p in inp.glob('*')]}")
    zips = list(inp.rglob("poisoned-tools-code.zip"))
    if zips:
        diag(f"  unzip {zips[0]}")
        shutil.unpack_archive(str(zips[0]), REPO)
    else:
        hits = list(inp.rglob("run.py"))
        if not hits:
            raise RuntimeError("code payload not found under /kaggle/input")
        shutil.copytree(hits[0].parent, REPO, dirs_exist_ok=True)
    assert (Path(REPO) / "run.py").exists(), "payload missing run.py"

    diag("=== STEP 2: deps + world + gates ===")
    sh("pip -q install requests==2.32.3 PyYAML==6.0.2", check=False)
    sh("python data/generate.py", cwd=REPO)
    for gate in ("injections.check", "grading.check_grader",
                 "defenses.check_defenses", "grading.check_tasks"):
        sh(f"python -m {gate}", cwd=REPO)

    diag("=== STEP 3: ollama install + serve ===")
    sh("apt-get install -y -qq zstd || (apt-get update -qq && "
       "apt-get install -y -qq zstd)", check=False)   # ollama installer needs zstd
    sh("curl -fsSL https://ollama.com/install.sh | sh")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    if not wait_ollama():
        raise RuntimeError("ollama serve did not come up")

    diag("=== STEP 4: pull + VERIFY the five Q8_0 tags ===")
    missing = []
    for m in MODELS:
        r = sh(f"ollama pull {m}", check=False, cwd=REPO)
        if r.returncode != 0:
            missing.append(m)
        else:
            sh(f"ollama show {m} | grep -i quant || true", check=False, cwd=REPO)
    if missing:
        raise RuntimeError(f"MODEL TAGS NOT FOUND: {missing} — fix tags in "
                           f"configs/matrix.py + kernel and re-push.")

    diag("=== STEP 5: timed pilot ===")
    run_dir = f"{WORK}/runs/core_v1"
    for m in MODELS:
        sh(f"python run.py --arms B --models {m} --defenses D0 "
           f"--tasks {PILOT_TASK} --seeds 1 --run-id core_v1 --out {WORK}/runs",
           cwd=REPO)

    import sys
    sys.path.insert(0, REPO)
    from configs.matrix import build_specs
    totals = Counter()
    for arm in "ABC":
        for s in build_specs(arm):
            totals[s["model"]] += 1
    means = mean_wall_by_model(run_dir)
    fired = asr = n = 0
    for p in Path(run_dir).glob("*/*.json"):
        ep = json.loads(p.read_text(encoding="utf-8"))
        if ep.get("injection"):
            n += 1
            fired += int(ep.get("injection_fired", False))
            asr += int(bool(ep["label"]["asr"]))
    diag(f"  pilot: {n} injected, fired {fired}/{n}, ASR {asr}/{n}")
    diag(f"  mean wall/model: { {m: round(v,1) for m,v in means.items()} }")
    # Fail only on a true pipeline break (nothing fired). A fire rate < 100% is
    # EXPECTED: some episodes the agent never calls the target tool, so there is
    # no poisoned surface. The analysis conditions on injection_fired.
    if n == 0 or fired == 0:
        raise RuntimeError("PILOT FAILED: no injection fired at all -> pipeline "
                           "broken (agent never reached the poisoned tool).")
    diag(f"  note: {n - fired}/{n} episodes had no exposure (agent didn't call "
         f"the target tool) - expected; conditioned out in analysis.")
    est_h = sum(totals[m] * means.get(m, 0.0) for m in totals) / 3600
    diag(f"  full episodes {sum(totals.values())} | EXTRAPOLATED {est_h:.1f} "
         f"GPU-h (budget {BUDGET_GPU_H})")
    if est_h > BUDGET_GPU_H:
        diag(f"ABORT: {est_h:.1f}h exceeds budget; pilot logs saved. Apply "
             f"design §10 rescale levers.")
        return

    diag("=== STEP 6: FULL MATRIX ===")
    t0 = time.time()
    sh(f"python run.py --arms A,B,C --run-id core_v1 --out {WORK}/runs", cwd=REPO)
    diag(f"  full run wall: {(time.time()-t0)/60:.1f} min")

    summ = {"episodes": 0, "by_arm": {}, "est_h": round(est_h, 1)}
    for p in Path(run_dir).glob("*/*.json"):
        ep = json.loads(p.read_text(encoding="utf-8"))
        d = summ["by_arm"].setdefault(ep.get("arm", "?"),
                                      {"n": 0, "asr": 0, "benign": 0})
        d["n"] += 1
        if ep.get("injection"):
            d["asr"] += int(bool(ep["label"]["asr"]))
        d["benign"] += int(bool(ep["label"]["benign_success"]))
        summ["episodes"] += 1
    diag("MATRIX SUMMARY: " + json.dumps(summ))
    Path(f"{WORK}/matrix_summary.json").write_text(json.dumps(summ, indent=1))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        diag("FATAL:\n" + traceback.format_exc())
        raise
