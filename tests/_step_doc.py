"""Workspace-local test helper for building single-Step composite documents.

`baseline.step` (a vivarium-workbench feature) lets a study reference a
process-bigraph Step directly, replacing the hand-written single-Step wrapper
composites this workspace used to carry. The old wrappers produced a document
of shape `{"state": {<output stores>, <step node>, <RAMEmitter>}, "run_steps_on_init": True}`;
`step_doc` rebuilds exactly that shape around one Step address + config, so the
demonstrate-loading tests can still build+run+emit a Step and assert on its
output stores.

Deliberately does NOT import from `vivarium_workbench`, so the workspace tests
stay independent of the (unreleased) workbench.
"""
from __future__ import annotations

import importlib
from typing import Any, Dict

from process_bigraph import Step


def _resolve(address: str):
    raw = address.split("local:", 1)[-1]
    mod, cls = raw.rsplit(".", 1)
    return getattr(importlib.import_module(mod), cls)


def step_doc(address: str, config: Dict[str, Any] | None, core) -> Dict[str, Any]:
    """Build the composite doc that wraps a single Step (mirrors the deleted
    single-Step composites): output stores + step node wired to them + a
    RAMEmitter over the outputs.

    `core` must be the same `build_core()` used to run the resulting Composite,
    so introspection (`inputs()`/`outputs()`) and the run share types. Build the
    doc AFTER any `monkeypatch.setattr(...)` — the Step calls its domain-module
    functions at `update()` time, so patches still apply.
    """
    step = _resolve(address)(config=dict(config or {}), core=core)
    out = list(step.outputs().keys())
    inp = list(step.inputs().keys())
    state: Dict[str, Any] = {p: {} for p in out}
    state["step"] = {
        "_type": "step",
        "address": address,
        "config": dict(config or {}),
        "inputs": {p: [p] for p in inp},
        "outputs": {p: [p] for p in out},
    }
    state["emitter"] = {
        "_type": "step",
        "address": "local:RAMEmitter",
        "config": {"emit": {p: "node" for p in out}},
        "inputs": {p: [p] for p in out},
    }
    return {"state": state, "run_steps_on_init": True}


def resolve_step_class(address: str) -> type:
    """Import the Step class named by a `local:<module>.<Class>` step address and
    assert it is a real `process_bigraph.Step` subclass. Returns the class."""
    klass = _resolve(address)
    assert isinstance(klass, type) and issubclass(klass, Step), (
        f"{address!r} does not resolve to a process_bigraph.Step subclass"
    )
    return klass


def registered_step_addresses(core) -> set[str]:
    """The set of `local:<module>.<Class>` addresses registered as workspace
    Steps by `build_core()` (via `_iter_workspace_edges`)."""
    from viva_human_atlas.core import _iter_workspace_edges
    import viva_human_atlas

    return {f"local:{dotted}" for _cls, dotted in _iter_workspace_edges(viva_human_atlas)}
