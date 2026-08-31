"""Design tokens and the stylesheet built from them.

Every colour, radius and spacing value in the application comes from a
:class:`Theme`. Widgets never hard-code a hex value, so switching between the
dark and light themes is a token swap rather than a per-widget rewrite.

Colour rules that the rest of the GUI relies on:

* **Red is reserved.** It means recording, destructive, or critical error - and
  nothing else. Success and warning have their own hues.
* **Status is never colour alone.** Every quality indicator pairs its colour
  with an icon and a word, so it stays readable in greyscale and for users who
  do not distinguish the hues.
* **Synthetic data has its own accent** so mock recordings are visibly not real
  measurements wherever they appear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from kinecapture.domain.enums import HealthLevel


@dataclass(frozen=True)
class Theme:
    """One complete colour and metric token set."""

    name: str
    is_dark: bool

    # Surfaces, from furthest back to closest to the user.
    bg_base: str
    bg_sunken: str
    bg_surface: str
    bg_elevated: str
    bg_hover: str
    bg_active: str

    # Lines.
    border: str
    border_strong: str
    focus_ring: str

    # Text.
    text_primary: str
    text_secondary: str
    text_muted: str
    text_on_accent: str

    # Meaning.
    accent: str
    accent_hover: str
    accent_pressed: str
    success: str
    warning: str
    danger: str
    info: str
    synthetic: str

    # Data visualisation.
    skeleton_center: str
    skeleton_left: str
    skeleton_right: str
    skeleton_dim: str
    grid: str

    # Metrics, in device-independent pixels.
    radius_sm: int = 4
    radius_md: int = 8
    radius_lg: int = 12
    space_xs: int = 4
    space_sm: int = 8
    space_md: int = 14
    space_lg: int = 20
    space_xl: int = 28
    font_size: int = 13
    font_size_sm: int = 11
    font_size_lg: int = 16
    font_size_xl: int = 22

    extra: Mapping[str, str] = field(default_factory=dict)

    def health_color(self, level: HealthLevel) -> str:
        return {
            HealthLevel.READY: self.success,
            HealthLevel.WARNING: self.warning,
            HealthLevel.BLOCKED: self.danger,
            HealthLevel.UNKNOWN: self.text_muted,
        }[level]


DARK_THEME = Theme(
    name="dark",
    is_dark=True,
    bg_base="#0e1116",
    bg_sunken="#0a0d11",
    bg_surface="#161b22",
    bg_elevated="#1c232c",
    bg_hover="#222b36",
    bg_active="#2a3542",
    border="#262d38",
    border_strong="#3a4552",
    focus_ring="#4c8dff",
    text_primary="#e8edf4",
    text_secondary="#9aa7b8",
    text_muted="#6b7787",
    text_on_accent="#ffffff",
    accent="#4c8dff",
    accent_hover="#639bff",
    accent_pressed="#3a7ae8",
    success="#3fb950",
    warning="#e3a008",
    danger="#f04d4d",
    info="#58a6ff",
    synthetic="#a371f7",
    skeleton_center="#7ee0d0",
    skeleton_left="#63a4ff",
    skeleton_right="#ffb454",
    skeleton_dim="#3a4552",
    grid="#1f2732",
)

LIGHT_THEME = Theme(
    name="light",
    is_dark=False,
    bg_base="#f4f6fa",
    bg_sunken="#e8ecf3",
    bg_surface="#ffffff",
    bg_elevated="#ffffff",
    bg_hover="#eef2f8",
    bg_active="#e2e9f4",
    border="#dbe1ea",
    border_strong="#b9c3d1",
    focus_ring="#1f6feb",
    text_primary="#1a1f27",
    text_secondary="#525d6b",
    text_muted="#7b8593",
    text_on_accent="#ffffff",
    accent="#1f6feb",
    accent_hover="#3a82f0",
    accent_pressed="#1858c4",
    success="#1a7f37",
    warning="#9a6700",
    danger="#cf222e",
    info="#0969da",
    synthetic="#8250df",
    skeleton_center="#0f8f7d",
    skeleton_left="#1f6feb",
    skeleton_right="#bc5b00",
    skeleton_dim="#c4ccd8",
    grid="#dde3ec",
)

_THEMES = {theme.name: theme for theme in (DARK_THEME, LIGHT_THEME)}


def get_theme(name: str) -> Theme:
    return _THEMES.get(name, DARK_THEME)


def available_themes() -> tuple[str, ...]:
    return tuple(_THEMES)


def build_stylesheet(theme: Theme) -> str:
    """The application-wide QSS, generated from ``theme``.

    Interaction states (hover, pressed, focus, disabled, checked) are defined
    once here for every control type rather than per widget.
    """
    t = theme
    return f"""
/* ---------------------------------------------------------------- base */
QWidget {{
    background-color: {t.bg_base};
    color: {t.text_primary};
    font-size: {t.font_size}px;
}}
QMainWindow, QDialog {{ background-color: {t.bg_base}; }}
QToolTip {{
    background-color: {t.bg_elevated};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: {t.radius_sm}px;
    padding: {t.space_xs}px {t.space_sm}px;
}}

/* -------------------------------------------------------------- labels */
QLabel {{ background: transparent; }}
QLabel[role="title"] {{
    font-size: {t.font_size_xl}px;
    font-weight: 600;
    color: {t.text_primary};
}}
QLabel[role="subtitle"] {{
    font-size: {t.font_size}px;
    color: {t.text_secondary};
}}
QLabel[role="section"] {{
    font-size: {t.font_size_lg}px;
    font-weight: 600;
    color: {t.text_primary};
}}
QLabel[role="caption"] {{
    font-size: {t.font_size_sm}px;
    color: {t.text_muted};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel[role="metric"] {{
    font-size: {t.font_size_xl}px;
    font-weight: 600;
    color: {t.text_primary};
}}
QLabel[role="muted"] {{ color: {t.text_muted}; }}
QLabel[role="error"] {{ color: {t.danger}; font-size: {t.font_size_sm}px; }}
QLabel[role="synthetic"] {{ color: {t.synthetic}; font-weight: 600; }}

/* --------------------------------------------------------------- cards */
QFrame[role="card"] {{
    background-color: {t.bg_surface};
    border: 1px solid {t.border};
    border-radius: {t.radius_lg}px;
}}
QFrame[role="inset"] {{
    background-color: {t.bg_sunken};
    border: 1px solid {t.border};
    border-radius: {t.radius_md}px;
}}
QFrame[role="separator"] {{
    background-color: {t.border};
    max-height: 1px;
    border: none;
}}

/* ------------------------------------------------------------- buttons */
QPushButton {{
    background-color: {t.bg_elevated};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: {t.radius_md}px;
    padding: {t.space_sm}px {t.space_md}px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{ background-color: {t.bg_hover}; border-color: {t.accent}; }}
QPushButton:pressed {{ background-color: {t.bg_active}; }}
QPushButton:focus {{ border: 1px solid {t.focus_ring}; outline: none; }}
QPushButton:disabled {{
    background-color: {t.bg_surface};
    color: {t.text_muted};
    border-color: {t.border};
}}
QPushButton[variant="primary"] {{
    background-color: {t.accent};
    color: {t.text_on_accent};
    border: 1px solid {t.accent};
}}
QPushButton[variant="primary"]:hover {{
    background-color: {t.accent_hover};
    border-color: {t.accent_hover};
}}
QPushButton[variant="primary"]:pressed {{ background-color: {t.accent_pressed}; }}
QPushButton[variant="primary"]:disabled {{
    background-color: {t.bg_surface};
    color: {t.text_muted};
    border-color: {t.border};
}}
QPushButton[variant="danger"] {{
    background-color: {t.danger};
    color: #ffffff;
    border: 1px solid {t.danger};
}}
QPushButton[variant="danger"]:hover {{ background-color: {t.danger}; border-color: #ffffff; }}
QPushButton[variant="ghost"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {t.text_secondary};
}}
QPushButton[variant="ghost"]:hover {{
    background-color: {t.bg_hover};
    color: {t.text_primary};
}}
QPushButton:checked {{
    background-color: {t.bg_active};
    border-color: {t.accent};
    color: {t.text_primary};
}}

/* ------------------------------------------------------------ nav rail */
QFrame#NavRail {{
    background-color: {t.bg_sunken};
    border: none;
    border-right: 1px solid {t.border};
}}
QPushButton[role="nav"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {t.radius_md}px;
    padding: {t.space_sm}px {t.space_md}px;
    text-align: left;
    color: {t.text_secondary};
    font-weight: 500;
}}
QPushButton[role="nav"]:hover {{
    background-color: {t.bg_hover};
    color: {t.text_primary};
}}
QPushButton[role="nav"]:checked {{
    background-color: {t.bg_active};
    color: {t.text_primary};
    border-color: {t.border_strong};
}}

/* The collapse control is not a list item. The page buttons above it are a
   left-aligned column, but this one sits alone under the institutional logo,
   where left-aligned content reads as a misalignment rather than as a list. */
QPushButton[role="navToggle"] {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {t.radius_md}px;
    padding: {t.space_sm}px {t.space_sm}px;
    text-align: center;
    color: {t.text_secondary};
}}
QPushButton[role="navToggle"]:hover {{
    background-color: {t.bg_hover};
    color: {t.text_primary};
}}

/* --------------------------------------------------------------- input */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {t.bg_sunken};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: {t.radius_md}px;
    padding: {t.space_sm}px {t.space_sm}px;
    selection-background-color: {t.accent};
    selection-color: {t.text_on_accent};
}}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: {t.accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {t.focus_ring};
}}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {t.bg_surface};
    color: {t.text_muted};
    border-color: {t.border};
}}
QLineEdit[state="invalid"], QComboBox[state="invalid"],
QSpinBox[state="invalid"], QPlainTextEdit[state="invalid"] {{
    border-color: {t.danger};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {t.bg_elevated};
    border: 1px solid {t.border_strong};
    border-radius: {t.radius_md}px;
    selection-background-color: {t.accent};
    selection-color: {t.text_on_accent};
    padding: {t.space_xs}px;
}}
QCheckBox, QRadioButton {{ spacing: {t.space_sm}px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {t.border_strong};
    background-color: {t.bg_sunken};
}}
QCheckBox::indicator {{ border-radius: {t.radius_sm}px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: {t.text_muted}; }}

/* --------------------------------------------------------------- lists */
QListWidget, QTreeWidget, QTableWidget, QTableView, QListView {{
    background-color: {t.bg_surface};
    border: 1px solid {t.border};
    border-radius: {t.radius_md}px;
    outline: none;
    alternate-background-color: {t.bg_base};
}}
QListWidget::item, QTreeWidget::item {{
    padding: {t.space_sm}px;
    border-radius: {t.radius_sm}px;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{ background-color: {t.bg_hover}; }}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {{
    background-color: {t.bg_active};
    color: {t.text_primary};
}}
QHeaderView::section {{
    background-color: {t.bg_elevated};
    color: {t.text_secondary};
    border: none;
    border-bottom: 1px solid {t.border};
    padding: {t.space_sm}px;
    font-weight: 600;
}}
QTableWidget {{ gridline-color: {t.border}; }}
QTableCornerButton::section {{ background-color: {t.bg_elevated}; border: none; }}

/* ------------------------------------------------------------ scrollbar */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle {{
    background: {t.border_strong};
    border-radius: 5px;
    min-height: 28px; min-width: 28px;
}}
QScrollBar::handle:hover {{ background: {t.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}

/* --------------------------------------------------------------- tabs */
QTabWidget::pane {{
    border: 1px solid {t.border};
    border-radius: {t.radius_md}px;
    background-color: {t.bg_surface};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {t.text_secondary};
    padding: {t.space_sm}px {t.space_md}px;
    border: 1px solid transparent;
    border-top-left-radius: {t.radius_md}px;
    border-top-right-radius: {t.radius_md}px;
    margin-right: 2px;
}}
QTabBar::tab:hover {{ color: {t.text_primary}; background: {t.bg_hover}; }}
QTabBar::tab:selected {{
    background: {t.bg_surface};
    color: {t.text_primary};
    border-color: {t.border};
    border-bottom-color: {t.bg_surface};
}}

/* ------------------------------------------------------------- sliders */
QSlider::groove:horizontal {{
    height: 4px; background: {t.border}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {t.text_primary};
    width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {t.accent}; }}
QSlider::groove:horizontal:disabled {{ background: {t.border}; }}
QSlider::sub-page:horizontal:disabled {{ background: {t.text_muted}; }}

/* ------------------------------------------------------------ progress */
QProgressBar {{
    background-color: {t.bg_sunken};
    border: 1px solid {t.border};
    border-radius: {t.radius_sm}px;
    height: 8px;
    text-align: center;
    color: {t.text_secondary};
}}
QProgressBar::chunk {{ background-color: {t.accent}; border-radius: {t.radius_sm}px; }}

/* --------------------------------------------------------- status bar */
QStatusBar {{
    background-color: {t.bg_sunken};
    border-top: 1px solid {t.border};
    color: {t.text_secondary};
}}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background-color: {t.border}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}
QMenu {{
    background-color: {t.bg_elevated};
    border: 1px solid {t.border_strong};
    border-radius: {t.radius_md}px;
    padding: {t.space_xs}px;
}}
QMenu::item {{ padding: {t.space_sm}px {t.space_lg}px; border-radius: {t.radius_sm}px; }}
QMenu::item:selected {{ background-color: {t.accent}; color: {t.text_on_accent}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: {t.space_xs}px 0; }}
"""


__all__ = [
    "DARK_THEME",
    "LIGHT_THEME",
    "Theme",
    "available_themes",
    "build_stylesheet",
    "get_theme",
]
