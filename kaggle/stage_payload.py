"""Stage the repo code as a SINGLE zip for upload as a private Kaggle Dataset
(the kernel mounts it and unzips). A single file avoids the CLI's default
skip-subfolders behaviour.

    python kaggle/stage_payload.py
    kaggle datasets create  -p kaggle/upload            # first time
    kaggle datasets version -p kaggle/upload -m "..."   # updates

Excludes git, caches, runs, the kaggle/ dir, and any credentials.
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TREE = ROOT / "kaggle" / "_tree"
UPLOAD = ROOT / "kaggle" / "upload"
ZIP_STEM = "poisoned-tools-code"
INCLUDE = ["harness", "tools", "grading", "injections", "defenses", "configs",
           "data/generate.py", "tasks/tasks.yaml", "run.py",
           "requirements.txt", "requirements-analysis.txt",
           "docs/injection_design.md"]
DATASET_META = {
    "title": "poisoned-tools-code",
    "id": "contactshahdhruvil/poisoned-tools-code",
    "licenses": [{"name": "CC0-1.0"}],
}


def main():
    for d in (TREE, UPLOAD):
        if d.exists():
            shutil.rmtree(d)
    TREE.mkdir(parents=True)
    UPLOAD.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for rel in INCLUDE:
        src, dst = ROOT / rel, TREE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ignore)
        else:
            shutil.copy2(src, dst)
    shutil.make_archive(str(UPLOAD / ZIP_STEM), "zip", root_dir=TREE)
    (UPLOAD / "dataset-metadata.json").write_text(
        json.dumps(DATASET_META, indent=1), encoding="utf-8")
    shutil.rmtree(TREE)
    zsize = (UPLOAD / f"{ZIP_STEM}.zip").stat().st_size
    print(f"wrote {UPLOAD / (ZIP_STEM + '.zip')} ({zsize} bytes) + "
          f"dataset-metadata.json")


if __name__ == "__main__":
    main()
