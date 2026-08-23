"""Selectable, versioned skeleton features.

The canonical dataset contract is still ``joints_xyz`` plus its frame indices
and camera timestamps. This package is what a user can *add* to that: quality
masks, the tracker's own raw outputs, alternative coordinate representations,
bone geometry, timestamp-aware kinematics, anatomical angles, bilateral
comparisons and a fixed-length summary vector for classical models.

Layering, deliberately kept free of Qt and of ``pyzed``:

``base``
    What a feature declares about itself.
``roles``
    Anatomical role -> joint index, per skeleton format.
``definitions``
    The versioned angle, distance and ratio lists that fix column order.
``temporal`` / ``geometry``
    The shared maths: gap-aware derivatives, angles, body frame, bones.
``compute``
    One function per feature, and the context they all read.
``summary``
    The fixed-length vector and its element names.
``registry``
    The ordered catalogue, applicability rules and the GUI presets.
``spec``
    The ``feature_spec.json`` document a release carries.

Nothing here interpolates, pads, resamples, augments or fits anything to the
dataset as a whole. Those are training-time decisions, and doing them at export
time would make a release neither raw nor reproducible.
"""

from kinecapture.features.base import (
    ArrayContract,
    Availability,
    FeatureCategory,
    FeatureDefinition,
    MappingSupport,
    SourceField,
)
from kinecapture.features.compute import (
    ComputedFeatures,
    FeatureContext,
    column_names,
    compute_features,
)
from kinecapture.features.registry import (
    DEFAULT_FEATURE_IDS,
    FEATURES,
    LOCKED_FEATURE_IDS,
    PRESETS,
    FeaturePreset,
    all_features,
    applicability,
    array_keys_for,
    estimate_bytes_per_frame,
    find_feature,
    get_feature,
    get_preset,
    match_preset,
    order_features,
    registry_fingerprint_keys,
)
from kinecapture.features.summary import (
    SUMMARY_LENGTH,
    SUMMARY_VERSION,
    summary_names,
)

__all__ = [
    "ArrayContract",
    "Availability",
    "ComputedFeatures",
    "DEFAULT_FEATURE_IDS",
    "FEATURES",
    "FeatureCategory",
    "FeatureContext",
    "FeatureDefinition",
    "FeaturePreset",
    "LOCKED_FEATURE_IDS",
    "MappingSupport",
    "PRESETS",
    "SUMMARY_LENGTH",
    "SUMMARY_VERSION",
    "SourceField",
    "all_features",
    "applicability",
    "array_keys_for",
    "column_names",
    "compute_features",
    "estimate_bytes_per_frame",
    "find_feature",
    "get_feature",
    "get_preset",
    "match_preset",
    "order_features",
    "registry_fingerprint_keys",
    "summary_names",
]
