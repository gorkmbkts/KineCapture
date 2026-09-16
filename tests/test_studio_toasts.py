"""A message must not move the work.

The visual acceptance the 15 September brief asks for, measured rather than
looked at: the main video and timeline rectangles have the same position and
the same size whether a notification is showing or not.

Also here: the grouping, lifetime and hover rules, because "the same event
twice must not stack up two cards" is the kind of thing that is easy to assert
and easy to regress.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.messages import Message, Severity  # noqa: E402
from kinecapture.studio.views.toasts import (  # noqa: E402
    INFO_LIFETIME_MS,
    MAX_TOASTS,
    WARNING_LIFETIME_MS,
    Toast,
    ToastLayer,
)
from kinecapture.studio.theme import load_tokens  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    widget = build_window(config, state_path=tmp_path / "window.json")
    # The size the audit used, because that is the layout being defended.
    widget.resize(1920, 1032)
    widget.show()
    # Behind the gate nothing of the workspace is laid out, so a geometry
    # comparison there would compare two sets of zeroes.
    assert widget.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    yield widget
    widget.close()


def _geometry(window, key: str) -> list[tuple]:
    """Where the page's main rectangles are, in window coordinates."""
    page = window.page(key)
    window.viewmodel.navigate(key)
    QApplication.processEvents()
    out = []
    for name in ("viewer", "skeleton", "timeline", "preview"):
        widget = getattr(page, name, None)
        if widget is None:
            continue
        top_left = widget.mapTo(window, widget.rect().topLeft())
        out.append((name, top_left.x(), top_left.y(), widget.width(), widget.height()))
    return out


# --------------------------------------------------- the geometry guarantee
@pytest.mark.parametrize("key", ["review", "capture"])
def test_a_notification_does_not_move_or_resize_the_work(window, app, key) -> None:
    before = _geometry(window, key)
    assert before, f"{key} has no main rectangles to measure"
    assert all(
        width > 0 and height > 0 for _name, _x, _y, width, height in before
    ), f"{key} was not laid out, so this comparison would prove nothing: {before}"

    window.viewmodel.report(
        Message(
            headline="Ham kayıt kaydedildi · İskelet bekliyor",
            severity=Severity.INFO,
            detail="1231 kare, 41.0 sn.",
            code="awaiting_processing",
        )
    )
    app.processEvents()
    assert window.toasts.toasts, "the message has to be on screen for this to mean anything"

    after = _geometry(window, key)
    assert after == before


def test_the_layer_is_above_the_page_and_out_of_its_layout(window, app) -> None:
    window.viewmodel.navigate("review")
    app.processEvents()
    layer = window.toasts
    assert isinstance(layer, ToastLayer)
    # No layout owns it: that is what keeps it from taking space.
    assert layer.parent() is window.stack
    assert window.stack.layout() is None or layer not in [
        window.stack.layout().itemAt(i).widget()
        for i in range(window.stack.layout().count())
    ]
    window.viewmodel.notify("Bir şey oldu")
    app.processEvents()
    # Sized to the cards, not to the page: that is what lets a click on empty
    # space reach the page underneath while the card's own buttons still work.
    assert layer.width() == window._tokens.metric("KcToastWidth")
    assert layer.height() < window.stack.height()
    assert window.stack.rect().contains(layer.geometry())


# ------------------------------------------------------------- the grouping
def test_the_same_event_twice_updates_one_card(window, app) -> None:
    for _ in range(3):
        window.viewmodel.report(
            Message(
                headline="Kare kaydedilemedi.",
                severity=Severity.ERROR,
                code="recording_loss",
            )
        )
        app.processEvents()
    assert len(window.toasts.toasts) == 1
    assert window.toasts.toasts[0].count == 3


def test_different_events_stack_but_not_without_limit(window, app) -> None:
    for index in range(MAX_TOASTS + 3):
        window.viewmodel.report(
            Message(headline=f"Olay {index}", severity=Severity.WARNING, code=f"e{index}")
        )
        app.processEvents()
    assert len(window.toasts.toasts) == MAX_TOASTS


# ------------------------------------------------------------- the lifetime
def test_information_fades_and_a_decision_does_not(app) -> None:
    host = QApplication.activeWindow()
    layer = ToastLayer(load_tokens("dark"), host or QApplication.allWidgets()[0])
    info = layer.show_message(Message(headline="Bitti", severity=Severity.INFO))
    warn = layer.show_message(Message(headline="Dikkat", severity=Severity.WARNING))
    error = layer.show_message(Message(headline="Olmadı", severity=Severity.ERROR))

    assert info.is_persistent is False
    assert warn.is_persistent is False
    # An error is a decision waiting to be made; it does not time out.
    assert error.is_persistent is True
    assert INFO_LIFETIME_MS < WARNING_LIFETIME_MS
    layer.clear()


def test_hovering_keeps_a_message_alive(app) -> None:
    layer = ToastLayer(load_tokens("dark"), QApplication.allWidgets()[0])
    toast: Toast = layer.show_message(Message(headline="Okunuyor", severity=Severity.INFO))
    assert toast._timer.isActive()
    toast.enterEvent(None)
    assert not toast._timer.isActive(), "a message under the pointer must not vanish"
    toast.leaveEvent(None)
    assert toast._timer.isActive()
    layer.clear()


# --------------------------------------------------------------- clickable
def test_the_buttons_on_a_message_actually_work(window, app) -> None:
    """They were painted but dead.

    ``WA_TransparentForMouseEvents`` on the layer removed its whole subtree
    from hit-testing, so "Ayrıntılar" and "Kapat" could not be pressed. This
    asks the window the same question the mouse asks: what is under here?
    """
    window.viewmodel.report(
        Message(
            headline="Proje klasörü bulunamadı.",
            severity=Severity.WARNING,
            detail="Veri diski bağlı olmayabilir.",
            code="project_folder_missing",
            technical={"yol": "D:/yok"},
        )
    )
    app.processEvents()
    card = window.toasts.toasts[-1]

    for button in (card._details_button, card._close_button):
        point = button.mapTo(window, button.rect().center())
        assert window.childAt(point) is button, (
            f"{button.text()} is not reachable by the mouse"
        )

    # And they do what they say.
    assert card.details_visible is False
    card._details_button.click()
    app.processEvents()
    assert card.details_visible is True
    assert "yol: D:/yok" in card._technical.text()

    card._close_button.click()
    app.processEvents()
    assert window.toasts.toasts == ()


def test_empty_space_still_belongs_to_the_page(window, app) -> None:
    """A message must not swallow clicks aimed at the screen behind it."""
    window.viewmodel.navigate("projects")
    app.processEvents()
    window.viewmodel.notify("Bir şey oldu")
    app.processEvents()
    layer = window.toasts
    assert layer.isVisible()
    # A point well away from the card is not the layer's.
    outside = window.stack.mapTo(window, window.stack.rect().topLeft())
    assert layer.geometry().contains(
        layer.mapFromParent(window.stack.mapFrom(window, outside))
    ) is False
