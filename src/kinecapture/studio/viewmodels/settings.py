"""The Settings screen: edit, validate, save - or say exactly what is wrong.

Edits are held here until saved, so leaving the screen with unsaved changes is
noticeable rather than silent, and a bad value never reaches the config that is
actually in use.

No Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from kinecapture.core.errors import ValidationError
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.settings import (
    GROUP_SUBTITLES,
    GROUP_TITLES,
    SettingField,
    SettingsService,
)

from .observable import Event, Observable


class SettingsViewModel:
    def __init__(self, service: SettingsService) -> None:
        self._service = service
        self.values: Observable[dict[str, Any]] = Observable(
            dict(service.snapshot().values), name="settings"
        )
        self.pending: Observable[dict[str, Any]] = Observable({}, name="pending")
        self.problems: Observable[dict[str, str]] = Observable({}, name="problems")
        self.dirty: Observable[bool] = Observable(False, name="dirty")
        self.message: Event[Message] = Event()

    # ------------------------------------------------------------------ read
    def groups(self) -> tuple[tuple[str, str, str, tuple[SettingField, ...]], ...]:
        return tuple(
            (group, GROUP_TITLES[group], GROUP_SUBTITLES[group], fields)
            for group, fields in self._service.groups()
        )

    def value_of(self, key: str) -> Any:
        """The value the screen should show: the pending edit if there is one."""
        if key in self.pending.value:
            return self.pending.value[key]
        return self.values.value.get(key)

    def problem_for(self, key: str) -> str:
        return self.problems.value.get(key, "")

    # ----------------------------------------------------------------- edit
    def edit(self, key: str, value: Any) -> None:
        """Record an edit. Validated immediately so the field can say so.

        Immediate feedback, deferred writing: the user learns about a bad value
        while looking at it, and the application keeps running on the old one.
        """
        pending = dict(self.pending.value)
        if value == self.values.value.get(key):
            pending.pop(key, None)
        else:
            pending[key] = value
        self.pending.force(pending)
        self.dirty.set(bool(pending))
        problems = dict(self.problems.value)
        single = self._service.validate({key: value}) if key in pending else {}
        if single:
            problems[key] = single[key]
        else:
            problems.pop(key, None)
        self.problems.force(problems)

    def discard(self) -> None:
        self.pending.force({})
        self.problems.force({})
        self.dirty.set(False)

    # ----------------------------------------------------------------- save
    def save(self) -> bool:
        changes = dict(self.pending.value)
        if not changes:
            return True
        problems = self._service.validate(changes)
        if problems:
            self.problems.force(problems)
            self.message.emit(
                Message(
                    headline="Ayarlar kaydedilmedi.",
                    severity=Severity.WARNING,
                    detail=(
                        f"{len(problems)} alan geçersiz. Eski değerler yürürlükte "
                        "kalmaya devam ediyor."
                    ),
                    code="settings_invalid",
                    technical={key: text for key, text in problems.items()},
                )
            )
            return False
        try:
            snapshot = self._service.apply(changes)
        except ValidationError as exc:
            self.problems.force(dict(exc.details.get("fields", {})))
            self.message.emit(from_error(exc, headline="Ayarlar kaydedilmedi."))
            return False
        self.values.force(dict(snapshot.values))
        self.discard()
        self.message.emit(
            Message(
                headline=f"{len(changes)} ayar kaydedildi.",
                severity=Severity.INFO,
            )
        )
        return True

    @property
    def service(self) -> SettingsService:
        return self._service


__all__ = ["SettingsViewModel"]
