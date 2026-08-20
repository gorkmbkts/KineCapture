"""Label schema: the project-scoped, versioned vocabulary for annotation.

The label ontology is *data*, not code. A project owns a ``label_schema.json``
and the annotation UI is built from it, so adding an exercise or an error type
is an editing operation rather than a code change.

The built-in default deliberately ships a small, generic starting point:

* exercises are empty by default, because inventing an exercise list for
  somebody else's protocol is worse than asking for one;
* error types are empty by default. MEMORY.md section 8 is explicit that error
  classes must not be invented in code, so the schema carries the *mechanism*
  for error types while leaving the vocabulary to the researcher.

``correctness``, ``movement_phase`` and the annotation statuses are structural
rather than domain-specific, so those do have defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from kinecapture import LABEL_SCHEMA_VERSION
from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import slugify
from kinecapture.domain.enums import Correctness


@dataclass(frozen=True)
class LabelOption:
    """One selectable value: a stable ``code`` plus a display ``label``."""

    code: str
    label: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "label": self.label, "description": self.description}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LabelOption":
        code = str(payload.get("code") or "").strip()
        if not code:
            raise ValidationError(
                "Etiket seçeneğinin 'code' alanı boş olamaz.",
                field="code",
                code="label_code_empty",
            )
        return cls(
            code=code,
            label=str(payload.get("label") or code),
            description=str(payload.get("description", "")),
        )

    @classmethod
    def from_name(cls, name: str, description: str = "") -> "LabelOption":
        """Build an option from a human name, deriving a stable code from it."""
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValidationError(
                "Ad boş olamaz.", field="label", code="label_name_empty"
            )
        return cls(code=slugify(cleaned, fallback="label"), label=cleaned, description=description)


#: Movement phases are kinematic structure, not a clinical claim, so a generic
#: default is safe. Projects can replace the list.
_DEFAULT_PHASES = (
    LabelOption("setup", "Hazırlık"),
    LabelOption("concentric", "Konsantrik"),
    LabelOption("hold", "Duraklama"),
    LabelOption("eccentric", "Eksantrik"),
    LabelOption("recovery", "Toparlanma"),
)

_CORRECTNESS_LABELS = {
    Correctness.CORRECT: "Doğru",
    Correctness.INCORRECT: "Hatalı",
    Correctness.UNCERTAIN: "Kararsız",
    Correctness.UNKNOWN: "Etiketlenmedi",
}


@dataclass
class LabelSchema:
    """A project's annotation vocabulary (``label_schema.json``)."""

    schema_version: str = LABEL_SCHEMA_VERSION
    exercises: list[LabelOption] = field(default_factory=list)
    error_types: list[LabelOption] = field(default_factory=list)
    movement_phases: list[LabelOption] = field(default_factory=lambda: list(_DEFAULT_PHASES))
    body_regions: list[LabelOption] = field(default_factory=list)
    severity_scale: tuple[float, float] = (0.0, 3.0)
    notes: str = ""

    @classmethod
    def default(cls) -> "LabelSchema":
        return cls()

    # --------------------------------------------------------------- lookups
    def exercise_codes(self) -> tuple[str, ...]:
        return tuple(option.code for option in self.exercises)

    def error_type_codes(self) -> tuple[str, ...]:
        return tuple(option.code for option in self.error_types)

    def label_for_exercise(self, code: str) -> str:
        return next((o.label for o in self.exercises if o.code == code), code)

    @staticmethod
    def label_for_correctness(value: Correctness) -> str:
        return _CORRECTNESS_LABELS.get(value, value.value)

    def find_exercise(self, code: str) -> Optional[LabelOption]:
        return next((o for o in self.exercises if o.code == code), None)

    # -------------------------------------------------------------- mutation
    def add_exercise(self, name: str, description: str = "") -> LabelOption:
        """Add an exercise, refusing a duplicate code rather than shadowing one."""
        option = LabelOption.from_name(name, description)
        if self.find_exercise(option.code) is not None:
            raise ValidationError(
                f"'{option.label}' egzersizi zaten tanımlı.",
                field="exercise",
                code="exercise_duplicate",
            )
        self.exercises.append(option)
        return option

    def add_error_type(self, name: str, description: str = "") -> LabelOption:
        option = LabelOption.from_name(name, description)
        if any(o.code == option.code for o in self.error_types):
            raise ValidationError(
                f"'{option.label}' hata türü zaten tanımlı.",
                field="error_type",
                code="error_type_duplicate",
            )
        self.error_types.append(option)
        return option

    # ------------------------------------------------------------ validation
    def validate_annotation_values(
        self, *, exercise: str, error_types: Sequence[str]
    ) -> list[dict[str, Any]]:
        """Report values that are not part of this schema.

        Used by the dataset QA screen to surface label-schema drift, for example
        after a schema was edited while old annotations still reference removed
        codes.
        """
        problems: list[dict[str, Any]] = []
        if exercise and self.exercises and exercise not in self.exercise_codes():
            problems.append(
                {
                    "issue": "unknown_exercise",
                    "value": exercise,
                    "message": f"'{exercise}' bu projenin etiket şemasında yok.",
                }
            )
        known_errors = set(self.error_type_codes())
        for code in error_types:
            if self.error_types and code not in known_errors:
                problems.append(
                    {
                        "issue": "unknown_error_type",
                        "value": code,
                        "message": f"'{code}' hata türü şemada tanımlı değil.",
                    }
                )
        return problems

    # ------------------------------------------------------------- transport
    def label_mapping(self) -> dict[str, Any]:
        """The mapping block written into a dataset release.

        Class indices are assigned by sorted code so two releases built from the
        same schema always agree on the integer meaning of a class.
        """
        exercises = sorted(self.exercise_codes())
        correctness = [c.value for c in Correctness]
        return {
            "schema_version": self.schema_version,
            "exercise": {
                "classes": exercises,
                "code_to_index": {code: i for i, code in enumerate(exercises)},
                "labels": {o.code: o.label for o in self.exercises},
            },
            "correctness": {
                "classes": correctness,
                "code_to_index": {code: i for i, code in enumerate(correctness)},
                "labels": {
                    c.value: _CORRECTNESS_LABELS[c] for c in Correctness
                },
            },
            "error_types": {
                "classes": sorted(self.error_type_codes()),
                "labels": {o.code: o.label for o in self.error_types},
            },
            "movement_phases": {
                "classes": [o.code for o in self.movement_phases],
                "labels": {o.code: o.label for o in self.movement_phases},
            },
            "severity_scale": list(self.severity_scale),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "exercises": [o.to_dict() for o in self.exercises],
            "error_types": [o.to_dict() for o in self.error_types],
            "movement_phases": [o.to_dict() for o in self.movement_phases],
            "body_regions": [o.to_dict() for o in self.body_regions],
            "severity_scale": list(self.severity_scale),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LabelSchema":
        def options(key: str, fallback: Sequence[LabelOption] = ()) -> list[LabelOption]:
            raw = payload.get(key)
            if raw is None:
                return list(fallback)
            return [LabelOption.from_dict(item) for item in raw]

        scale = payload.get("severity_scale") or (0.0, 3.0)
        return cls(
            schema_version=str(payload.get("schema_version") or LABEL_SCHEMA_VERSION),
            exercises=options("exercises"),
            error_types=options("error_types"),
            movement_phases=options("movement_phases", _DEFAULT_PHASES),
            body_regions=options("body_regions"),
            severity_scale=(float(scale[0]), float(scale[1])),
            notes=str(payload.get("notes", "")),
        )


__all__ = ["LabelOption", "LabelSchema"]
