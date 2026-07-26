"""build_core() for viva-human-atlas.

Registers the workspace-local Steps (walking the viva_human_atlas package the
same way pbg-biomodels does) plus everything pbg-biomodels' build_core sets up
(simulator Process backends + biomodels types), since we reuse its composites.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Iterable

from process_bigraph import Process, Step, allocate_core

import viva_human_atlas


def _iter_workspace_edges(package) -> Iterable[tuple[type, str]]:
    pkg_name = package.__name__
    seen: set[type] = set()
    for _, modname, _ in pkgutil.walk_packages(package.__path__, prefix=f"{pkg_name}."):
        try:
            mod = importlib.import_module(modname)
        except Exception as exc:  # pragma: no cover
            import warnings
            warnings.warn(f"build_core: skipping {modname}: {type(exc).__name__}: {exc}")
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if cls in (Step, Process):
                continue
            if not issubclass(cls, (Step, Process)):
                continue
            if not (cls.__module__ or "").startswith(pkg_name + "."):
                continue
            if cls in seen:
                continue
            seen.add(cls)
            yield cls, f"{cls.__module__}.{cls.__name__}"


def build_core():
    core = allocate_core()
    # Register pbg-biomodels' simulator backends + types (reused by our composites).
    from pbg_biomodels.simulators import register_simulator_backends
    from pbg_biomodels import register_types as register_biomodels_types
    from viva_human_atlas.types import register_workspace_types
    register_simulator_backends(core)
    register_biomodels_types(core)
    register_workspace_types(core)
    # Register this workspace's local Steps by dotted path and short name.
    for cls, dotted in _iter_workspace_edges(viva_human_atlas):
        core.register_link(dotted, cls)
        core.register_link(cls.__name__, cls)
    return core
