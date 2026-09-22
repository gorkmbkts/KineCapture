"""A notification card never cuts a word in half.

From the 20 September evidence: a card offering "Etiketlemeyi aç" and "Sürüm
listesi" beside "Ayrıntılar" and "Kapat" drew them as "iketlemeyi a" and
"Sürüm listes". A ``QPushButton`` given less width than its label needs does
not wrap and does not elide - it centres the text and clips both ends, so the
first thing lost is the first letter.

A second card, on the same day, was cut off across the bottom: its height had
been measured before "Ayrıntılar" unfolded the technical line inside it, and
that line - a list of issue codes with no spaces - could not wrap either, so
it ran off the right edge as well.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.messages import (  # noqa: E402
    Action,
    Message,
    Severity,
)

from conftest import enter_the_workspace  # noqa: E402

#: The card from `input-06.png`, as close as the evidence allows.
THE_REAL_ONE = Message(
    headline="P0001 kaydı işlendi · notlarla.",
    severity=Severity.WARNING,
    detail=(
        "1475 kareden 1473 tanesi eşleşti · Kayıt sırasındaki bazı kareler ham "
        "kaynakta eşleştirilemedi. · Kamera iki kareye aynı mikrosaniyeyi verdi; "
        "kareler sırayla eşleştirildi. · +3 not daha"
    ),
    code="processing_done",
    technical={
        "issues": [
            "capture_frames_unmatched",
            "capture_timestamp_duplicated",
            "source_frame_count_mismatch",
            "source_timestamp_gap",
            "subject_anchor_before_recording",
        ]
    },
    actions=(
        Action("review:C:/kc15/run", "Etiketlemeyi aç", primary=True),
        Action("goto:library", "Sürüm listesi"),
    ),
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    config = AppConfig.sandboxed(tmp_path / "toasts")
    config.dataset_root.mkdir(parents=True, exist_ok=True)
    built = build_window(config, state_path=tmp_path / "window.json")
    built.show()
    assert built.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    enter_the_workspace(built, app)
    yield built
    built.close()


def _buttons(card) -> list[QPushButton]:
    return [b for b in card.findChildren(QPushButton) if not b.isHidden()]


def _clipped(button: QPushButton) -> bool:
    """Whether this button is narrower than the text it is drawing."""
    needed = button.fontMetrics().horizontalAdvance(button.text())
    return button.width() < needed + 8


def test_no_action_label_is_ever_clipped(window, app) -> None:
    window.toasts.show_message(THE_REAL_ONE)
    app.processEvents()
    card = window.toasts.toasts[-1]

    clipped = [b.text() for b in _buttons(card) if _clipped(b)]
    assert clipped == [], clipped


@pytest.mark.parametrize(
    "labels",
    [
        (),
        ("Etiketlemeyi aç",),
        ("Etiketlemeyi aç", "Sürüm listesi"),
        ("Etiketlemeyi aç", "Sürüm listesi", "Yeni sürüm hesapla"),
        (
            "Etiketlemeyi aç",
            "Sürüm listesi",
            "Yeni sürüm hesapla",
            "Klasörü aç",
            "Ayarları göster",
        ),
    ],
)
def test_any_number_of_actions_fits_without_clipping(window, app, labels) -> None:
    """Zero, one, or five. The row wraps rather than squeezing."""
    window.toasts.clear()
    app.processEvents()
    window.toasts.show_message(
        Message(
            headline="Bir şey oldu.",
            severity=Severity.INFO,
            detail="Kısa bir açıklama.",
            code=f"many-{len(labels)}",
            actions=tuple(
                Action(f"goto:library#{i}", text, primary=(i == 0))
                for i, text in enumerate(labels)
            ),
        )
    )
    app.processEvents()
    card = window.toasts.toasts[-1]

    buttons = _buttons(card)
    # The actions, plus "Ayrıntılar" (the message carries a code) and "Kapat".
    assert len(buttons) == len(labels) + 2
    assert [b.text() for b in buttons if _clipped(b)] == []


def test_the_buttons_never_overlap_each_other(window, app) -> None:
    window.toasts.show_message(THE_REAL_ONE)
    app.processEvents()
    card = window.toasts.toasts[-1]

    boxes = [(b.geometry(), b.text()) for b in _buttons(card)]
    for index, (first, name) in enumerate(boxes):
        for second, other in boxes[index + 1 :]:
            assert not first.intersects(second), f"{name} overlaps {other}"


def test_nothing_is_drawn_outside_the_card(window, app) -> None:
    """Including after "Ayrıntılar", which used to cut the sentence above it."""
    window.toasts.show_message(THE_REAL_ONE)
    app.processEvents()
    card = window.toasts.toasts[-1]

    def inside() -> list[str]:
        out = []
        for child in card.findChildren(QPushButton):
            if child.isHidden():
                continue
            if not card.rect().contains(child.geometry()):
                out.append(child.text())
        return out

    assert inside() == []
    QTest.mouseClick(card._details_button, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert inside() == []
    card._details_window.close()


def test_the_detail_window_carries_the_whole_technical_text(window, app) -> None:
    """It is a list of codes with no spaces in it; a label cannot wrap that."""
    window.toasts.show_message(THE_REAL_ONE)
    app.processEvents()
    card = window.toasts.toasts[-1]

    QTest.mouseClick(card._details_button, Qt.MouseButton.LeftButton)
    app.processEvents()
    try:
        assert card.details_visible
        text = card.details_text
        for code in THE_REAL_ONE.technical["issues"]:
            assert code in text, code
        assert THE_REAL_ONE.detail in text
    finally:
        card._details_window.close()


def test_a_card_with_no_details_offers_no_details_button(window, app) -> None:
    window.toasts.clear()
    app.processEvents()
    # No code and no technical block, so there is nothing to detail.
    window.toasts.show_message(
        Message(headline="Kaydedildi.", severity=Severity.INFO)
    )
    app.processEvents()
    card = window.toasts.toasts[-1]

    assert card._details_button.isHidden()
    assert not card._close_button.isHidden()


def test_a_stack_of_cards_still_clears_the_navigation(window, app) -> None:
    """The layer's own rule, still true now the cards can be taller."""
    for index in range(4):
        window.toasts.show_message(
            Message(
                headline=f"{index}. bildirim",
                severity=Severity.WARNING,
                detail="Bir açıklama cümlesi.",
                code=f"stack-{index}",
                actions=(Action("goto:library", "Sürüm listesi"),),
            )
        )
    app.processEvents()

    layer = window.toasts
    nav = window.nav_bar
    nav_top = nav.mapTo(window, nav.rect().topLeft()).y()
    layer_bottom = layer.mapTo(window, layer.rect().bottomLeft()).y()
    assert layer_bottom <= nav_top, (layer_bottom, nav_top)


def test_the_primary_action_is_the_widest_thing_it_needs_to_be(window, app) -> None:
    """A primary action people are meant to press is not the one that shrinks."""
    window.toasts.show_message(THE_REAL_ONE)
    app.processEvents()
    card = window.toasts.toasts[-1]

    primary = next(b for b in _buttons(card) if b.text() == "Etiketlemeyi aç")
    assert primary.width() >= primary.fontMetrics().horizontalAdvance(primary.text()) + 8


def test_the_processing_card_opens_the_version_it_names(
    window, app, tmp_path, monkeypatch
) -> None:
    """"Etiketlemeyi aç" has to carry the run, not just the screen.

    The card raised when a version finishes offers to open it. Naming the
    screen and leaving the person to find the take again is what this action
    exists to avoid, so the directory has to arrive with the navigation.
    """
    # Navigation is held still: the labelling screen *consumes* the handoff as
    # it activates, which is correct and also means the value is gone by the
    # time a test could look at it.
    asked: list[str] = []
    monkeypatch.setattr(
        window.viewmodel, "navigate", lambda key: (asked.append(key), True)[1]
    )
    wanted = str(tmp_path / "run_0001")
    window.toasts.clear()
    app.processEvents()
    window.pending_review = None
    window.toasts.show_message(
        Message(
            headline="P0001 kaydı işlendi.",
            severity=Severity.INFO,
            code="processing_done",
            actions=(Action(f"review:{wanted}", "Etiketlemeyi aç", primary=True),),
        )
    )
    app.processEvents()
    card = window.toasts.toasts[-1]
    button = next(b for b in _buttons(card) if b.text() == "Etiketlemeyi aç")

    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    app.processEvents()

    assert window.pending_review == wanted
    assert asked == ["review"]
