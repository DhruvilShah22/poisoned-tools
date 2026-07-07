# Launching the core matrix on free Kaggle GPU

One self-gating kernel: setup → pull+verify the five Q8_0 tags → run all check
gates → **timed pilot on real GPU** → extrapolate full runtime and **only
proceed if it fits under ~22 GPU-h** → full 4,224-episode matrix (resumable).
Logs land in `/kaggle/working/runs/` (kernel output). No GitHub needed — code
rides in a private Kaggle Dataset.

## 0. One-time auth (secure; the raw key is never handled by anyone but you)
1. Kaggle → Settings → API → **Expire API Token**, then **Create New API Token**
   (downloads `kaggle.json`).
2. `move "%USERPROFILE%\Downloads\kaggle.json" "%USERPROFILE%\.kaggle\kaggle.json"`
3. Verify: `kaggle kernels list --mine -p 1` (should list, not error).

## 1. Stage + upload the code dataset (private)
```
python kaggle/stage_payload.py
kaggle datasets create -p kaggle/payload          # first time
# later updates:  kaggle datasets version -p kaggle/payload -m "update"
```

## 2. Push + run the kernel (GPU + internet enabled in its metadata)
```
kaggle kernels push -p kaggle/kernel
```
Enable GPU in the kernel's settings if Kaggle doesn't honour the metadata flag.

## 3. Monitor / collect
```
kaggle kernels status  contactshahdhruvil/poisoned-tools-core
kaggle kernels output  contactshahdhruvil/poisoned-tools-core -p runs_from_kaggle
```
The pilot prints `EXTRAPOLATED GPU time: X h`. If it exceeds the budget the
kernel stops before the full run (apply the design §10 rescale levers). On a
session timeout, re-running resumes only the missing episodes **if** the prior
`runs/` is re-attached as an input dataset (see below).

## 4. Multi-session resume (only if one 12h session isn't enough)
Version the partial output back into a runs dataset and mount it next launch:
```
kaggle kernels output contactshahdhruvil/poisoned-tools-core -p out
# create/version a dataset from out/runs, add it to kernel-metadata dataset_sources,
# and the kernel copies it into repo/runs before running (run.py skips completed).
```
The runner already front-loads the screen + small models and runs 7B-Q8 last, so
even a truncated session yields a usable dataset.
