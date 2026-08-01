"""viva_human_atlas — HRA / Whole Person Physiome modeling workspace.

Importing the package fires the @composite_generator decorators in composites/
so discover_generators() finds them.
"""
from viva_human_atlas import composites  # noqa: F401


def register_types(core):
    """Register the types this workspace needs: pbg-biomodels' shared types,
    plus viva-human-atlas's own workspace types (reference_organ,
    cell_type_term, anatomical_term, matched_organ, biomodel_do,
    organ_to_models — see `types.py`)."""
    from viva_biomodels import register_types as _reg
    _reg(core)
    from viva_human_atlas.types import register_workspace_types
    return register_workspace_types(core)


__all__ = ["register_types"]
