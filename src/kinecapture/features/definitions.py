"""Versioned angle, distance and ratio definitions.

These lists are the *contract*. Column order in ``joint_angles_rad``,
``segment_distances`` and ``segment_ratios`` is the order here, and the release
writes the names, the joints used and the mathematical definition of every one
of them into ``feature_spec.json``. Adding a definition appends to the end and
bumps the family's version; reordering or reinterpreting one is a breaking
change.

Nothing here is a clinical measurement. ``left_knee_flexion`` is the interior
angle between two segments of a consumer-grade tracker's skeleton, not a
goniometer reading, and the names in the release say ``angle`` rather than
borrowing clinical terminology.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


#: Bumped when any angle definition changes meaning.
ANGLE_SET_VERSION = "1.0.0"
#: Bumped when any distance or ratio definition changes meaning.
DISTANCE_SET_VERSION = "1.0.0"


@dataclass(frozen=True)
class AngleDefinition:
    """One named angle, in radians.

    ``kind`` decides the maths:

    ``three_point``
        Interior angle at ``vertex`` between the segments to ``proximal`` and
        ``distal``, as ``atan2(|u x v|, u . v)``. Range ``[0, pi]``. The
        cross-product form is used rather than ``arccos`` of a normalised dot
        product because it stays accurate near 0 and pi instead of losing
        precision where a fully extended or fully folded limb sits.

    ``vector_axis``
        Angle between the segment ``proximal -> distal`` and the skeleton's
        configured vertical axis. Range ``[0, pi]``.

    ``line_tilt``
        Signed inclination of the line ``right -> left`` out of the horizontal
        plane, as ``asin((v . up) / |v|)``. Range ``[-pi/2, pi/2]``, positive
        when the left joint is higher than the right.

    Each point is a *chain* of roles: the first role the skeleton actually has
    is used, and which one that was is recorded per release. A chain of one is
    the common case.
    """

    angle_id: str
    label: str
    kind: str
    points: tuple[tuple[str, ...], ...]
    description: str
    valid_range: tuple[float, float]
    bilateral_group: str = ""
    side: str = ""

    def to_dict(self, resolved_points: dict[str, Any] | None = None) -> dict[str, Any]:
        block: dict[str, Any] = {
            "angle_id": self.angle_id,
            "label": self.label,
            "kind": self.kind,
            "unit": "radian",
            "valid_range": list(self.valid_range),
            "role_chains": [list(chain) for chain in self.points],
            "definition": self.description,
            "bilateral_group": self.bilateral_group,
            "side": self.side,
        }
        if resolved_points is not None:
            block["resolved"] = resolved_points
        return block


_THREE_POINT = (
    "Üç noktalı iç açı: atan2(|u x v|, u . v), u ve v köşeden diğer iki "
    "noktaya giden vektörler. Nokta eksikse veya vektörlerden biri sıfıra "
    "yakınsa NaN."
)

#: Order fixed: this is the column order of ``joint_angles_rad``.
ANGLE_DEFINITIONS: tuple[AngleDefinition, ...] = (
    AngleDefinition(
        "left_elbow_angle",
        "Sol dirsek açısı",
        "three_point",
        (("left_shoulder",), ("left_elbow",), ("left_wrist",)),
        _THREE_POINT,
        (0.0, 3.141592653589793),
        bilateral_group="elbow",
        side="left",
    ),
    AngleDefinition(
        "right_elbow_angle",
        "Sağ dirsek açısı",
        "three_point",
        (("right_shoulder",), ("right_elbow",), ("right_wrist",)),
        _THREE_POINT,
        (0.0, 3.141592653589793),
        bilateral_group="elbow",
        side="right",
    ),
    AngleDefinition(
        "left_knee_angle",
        "Sol diz açısı",
        "three_point",
        (("left_hip",), ("left_knee",), ("left_ankle",)),
        _THREE_POINT,
        (0.0, 3.141592653589793),
        bilateral_group="knee",
        side="left",
    ),
    AngleDefinition(
        "right_knee_angle",
        "Sağ diz açısı",
        "three_point",
        (("right_hip",), ("right_knee",), ("right_ankle",)),
        _THREE_POINT,
        (0.0, 3.141592653589793),
        bilateral_group="knee",
        side="right",
    ),
    AngleDefinition(
        "left_hip_angle",
        "Sol kalça açısı",
        "three_point",
        (("chest", "spine_mid", "neck"), ("left_hip",), ("left_knee",)),
        _THREE_POINT
        + " Proksimal referans, iskelette bulunan ilk gövde eklemidir "
        "(chest -> spine_mid -> neck) ve hangisinin kullanıldığı sürümde yazılıdır.",
        (0.0, 3.141592653589793),
        bilateral_group="hip",
        side="left",
    ),
    AngleDefinition(
        "right_hip_angle",
        "Sağ kalça açısı",
        "three_point",
        (("chest", "spine_mid", "neck"), ("right_hip",), ("right_knee",)),
        _THREE_POINT
        + " Proksimal referans, iskelette bulunan ilk gövde eklemidir "
        "(chest -> spine_mid -> neck) ve hangisinin kullanıldığı sürümde yazılıdır.",
        (0.0, 3.141592653589793),
        bilateral_group="hip",
        side="right",
    ),
    AngleDefinition(
        "left_ankle_angle",
        "Sol ayak bileği açısı",
        "three_point",
        (("left_knee",), ("left_ankle",), ("left_foot",)),
        _THREE_POINT + " Yalnız iskelette bir ayak/parmak eklemi varsa üretilir.",
        (0.0, 3.141592653589793),
        bilateral_group="ankle",
        side="left",
    ),
    AngleDefinition(
        "right_ankle_angle",
        "Sağ ayak bileği açısı",
        "three_point",
        (("right_knee",), ("right_ankle",), ("right_foot",)),
        _THREE_POINT + " Yalnız iskelette bir ayak/parmak eklemi varsa üretilir.",
        (0.0, 3.141592653589793),
        bilateral_group="ankle",
        side="right",
    ),
    AngleDefinition(
        "trunk_inclination",
        "Gövde eğimi",
        "vector_axis",
        (("pelvis", "spine_mid"), ("neck",)),
        "Pelvis'ten boyuna giden vektör ile iskeletin dikey ekseni arasındaki "
        "açı. İşaretsizdir: yön değil, dikeyden sapma miktarıdır.",
        (0.0, 3.141592653589793),
    ),
    AngleDefinition(
        "pelvis_tilt",
        "Pelvis eğimi",
        "line_tilt",
        (("left_hip",), ("right_hip",)),
        "Sağ kalçadan sol kalçaya giden çizginin yatay düzlemden sapması: "
        "asin((v . dikey) / |v|). Sol taraf yüksekse pozitiftir.",
        (-1.5707963267948966, 1.5707963267948966),
    ),
    AngleDefinition(
        "shoulder_tilt",
        "Omuz hattı eğimi",
        "line_tilt",
        (("left_shoulder",), ("right_shoulder",)),
        "Sağ omuzdan sol omuza giden çizginin yatay düzlemden sapması. "
        "Sol taraf yüksekse pozitiftir.",
        (-1.5707963267948966, 1.5707963267948966),
    ),
)

ANGLE_IDS: tuple[str, ...] = tuple(a.angle_id for a in ANGLE_DEFINITIONS)

#: ``(group, left angle index, right angle index)`` for bilateral comparison.
BILATERAL_ANGLE_GROUPS: tuple[tuple[str, int, int], ...] = tuple(
    (
        group,
        ANGLE_IDS.index(f"left_{group}_angle"),
        ANGLE_IDS.index(f"right_{group}_angle"),
    )
    for group in ("elbow", "knee", "hip", "ankle")
)


@dataclass(frozen=True)
class DistanceDefinition:
    """Euclidean distance between two role joints, in the capture length unit."""

    distance_id: str
    label: str
    role_a: str
    role_b: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "distance_id": self.distance_id,
            "label": self.label,
            "roles": [self.role_a, self.role_b],
            "unit": "length_unit",
            "definition": self.description,
        }


#: Order fixed: column order of ``segment_distances``.
DISTANCE_DEFINITIONS: tuple[DistanceDefinition, ...] = (
    DistanceDefinition(
        "ankle_separation", "Ayak bileği açıklığı", "left_ankle", "right_ankle",
        "İki ayak bileği arasındaki 3B uzaklık.",
    ),
    DistanceDefinition(
        "knee_separation", "Diz açıklığı", "left_knee", "right_knee",
        "İki diz arasındaki 3B uzaklık.",
    ),
    DistanceDefinition(
        "wrist_separation", "Bilek açıklığı", "left_wrist", "right_wrist",
        "İki bilek arasındaki 3B uzaklık.",
    ),
    DistanceDefinition(
        "hip_width", "Kalça genişliği", "left_hip", "right_hip",
        "İki kalça eklemi arasındaki 3B uzaklık.",
    ),
    DistanceDefinition(
        "shoulder_width", "Omuz genişliği", "left_shoulder", "right_shoulder",
        "İki omuz arasındaki 3B uzaklık.",
    ),
    DistanceDefinition(
        "trunk_length", "Gövde uzunluğu", "pelvis", "neck",
        "Pelvis ile boyun arasındaki 3B uzaklık.",
    ),
    DistanceDefinition(
        "left_thigh_length", "Sol uyluk uzunluğu", "left_hip", "left_knee",
        "Kalça-diz segment uzunluğu.",
    ),
    DistanceDefinition(
        "right_thigh_length", "Sağ uyluk uzunluğu", "right_hip", "right_knee",
        "Kalça-diz segment uzunluğu.",
    ),
    DistanceDefinition(
        "left_shank_length", "Sol baldır uzunluğu", "left_knee", "left_ankle",
        "Diz-ayak bileği segment uzunluğu.",
    ),
    DistanceDefinition(
        "right_shank_length", "Sağ baldır uzunluğu", "right_knee", "right_ankle",
        "Diz-ayak bileği segment uzunluğu.",
    ),
    DistanceDefinition(
        "root_to_left_wrist", "Pelvis - sol bilek", "pelvis", "left_wrist",
        "Kök eklem ile sol bilek arasındaki uzaklık.",
    ),
    DistanceDefinition(
        "root_to_right_wrist", "Pelvis - sağ bilek", "pelvis", "right_wrist",
        "Kök eklem ile sağ bilek arasındaki uzaklık.",
    ),
    DistanceDefinition(
        "root_to_left_ankle", "Pelvis - sol ayak bileği", "pelvis", "left_ankle",
        "Kök eklem ile sol ayak bileği arasındaki uzaklık.",
    ),
    DistanceDefinition(
        "root_to_right_ankle", "Pelvis - sağ ayak bileği", "pelvis", "right_ankle",
        "Kök eklem ile sağ ayak bileği arasındaki uzaklık.",
    ),
)

DISTANCE_IDS: tuple[str, ...] = tuple(d.distance_id for d in DISTANCE_DEFINITIONS)


@dataclass(frozen=True)
class RatioDefinition:
    """A dimensionless ratio of two distances."""

    ratio_id: str
    label: str
    numerator: str
    denominator: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ratio_id": self.ratio_id,
            "label": self.label,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "unit": "ratio",
            "definition": self.description,
        }


#: Order fixed: column order of ``segment_ratios``.
RATIO_DEFINITIONS: tuple[RatioDefinition, ...] = (
    RatioDefinition(
        "knee_over_hip_width", "Diz açıklığı / kalça genişliği",
        "knee_separation", "hip_width",
        "Diz açıklığının kişinin kendi kalça genişliğine oranı. Boya göre "
        "normalize olduğu için kişiler arasında karşılaştırılabilir; klinik bir "
        "eşiği yoktur.",
    ),
    RatioDefinition(
        "stance_over_hip_width", "Ayak açıklığı / kalça genişliği",
        "ankle_separation", "hip_width",
        "Duruş genişliğinin kalça genişliğine oranı.",
    ),
    RatioDefinition(
        "shoulder_over_hip_width", "Omuz / kalça genişliği",
        "shoulder_width", "hip_width",
        "Gövde oranı proxy'si.",
    ),
)

RATIO_IDS: tuple[str, ...] = tuple(r.ratio_id for r in RATIO_DEFINITIONS)


__all__ = [
    "ANGLE_DEFINITIONS",
    "ANGLE_IDS",
    "ANGLE_SET_VERSION",
    "AngleDefinition",
    "BILATERAL_ANGLE_GROUPS",
    "DISTANCE_DEFINITIONS",
    "DISTANCE_IDS",
    "DISTANCE_SET_VERSION",
    "DistanceDefinition",
    "RATIO_DEFINITIONS",
    "RATIO_IDS",
    "RatioDefinition",
]
