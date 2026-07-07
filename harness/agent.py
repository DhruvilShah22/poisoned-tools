"""The agent loop under test (design §3) with the guardrail as a togglable layer.

One `run_episode()` call = one episode: system prompt + task -> iterate model
tool calls against local tools -> final answer. Everything observable is
appended to `events` in order; grading and attribution consume that record.

Conditions (design §7):
  baseline  — tool calls execute as-is; invalid ones hit the tool layer and
              fail "naturally" (terse strings, like a real API).
  guardrail — schema validation *before* execution; violations return a typed
              error and the model retries, bounded by max_schema_retries per
              tool and max_extra_calls per episode.
Schema validity is computed and logged in BOTH conditions.
"""

import json
import time

import tools
from harness import guardrail
from tools.faults import FaultInjector

NUDGE = ("If you have the answer, reply on a single line starting with "
         "'FINAL ANSWER:'. Otherwise, continue using tools.")
MAX_RESULT_CHARS = 6000


def _content_of(result: dict) -> str:
    text = json.dumps(result, ensure_ascii=False)
    return text[:MAX_RESULT_CHARS]


def _extract_final(content: str) -> str | None:
    lower = content.lower()
    marker = lower.rfind("final answer")
    if marker == -1:
        return None
    tail = content[marker:]
    return tail.split(":", 1)[1].strip() if ":" in tail else tail.strip()


def run_episode(task: dict, cell: dict, cfg: dict, client,
                injector=None, defense=None) -> dict:
    """One episode. `injector` (injections.inject.Injector) poisons one tool
    output at runtime; `defense` (defenses/, step 6) shapes the system prompt,
    how tool results are shown, and any post-observation reminders. Both default
    to None, which reproduces exact paper-1 behaviour.

    Defense interface (duck-typed): `.name`, `.system_prompt(base) -> str`,
    `.render_tool_message(name, result) -> str`, `.post_observation(task) ->
    list[message]`.
    """
    guard = cell["condition"] == "guardrail"
    grail = cfg["guardrail"]
    schemas = tools.schemas()
    schemas_by_name = {s["function"]["name"]: s for s in schemas}
    fault = FaultInjector(task.get("fault"), guard)
    options = dict(cfg["options"])
    options["seed"] = task["_seed"]

    sys_prompt = (defense.system_prompt(cfg["system_prompt"]) if defense
                  else cfg["system_prompt"])
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": task["prompt"]}]
    events: list[dict] = []
    ep = {"task_id": task["id"], "seed": task["_seed"], "cell": cell["name"],
          "model": cell["model"], "condition": cell["condition"],
          "slice": task["slice"],
          "defense": (defense.name if defense else "D0"),
          "injection": injector.summary() if injector else None,
          "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "events": events, "final_answer": None, "asked_clarification": False,
          "nudges": 0, "hit_max_turns": False, "injection_fired": False}

    blocks_used = 0            # guardrail extra-call budget consumed
    consec_blocks: dict[str, int] = {}   # per-tool consecutive schema blocks
    t0 = time.time()

    for turn in range(cfg["max_turns"]):
        resp, infra_retries = client.chat(cell["model"], messages, schemas, options)
        msg = resp.get("message", {})
        events.append({"type": "model_call", "turn": turn,
                       "content": msg.get("content", ""),
                       "tool_calls": msg.get("tool_calls"),
                       "infra_retries": infra_retries,
                       "timings": {k: resp.get(k) for k in (
                           "prompt_eval_count", "prompt_eval_duration",
                           "eval_count", "eval_duration",
                           "total_duration", "load_duration")}})
        messages.append({"role": "assistant",
                         "content": msg.get("content", ""),
                         **({"tool_calls": msg["tool_calls"]}
                            if msg.get("tool_calls") else {})})

        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):  # some models emit stringified JSON
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_unparseable": args[:200]}
                violations = guardrail.validate(name, args, schemas_by_name)
                ev = {"type": "tool_call", "turn": turn, "name": name,
                      "args": args, "violations": violations,
                      "blocked": False, "fault_mode": None, "executed": False,
                      "result_error": False, "injection": None, "result": None}
                may_block = (guard and violations
                             and blocks_used < grail["max_extra_calls"]
                             and consec_blocks.get(name, 0) < grail["max_schema_retries"])
                if may_block:
                    ev["blocked"] = True
                    blocks_used += 1
                    consec_blocks[name] = consec_blocks.get(name, 0) + 1
                    result = guardrail.typed_error(violations)
                else:
                    consec_blocks[name] = 0
                    if injector is not None and injector.wants_preexec(name):
                        result, inj = injector.preexec_payload()
                        ev["fault_mode"] = "injected_error"
                        ev["injection"] = inj
                    else:
                        injected = fault.intercept(name)
                        if injected is not None:
                            ev["fault_mode"] = task["fault"]["mode"]
                            result = injected
                        else:
                            result = tools.execute(name, args)
                            ev["executed"] = True
                        if injector is not None:
                            result, inj = injector.maybe_poison(name, result)
                            if inj is not None:
                                ev["injection"] = inj
                    ev["result_error"] = bool(
                        isinstance(result, dict)
                        and (result.get("error") or result.get("error_type")
                             or "not found" in str(result.get("error", ""))))
                ev["result"] = result
                events.append(ev)
                tool_content = (defense.render_tool_message(name, result)
                                if defense else _content_of(result))
                messages.append({"role": "tool", "tool_name": name,
                                 "content": tool_content})
            if defense is not None:
                for m in defense.post_observation(task):
                    messages.append(m)
                    events.append({"type": "defense_reminder"})
            continue

        content = msg.get("content", "")
        final = _extract_final(content)
        if final is not None:
            ep["final_answer"] = final
            break
        if ("?" in content and task.get("clarification")
                and not ep["asked_clarification"]):
            ep["asked_clarification"] = True
            events.append({"type": "clarification",
                           "reply": task["clarification"]})
            messages.append({"role": "user", "content": task["clarification"]})
            continue
        if ep["nudges"] == 0:
            ep["nudges"] = 1
            events.append({"type": "nudge"})
            messages.append({"role": "user", "content": NUDGE})
            continue
        ep["final_answer"] = content.strip()  # last resort: treat as answer
        break
    else:
        ep["hit_max_turns"] = True

    ep["injection_fired"] = bool(injector and injector.fired)
    mc = [e for e in events if e["type"] == "model_call"]
    ep["wall_s"] = round(time.time() - t0, 2)
    ep["turns"] = len(mc)
    ep["blocks_used"] = blocks_used
    ep["token_totals"] = {
        "prompt_eval": sum(e["timings"].get("prompt_eval_count") or 0 for e in mc),
        "eval": sum(e["timings"].get("eval_count") or 0 for e in mc)}
    ep["max_context_tokens"] = max(
        ((e["timings"].get("prompt_eval_count") or 0)
         + (e["timings"].get("eval_count") or 0) for e in mc), default=0)
    return ep
