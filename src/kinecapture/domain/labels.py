"""Label schema: the project-scoped, versioned vocabulary for annotation.

The label ontology is *data*, not code. A project owns a ``label_schema.json``
and the annotation UI is built from it, so adding an exercise or an error class
is an editing operation rather than a code change.

The built-in default deliberately ships a small, generic starting point:

* exercises are empty by default, because inventing an exercise list for
  somebody else's protocol is worse than asking for one;
* error classes are empty by default. MEMORY.md is explicit that error classes
  must not be invented in code, so the schema carries the *mechanism* while
  leaving the vocabulary to the researcher.

Only ``correctness`` is structural rather than domain-specific, and it is
binary: a movement was performed correctly or it was not.

Movement phase was removed in the two-level label redesign. Older schema files
may still contain a ``movement_phases`` list; it is read into :attr:`LabelSchema.legacy`
so nothing is destroyed, but nothing in the application offers it any more.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from kinecapture import LABEL_SCHEMA_VERSION
from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import slugify
from kinecapture.domain.enums import Correctness


def _match_key(text: str) -> str:
    """Normalised form used to detect "the same class typed differently".

    Case, surrounding and repeated whitespace, and Unicode composition are all
    ignored, so ``"Diz içe çöküyor"``, ``"diz  içe çöküyor "`` and
    ``"DİZ İÇE ÇÖKÜYOR"`` are recognised as one class rather than silently
    becoming three.
    """
    normalised = unicodedata.normalize("NFKC", text or "")
    # Turkish dotted/dotless I: casefold maps these consistently enough for
    # duplicate detection, which is all this key is used for.
    return " ".join(normalised.casefold().split())


@dataclass(frozen=True)
class LabelOption:
    """One selectable value: a stable ``code`` plus a display ``label``.

    An error class also carries the anatomical joints it is *about*. That
    relationship is defined once, when the class is created, and applied to
    every interval afterwards so nobody is asked the same question thirty
    times - but see :attr:`default_roles` for what it is and is not.
    """

    code: str
    label: str
    description: str = ""
    #: Anatomical roles this class is about, by role name - never by joint
    #: index, which means different joints in different skeleton formats.
    #: Empty for a movement class and for an error class defined before this
    #: existed; empty means *unknown*, not *none*.
    default_roles: tuple[str, ...] = ()
    #: Bumped whenever ``default_roles`` changes. An interval records the
    #: revision it copied, so a class edited later cannot silently rewrite
    #: what somebody already reviewed.
    roles_revision: int = 0

    @property
    def match_key(self) -> str:
        return _match_key(self.label)

    @property
    def has_roles(self) -> bool:
        return bool(self.default_roles)

    def with_roles(self, roles: Sequence[str]) -> "LabelOption":
        """A copy with new default joints and the next revision.

        The revision moves even when the set is unchanged in content but was
        re-stated by a person: what an interval records is *which* definition
        it copied, and two definitions that happen to agree are still two.
        """
        return LabelOption(
            code=self.code,
            label=self.label,
            description=self.description,
            default_roles=tuple(dict.fromkeys(str(role) for role in roles)),
            roles_revision=self.roles_revision + 1,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "label": self.label,
            "description": self.description,
        }
        if self.default_roles or self.roles_revision:
            # Written only when there is something to say, so a schema with no
            # joint relationships is byte-identical to the one before this.
            payload["default_roles"] = list(self.default_roles)
            payload["roles_revision"] = int(self.roles_revision)
        return payload

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
            default_roles=tuple(
                str(role) for role in payload.get("default_roles") or ()
            ),
            roles_revision=int(payload.get("roles_revision") or 0),
        )

    @classmethod
    def from_name(
        cls,
        name: str,
        description: str = "",
        roles: Sequence[str] = (),
    ) -> "LabelOption":
        """Build an option from a human name, deriving a stable code from it."""
        cleaned = " ".join((name or "").split())
        if not cleaned:
            raise ValidationError(
                "Ad boş olamaz.", field="label", code="label_name_empty"
            )
        chosen = tuple(dict.fromkeys(str(role) for role in roles))
        return cls(
            code=slugify(cleaned, fallback="label"),
            label=cleaned,
            description=description,
            default_roles=chosen,
            # A class created *with* joints has already had them decided once.
            roles_revision=1 if chosen else 0,
        )


_CORRECTNESS_LABELS = {
    Correctness.CORRECT: "Doğru",
    Correctness.INCORRECT: "Hatalı",
    Correctness.UNLABELLED: "Etiketlenmedi",
}


@dataclass
class LabelSchema:
    """A project's annotation vocabulary (``label_schema.json``)."""

    schema_version: str = LABEL_SCHEMA_VERSION
    exercises: list[LabelOption] = field(default_factory=list)
    error_types: list[LabelOption] = field(default_factory=list)
    notes: str = ""
    #: Blocks from an older schema that this version no longer models
    #: (``movement_phases``, ``body_regions``, ``severity_scale``). Preserved
    #: verbatim so upgrading never throws a researcher's work away.
    legacy: dict[str, Any] = field(default_factory=dict)

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

    def label_for_error(self, code: str) -> str:
        """Display name for an error class, falling back to its raw code.

        A code with no definition still renders, so an annotation that
        references a removed class stays readable instead of showing blank.
        """
        return next((o.label for o in self.error_types if o.code == code), code)

    @staticmethod
    def label_for_correctness(value: Correctness) -> str:
        return _CORRECTNESS_LABELS.get(value, value.value)

    def find_exercise(self, code: str) -> Optional[LabelOption]:
        return next((o for o in self.exercises if o.code == code), None)

    def find_error_type(self, code: str) -> Optional[LabelOption]:
        return next((o for o in self.error_types if o.code == code), None)

    def match_exercise(self, name: str) -> Optional[LabelOption]:
        """Find an existing exercise that a typed name would duplicate.

        Exercises are now created mid-labelling exactly like error classes, so
        they need the same forgiving duplicate rule: a stray capital or a
        double space must select the existing class rather than quietly
        splitting one movement into two.
        """
        candidate = LabelOption.from_name(name) if name.strip() else None
        if candidate is None:
            return None
        key = candidate.match_key
        for option in self.exercises:
            if option.match_key == key or option.code == candidate.code:
                return option
        return None

    def search_exercises(self, query: str) -> list[LabelOption]:
        """Exercises matching a free-text query, best matches first."""
        text = _match_key(query)
        if not text:
            return list(self.exercises)
        starts: list[LabelOption] = []
        contains: list[LabelOption] = []
        for option in self.exercises:
            haystack = f"{option.match_key} {option.code}"
            if option.match_key.startswith(text) or option.code.startswith(text):
                starts.append(option)
            elif text in haystack:
                contains.append(option)
        return starts + contains

    def ensure_exercise(self, name: str, description: str = "") -> LabelOption:
        """Return the matching exercise, creating it only if it is new."""
        existing = self.match_exercise(name)
        if existing is not None:
            return existing
        return self.add_exercise(name, description)

    def match_error_type(self, name: str) -> Optional[LabelOption]:
        """Find an existing class that a typed name would duplicate."""
        candidate = LabelOption.from_name(name) if name.strip() else None
        if candidate is None:
            return None
        key = candidate.match_key
        for option in self.error_types:
            if option.match_key == key or option.code == candidate.code:
                return option
        return None

    def search_error_types(self, query: str) -> list[LabelOption]:
        """Error classes matching a free-text query, best matches first.

        Used by the labelling picker, which has to stay fast and forgiving:
        the researcher types a fragment, not an exact code.
        """
        text = _match_key(query)
        if not text:
            return list(self.error_types)
        starts: list[LabelOption] = []
        contains: list[LabelOption] = []
        for option in self.error_types:
            haystack = f"{option.match_key} {option.code}"
            if option.match_key.startswith(text) or option.code.startswith(text):
                starts.append(option)
            elif text in haystack:
                contains.append(option)
        return starts + contains

    # -------------------------------------------------------------- mutation
    def add_exercise(self, name: str, description: str = "") -> LabelOption:
        """Add an exercise, refusing a near-duplicate.

        Detection matches :meth:`add_error_type`: case, spacing and Unicode
        form are normalised, because both vocabularies are now edited from a
        labelling dialog where a typo would otherwise create a second class
        that means the same thing.
        """
        option = LabelOption.from_name(name, description)
        existing = self.match_exercise(name)
        if existing is not None:
            raise ValidationError(
                f"'{existing.label}' egzersizi zaten tanımlı.",
                field="exercise",
                code="exercise_duplicate",
            )
        self.exercises.append(option)
        return option

    def add_error_type(self, name: str, description: str = "") -> LabelOption:
        """Add an error class, refusing a near-duplicate.

        Duplicate detection is deliberately loose (case, spacing, Unicode form)
        because the picker creates classes mid-labelling, where a stray capital
        would otherwise silently split one class into two.
        """
        option = LabelOption.from_name(name, description)
        existing = self.match_error_type(name)
        if existing is not None:
            raise ValidationError(
                f"'{existing.label}' hata türü zaten tanımlı.",
                field="error_type",
                code="error_type_duplicate",
                details={"code": existing.code, "label": existing.label},
            )
        self.error_types.append(option)
        return option

    def ensure_error_type(self, name: str, description: str = "") -> LabelOption:
        """Return the matching error class, creating it only if it is new.

        This is what the labelling picker calls: typing a name that already
        exists selects it instead of raising, so the annotator never has to
        care whether they are creating or reusing.
        """
        existing = self.match_error_type(name)
        if existing is not None:
            return existing
        return self.add_error_type(name, description)

    def add_error_type_with_roles(
        self, name: str, roles: Sequence[str], description: str = ""
    ) -> LabelOption:
        """Add an error class together with the joints it is about.

        One operation, because the two halves are one decision: a class stored
        without its joints is a class somebody has to be asked about again,
        and a half-made class is exactly what JOINT-01 rules out.
        """
        cleaned = " ".join((name or "").split())
        chosen = tuple(dict.fromkeys(str(role) for role in roles if role))
        if not chosen:
            raise ValidationError(
                "Yeni hata sınıfı için en az bir eklem seçilmelidir.",
                field="error_type",
                code="error_type_without_roles",
                remedy="3B görünümde ilgili eklemlere çift tıklayın.",
            )
        existing = self.match_error_type(cleaned)
        if existing is not None:
            raise ValidationError(
                f"'{existing.label}' hata türü zaten tanımlı.",
                field="error_type",
                code="error_type_duplicate",
                details={"code": existing.code, "label": existing.label},
            )
        option = LabelOption.from_name(cleaned, description, roles=chosen)
        self.error_types.append(option)
        return option

    def set_error_type_roles(
        self, code: str, roles: Sequence[str]
    ) -> LabelOption:
        """Change which joints a class is about, and move its revision.

        What this does **not** do is reach into the intervals already labelled
        with the class. Each of those recorded the revision it copied, so an
        edit here changes what the *next* interval inherits and leaves every
        earlier decision exactly as the person left it.
        """
        option = self.find_error_type(code)
        if option is None:
            raise ValidationError(
                f"'{code}' hata türü bulunamadı.",
                field="error_type",
                code="error_type_missing",
            )
        updated = option.with_roles(roles)
        self.error_types = [
            updated if o.code == option.code else o for o in self.error_types
        ]
        return updated

    def roles_for_error_type(self, code: str) -> tuple[str, ...]:
        """A class's default joints, or empty when it declares none."""
        option = self.find_error_type(code)
        return option.default_roles if option is not None else ()

    def rename_error_type(self, code: str, new_name: str) -> LabelOption:
        """Change an error class's display name, keeping its code stable.

        The code is what annotations and exported releases reference, so it is
        never rewritten: renaming stays a purely cosmetic, non-destructive act.
        """
        option = self.find_error_type(code)
        if option is None:
            raise ValidationError(
                f"'{code}' hata türü bulunamadı.",
                field="error_type",
                code="error_type_missing",
            )
        renamed = LabelOption(
            code=option.code,
            label=" ".join((new_name or "").split()) or option.label,
            description=option.description,
        )
        clash = next(
            (
                o
                for o in self.error_types
                if o.code != option.code and o.match_key == renamed.match_key
            ),
            None,
        )
        if clash is not None:
            raise ValidationError(
                f"'{clash.label}' adı başka bir hata türünde kullanılıyor.",
                field="error_type",
                code="error_type_duplicate",
            )
        self.error_types = [
            renamed if o.code == option.code else o for o in self.error_types
        ]
        return renamed

    def remove_error_type(self, code: str, *, used_codes: Sequence[str] = ()) -> None:
        """Remove an unused error class.

        Refuses while any annotation still references it: silently deleting a
        class would leave stored labels pointing at a code nothing defines.
        """
        option = self.find_error_type(code)
        if option is None:
            raise ValidationError(
                f"'{code}' hata türü bulunamadı.",
                field="error_type",
                code="error_type_missing",
            )
        if code in set(used_codes):
            raise ValidationError(
                f"'{option.label}' hata türü etiketlerde kullanılıyor; silinemez.",
                field="error_type",
                code="error_type_in_use",
                remedy="Önce bu hata türünü kullanan aralıkları değiştirin.",
            )
        self.error_types = [o for o in self.error_types if o.code != code]

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
            if code not in known_errors:
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
        same schema always agree on the integer meaning of a class. The error
        mapping is what a temporal-localisation target array is indexed by, so
        its stability matters as much as the exercise mapping's.
        """
        exercises = sorted(self.exercise_codes())
        errors = sorted(self.error_type_codes())
        # Only decided verdicts are exportable, so only they get class indices.
        correctness = [Correctness.CORRECT.value, Correctness.INCORRECT.value]
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
                    Correctness.CORRECT.value: _CORRECTNESS_LABELS[Correctness.CORRECT],
                    Correctness.INCORRECT.value: _CORRECTNESS_LABELS[
                        Correctness.INCORRECT
                    ],
                },
                "binary": True,
                "note": (
                    "Karar ikilidir. Etiketlenmemiş örnekler export edilmez ve "
                    "bir sınıf indeksi almaz."
                ),
            },
            "error_types": {
                "classes": errors,
                "code_to_index": {code: i for i, code in enumerate(errors)},
                "labels": {o.code: o.label for o in self.error_types},
                # The joints a class is *defined* as being about, and which
                # revision of that definition this release was built from.
                # An interval's own roles are exported separately: a default
                # carried over is a different claim from a joint somebody
                # looked at for that repetition, and a release has to keep
                # the two apart to be usable as node-level supervision.
                "default_roles": {
                    o.code: list(o.default_roles)
                    for o in self.error_types
                    if o.default_roles
                },
                "roles_revision": {
                    o.code: int(o.roles_revision)
                    for o in self.error_types
                    if o.roles_revision
                },
                "note": (
                    "error_multi_hot dizisinin sütun sırası bu code_to_index "
                    "eşlemesiyle aynıdır. default_roles sınıf tanımıdır; "
                    "bir aralığın kendi eklemleri örnek kaydındadır."
                ),
            },
        }

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "exercises": [o.to_dict() for o in self.exercises],
            "error_types": [o.to_dict() for o in self.error_types],
            "notes": self.notes,
        }
        if self.legacy:
            payload["legacy"] = dict(self.legacy)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LabelSchema":
        def options(key: str) -> list[LabelOption]:
            raw = payload.get(key)
            if not raw:
                return []
            return [LabelOption.from_dict(item) for item in raw]

        legacy = dict(payload.get("legacy") or {})
        # Blocks this version dropped. Kept so a downgrade or a later decision
        # can still see what the project used to define.
        for dropped in ("movement_phases", "body_regions", "severity_scale"):
            if payload.get(dropped):
                legacy.setdefault(dropped, payload[dropped])

        return cls(
            schema_version=str(payload.get("schema_version") or LABEL_SCHEMA_VERSION),
            exercises=options("exercises"),
            error_types=options("error_types"),
            notes=str(payload.get("notes", "")),
            legacy=legacy,
        )


__all__ = ["LabelOption", "LabelSchema"]
