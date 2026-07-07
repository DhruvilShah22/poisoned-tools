"""Compare blind hand labels against the programmatic injection grader.

Recomputes ASR + compliance with the CURRENT grader (grading/label.py), not any
value stored at run time, so this validates whatever code the analysis will use.
Reports raw agreement and Cohen's kappa for (a) binary ASR and (b) compliance
category, plus a list of disagreements for reconciliation (design §10).

    python -m analysis.compare_labels [--run-dir <abs path>]

Reads analysis/labeling/sample_keys.json (from blind_sample.py) and
analysis/labeling/labels.json (hand-filled), each label keyed by the unique
per-episode `idx` shown in blind_sample.md:
  {"idx": int, "asr": bool, "compliance": <category>}
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from grading.kappa import cohen_kappa  # noqa: E402
from grading.label import label_episode  # noqa: E402

LAB = ROOT / "analysis" / "labeling"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args()

    tasks = {t["id"]: t for t in yaml.safe_load(
        (ROOT / "tasks" / "tasks.yaml").read_text(encoding="utf-8"))}
    keys = json.loads((LAB / "sample_keys.json").read_text(encoding="utf-8"))
    labels = json.loads((LAB / "labels.json").read_text(encoding="utf-8"))["labels"]
    by_idx = {l["idx"]: l for l in labels}

    asr_pairs, comp_pairs, disagreements = [], [], []
    for k in keys:
        path = ROOT / k["file"]
        ep = json.loads(path.read_text(encoding="utf-8"))
        auto = label_episode(ep, dict(tasks[k["task"]]))
        hum = by_idx[k["idx"]]
        asr_pairs.append((bool(auto["asr"]), bool(hum["asr"])))
        comp_pairs.append((auto["compliance"], hum["compliance"]))
        if bool(auto["asr"]) != bool(hum["asr"]) or auto["compliance"] != hum["compliance"]:
            disagreements.append(
                f"{k['model']}/{k['defense']}/{k['task']}/s{k['seed']}: "
                f"auto=({auto['asr']},{auto['compliance']}) "
                f"human=({hum['asr']},{hum['compliance']}) "
                f"answer={ep.get('final_answer')!r:.60}")

    n = len(asr_pairs)
    print(f"n={n}")
    print(f"ASR:        agreement {sum(a == b for a, b in asr_pairs)}/{n} "
          f"= {sum(a == b for a, b in asr_pairs)/n:.3f}, "
          f"kappa = {cohen_kappa(asr_pairs):.3f}")
    print(f"compliance: agreement {sum(a == b for a, b in comp_pairs)}/{n} "
          f"= {sum(a == b for a, b in comp_pairs)/n:.3f}, "
          f"kappa = {cohen_kappa(comp_pairs):.3f}")
    for d in disagreements:
        print("DISAGREE:", d)


if __name__ == "__main__":
    main()
