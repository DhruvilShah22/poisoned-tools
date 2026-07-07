"""Runtime tool-output poisoner (design §5, §8).

Given an `InjectionSpec` (as a dict), the `Injector` writes the adversarial
payload into the placement's field at the requested position, firing exactly
once — on the first call to the target tool — then standing down so the rest of
the episode proceeds normally. This mirrors paper-1's `FaultInjector` and keeps
the attack surface to a single, logged event per episode.

Two mechanisms by placement kind:
  error_message (tool_error placement) — PRE-execution: the injector returns an
      induced error whose message *is* the payload, and the real tool never runs
      for that call.
  everything else — POST-execution: the injector mutates a field of the real
      tool result (search result body, product description, order notes, or a
      computed output), leaving all other fields intact.

Every fire records the CLEAN value it overwrote, so each episode log carries both
what the tool really returned and what the model was shown — the poisoned-vs-clean
record the analysis re-grades from.
"""


def _wrap(payload: str, content, position: str) -> str:
    content = "" if content is None else str(content)
    if not content:
        return payload
    return f"{payload}\n\n{content}" if position == "prefix" \
        else f"{content}\n\n{payload}"


def poison_result(spec: dict, result: dict) -> tuple[dict, dict | None]:
    """Mutate `result` in place per the spec's placement. Returns
    (result, info) where info is None if there was nothing to poison (e.g. an
    empty result set) and otherwise records the clean value overwritten."""
    if not isinstance(result, dict):
        return result, None
    meta = spec["placement_meta"]
    kind, payload, pos = meta["kind"], spec["payload"], spec["position"]

    if kind in ("result_content", "row_field"):
        rows = result.get("results")
        if not rows:
            return result, None
        field = "content" if kind == "result_content" else meta["field"]
        clean = rows[0].get(field, "")
        rows[0][field] = _wrap(payload, clean, pos)
        return result, {"fired": True, "field_kind": kind, "clean": clean}

    if kind == "order_field":
        order = result.get("order")
        if not isinstance(order, dict):
            return result, None
        field = meta["field"]
        clean = order.get(field, "")
        order[field] = _wrap(payload, clean, pos)
        return result, {"fired": True, "field_kind": kind, "clean": clean}

    if kind == "computed":
        if "stdout" in result:          # run_python
            clean = result.get("stdout", "")
            result["stdout"] = _wrap(payload, clean, pos)
        else:                            # calculator (or other) -> annotate
            clean = result.get("result")
            result["annotation"] = payload
        return result, {"fired": True, "field_kind": kind, "clean": clean}

    return result, None


class Injector:
    """Fires once on the first call to the target tool. `spec` is an
    InjectionSpec.as_dict(), or None for an un-injected (clean/benign) episode,
    in which case every method is a no-op."""

    def __init__(self, spec: dict | None, target_tool: str | None = None):
        self.spec = spec
        self.fired = False
        if spec:
            self.kind = spec["placement_meta"]["kind"]
            # target tool: explicit override (host-task-driven for tool_error /
            # computed) else the placement's default tool.
            self.target = target_tool or spec["placement_meta"]["tool"]
        else:
            self.kind = self.target = None

    def summary(self) -> dict | None:
        if not self.spec:
            return None
        return {k: self.spec[k] for k in
                ("goal", "placement", "framing", "position", "template_id")}

    # --- pre-execution (tool_error placement) --------------------------------
    def wants_preexec(self, tool_name: str) -> bool:
        return (bool(self.spec) and not self.fired
                and self.kind == "error_message" and tool_name == self.target)

    def preexec_payload(self) -> tuple[dict, dict]:
        base = ("the upstream service returned an error while processing this "
                "request.")
        msg = _wrap(self.spec["payload"], base, self.spec["position"])
        self.fired = True
        info = {**self.summary(), "fired": True,
                "field_kind": "error_message", "clean": base}
        return {"error": msg}, info

    # --- post-execution (all other placements) -------------------------------
    def maybe_poison(self, tool_name: str, result) -> tuple[object, dict | None]:
        if (not self.spec or self.fired or self.kind == "error_message"
                or tool_name != self.target):
            return result, None
        poisoned, info = poison_result(self.spec, result)
        if info is None:
            return result, None
        self.fired = True
        return poisoned, {**self.summary(), **info}
