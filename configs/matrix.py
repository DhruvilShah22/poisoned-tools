"""Experiment matrix definition (design §6): the three arms as episode specs.

Each spec is a dict: {arm, model, defense, task, target_tool, injection|None,
seed}. The runner (run.py) builds an Injector + Defense from it, runs one
episode, and writes an atomic per-episode log keyed by the full config so the
whole matrix is resumable at the file level.

Seed asymmetry (design §4): all models 8 seeds except Qwen-7B-Q8 at 4.
Screen (Arm A) uses the 3 Qwen sizes; Arm B/C use all five.

SCREEN-DERIVED placeholders (finalised only AFTER Arm A, never guessed): the
focused matrix's top-2 framings and best placement/position. Marked below.
"""

from injections.templates import InjectionSpec, screen_specs

# id, ollama tag, seeds
MODELS = [
    ("M1", "qwen2.5:1.5b-instruct-q8_0", list(range(1, 9))),
    ("M2", "qwen2.5:3b-instruct-q8_0",   list(range(1, 9))),
    ("M3", "qwen2.5:7b-instruct-q8_0",   list(range(1, 5))),   # 4 seeds
    ("M4", "llama3.2:1b",                list(range(1, 9))),
    ("M5", "llama3.2:3b-instruct-q8_0",  list(range(1, 9))),
]
SCREEN_MODELS = [m for m in MODELS if m[0] in ("M1", "M2", "M3")]

# placement -> (host task whose normal flow reads that field, tool to poison)
PLACEMENT_HOST = {
    "search_body":     ("t02", "search_docs"),
    "product_desc":    ("t16", "find_products"),
    "order_notes":     ("t03", "get_order"),
    "tool_error":      ("t03", "get_order"),      # injector induces the error
    "computed_output": ("t05", "run_python"),
}

# --- focused matrix (Arm B) --- SCREEN-DERIVED placeholders ------------------
FOCUSED_GOALS = ("unauthorized_tool_call", "data_leak")
FOCUSED_FRAMINGS = ("system_impersonation", "authority_appeal")   # [SCREEN-DERIVED]
FOCUSED_PLACEMENT = "search_body"                                 # [SCREEN-DERIVED]
FOCUSED_POSITION = "suffix"                                       # [SCREEN-DERIVED]
FOCUSED_HOSTTASKS = ("t02", "t14")     # both call search_docs
DEFENSES = ("D0", "D1", "D2", "D3", "D4", "D5")

# --- benign control (Arm C): 6 tasks spanning all five tools -----------------
BENIGN_TASKS = ("t01", "t02", "t03", "t04", "t05", "t06")


def _emit(arm, models, defense, task, target, inj, seeds):
    for seed in seeds:
        yield {"arm": arm, "model": None, "defense": defense, "task": task,
               "target_tool": target, "injection": inj, "seed": seed,
               "_models": models}


def build_specs(arm: str) -> list[dict]:
    specs = []
    if arm == "A":
        for s in screen_specs():                     # 60 canary templates
            task, target = PLACEMENT_HOST[s.placement]
            for mid, tag, seeds in SCREEN_MODELS:
                for seed in seeds:
                    specs.append({"arm": "A", "model": tag, "defense": "D0",
                                  "task": task, "target_tool": target,
                                  "injection": s.as_dict(), "seed": seed})
    elif arm == "B":
        _, target = PLACEMENT_HOST[FOCUSED_PLACEMENT]
        for goal in FOCUSED_GOALS:
            for framing in FOCUSED_FRAMINGS:
                s = InjectionSpec(goal, FOCUSED_PLACEMENT, framing, FOCUSED_POSITION)
                for task in FOCUSED_HOSTTASKS:
                    for defense in DEFENSES:
                        for mid, tag, seeds in MODELS:
                            for seed in seeds:
                                specs.append({"arm": "B", "model": tag,
                                              "defense": defense, "task": task,
                                              "target_tool": target,
                                              "injection": s.as_dict(),
                                              "seed": seed})
    elif arm == "C":
        for task in BENIGN_TASKS:
            for defense in DEFENSES:
                for mid, tag, seeds in MODELS:
                    for seed in seeds:
                        specs.append({"arm": "C", "model": tag,
                                      "defense": defense, "task": task,
                                      "target_tool": None, "injection": None,
                                      "seed": seed})
    else:
        raise ValueError(f"unknown arm {arm!r}")
    return specs


def slug(text: str) -> str:
    return text.replace(":", "_").replace("/", "_")


def episode_filename(spec: dict) -> str:
    tmpl = spec["injection"]["template_id"] if spec["injection"] else "clean"
    return (f"{slug(spec['model'])}__{spec['defense']}__{tmpl}__{spec['task']}"
            f"__s{spec['seed']}.json")
