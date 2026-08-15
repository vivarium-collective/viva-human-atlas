"""Importing this package registers viva-human-atlas @composite_generator entries.

Only genuine multi-process composites live here. Single-Step studies reference
their Step directly via ``baseline.step`` in study.yaml — no thin single-Step
wrapper composite is needed (see vivarium-workbench ``baseline.step`` support).
"""
from viva_human_atlas.composites import glucose_regulation  # noqa: F401
from viva_human_atlas.composites import corpus_coverage_composite  # noqa: F401
from viva_human_atlas.composites import ftu_coverage_composite  # noqa: F401
from viva_human_atlas.composites import vasculature_network_composite  # noqa: F401
from viva_human_atlas.composites import organ_vasculature_scaffold  # noqa: F401
from viva_human_atlas.composites import atlas_pipeline  # noqa: F401
