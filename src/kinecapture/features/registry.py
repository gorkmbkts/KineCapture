"""The ordered feature registry and the presets built on top of it.

Order matters twice over. It is the order features are computed in (so a
dependency is always ready before its dependant), and it is the order the
export screen lists them in. It is a tuple, never a set: a fingerprint or a
checkbox list whose order came from set iteration would be reproducible only by
accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from kinecapture.features.base import (
    ArrayContract,
    FeatureCategory,
    FeatureDefinition,
    MappingSupport,
    SourceField,
)
from kinecapture.features.definitions import (
    ANGLE_SET_VERSION,
    DISTANCE_SET_VERSION,
)
from kinecapture.features.roles import missing_roles
from kinecapture.features.summary import SUMMARY_LENGTH, SUMMARY_VERSION
from kinecapture.features.temporal import DEFAULT_GAP_FACTOR
from kinecapture.visualization.skeleton_spec import SkeletonSpec

_LENGTH = "length_unit"
_CAPTURE_SPACE = "capture (ham yakalama koordinat sistemi)"
_NONE_SPACE = "-"

_DERIVATIVE_PARAMS: dict[str, Any] = {
    "method": "central_difference_on_camera_timestamps",
    "boundary": "one_sided",
    "gap_factor": DEFAULT_GAP_FACTOR,
    "gap_rule": "dt <= gap_factor / target_fps ve dt > 0",
    "smoothing": "none",
}

#: Canonical arrays, always written, never selectable.
CANONICAL_ARRAYS: tuple[ArrayContract, ...] = (
    ArrayContract(
        "joints_xyz",
        "[T, J, 3]",
        "float32",
        _LENGTH,
        _CAPTURE_SPACE,
        "Ham eklem koordinatları. Normalizasyon, interpolasyon ve augmentation "
        "uygulanmaz; görülmeyen eklem NaN kalır.",
    ),
    ArrayContract(
        "frame_indices",
        "[T]",
        "int64",
        "kare numarası",
        _NONE_SPACE,
        "Kameranın kendi kare numaraları.",
    ),
    ArrayContract(
        "camera_timestamps_ns",
        "[T]",
        "int64",
        "nanosecond",
        _NONE_SPACE,
        "Kameranın kendi zaman damgaları. Bütün fiziksel türevler bunlardan "
        "hesaplanır.",
    ),
)


FEATURES: tuple[FeatureDefinition, ...] = (
    # ------------------------------------------------------------ canonical
    FeatureDefinition(
        feature_id="canonical_pose",
        version="1.0.0",
        label="Canonical iskelet verisi",
        description=(
            "Ham eklem koordinatları, kare numaraları ve kamera zaman damgaları. "
            "Her sürümde bulunur ve kapatılamaz."
        ),
        category=FeatureCategory.CANONICAL,
        arrays=CANONICAL_ARRAYS,
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        missing_policy="Görülmeyen eklem NaN kalır.",
        default_on=True,
        locked=True,
    ),
    # -------------------------------------------------------------- quality
    FeatureDefinition(
        feature_id="joint_confidences",
        version="1.0.0",
        label="Eklem güven değerleri",
        description="Tracker'ın eklem başına güveni (0..1). Bilinmiyorsa NaN.",
        category=FeatureCategory.QUALITY,
        arrays=(
            ArrayContract(
                "joint_confidences",
                "[T, J]",
                "float32",
                "0..1",
                _NONE_SPACE,
                "Eklem başına güven. Bilinmeyen değer NaN'dır, 0 değil.",
            ),
        ),
        requires=(SourceField.CONFIDENCES,),
        mapping_support=MappingSupport.INDEX_REMAP,
        default_on=True,
    ),
    FeatureDefinition(
        feature_id="validity_masks",
        version="1.0.0",
        label="Geçerlilik maskeleri",
        description=(
            "Hangi eklemin ve hangi karenin gerçekten ölçüldüğünü söyleyen "
            "maskeler. NaN düzeniyle birebir tutarlıdır."
        ),
        category=FeatureCategory.QUALITY,
        arrays=(
            ArrayContract(
                "joint_valid_mask",
                "[T, J]",
                "bool",
                "-",
                _NONE_SPACE,
                "Üç koordinatı da sonlu olan eklemler.",
            ),
            ArrayContract(
                "frame_valid_mask",
                "[T]",
                "bool",
                "-",
                _NONE_SPACE,
                "En az bir kullanılabilir eklem içeren kareler.",
            ),
        ),
        mapping_support=MappingSupport.RECOMPUTE,
    ),
    FeatureDefinition(
        feature_id="frame_timing",
        version="1.0.0",
        label="Kare zamanlaması",
        description=(
            "Kamera zaman damgalarından gelen kareler arası süre. İlk karede "
            "NaN'dır; hedef FPS ile uydurulmaz."
        ),
        category=FeatureCategory.QUALITY,
        arrays=(
            ArrayContract(
                "delta_time_s",
                "[T]",
                "float32",
                "second",
                _NONE_SPACE,
                "s[t] - s[t-1]. İlk kare NaN.",
            ),
        ),
        requires=(SourceField.TIMESTAMPS,),
        mapping_support=MappingSupport.INDEPENDENT,
    ),
    FeatureDefinition(
        feature_id="body_state",
        version="1.0.0",
        label="Gövde durumu",
        description=(
            "Kare başına gövde varlığı, tracker güveni, takip durumu ve "
            "tracker'ın eylem durumu. Klinik bir değerlendirme değildir."
        ),
        category=FeatureCategory.QUALITY,
        arrays=(
            ArrayContract(
                "body_present_mask", "[T]", "bool", "-", _NONE_SPACE,
                "Seçili gövdenin o karede bulunup bulunmadığı.",
            ),
            ArrayContract(
                "body_confidence", "[T]", "float32", "0..100", _NONE_SPACE,
                "Tracker'ın gövde güveni, kaydedildiği ölçekte.",
            ),
            ArrayContract(
                "tracking_state_code", "[T]", "uint8", "kod", _NONE_SPACE,
                "0=yok, 1=ok, 2=searching, 3=off, 4=terminate.",
            ),
            ArrayContract(
                "action_state_code", "[T]", "uint8", "kod", _NONE_SPACE,
                "0=bilinmiyor, 1=idle, 2=moving.",
            ),
        ),
        requires=(SourceField.BODY_STATE,),
        mapping_support=MappingSupport.INDEPENDENT,
    ),
    # --------------------------------------------------------- tracker raw
    FeatureDefinition(
        feature_id="tracker_joint_orientations",
        version="1.0.0",
        label="Eklem quaternionları (local)",
        description=(
            "Tracker'ın parent'a göre eklem yönelimleri, xyzw sırasında. "
            "Parent zinciri kaynağa özgü olduğu için eklem eşleştirmesi "
            "yapıldığında yazılmaz."
        ),
        category=FeatureCategory.TRACKER_RAW,
        arrays=(
            ArrayContract(
                "joint_orientations_xyzw",
                "[T, J, 4]",
                "float32",
                "birim quaternion",
                "parent eklem çerçevesi",
                "Bileşen sırası xyzw. Yerel SDK üzerinde doğrulandı.",
            ),
        ),
        requires=(SourceField.JOINT_ORIENTATIONS,),
        mapping_support=MappingSupport.NATIVE_ONLY,
    ),
    FeatureDefinition(
        feature_id="tracker_joint_positions_2d",
        version="1.0.0",
        label="2B eklem noktaları",
        description=(
            "Sol kamera görüntüsündeki piksel konumları. Yalnız kaydın "
            "provenance'ındaki görüntü boyutu ve iç parametrelerle anlamlıdır."
        ),
        category=FeatureCategory.TRACKER_RAW,
        arrays=(
            ArrayContract(
                "joint_positions_2d",
                "[T, J, 2]",
                "float32",
                "piksel",
                "sol kamera görüntüsü",
                "Görüntü dışındaki veya görülmeyen eklem NaN.",
            ),
        ),
        requires=(SourceField.JOINT_POSITIONS_2D,),
        mapping_support=MappingSupport.INDEX_REMAP,
    ),
    FeatureDefinition(
        feature_id="tracker_joint_covariances",
        version="1.0.0",
        label="Eklem kovaryansları (ham)",
        description=(
            "Eklem başına altı kovaryans değeri, SDK'nın kendi eleman "
            "sırasında. Eleman sırası doğrulanmadığı için buradan std veya "
            "belirsizlik türetilmez."
        ),
        category=FeatureCategory.TRACKER_RAW,
        arrays=(
            ArrayContract(
                "joint_position_covariances_raw",
                "[T, J, 6]",
                "float32",
                "length_unit^2 (varsayılan)",
                "SDK native order",
                "Yorumlanmadan saklanır; adlandırılmış bir 3x3 matris değildir.",
            ),
        ),
        requires=(SourceField.JOINT_POSITION_COVARIANCES,),
        mapping_support=MappingSupport.INDEX_REMAP,
    ),
    FeatureDefinition(
        feature_id="tracker_local_joint_positions",
        version="1.0.0",
        label="Parent'a göre eklem konumları",
        description=(
            "SDK body fitting çıktısı. Parent zincirine bağlı olduğu için "
            "eklem eşleştirmesi yapıldığında yazılmaz."
        ),
        category=FeatureCategory.TRACKER_RAW,
        arrays=(
            ArrayContract(
                "local_joint_positions_xyz",
                "[T, J, 3]",
                "float32",
                _LENGTH,
                "parent eklem çerçevesi",
                "Bazı body formatlarında hiç üretilmez; o zaman NaN kalır.",
            ),
        ),
        requires=(SourceField.LOCAL_JOINT_POSITIONS,),
        mapping_support=MappingSupport.NATIVE_ONLY,
    ),
    FeatureDefinition(
        feature_id="tracker_root_state",
        version="1.0.0",
        label="Tracker kök durumu",
        description=(
            "Tracker'ın kendi kök konumu, yönelimi, hızı ve konum kovaryansı. "
            "Kök hızı, koordinatlardan türetilen hızdan AYRI bir dizidir."
        ),
        category=FeatureCategory.TRACKER_RAW,
        arrays=(
            ArrayContract(
                "root_position_xyz", "[T, 3]", "float32", _LENGTH, _CAPTURE_SPACE,
                "Tracker'ın kök konumu.",
            ),
            ArrayContract(
                "root_orientation_xyzw", "[T, 4]", "float32", "birim quaternion",
                _CAPTURE_SPACE, "Global kök yönelimi, xyzw sırasında.",
            ),
            ArrayContract(
                "tracker_root_velocity_xyz", "[T, 3]", "float32",
                "length_unit/second", _CAPTURE_SPACE,
                "Tracker'ın bildirdiği hız. Türetilen hızla karıştırılmamalıdır.",
            ),
            ArrayContract(
                "root_position_covariance_raw", "[T, 6]", "float32",
                "length_unit^2 (varsayılan)", "SDK native order",
                "Yorumlanmadan saklanır.",
            ),
        ),
        requires=(
            SourceField.ROOT_POSITION,
            SourceField.ROOT_ORIENTATION,
            SourceField.ROOT_VELOCITY,
            SourceField.ROOT_POSITION_COVARIANCE,
        ),
        mapping_support=MappingSupport.INDEPENDENT,
    ),
    # ------------------------------------------------------- coordinates
    FeatureDefinition(
        feature_id="root_centered_positions",
        version="1.0.0",
        label="Kök merkezli koordinatlar",
        description=(
            "Her kare kök eklemden çıkarılmış koordinatlar. Ham koordinatın "
            "yerine geçmez; ayrı bir dizidir."
        ),
        category=FeatureCategory.COORDINATES,
        arrays=(
            ArrayContract(
                "root_centered_xyz", "[T, J, 3]", "float32", _LENGTH,
                "kök eklem orijinli, kamera eksenleri",
                "joints_xyz - joints_xyz[:, root]. Dönme uygulanmaz.",
            ),
        ),
        required_roles=(),
        mapping_support=MappingSupport.RECOMPUTE,
    ),
    FeatureDefinition(
        feature_id="body_aligned_positions",
        version="1.0.0",
        label="Gövdeye hizalı koordinatlar",
        description=(
            "Pelvisten kurulan gövde çerçevesine döndürülmüş koordinatlar. "
            "x = sağ kalçadan sol kalçaya yatay eksen, y = iskeletin dikey "
            "ekseni, z = sağ el kuralıyla tamamlanan eksen."
        ),
        category=FeatureCategory.COORDINATES,
        arrays=(
            ArrayContract(
                "body_aligned_xyz", "[T, J, 3]", "float32", _LENGTH,
                "gövde çerçevesi (kare başına)",
                "Kalçalar görünmeyen karede NaN.",
            ),
            ArrayContract(
                "body_frame_rotation", "[T, 3, 3]", "float32", "-",
                "satırlar gövde eksenleri, kamera koordinatlarında",
                "Kare başına dönme. Sekans düzeyindeki yönelimle aynı isimde "
                "değildir.",
            ),
            ArrayContract(
                "body_frame_valid_mask", "[T]", "bool", "-", _NONE_SPACE,
                "Gövde çerçevesinin kurulabildiği kareler.",
            ),
        ),
        required_roles=("left_hip", "right_hip"),
        mapping_support=MappingSupport.RECOMPUTE,
    ),
    FeatureDefinition(
        feature_id="body_scale",
        version="1.0.0",
        label="Gövde ölçeği (sekans düzeyi)",
        description=(
            "Gövde + uyluk + baldır uzunluklarının kareler üzerindeki medyanı. "
            "Bir boy ölçümü değil, kişi büyüklüğü proxy'sidir."
        ),
        category=FeatureCategory.COORDINATES,
        arrays=(
            ArrayContract(
                "body_scale", "[1]", "float32", _LENGTH, _NONE_SPACE,
                "Sekans başına tek değer. Hesaplanamazsa NaN.",
                time_alignment="sequence",
            ),
        ),
        required_roles=("pelvis", "neck", "left_hip", "left_knee", "left_ankle"),
        mapping_support=MappingSupport.RECOMPUTE,
    ),
    FeatureDefinition(
        feature_id="scale_normalized_positions",
        version="1.0.0",
        label="Ölçeğe bölünmüş koordinatlar",
        description=(
            "Kök merkezli koordinatların gövde ölçeğine bölünmüş hâli. "
            "Ayrı bir özelliktir: ham koordinat da, kök merkezli koordinat da "
            "değişmeden kalır."
        ),
        category=FeatureCategory.COORDINATES,
        arrays=(
            ArrayContract(
                "scale_normalized_xyz", "[T, J, 3]", "float32", "birimsiz",
                "kök eklem orijinli, gövde ölçeğine bölünmüş",
                "Gövde ölçeği hesaplanamazsa tamamen NaN.",
            ),
        ),
        depends_on=("body_scale",),
        required_roles=("pelvis", "neck", "left_hip", "left_knee", "left_ankle"),
        mapping_support=MappingSupport.RECOMPUTE,
    ),
    # ---------------------------------------------------------- geometry
    FeatureDefinition(
        feature_id="bone_geometry",
        version="1.0.0",
        label="Kemik vektörleri ve uzunlukları",
        description=(
            "SkeletonSpec.edges sırasına hizalı kemik vektörleri, uzunlukları "
            "ve birim vektörleri. Eşleştirme yapıldığında hedef iskeletin "
            "topolojisi üzerinde hesaplanır."
        ),
        category=FeatureCategory.GEOMETRY,
        arrays=(
            ArrayContract(
                "bone_vectors_xyz", "[T, B, 3]", "float32", _LENGTH, _CAPTURE_SPACE,
                "child - parent. Uçlarından biri eksikse NaN.",
            ),
            ArrayContract(
                "bone_lengths", "[T, B]", "float32", _LENGTH, _NONE_SPACE,
                "Kemik vektörünün normu.",
            ),
            ArrayContract(
                "bone_unit_vectors_xyz", "[T, B, 3]", "float32", "birimsiz",
                _CAPTURE_SPACE, "Normalize kemik yönü; sıfıra yakın kemikte NaN.",
            ),
            ArrayContract(
                "bone_valid_mask", "[T, B]", "bool", "-", _NONE_SPACE,
                "Her iki ucu da ölçülmüş kemikler.",
            ),
        ),
        mapping_support=MappingSupport.RECOMPUTE,
        parameters={"bone_order": "SkeletonSpec.edges"},
    ),
    FeatureDefinition(
        feature_id="segment_distances",
        version=DISTANCE_SET_VERSION,
        label="Seçilmiş mesafeler",
        description=(
            "Sürümlü ve açıklanabilir bir mesafe listesi. Bütün eklem "
            "çiftlerinin karesel kombinasyonu üretilmez."
        ),
        category=FeatureCategory.SYMMETRY,
        arrays=(
            ArrayContract(
                "segment_distances", "[T, D]", "float32", _LENGTH, _NONE_SPACE,
                "Sütun sırası feature_spec.json'daki mesafe listesidir.",
            ),
            ArrayContract(
                "segment_distance_valid_mask", "[T, D]", "bool", "-", _NONE_SPACE,
                "Her iki eklemi de ölçülmüş mesafeler.",
            ),
        ),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="segment_distances",
    ),
    FeatureDefinition(
        feature_id="segment_ratios",
        version=DISTANCE_SET_VERSION,
        label="Mesafe oranları",
        description=(
            "Kişinin kendi ölçüsüne göre normalize edilmiş boyutsuz oranlar. "
            "Klinik eşik taşımazlar."
        ),
        category=FeatureCategory.SYMMETRY,
        arrays=(
            ArrayContract(
                "segment_ratios", "[T, R]", "float32", "birimsiz", _NONE_SPACE,
                "Payda sıfıra yakınsa NaN.",
            ),
        ),
        depends_on=("segment_distances",),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="segment_ratios",
    ),
    FeatureDefinition(
        feature_id="joint_centroid_proxy",
        version="1.0.0",
        label="Eklem ağırlık merkezi proxy'si",
        description=(
            "Görülen eklemlerin ortalaması. Doğrulanmış antropometrik model "
            "olmadığı için 'center of mass' DEĞİLDİR ve öyle adlandırılmaz."
        ),
        category=FeatureCategory.GEOMETRY,
        arrays=(
            ArrayContract(
                "joint_centroid_proxy_xyz", "[T, 3]", "float32", _LENGTH,
                _CAPTURE_SPACE, "Görülen eklemlerin aritmetik ortalaması.",
            ),
            ArrayContract(
                "joint_centroid_valid_mask", "[T]", "bool", "-", _NONE_SPACE,
                "En az bir eklemin görüldüğü kareler.",
            ),
        ),
        mapping_support=MappingSupport.RECOMPUTE,
    ),
    # -------------------------------------------------------- kinematics
    FeatureDefinition(
        feature_id="joint_displacement",
        version="1.0.0",
        label="Eklem yer değiştirmesi (kare farkı)",
        description=(
            "x[t] - x[t-1]. FİZİKSEL HIZ DEĞİLDİR: FPS değişince değişir. "
            "KineSynthV3'ün 'velocity' kanalı bu türdendir."
        ),
        category=FeatureCategory.KINEMATICS,
        arrays=(
            ArrayContract(
                "joint_displacement_xyz", "[T, J, 3]", "float32", _LENGTH,
                _CAPTURE_SPACE, "İlk kare NaN; sahte sıfır yazılmaz.",
            ),
            ArrayContract(
                "joint_displacement_valid_mask", "[T, J]", "bool", "-", _NONE_SPACE,
                "İki ucu da ölçülmüş kare farkları.",
            ),
        ),
        requires=(SourceField.JOINTS,),
        mapping_support=MappingSupport.RECOMPUTE,
        parameters={"method": "frame_difference", "note": "rate değil, fark"},
    ),
    FeatureDefinition(
        feature_id="joint_velocity",
        version="1.0.0",
        label="Eklem hızı (fiziksel)",
        description=(
            "Kamera zaman damgalarına göre türev; birimi length_unit/saniye. "
            "Takip boşluğu üzerinden köprü kurulmaz."
        ),
        category=FeatureCategory.KINEMATICS,
        arrays=(
            ArrayContract(
                "joint_velocity_xyz", "[T, J, 3]", "float32", "length_unit/second",
                _CAPTURE_SPACE, "İç noktalarda merkezi fark, uçlarda tek yanlı.",
            ),
            ArrayContract(
                "joint_speed", "[T, J]", "float32", "length_unit/second",
                _NONE_SPACE, "Hız vektörünün normu.",
            ),
            ArrayContract(
                "joint_velocity_valid_mask", "[T, J]", "bool", "-", _NONE_SPACE,
                "Türevin gerçekten hesaplanabildiği yerler.",
            ),
        ),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        parameters=dict(_DERIVATIVE_PARAMS),
    ),
    FeatureDefinition(
        feature_id="joint_acceleration",
        version="1.0.0",
        label="Eklem ivmesi",
        description=(
            "Düzensiz zaman gridinde üç noktalı ikinci türev. İlk ve son kare "
            "NaN'dır; ekstrapolasyon yapılmaz."
        ),
        category=FeatureCategory.KINEMATICS,
        arrays=(
            ArrayContract(
                "joint_acceleration_xyz", "[T, J, 3]", "float32",
                "length_unit/second^2", _CAPTURE_SPACE,
                "2*((x2-x1)/dt1 - (x1-x0)/dt0)/(dt0+dt1).",
            ),
            ArrayContract(
                "joint_acceleration_magnitude", "[T, J]", "float32",
                "length_unit/second^2", _NONE_SPACE, "İvme vektörünün normu.",
            ),
            ArrayContract(
                "joint_acceleration_valid_mask", "[T, J]", "bool", "-", _NONE_SPACE,
                "Üç noktalı şablonun kurulabildiği yerler.",
            ),
        ),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        parameters=dict(_DERIVATIVE_PARAMS, boundary="nan"),
    ),
    FeatureDefinition(
        feature_id="root_kinematics",
        version="1.0.0",
        label="Kök yörüngesi ve hızı",
        description=(
            "Kök eklemin yörüngesi, türetilen hızı, sürati ve yol uzunluğu. "
            "Tracker'ın kendi kök hızından ayrı adlarla yazılır."
        ),
        category=FeatureCategory.KINEMATICS,
        arrays=(
            ArrayContract(
                "root_trajectory_xyz", "[T, 3]", "float32", _LENGTH, _CAPTURE_SPACE,
                "Kök eklemin ham konumu.",
            ),
            ArrayContract(
                "root_velocity_derived_xyz", "[T, 3]", "float32",
                "length_unit/second", _CAPTURE_SPACE,
                "Koordinatlardan türetilen hız (tracker'ınki değil).",
            ),
            ArrayContract(
                "root_speed", "[T]", "float32", "length_unit/second", _NONE_SPACE,
                "Türetilen hızın normu.",
            ),
            ArrayContract(
                "root_path_length", "[1]", "float32", _LENGTH, _NONE_SPACE,
                "Geçerli adımların toplamı; boşluk üzerinden atlanır.",
                time_alignment="sequence",
            ),
        ),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        parameters=dict(_DERIVATIVE_PARAMS),
    ),
    FeatureDefinition(
        feature_id="joint_jerk",
        version="0.1.0",
        label="Eklem jerk büyüklüğü",
        description=(
            "İvmenin türevi. Tracker gürültüsüne çok duyarlıdır; DENEYSEL ve "
            "varsayılan olarak kapalıdır."
        ),
        category=FeatureCategory.KINEMATICS,
        arrays=(
            ArrayContract(
                "joint_jerk_magnitude", "[T, J]", "float32",
                "length_unit/second^3", _NONE_SPACE,
                "İkinci türevin bir kez daha türevi.",
            ),
            ArrayContract(
                "joint_jerk_valid_mask", "[T, J]", "bool", "-", _NONE_SPACE,
                "Hesaplanabilen yerler.",
            ),
        ),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        experimental=True,
        parameters=dict(_DERIVATIVE_PARAMS),
    ),
    # ------------------------------------------------------------ angles
    FeatureDefinition(
        feature_id="joint_angles",
        version=ANGLE_SET_VERSION,
        label="Eklem açıları (radyan)",
        description=(
            "Sürümlü anatomik açı tanımları. Sütun adları ve kullanılan "
            "eklemler feature_spec.json içindedir."
        ),
        category=FeatureCategory.ANGLES,
        arrays=(
            ArrayContract(
                "joint_angles_rad", "[T, A]", "float32", "radian", _NONE_SPACE,
                "atan2(|u x v|, u . v) tabanlı; eksik nokta veya sıfıra yakın "
                "vektörde NaN.",
            ),
            ArrayContract(
                "joint_angle_valid_mask", "[T, A]", "bool", "-", _NONE_SPACE,
                "Açının hesaplanabildiği yerler.",
            ),
        ),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="joint_angles_rad",
    ),
    FeatureDefinition(
        feature_id="joint_angles_degrees",
        version=ANGLE_SET_VERSION,
        label="Eklem açıları (derece)",
        description=(
            "Aynı açıların derece cinsinden ayrı dizisi. Bir dizinin birimi "
            "hiçbir zaman belirsiz bırakılmaz."
        ),
        category=FeatureCategory.ANGLES,
        arrays=(
            ArrayContract(
                "joint_angles_deg", "[T, A]", "float32", "degree", _NONE_SPACE,
                "joint_angles_rad'ın derece karşılığı.",
            ),
        ),
        depends_on=("joint_angles",),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="joint_angles_rad",
    ),
    FeatureDefinition(
        feature_id="joint_angular_velocity",
        version=ANGLE_SET_VERSION,
        label="Açısal hız (açı tanımlarından)",
        description=(
            "Tanımlı açıların zaman damgasına göre türevi. Quaternion kaynaklı "
            "açısal hızdan ayrı bir dizidir."
        ),
        category=FeatureCategory.ANGLES,
        arrays=(
            ArrayContract(
                "joint_angular_velocity_rad_s", "[T, A]", "float32", "radian/second",
                _NONE_SPACE, "Merkezi fark; boşluk üzerinden hesaplanmaz.",
            ),
            ArrayContract(
                "joint_angular_velocity_valid_mask", "[T, A]", "bool", "-",
                _NONE_SPACE, "Türevin hesaplanabildiği yerler.",
            ),
        ),
        depends_on=("joint_angles",),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        parameters=dict(_DERIVATIVE_PARAMS),
        column_source="joint_angles_rad",
    ),
    FeatureDefinition(
        feature_id="quaternion_angular_speed",
        version="0.1.0",
        label="Quaternion açısal sürati",
        description=(
            "Eklem quaternionlarından 2*arccos(|<qa,qb>|)/dt ile hesaplanan "
            "toplam dönme hızı. q ile -q eşdeğerliği mutlak iç çarpımla "
            "çözülür; Euler açıları farklanmaz. DENEYSEL."
        ),
        category=FeatureCategory.ANGLES,
        arrays=(
            ArrayContract(
                "quaternion_angular_speed_rad_s", "[T, J]", "float32",
                "radian/second", "parent eklem çerçevesi",
                "Normu birim olmayan quaternionda NaN.",
            ),
            ArrayContract(
                "quaternion_angular_speed_valid_mask", "[T, J]", "bool", "-",
                _NONE_SPACE, "Hesaplanabilen yerler.",
            ),
        ),
        requires=(SourceField.JOINT_ORIENTATIONS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.NATIVE_ONLY,
        experimental=True,
        parameters=dict(_DERIVATIVE_PARAMS, method="quaternion_inner_product"),
    ),
    # ---------------------------------------------------------- symmetry
    FeatureDefinition(
        feature_id="bilateral_angles",
        version=ANGLE_SET_VERSION,
        label="Sol-sağ açı farkları",
        description=(
            "Eşleşen sol/sağ açıların işaretli ve mutlak farkı. Asimetri "
            "teşhisi değildir."
        ),
        category=FeatureCategory.SYMMETRY,
        arrays=(
            ArrayContract(
                "bilateral_angle_difference_rad", "[T, P_a]", "float32", "radian",
                _NONE_SPACE, "sol - sağ, işaretli.",
            ),
            ArrayContract(
                "bilateral_angle_absolute_difference_rad", "[T, P_a]", "float32",
                "radian", _NONE_SPACE, "|sol - sağ|.",
            ),
            ArrayContract(
                "bilateral_angle_valid_mask", "[T, P_a]", "bool", "-", _NONE_SPACE,
                "İki tarafı da hesaplanabilen çiftler.",
            ),
        ),
        depends_on=("joint_angles",),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="bilateral_angle_difference_rad",
    ),
    FeatureDefinition(
        feature_id="bilateral_speed",
        version="1.0.0",
        label="Sol-sağ hız farkları",
        description="Eşleşen sol/sağ eklemlerin süratleri arasındaki fark.",
        category=FeatureCategory.SYMMETRY,
        arrays=(
            ArrayContract(
                "bilateral_speed_difference", "[T, P]", "float32",
                "length_unit/second", _NONE_SPACE, "sol - sağ, işaretli.",
            ),
            ArrayContract(
                "bilateral_speed_absolute_difference", "[T, P]", "float32",
                "length_unit/second", _NONE_SPACE, "|sol - sağ|.",
            ),
            ArrayContract(
                "bilateral_speed_valid_mask", "[T, P]", "bool", "-", _NONE_SPACE,
                "İki tarafı da ölçülmüş çiftler.",
            ),
        ),
        depends_on=("joint_velocity",),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="bilateral_speed_difference",
    ),
    FeatureDefinition(
        feature_id="bilateral_mirror",
        version="1.0.0",
        label="Ayna mesafesi (gövde uzayında)",
        description=(
            "Sol eklem ile sağ eklemin sagittal düzleme göre yansımasının "
            "arasındaki uzaklık. Kamera koordinatında değil, gövde uzayında "
            "hesaplanır; aksi hâlde kameraya göre duruş açısı asimetri gibi "
            "görünürdü."
        ),
        category=FeatureCategory.SYMMETRY,
        arrays=(
            ArrayContract(
                "bilateral_mirror_distance", "[T, P]", "float32", _LENGTH,
                "gövde çerçevesi", "Gövde çerçevesi kurulamayan karede NaN.",
            ),
            ArrayContract(
                "bilateral_mirror_valid_mask", "[T, P]", "bool", "-", _NONE_SPACE,
                "Hesaplanabilen çiftler.",
            ),
        ),
        depends_on=("body_aligned_positions",),
        required_roles=("left_hip", "right_hip"),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="bilateral_mirror_distance",
    ),
    # ----------------------------------------------------------- summary
    FeatureDefinition(
        feature_id="summary_vector",
        version=SUMMARY_VERSION,
        label="Klasik ML özet vektörü",
        description=(
            f"Sabit uzunluklu ({SUMMARY_LENGTH}) özet vektörü. Eleman adları "
            "feature_spec.json içindedir. Etikete, katılımcıya veya dataset "
            "geneline bakan hiçbir eleman yoktur."
        ),
        category=FeatureCategory.SUMMARY,
        arrays=(
            ArrayContract(
                "summary_features",
                f"[{SUMMARY_LENGTH}]",
                "float32",
                "karışık (eleman başına feature_spec'te)",
                _NONE_SPACE,
                "Hesaplanamayan eleman NaN; uzunluk örnekten örneğe değişmez.",
                time_alignment="sequence",
            ),
        ),
        depends_on=("joint_angles", "joint_velocity", "body_aligned_positions"),
        requires=(SourceField.JOINTS, SourceField.TIMESTAMPS),
        mapping_support=MappingSupport.RECOMPUTE,
        column_source="summary_features",
    ),
)

_BY_ID: dict[str, FeatureDefinition] = {f.feature_id: f for f in FEATURES}

#: Features written by an export that changes nothing from the pre-feature
#: behaviour: the canonical arrays plus the confidences that were always there.
DEFAULT_FEATURE_IDS: tuple[str, ...] = tuple(
    f.feature_id for f in FEATURES if f.default_on
)

#: Ids that cannot be switched off.
LOCKED_FEATURE_IDS: tuple[str, ...] = tuple(f.feature_id for f in FEATURES if f.locked)


def all_features() -> tuple[FeatureDefinition, ...]:
    return FEATURES


def get_feature(feature_id: str) -> FeatureDefinition:
    try:
        return _BY_ID[feature_id]
    except KeyError:
        known = ", ".join(sorted(_BY_ID))
        raise KeyError(
            f"Bilinmeyen özellik '{feature_id}'. Kayıtlı özellikler: {known}."
        ) from None


def find_feature(feature_id: str) -> Optional[FeatureDefinition]:
    return _BY_ID.get(feature_id)


def order_features(feature_ids: Iterable[str]) -> tuple[str, ...]:
    """Registry order, dependencies first, duplicates and unknowns removed."""
    wanted = {fid for fid in feature_ids if fid in _BY_ID}
    wanted.update(LOCKED_FEATURE_IDS)
    # Pull in dependencies transitively; a feature that needs another one's
    # intermediate results must not depend on the user having ticked both.
    changed = True
    while changed:
        changed = False
        for feature_id in list(wanted):
            for dependency in _BY_ID[feature_id].depends_on:
                if dependency not in wanted:
                    wanted.add(dependency)
                    changed = True
    return tuple(f.feature_id for f in FEATURES if f.feature_id in wanted)


def array_keys_for(feature_ids: Iterable[str]) -> tuple[str, ...]:
    """Every array key the given selection writes, in registry order."""
    keys: list[str] = []
    for feature_id in order_features(feature_ids):
        keys.extend(_BY_ID[feature_id].array_keys)
    return tuple(keys)


#: Bytes per element, by declared dtype.
_ITEM_BYTES: dict[str, int] = {
    "float32": 4,
    "float64": 8,
    "int32": 4,
    "int64": 8,
    "uint8": 1,
    "bool": 1,
}

#: Symbolic shape dimensions that are fixed by a definition list rather than by
#: the skeleton. ``T`` (frames), ``J`` (joints) and ``B`` (bones) are resolved
#: from the sample instead.
_FIXED_DIMENSIONS: dict[str, int] = {
    "A": 11,  # angle definitions
    "D": 14,  # distance definitions
    "R": 3,  # ratio definitions
    "P": 10,  # bilateral joint pairs
    "P_a": 4,  # bilateral angle groups
}


def estimate_bytes_per_frame(
    feature_ids: Iterable[str], *, num_joints: int, num_bones: int
) -> int:
    """Rough uncompressed bytes each frame of a sample costs.

    Used only to warn the user before a large export. It is an *upper* estimate
    of the stored size: the ``.npz`` is compressed, and NaN-heavy arrays
    compress very well.
    """
    from kinecapture.features.summary import SUMMARY_LENGTH

    dimensions = dict(_FIXED_DIMENSIONS)
    dimensions.update({"J": int(num_joints), "B": int(num_bones)})
    total = 0
    for feature_id in order_features(feature_ids):
        for contract in _BY_ID[feature_id].arrays:
            tokens = [
                token.strip()
                for token in contract.shape.strip("[]").split(",")
                if token.strip()
            ]
            elements = 1
            per_frame = False
            for token in tokens:
                if token == "T":
                    per_frame = True
                    continue
                if token.isdigit():
                    elements *= int(token)
                elif token in dimensions:
                    elements *= dimensions[token]
                elif token == str(SUMMARY_LENGTH):
                    elements *= SUMMARY_LENGTH
                else:
                    elements *= 1
            if not per_frame:
                # Sequence-level arrays cost the same regardless of length; a
                # per-frame estimate would over-count them badly on long takes.
                continue
            total += elements * _ITEM_BYTES.get(contract.dtype, 4)
    return total


@dataclass(frozen=True)
class Applicability:
    """Whether a feature can run at all for a given export configuration."""

    supported: bool
    reason: str = ""

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.supported


def applicability(
    definition: FeatureDefinition,
    spec: SkeletonSpec,
    *,
    mapping_active: bool = False,
    available_sources: Optional[Sequence[str]] = None,
) -> Applicability:
    """Can this feature produce anything for ``spec``?

    ``available_sources`` lists the optional tracker fields the takes actually
    contain. When it is ``None`` the question is answered on the skeleton and
    mapping alone, which is what the export screen shows before a build.
    """
    if mapping_active and definition.mapping_support is MappingSupport.NATIVE_ONLY:
        return Applicability(
            False,
            "Eklem eşleştirmesi seçiliyken bu alan anlamını yitirir; yalnız "
            "native iskelet biçiminde yazılır.",
        )
    missing = missing_roles(spec, definition.required_roles)
    if missing:
        return Applicability(
            False,
            f"'{spec.name}' iskeletinde şu eklem rolleri yok: {', '.join(missing)}.",
        )
    if available_sources is not None:
        optional = [
            source
            for source in definition.requires
            if source
            not in (SourceField.JOINTS, SourceField.TIMESTAMPS, SourceField.BODY_STATE)
        ]
        if optional and all(
            source.value not in available_sources for source in optional
        ):
            names = ", ".join(source.label for source in optional)
            return Applicability(
                False, f"Bu kayıtlarda gerekli tracker alanı yok: {names}."
            )
    return Applicability(True)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeaturePreset:
    """A named starting selection. Presets only tick boxes; the export always
    records the resolved feature ids, never the preset name alone."""

    preset_id: str
    label: str
    description: str
    feature_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "label": self.label,
            "description": self.description,
            "feature_ids": list(self.feature_ids),
        }


_QUALITY = ("joint_confidences", "validity_masks", "frame_timing", "body_state")
_COORDS = (
    "root_centered_positions",
    "body_aligned_positions",
    "body_scale",
    "scale_normalized_positions",
)
_KINEMATICS = (
    "joint_displacement",
    "joint_velocity",
    "joint_acceleration",
    "root_kinematics",
)
_ANGLES = ("joint_angles", "joint_angular_velocity")
_SYMMETRY = (
    "segment_distances",
    "segment_ratios",
    "bilateral_angles",
    "bilateral_speed",
    "bilateral_mirror",
)

PRESETS: tuple[FeaturePreset, ...] = (
    FeaturePreset(
        "minimal",
        "Minimum canonical",
        "Yalnız ham iskelet, kare numaraları ve zaman damgaları.",
        (),
    ),
    FeaturePreset(
        "kinesynth_compat",
        "KineSynth temel uyumluluk",
        (
            "Mevcut KineSynth modelinin beklediği kanallar: ham koordinat, "
            "kök merkezli koordinat ve KARE FARKI (joint_displacement). "
            "KineSynth'in 'velocity' kanalı fiziksel hız değildir; fiziksel hız "
            "bu presete dahil edilmez."
        ),
        ("joint_confidences", "validity_masks", "root_centered_positions",
         "joint_displacement"),
    ),
    FeaturePreset(
        "kinematics_research",
        "Kinematik araştırma",
        "Kalite, koordinat temsilleri, kemik geometrisi, fiziksel türevler, "
        "açılar ve simetri.",
        _QUALITY + _COORDS + ("bone_geometry", "joint_centroid_proxy")
        + _KINEMATICS + _ANGLES + _SYMMETRY,
    ),
    FeaturePreset(
        "classical_ml",
        "Klasik ML",
        "Sabit uzunluklu özet vektörü ve onu besleyen açı/mesafe özellikleri.",
        _QUALITY + ("body_scale", "joint_angles", "joint_velocity",
                    "segment_distances", "segment_ratios", "bilateral_angles",
                    "summary_vector"),
    ),
    FeaturePreset(
        "research_all",
        "Desteklenen tüm araştırma özellikleri",
        "Deneysel olanlar dışında kayıtlı bütün özellikler.",
        tuple(f.feature_id for f in FEATURES if not f.experimental and not f.locked),
    ),
)

_PRESETS_BY_ID = {preset.preset_id: preset for preset in PRESETS}


def get_preset(preset_id: str) -> FeaturePreset:
    try:
        return _PRESETS_BY_ID[preset_id]
    except KeyError:
        known = ", ".join(p.preset_id for p in PRESETS)
        raise KeyError(f"Bilinmeyen preset '{preset_id}'. Kayıtlı: {known}.") from None


def match_preset(feature_ids: Iterable[str]) -> Optional[str]:
    """The preset that exactly matches a selection, if any."""
    selection = set(order_features(feature_ids))
    for preset in PRESETS:
        if set(order_features(preset.feature_ids)) == selection:
            return preset.preset_id
    return None


def registry_fingerprint_keys(feature_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Definition identities for the dataset fingerprint, in registry order."""
    return [_BY_ID[fid].fingerprint_key() for fid in order_features(feature_ids)]


__all__ = [
    "Applicability",
    "CANONICAL_ARRAYS",
    "DEFAULT_FEATURE_IDS",
    "FEATURES",
    "FeaturePreset",
    "LOCKED_FEATURE_IDS",
    "PRESETS",
    "all_features",
    "applicability",
    "array_keys_for",
    "estimate_bytes_per_frame",
    "find_feature",
    "get_feature",
    "get_preset",
    "match_preset",
    "order_features",
    "registry_fingerprint_keys",
]
