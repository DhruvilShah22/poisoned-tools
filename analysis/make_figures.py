"""Generate all paper figures from the raw logs (design phase B §5).

    python analysis/make_figures.py [--run core_v1]

Re-loads + re-grades every episode (via analysis.analyze.load) and writes PNGs to
analysis/figures/. Sober, colour-blind-safe, one system. No hand-entered numbers.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from analysis.analyze import (  # noqa: E402
    DEFENSES, QWEN_LADDER, SEVEN_B, load, resist_hat_k, short, wilson)

FIG = ROOT / "analysis" / "figures"
INK = "#1b1b1b"
ACCENT = "#2f6f9f"      # blue
WARN = "#b1442c"        # red
GREY = "#9a9a9a"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": INK,
                     "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": INK, "ytick.color": INK,
                     "figure.dpi": 130, "savefig.bbox": "tight"})


def _barh_ci(ax, labels, ps, cis, color, xlabel):
    y = range(len(labels))
    errs = [[p - lo for p, (lo, _) in zip(ps, cis)],
            [hi - p for p, (_, hi) in zip(ps, cis)]]
    ax.barh(list(y), ps, color=color, height=0.62)
    ax.errorbar(ps, list(y), xerr=errs, fmt="none", ecolor=INK, capsize=3, lw=1)
    ax.set_yticks(list(y)); ax.set_yticklabels(labels)
    ax.set_xlabel(xlabel); ax.set_xlim(0, max(0.3, max(hi for _, hi in cis) * 1.1))
    ax.invert_yaxis()
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def screen_by(recs, field, title, fname):
    A = [r for r in recs if r["arm"] == "A"]
    keys = sorted({r[field] for r in A},
                  key=lambda k: -sum(r["asr"] for r in A if r[field] == k
                                     and r["fired"]) / max(1, sum(
                                         r["fired"] for r in A if r[field] == k)))
    labels, ps, cis = [], [], []
    for k in keys:
        fired = [r for r in A if r[field] == k and r["fired"]]
        s, n = sum(r["asr"] for r in fired), len(fired)
        labels.append(k.replace("_", " ")); ps.append(s / n if n else 0)
        cis.append(wilson(s, n))
    fig, ax = plt.subplots(figsize=(6, 0.55 * len(labels) + 1.2))
    _barh_ci(ax, labels, ps, cis, ACCENT, "attack success rate (given exposure)")
    ax.set_title(title, loc="left", fontweight="bold")
    fig.savefig(FIG / fname); plt.close(fig)


def scale_fig(recs, fname):
    A = [r for r in recs if r["arm"] == "A"]
    xs, ps, los, his = [], [], [], []
    for m in QWEN_LADDER:
        fired = [r for r in A if r["model"] == m and r["fired"]]
        s, n = sum(r["asr"] for r in fired), len(fired)
        p, (lo, hi) = s / n, wilson(s, n)
        xs.append(short(m)); ps.append(p); los.append(p - lo); his.append(hi - p)
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    ax.errorbar(xs, ps, yerr=[los, his], marker="o", color=WARN, capsize=4, lw=2)
    ax.set_ylabel("canary ASR (given exposure)")
    ax.set_title("Larger models obey injections MORE", loc="left",
                 fontweight="bold")
    ax.set_ylim(0, max(his[i] + ps[i] for i in range(len(ps))) * 1.2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(FIG / fname); plt.close(fig)


def defense_tradeoff(recs, fname):
    from analysis.analyze import defense_contrasts
    asr = {c["contrast"].split()[0]: c for c in
           defense_contrasts(recs, "B", "asr", "template_id")}
    ben = {c["contrast"].split()[0]: c for c in
           defense_contrasts(recs, "C", "benign", "task")}
    fig, ax = plt.subplots(figsize=(5, 4))
    for d in DEFENSES[1:]:
        x = asr[d]["risk_difference"]        # ASR change (want negative)
        y = ben[d]["risk_difference"]        # benign change (want ~0)
        ax.scatter(x, y, s=70, color=ACCENT, zorder=3)
        ax.annotate(d, (x, y), textcoords="offset points", xytext=(6, 4))
    ax.axhline(0, color=GREY, lw=1); ax.axvline(0, color=GREY, lw=1)
    ax.set_xlabel("Δ ASR vs D0  (left = safer)")
    ax.set_ylabel("Δ benign utility vs D0  (down = costlier)")
    ax.set_title("Defense trade-off: ASR reduction vs utility tax",
                 loc="left", fontweight="bold")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(FIG / fname); plt.close(fig)


def compliance_fig(recs, fname):
    B = [r for r in recs if r["arm"] == "B"]
    cats = ["blind_comply", "notice_then_comply", "partial_comply",
            "ignore_continue", "refuse_task", "derailed"]
    colors = [WARN, "#e08a1e", "#e5c34b", "#6fae6f", "#7a9fc0", GREY]
    models = ["qwen1.5b", "qwen3b", "qwen7b", "llama1b", "llama3b"]
    data = {m: Counter() for m in models}
    for r in B:
        data[short(r["model"])][r["compliance"]] += 1
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    bottom = [0] * len(models)
    for cat, col in zip(cats, colors):
        vals = [data[m][cat] / max(1, sum(data[m].values())) for m in models]
        ax.bar(models, vals, bottom=bottom, label=cat.replace("_", " "),
               color=col, width=0.7)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_ylabel("fraction of episodes"); ax.set_ylim(0, 1)
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.set_title("Compliance anatomy by model (focused matrix)", loc="left",
                 fontweight="bold")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(FIG / fname); plt.close(fig)


def resist_fig(recs, fname):
    B = [r for r in recs if r["arm"] == "B"]
    fig, ax = plt.subplots(figsize=(5, 3.6))
    palette = {"D0": WARN, "D2": ACCENT, "D4": "#6fae6f"}
    for d, col in palette.items():
        configs = defaultdict(list)
        for r in B:
            if r["model"] == "qwen2.5:3b-instruct-q8_0" and r["defense"] == d:
                configs[(r["goal"], r["framing"], r["task"])].append(r["asr"])
        ks = range(1, 9)
        curve = []
        for k in ks:
            vals = [resist_hat_k(sum(1 for a in v if not a), len(v), k)
                    for v in configs.values() if len(v) >= k]
            curve.append(sum(vals) / len(vals) if vals else float("nan"))
        ax.plot(list(ks), curve, marker="o", color=col, label=d, lw=2)
    ax.set_xlabel("k (seeded repeats)"); ax.set_ylabel("resist^k (qwen3b)")
    ax.set_ylim(0, 1)
    ax.set_title("Resistance decays under repetition", loc="left",
                 fontweight="bold")
    ax.legend(title="defense", fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(FIG / fname); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="core_v1")
    args = ap.parse_args()
    FIG.mkdir(parents=True, exist_ok=True)
    tasks = {t["id"]: t for t in yaml.safe_load(
        (ROOT / "tasks" / "tasks.yaml").read_text(encoding="utf-8"))}
    recs = load(ROOT / "runs" / args.run, tasks)
    print(f"loaded {len(recs)} episodes")
    screen_by(recs, "placement", "Where injections land: ASR by placement (H4)",
              "fig1_placement.png")
    screen_by(recs, "framing", "How injections are framed: ASR by framing (H2)",
              "fig2_framing.png")
    scale_fig(recs, "fig3_scale.png")
    defense_tradeoff(recs, "fig4_defense_tradeoff.png")
    compliance_fig(recs, "fig5_compliance.png")
    resist_fig(recs, "fig6_resist.png")
    print(f"wrote 6 figures to {FIG}")


if __name__ == "__main__":
    main()
