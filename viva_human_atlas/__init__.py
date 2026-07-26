"""viva_human_atlas — HRA / Whole Person Physiome modeling workspace.

Importing the package fires the @composite_generator decorators in composites/
so discover_generators() finds them.
"""
from viva_human_atlas import composites  # noqa: F401


def register_types(core):
    """Register the types this workspace needs (delegates to pbg-biomodels)."""
    from pbg_biomodels import register_types as _reg
    return _reg(core)


__all__ = ["register_types"]
