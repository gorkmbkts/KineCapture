"""What a feature *is*, before anything computes one.

A feature here is a named, versioned recipe that turns the canonical raw
arrays of one exported movement sample into one or more additional named
arrays. Three rules shape the design:

* **The canonical arrays never move.** ``joints_xyz``, ``frame_indices`` and
  ``camera_timestamps_ns`` stay exactly what the tracker produced. Everything
  in this package is *additional*, written under its own key, and can be
  recomputed from the raw take at any time.
* **A feature declares itself completely.** Shape, dtype, unit, reference
  frame, time alignment, missing-value policy, which skeleton roles it needs
  and what happens under a joint mapping are all part of the definition, not
  folklore in the exporter. The release writes those declarations out verbatim
  so a consumer never has to reverse-engineer a column.
* **Nothing is invented.** A feature that cannot be computed for a frame emits
  NaN (or ``False`` in a mask), never zero and never a carried-forward value.

None of these outputs are clinically validated measurements. They are
kinematic quantities derived from a consumer-grade tracker; the labels and
descriptions say so, and the release repeats it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class FeatureCategory(str, Enum):
    """Product-level grouping, also used as the export screen's tree."""

    CANONICAL = "canonical"
    QUALITY = "quality"
    TRACKER_RAW = "tracker_raw"
    COORDINATES = "coordinates"
    GEOMETRY = "geometry"
    KINEMATICS = "kinematics"
    ANGLES = "angles"
    SYMMETRY = "symmetry"
    SUMMARY = "summary"

    @property
    def label(self) -> str:
        return _CATEGORY_LABELS[self]

    @property
    def description(self) -> str:
        return _CATEGORY_DESCRIPTIONS[self]


_CATEGORY_LABELS: dict[FeatureCategory, str] = {
    FeatureCategory.CANONICAL: "Zorunlu canonical veri",
    FeatureCategory.QUALITY: "Kalite ve maskeler",
    FeatureCategory.TRACKER_RAW: "Tracker ham çıktıları",
    FeatureCategory.COORDINATES: "Koordinat temsilleri",
    FeatureCategory.GEOMETRY: "Kemik / geometri",
    FeatureCategory.KINEMATICS: "Hız ve ivme",
    FeatureCategory.ANGLES: "Açılar ve açısal hareket",
    FeatureCategory.SYMMETRY: "Simetri ve oran proxy'leri",
    FeatureCategory.SUMMARY: "Klasik ML özetleri",
}

_CATEGORY_DESCRIPTIONS: dict[FeatureCategory, str] = {
    FeatureCategory.CANONICAL: "Her sürümde bulunur ve kapatılamaz.",
    FeatureCategory.QUALITY: "Neyin ölçüldüğünü, neyin eksik olduğunu söyleyen diziler.",
    FeatureCategory.TRACKER_RAW: (
        "Tracker'ın kendi çıktıları. Koordinatlardan geri üretilemezler; "
        "yalnız kaydedildilerse vardır."
    ),
    FeatureCategory.COORDINATES: (
        "Ham koordinatın yerine geçmeyen alternatif temsiller."
    ),
    FeatureCategory.GEOMETRY: "İskelet topolojisine bağlı kemik geometrisi.",
    FeatureCategory.KINEMATICS: (
        "Zaman damgası tabanlı türevler. Kare farkı ile fiziksel hız ayrı adlarla "
        "yazılır."
    ),
    FeatureCategory.ANGLES: "Sürümlü anatomik açı tanımları ve açısal hızları.",
    FeatureCategory.SYMMETRY: (
        "Sol-sağ karşılaştırmaları ve seçilmiş mesafe/oran proxy'leri. "
        "Asimetri teşhisi değildir."
    ),
    FeatureCategory.SUMMARY: (
        "Random Forest / SVM / XGBoost gibi modeller için sabit uzunluklu vektör."
    ),
}

#: Label used by the export screen for the group experimental features move to.
EXPERIMENTAL_GROUP_LABEL = "Deneysel"


class MappingSupport(str, Enum):
    """What happens to a feature when a joint mapping is in effect.

    A joint mapping is an index permutation designed for *positions*. Carrying
    every array through it blindly would be wrong for anything whose meaning
    depends on the source skeleton's parent chain.
    """

    #: Geometric; recomputed from the target skeleton's own coordinates.
    RECOMPUTE = "recompute"
    #: Per-joint values that stay meaningful under a pure index permutation.
    INDEX_REMAP = "index_remap"
    #: Meaning depends on the source parent chain - unavailable when mapped.
    NATIVE_ONLY = "native_only"
    #: Not per-joint at all, so a mapping cannot affect it.
    INDEPENDENT = "independent"

    @property
    def label(self) -> str:
        return {
            MappingSupport.RECOMPUTE: "hedef iskelette yeniden hesaplanır",
            MappingSupport.INDEX_REMAP: "eklem indeksiyle taşınır",
            MappingSupport.NATIVE_ONLY: "yalnız native biçimde",
            MappingSupport.INDEPENDENT: "eşleştirmeden etkilenmez",
        }[self]


class SourceField(str, Enum):
    """Inputs a feature may need from the recorded take."""

    JOINTS = "joints"
    TIMESTAMPS = "timestamps"
    CONFIDENCES = "confidences"
    JOINT_ORIENTATIONS = "joint_orientations"
    JOINT_POSITIONS_2D = "joint_positions_2d"
    JOINT_POSITION_COVARIANCES = "joint_position_covariances"
    LOCAL_JOINT_POSITIONS = "local_joint_positions_xyz"
    ROOT_POSITION = "root_position"
    ROOT_ORIENTATION = "root_orientation"
    ROOT_VELOCITY = "tracker_root_velocity_xyz"
    ROOT_POSITION_COVARIANCE = "root_position_covariance"
    BODY_STATE = "body_state"

    @property
    def label(self) -> str:
        return _SOURCE_LABELS[self]


_SOURCE_LABELS: dict[SourceField, str] = {
    SourceField.JOINTS: "eklem koordinatları",
    SourceField.TIMESTAMPS: "kamera zaman damgaları",
    SourceField.CONFIDENCES: "eklem güven değerleri",
    SourceField.JOINT_ORIENTATIONS: "eklem quaternionları",
    SourceField.JOINT_POSITIONS_2D: "2B eklem noktaları",
    SourceField.JOINT_POSITION_COVARIANCES: "eklem kovaryansları",
    SourceField.LOCAL_JOINT_POSITIONS: "parent'a göre eklem konumları",
    SourceField.ROOT_POSITION: "kök konumu",
    SourceField.ROOT_ORIENTATION: "kök yönelimi",
    SourceField.ROOT_VELOCITY: "tracker kök hızı",
    SourceField.ROOT_POSITION_COVARIANCE: "kök konum kovaryansı",
    SourceField.BODY_STATE: "gövde durumu (takip/eylem/güven)",
}


@dataclass(frozen=True)
class ArrayContract:
    """One named array a feature writes into the ``.npz``."""

    key: str
    shape: str
    dtype: str
    unit: str
    space: str
    description: str
    time_alignment: str = "per_frame"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "shape": self.shape,
            "dtype": self.dtype,
            "unit": self.unit,
            "coordinate_space": self.space,
            "time_alignment": self.time_alignment,
            "description": self.description,
        }


@dataclass(frozen=True)
class FeatureDefinition:
    """A versioned, self-describing feature.

    ``version`` changes whenever the *numbers* a feature produces could change.
    It is hashed into the dataset fingerprint, so a release always states which
    definition produced its arrays.
    """

    feature_id: str
    version: str
    label: str
    description: str
    category: FeatureCategory
    arrays: tuple[ArrayContract, ...]
    requires: tuple[SourceField, ...] = (SourceField.JOINTS,)
    #: Anatomical roles that must resolve on the output skeleton.
    required_roles: tuple[str, ...] = ()
    mapping_support: MappingSupport = MappingSupport.RECOMPUTE
    missing_policy: str = (
        "Hesaplanamayan değer NaN, ilgili validity maskesi False kalır."
    )
    experimental: bool = False
    #: Included by the default (canonical-compatible) export.
    default_on: bool = False
    #: Cannot be turned off in the GUI.
    locked: bool = False
    parameters: Mapping[str, Any] = field(default_factory=dict)
    #: Feature ids that must be computed before this one.
    depends_on: tuple[str, ...] = ()
    #: Names of the columns of the feature's primary 2D array, when they are
    #: fixed by a definition list rather than by the skeleton.
    column_source: Optional[str] = None

    @property
    def array_keys(self) -> tuple[str, ...]:
        return tuple(contract.key for contract in self.arrays)

    @property
    def group_label(self) -> str:
        """Where the export screen puts this feature."""
        return EXPERIMENTAL_GROUP_LABEL if self.experimental else self.category.label

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "version": self.version,
            "label": self.label,
            "description": self.description,
            "category": self.category.value,
            "arrays": [contract.to_dict() for contract in self.arrays],
            "requires": [source.value for source in self.requires],
            "required_roles": list(self.required_roles),
            "mapping_support": self.mapping_support.value,
            "missing_value_policy": self.missing_policy,
            "experimental": self.experimental,
            "default_on": self.default_on,
            "parameters": dict(self.parameters),
            "depends_on": list(self.depends_on),
        }

    def fingerprint_key(self) -> dict[str, Any]:
        """The part of a definition that can change the numbers it produces."""
        return {
            "feature_id": self.feature_id,
            "version": self.version,
            "arrays": [contract.key for contract in self.arrays],
            "parameters": dict(self.parameters),
        }


class Availability(str, Enum):
    """How much of a feature actually came out for one sample."""

    FULL = "full"
    PARTIAL = "partial"
    ABSENT = "absent"

    @property
    def label(self) -> str:
        return {
            Availability.FULL: "tam",
            Availability.PARTIAL: "kısmi",
            Availability.ABSENT: "yok",
        }[self]


__all__ = [
    "ArrayContract",
    "Availability",
    "EXPERIMENTAL_GROUP_LABEL",
    "FeatureCategory",
    "FeatureDefinition",
    "MappingSupport",
    "SourceField",
]
