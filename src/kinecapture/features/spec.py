"""``feature_spec.json``: what a release says about its own feature arrays.

The manifest describes the *samples*; this document describes the *columns*.
Anyone opening a release should be able to answer, without reading this source
tree, what every array is, what unit it is in, which frame it is expressed in,
how it behaves at a gap, which joints or angles its columns correspond to, and
how often it actually came out.

It also states plainly what these numbers are not: no clinical validation, no
diagnostic thresholds, no normative reference values.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from kinecapture import FEATURE_SPEC_SCHEMA_VERSION
from kinecapture.features.base import Availability
from kinecapture.features.compute import column_names
from kinecapture.features.definitions import (
    ANGLE_DEFINITIONS,
    ANGLE_SET_VERSION,
    BILATERAL_ANGLE_GROUPS,
    DISTANCE_DEFINITIONS,
    DISTANCE_SET_VERSION,
    RATIO_DEFINITIONS,
)
from kinecapture.features.geometry import bone_table
from kinecapture.features.registry import get_feature, order_features
from kinecapture.features.roles import BILATERAL_ROLE_PAIRS, role_table
from kinecapture.features.summary import summary_contract
from kinecapture.features.temporal import DEFAULT_GAP_FACTOR
from kinecapture.visualization.skeleton_spec import SkeletonSpec

CLINICAL_DISCLAIMER = (
    "Bu dizilerin hiçbiri klinik olarak doğrulanmış bir ölçüm değildir. "
    "Tüketici sınıfı bir derinlik kamerasının iskelet tahmininden türetilmiş "
    "kinematik büyüklüklerdir; tanı, şiddet derecelendirmesi veya normatif "
    "referans değeri olarak kullanılamaz. 'Açı', 'mesafe' ve 'proxy' adları "
    "bilinçlidir; klinik terminoloji kullanılmamıştır."
)

MISSING_DATA_POLICY = (
    "Eksik veri hiçbir yerde uydurulmaz. Görülmeyen eklem NaN kalır; NaN "
    "sıfıra çevrilmez, önceki kareyle doldurulmaz, interpolasyon yapılmaz. "
    "Takip boşluğu üzerinden türev alınmaz; ilk hız karesi sahte sıfırla "
    "doldurulmaz. Her özellik, üretebiliyorsa kendi validity maskesini yazar "
    "ve maske ile NaN düzeni doğrulamada karşılaştırılır."
)

DERIVATIVE_POLICY = (
    "Fiziksel türevler kamera zaman damgalarından hesaplanır. Bir adım ancak "
    f"0 < dt <= {DEFAULT_GAP_FACTOR} / hedef_fps ise kullanılır. İç noktalarda "
    "merkezi fark, birinci türevin uçlarında tek yanlı fark kullanılır; ikinci "
    "türevin uçları NaN'dır. Hiçbir yerde filtre veya yumuşatma uygulanmaz."
)

DISPLACEMENT_NOTE = (
    "joint_displacement_xyz kare farkıdır ve FPS'e bağlıdır; fiziksel hız "
    "değildir. KineSynthV3'ün mevcut 'velocity' kanalı bu türdendir. Fiziksel "
    "hız ayrı bir dizi olan joint_velocity_xyz'dir ve birimi "
    "length_unit/saniyedir. İkisi aynı kanal değildir."
)


def angle_block(spec: SkeletonSpec, resolved: Optional[Sequence[Mapping[str, Any]]] = None) -> dict[str, Any]:
    """Angle definitions plus, when known, which joints they resolved to."""
    by_id = {entry["angle_id"]: entry for entry in (resolved or ())}
    return {
        "version": ANGLE_SET_VERSION,
        "unit": "radian",
        "column_order": [definition.angle_id for definition in ANGLE_DEFINITIONS],
        "definitions": [
            definition.to_dict(by_id.get(definition.angle_id))
            for definition in ANGLE_DEFINITIONS
        ],
        "bilateral_groups": [
            {"group": group, "left": ANGLE_DEFINITIONS[left].angle_id,
             "right": ANGLE_DEFINITIONS[right].angle_id}
            for group, left, right in BILATERAL_ANGLE_GROUPS
        ],
        "note": (
            "Sütun sırası sabittir. İskelette gerekli eklem yoksa o sütun NaN "
            "kalır; sütun kaldırılmaz."
        ),
    }


def distance_block() -> dict[str, Any]:
    return {
        "version": DISTANCE_SET_VERSION,
        "distances": [definition.to_dict() for definition in DISTANCE_DEFINITIONS],
        "ratios": [definition.to_dict() for definition in RATIO_DEFINITIONS],
        "note": (
            "Zemin yüksekliği, ayak teması ve mutlak duruş genişliği gibi "
            "büyüklükler doğrulanmış bir dünya/zemin kalibrasyonu gerektirdiği "
            "için üretilmez. Kamera koordinatındaki y=0 zemin kabul edilmez."
        ),
    }


def bilateral_block() -> dict[str, Any]:
    return {
        "pair_order": [role for role, _, _ in BILATERAL_ROLE_PAIRS],
        "pairs": [
            {"pair": role, "left_role": left, "right_role": right}
            for role, left, right in BILATERAL_ROLE_PAIRS
        ],
        "sagittal_plane": (
            "Ayna mesafesi gövde uzayında, x = 0 düzlemine göre hesaplanır. "
            "Kamera koordinatında doğrudan sol-sağ farkı alınmaz."
        ),
        "interpretation_limit": (
            "Bu değerler geometrik farklardır; asimetri teşhisi veya klinik "
            "bir değerlendirme değildir."
        ),
    }


def build_feature_spec(
    *,
    feature_ids: Sequence[str],
    specs: Mapping[str, SkeletonSpec],
    preset_id: Optional[str],
    availability: Mapping[str, Mapping[str, int]],
    sample_count: int,
    mapping: Optional[Mapping[str, Any]] = None,
    resolved_angles: Optional[Sequence[Mapping[str, Any]]] = None,
    source_fields: Optional[Mapping[str, int]] = None,
) -> dict[str, Any]:
    """Assemble the whole document.

    ``availability`` is ``{feature_id: {"full": n, "partial": n, "absent": n}}``
    counted over the samples actually written.
    """
    ordered = order_features(feature_ids)
    features = [get_feature(feature_id) for feature_id in ordered]
    primary_spec = next(iter(specs.values())) if specs else None

    return {
        "schema_version": FEATURE_SPEC_SCHEMA_VERSION,
        "preset": preset_id,
        "selected_feature_ids": list(ordered),
        "features": [definition.to_dict() for definition in features],
        "array_keys": [key for definition in features for key in definition.array_keys],
        "columns": (
            column_names(primary_spec) if primary_spec is not None else {}
        ),
        "angles": angle_block(primary_spec, resolved_angles) if primary_spec else {},
        "distances": distance_block(),
        "bilateral": bilateral_block(),
        "summary": summary_contract(),
        "bones": {
            name: bone_table(spec) for name, spec in sorted(specs.items())
        },
        "roles": {
            name: role_table(spec) for name, spec in sorted(specs.items())
        },
        "policies": {
            "missing_data": MISSING_DATA_POLICY,
            "derivatives": DERIVATIVE_POLICY,
            "displacement_vs_velocity": DISPLACEMENT_NOTE,
            "not_applied": (
                "Interpolation, padding, temporal resampling, augmentation ve "
                "train dataset'inden öğrenilen normalizasyon bu katmanda "
                "uygulanmaz; eğitim katmanına aittir."
            ),
            "leakage": (
                "Hiçbir özellik dataset genelinde hesaplanmış bir istatistiğe, "
                "etikete veya katılımcı kimliğine bakmaz."
            ),
        },
        "availability": {
            feature_id: dict(counts) for feature_id, counts in sorted(availability.items())
        },
        "source_field_availability": dict(sorted((source_fields or {}).items())),
        "sample_count": sample_count,
        "joint_mapping": dict(mapping) if mapping else None,
        "clinical_validation": CLINICAL_DISCLAIMER,
    }


def availability_counter() -> dict[str, int]:
    return {level.value: 0 for level in Availability}


__all__ = [
    "CLINICAL_DISCLAIMER",
    "DERIVATIVE_POLICY",
    "DISPLACEMENT_NOTE",
    "MISSING_DATA_POLICY",
    "availability_counter",
    "build_feature_spec",
]
