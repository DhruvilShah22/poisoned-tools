# poisoned-tools

**How often do small open-weight tool agents (1–7B) obey adversarial
instructions planted inside tool outputs — where do they get hijacked, and do
cheap training-free defenses actually help, at what cost to benign task success?**

Research portfolio project; direct sequel to
[slm-agent-eval](https://github.com/DhruvilShah22/slm-agent-eval) (*Quantization,
Not Just Scale*). Where paper 1 measured **accidental** failure of small local
agents, this measures **induced** failure: indirect prompt injection. Quantization
is held **fixed at Q8_0** — the variables are the injection and the defense.

## Status

Complete. **Findings and paper-style write-up: [`docs/paper.md`](docs/paper.md);**
pre-registration: [`docs/injection_design.md`](docs/injection_design.md).
Headlines from 4,224 seeded episodes (blind-validated grading: ASR κ = 1.00,
compliance κ = 0.95): injections in **tool-error strings** are obeyed most (ASR
0.24) and in **search bodies** least (0.005) — the reverse of the trusted-surface
intuition; **larger models obey injections more** (qwen 1.5B 0.02 → 3B 0.18 → 7B
0.24); **no cheap defense significantly reduces ASR**, and a goal-reminder
"sandwich" costs **−19pp benign utility**; resistance collapses under repetition
(qwen-3B resist⁸ = 0.50).

## Reproducing

Every number in `docs/paper.md` regenerates from the committed raw logs in
`runs/core_v1/`:

```
pip install -r requirements.txt -r requirements-analysis.txt
python data/generate.py                 # deterministic world (CI asserts no diff)
python -m injections.check              # injection library + detector gate
python -m grading.check_grader          # grader gate (branches + token hygiene)
python -m defenses.check_defenses       # defenses gate
python -m grading.check_tasks           # all 25 golds resolve
python -m analysis.compare_labels       # grader vs blind hand labels (kappa)
python analysis/analyze.py              # tables from logs
python analysis/make_figures.py         # figures from logs
```

Re-running the **experiments** (new episodes, ~4 GPU-h on a free Kaggle P100 or
days on a CPU): the self-gating kernel in `kaggle/` pulls the five Q8_0 models
via Ollama, runs a timed pilot + budget check, then the full matrix (resumable).
See `kaggle/LAUNCH.md`.

## Layout

```
docs/injection_design.md   pre-registration: RQs, hypotheses, taxonomy, stats, ethics
docs/paper.md              the write-up (every number from analysis/)
injections/                templates + runtime poisoner + deterministic ASR detectors
defenses/                  D0-D5 training-free inference-time defenses
harness/                   agent loop (reused from paper 1) + injection/defense hooks
tools/  data/  tasks/      the 5 local tools, seeded synthetic world, 25 tasks
grading/                   ASR + compliance-anatomy + benign graders; blind kappa
analysis/                  analyze.py, make_figures.py, blind_sample.py, results
run.py  configs/matrix.py  resumable runner + the three-arm matrix
kaggle/                    self-gating GPU kernel + code-dataset staging + launch doc
runs/core_v1/              the 4,224 committed episode logs (every number traces here)
STATE.json  PROGRESS.md    machine + human project checkpoints
```
