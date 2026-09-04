from __future__ import annotations

from dataclasses import dataclass
from string import Template

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QPalette
from PyQt6.QtWidgets import QApplication, QMenu


@dataclass(frozen=True)
class ThemeDefinition:
    name: str
    label: str
    is_dark: bool
    colors: dict[str, str]
    chart_colors: tuple[str, ...]


LIGHT_THEME = ThemeDefinition(
    name="light",
    label="Светлая",
    is_dark=False,
    colors={
        "window_bg": "#f5f1eb",
        "window_alt": "#ece5dd",
        "surface": "#fffdf9",
        "surface_alt": "#f7f2ec",
        "surface_hover": "#efe7df",
        "surface_overlay": "rgba(255, 252, 248, 0.94)",
        "field_bg": "#fcf8f3",
        "field_border": "#d9cec1",
        "field_hover": "#b5c6cb",
        "text": "#27323b",
        "text_strong": "#1e272f",
        "muted": "#6f7a83",
        "border": "#ddd2c7",
        "border_soft": "#ebe3db",
        "accent": "#7ea7ad",
        "accent_hover": "#90b6bc",
        "accent_pressed": "#6c969c",
        "accent_soft": "#e5f0f1",
        "accent_soft_hover": "#dcebee",
        "accent_border": "#bfd4d7",
        "accent_text": "#f8fbfc",
        "danger": "#c78784",
        "danger_hover": "#d69996",
        "danger_pressed": "#b87774",
        "danger_soft": "#f5e3e1",
        "danger_border": "#e0b7b4",
        "success": "#7ca58a",
        "warning": "#c7a56e",
        "scroll": "#c5cec9",
        "scroll_hover": "#a8b3ad",
        "tooltip_bg": "#26313a",
        "tooltip_text": "#f8fbfc",
        "placeholder": "#8a949d",
        "hero_start": "#faf7f4",
        "hero_end": "#edf3f4",
    },
    chart_colors=("#7ea7ad", "#c9aba0", "#97b88f", "#d2bd8c", "#9db8c8", "#d79a95"),
)


DARK_THEME = ThemeDefinition(
    name="dark",
    label="Тёмная",
    is_dark=True,
    colors={
        "window_bg": "#1b2128",
        "window_alt": "#232b34",
        "surface": "#252d37",
        "surface_alt": "#2c3540",
        "surface_hover": "#333d48",
        "surface_overlay": "rgba(40, 48, 58, 0.92)",
        "field_bg": "#2a323d",
        "field_border": "#46515d",
        "field_hover": "#657685",
        "text": "#edf2f5",
        "text_strong": "#f8fbfc",
        "muted": "#a8b3bd",
        "border": "#3d4855",
        "border_soft": "#313b46",
        "accent": "#93b9c2",
        "accent_hover": "#a6c9d0",
        "accent_pressed": "#7ea7b1",
        "accent_soft": "#344651",
        "accent_soft_hover": "#3d5360",
        "accent_border": "#597586",
        "accent_text": "#142029",
        "danger": "#d19895",
        "danger_hover": "#deaba8",
        "danger_pressed": "#ba817e",
        "danger_soft": "#4a3538",
        "danger_border": "#765256",
        "success": "#94bc9f",
        "warning": "#d7bd8d",
        "scroll": "#677281",
        "scroll_hover": "#8691a0",
        "tooltip_bg": "#eef2f5",
        "tooltip_text": "#18212a",
        "placeholder": "#86919a",
        "hero_start": "#1d232b",
        "hero_end": "#222c34",
    },
    chart_colors=("#93b9c2", "#d1a8a1", "#98c49f", "#dcc18d", "#9db9cf", "#dba39d"),
)


THEMES = {
    LIGHT_THEME.name: LIGHT_THEME,
    DARK_THEME.name: DARK_THEME,
}

DEFAULT_THEME = LIGHT_THEME.name
SETTINGS_ORG = "ShukCar"
SETTINGS_APP = "ShukCar"
SETTINGS_KEY = "appearance/theme"


STYLESHEET_TEMPLATE = Template(
    """
QWidget {
    background: $window_bg;
    color: $text;
    font-family: "Segoe UI Variable", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
    selection-background-color: $accent_soft;
    selection-color: $text;
}

QWidget#LoginRoot, QWidget#AppRoot {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 $hero_start,
        stop: 1 $hero_end
    );
}

QDialog, QMainWindow {
    background: $window_bg;
}

QLabel {
    background: transparent;
}

QLabel#LoginTitle,
QLabel#HeaderTitle,
QLabel#SectionTitle,
QLabel#ResultLabel {
    color: $text_strong;
}

QLabel#LoginTitle {
    font-size: 30px;
    font-weight: 700;
    letter-spacing: 0.4px;
}

QLabel#HeaderTitle,
QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 650;
}

QLabel#HomeWelcome {
    font-size: 28px;
    font-weight: 700;
    color: $text_strong;
    padding: 0;
}

QLabel#BrandTitle {
    font-size: 24px;
    font-weight: 700;
    color: $text_strong;
    letter-spacing: 0.2px;
}

QLabel#BrandCaption,
QLabel#PageSubtitle,
QLabel#HeroCaption,
QLabel#SectionCaption {
    color: $muted;
    font-size: 13px;
}

QLabel#HeroKicker {
    color: $accent;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}

QFrame#TopBar QLabel#HeaderTitle {
    font-size: 22px;
    font-weight: 700;
}

QLabel[chip="true"] {
    background: $accent_soft;
    color: $text;
    border: 1px solid $accent_border;
    border-radius: 12px;
    padding: 4px 10px;
    font-weight: 600;
}

QLabel#AvatarBadge {
    background: $accent_soft;
    color: $text_strong;
    border: 1px solid $accent_border;
    border-radius: 18px;
    font-size: 13px;
    font-weight: 700;
    min-width: 36px;
    min-height: 36px;
    padding: 6px;
}

QLabel#HeaderUser,
QLabel#MutedLabel,
QLabel#SearchStatus,
QLabel#SelectionHint,
QLabel#InlineMutedLabel,
QLabel#StatusInfo {
    color: $muted;
}

QLabel#LoginInfo[state="success"] {
    color: $success;
    font-weight: 600;
}

QLabel#LoginInfo[state="muted"] {
    color: $muted;
}

QLabel#LoginInfo[state="error"] {
    color: $danger;
    font-weight: 600;
}

QLabel#ResultLabel {
    font-size: 20px;
    font-weight: 700;
}

QLabel[role="title"] {
    color: $muted;
    font-size: 13px;
}

QLabel[role="value"] {
    color: $text_strong;
    font-size: 28px;
    font-weight: 700;
}

QLabel[role="sub"] {
    color: $muted;
    font-size: 12px;
}

QFrame#LoginCard,
QFrame#CarCard,
QFrame#KpiCard,
QFrame#PlaceholderChart,
QFrame#TopBar,
QFrame#Sidebar,
QFrame#SidebarUserCard,
QFrame#HomeHero,
QFrame#HeroSpotlight,
QFrame[metric="true"],
QFrame[card="true"],
QWidget[card="true"],
QGroupBox,
QTabWidget::pane,
QChartView {
    background: $surface;
    border: 1px solid $border;
    border-radius: 18px;
}

QFrame#LoginCard {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 $surface,
        stop: 1 $surface_alt
    );
}

QFrame#ShellSurface {
    background: transparent;
    border: none;
}

QFrame#Sidebar {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 $surface,
        stop: 1 $surface_alt
    );
    border-radius: 26px;
}

QFrame#TopBar {
    background: $surface_overlay;
    border-radius: 24px;
}

QFrame#SidebarUserCard,
QFrame#HeroSpotlight {
    background: $surface_overlay;
}

QFrame#BrandCard {
    background: transparent;
    border: 1px solid $border_soft;
}

QFrame#HomeHero {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 $surface,
        stop: 0.6 $surface,
        stop: 1 $accent_soft
    );
}

QFrame[metric="true"][tone="accent"] {
    background: $accent_soft;
    border-color: $accent_border;
}

QFrame[metric="true"][tone="danger"] {
    background: $danger_soft;
    border-color: $danger_border;
}

QFrame[metric="true"][tone="warning"] {
    background: $surface_alt;
    border-color: $accent_border;
}

QFrame[metric="true"][tone="success"] {
    border-color: $accent_border;
}

QWidget#Header {
    background: $surface_overlay;
    border-bottom: 1px solid $border_soft;
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QDateEdit,
QSpinBox,
QDoubleSpinBox,
QListWidget,
QTableView,
QTreeView,
QListView {
    background: $surface;
    border: 1px solid $border;
    border-radius: 14px;
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QDateEdit,
QSpinBox,
QDoubleSpinBox {
    background: $field_bg;
    border: 1px solid $field_border;
    padding: 10px 12px;
    border-radius: 12px;
    font-size: 14px;
}

QLineEdit:hover,
QTextEdit:hover,
QPlainTextEdit:hover,
QComboBox:hover,
QDateEdit:hover,
QSpinBox:hover,
QDoubleSpinBox:hover {
    border-color: $field_hover;
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QDateEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    background: $surface;
    border: 1px solid $accent;
}

QLineEdit[readOnly="true"],
QTextEdit[readOnly="true"],
QPlainTextEdit[readOnly="true"] {
    color: $muted;
}

QComboBox::drop-down,
QDateEdit::drop-down {
    width: 28px;
    border: none;
    background: transparent;
}

QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 6px;
    selection-background-color: $accent_soft;
    selection-color: $text;
}

QPushButton {
    background: $accent;
    color: $accent_text;
    border: 1px solid $accent;
    border-radius: 12px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 600;
}

QPushButton:hover {
    background: $accent_hover;
    border-color: $accent_hover;
}

QPushButton:pressed {
    background: $accent_pressed;
    border-color: $accent_pressed;
}

QPushButton:disabled {
    background: $surface_alt;
    color: $placeholder;
    border-color: $border;
}

QPushButton[accent="secondary"] {
    background: $surface_alt;
    color: $text;
    border: 1px solid $border;
}

QPushButton[accent="secondary"]:hover {
    background: $surface_hover;
    border-color: $field_hover;
}

QPushButton[accent="danger"] {
    background: $danger;
    color: $accent_text;
    border: 1px solid $danger;
}

QPushButton[accent="danger"]:hover {
    background: $danger_hover;
    border-color: $danger_hover;
}

QPushButton[accent="danger"]:pressed {
    background: $danger_pressed;
    border-color: $danger_pressed;
}

QPushButton[accent="danger-secondary"] {
    background: $danger_soft;
    color: $danger;
    border: 1px solid $danger_border;
}

QPushButton[accent="danger-secondary"]:hover {
    background: $danger_hover;
    color: $accent_text;
    border-color: $danger_hover;
}

QPushButton#KebabButton {
    background: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 0;
    font-size: 18px;
}

QPushButton#KebabButton:hover {
    background: $surface_hover;
    border-color: $field_hover;
}

QPushButton#KebabButton:pressed {
    background: $surface_alt;
}

QPushButton#SidebarToggle,
QPushButton#BackButton,
QPushButton#SearchButton,
QPushButton#MenuButton,
QPushButton#ProfileButton {
    border-radius: 14px;
    padding: 10px 14px;
}

QPushButton#SidebarToggle,
QPushButton#BackButton,
QPushButton#SearchButton,
QPushButton#MenuButton,
QPushButton#ProfileButton {
    background: $surface;
    color: $text;
    border: 1px solid $border;
}

QPushButton#SidebarToggle:hover,
QPushButton#BackButton:hover,
QPushButton#SearchButton:hover,
QPushButton#MenuButton:hover,
QPushButton#ProfileButton:hover {
    background: $surface_hover;
    border-color: $field_hover;
}

QPushButton#ProfileButton {
    background: $surface_alt;
    text-align: left;
}

QPushButton#SidebarToggle {
    font-size: 20px;
    font-weight: 700;
    padding: 8px 0;
}

QPushButton#MenuButton::menu-indicator,
QPushButton#ProfileButton::menu-indicator {
    image: none;
    width: 0px;
}

QPushButton[nav="true"] {
    background: transparent;
    color: $text;
    border: 1px solid transparent;
    border-radius: 16px;
    padding: 14px 16px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
}

QPushButton[nav="true"]:hover {
    background: $surface_alt;
    border-color: $border;
}

QPushButton[nav="true"]:checked {
    background: $accent_soft;
    color: $text_strong;
    border-color: $accent_border;
}

QPushButton[nav="true"][compact="true"] {
    padding: 0;
    text-align: center;
    font-size: 13px;
    font-weight: 700;
}

QFrame#Sidebar[collapsed="true"] QFrame[card="true"],
QFrame#Sidebar[collapsed="true"] QFrame#SidebarUserCard {
    border-radius: 20px;
}

QFrame#Sidebar[collapsed="true"] QPushButton[nav="true"] {
    background: $surface;
    border: 1px solid $border;
    color: $text;
}

QFrame#Sidebar[collapsed="true"] QPushButton[nav="true"]:hover {
    background: $surface_hover;
    border-color: $field_hover;
}

QFrame#Sidebar[collapsed="true"] QPushButton[nav="true"]:checked {
    background: $accent_soft;
    border-color: $accent_border;
    color: $text_strong;
}

QFrame#BrandCard[compact="true"],
QFrame#SidebarUserCard[compact="true"] {
    background: transparent;
    border-color: transparent;
}

QPushButton[quickTile="true"] {
    background: $surface;
    color: $text_strong;
    border: 1px solid $border;
    border-radius: 18px;
    padding: 16px 18px;
    text-align: left;
    font-size: 14px;
    font-weight: 650;
}

QPushButton[quickTile="true"]:hover {
    background: $surface_hover;
    border-color: $accent_border;
}

QPushButton[quickTile="true"]:pressed {
    background: $surface_alt;
}

QPushButton[mobileNav="true"] {
    background: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 18px;
    padding: 14px 18px;
    font-size: 14px;
    font-weight: 650;
}

QPushButton[mobileNav="true"]:hover {
    background: $surface_hover;
    border-color: $field_hover;
}

QPushButton[mobileNav="true"]:checked {
    background: $accent_soft;
    color: $text_strong;
    border-color: $accent_border;
}

QFrame#MobileTopBar,
QFrame#MobileNavBar {
    background: $surface_overlay;
}

QListWidget[mobileList="true"]::item {
    padding: 10px 12px;
    border-radius: 12px;
    margin: 2px 0;
}

QListWidget[mobileList="true"]::item:selected {
    background: $accent_soft;
    color: $text_strong;
    border: 1px solid $accent_border;
}

QToolBar {
    background: transparent;
    border: none;
    spacing: 8px;
    padding: 8px 10px 4px 10px;
}

QToolBar::separator {
    width: 1px;
    margin: 8px 6px;
    background: $border;
}

QToolButton {
    background: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 7px 12px;
    margin: 2px;
}

QToolButton:hover {
    background: $surface_hover;
    border-color: $field_hover;
}

QToolButton:pressed {
    background: $surface_alt;
}

QMenu {
    background: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 14px;
    padding: 8px;
}

QMenu::item {
    padding: 8px 12px;
    margin: 2px 0;
    border-radius: 8px;
}

QMenu::item:selected {
    background: $accent_soft;
    color: $text;
}

QMenu::separator {
    height: 1px;
    margin: 6px 8px;
    background: $border_soft;
}

QTableView,
QTreeView,
QListView,
QListWidget {
    background: $surface;
    alternate-background-color: $surface_alt;
    gridline-color: $border_soft;
    outline: none;
    padding: 6px;
}

QTableView::item:selected,
QTreeView::item:selected,
QListView::item:selected,
QListWidget::item:selected {
    background: $accent_soft;
    color: $text;
    border-radius: 10px;
}

QHeaderView::section {
    background: $surface_alt;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 10px 8px;
    font-weight: 600;
}

QTableCornerButton::section {
    background: $surface_alt;
    border: none;
    border-bottom: 1px solid $border;
    border-right: 1px solid $border;
}

QScrollArea,
QAbstractScrollArea {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 4px 0;
}

QScrollBar::handle:vertical {
    background: $scroll;
    min-height: 28px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background: $scroll_hover;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 11px;
    margin: 0 4px;
}

QScrollBar::handle:horizontal {
    background: $scroll;
    min-width: 28px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal:hover {
    background: $scroll_hover;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

QTabWidget::pane {
    margin-top: 10px;
    padding: 10px;
}

QTabBar::tab {
    background: $surface_alt;
    color: $muted;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 8px 14px;
    margin-right: 6px;
}

QTabBar::tab:hover {
    background: $surface_hover;
}

QTabBar::tab:selected {
    background: $accent_soft;
    color: $text_strong;
    border-color: $accent_border;
}

QStatusBar {
    background: transparent;
    color: $muted;
    border-top: 1px solid $border_soft;
}

QStatusBar::item {
    border: none;
}

QDialogButtonBox QPushButton {
    min-width: 110px;
}

QCheckBox,
QRadioButton {
    spacing: 10px;
}

QCheckBox::indicator,
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    background: $field_bg;
    border: 1px solid $field_border;
}

QCheckBox::indicator {
    border-radius: 6px;
}

QCheckBox::indicator:checked {
    background: $accent;
    border-color: $accent;
}

QRadioButton::indicator {
    border-radius: 9px;
}

QRadioButton::indicator:checked {
    background: $accent;
    border-color: $accent;
}

QListWidget#SuggestPopup {
    background: $surface;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 6px;
}

QListWidget#SuggestPopup::item {
    padding: 6px 8px;
}

QListWidget[overviewList="true"] {
    background: transparent;
    border: none;
    padding: 0;
}

QListWidget[overviewList="true"]::item {
    background: $surface_alt;
    border: 1px solid $border_soft;
    border-radius: 14px;
    padding: 12px;
    margin: 0 0 6px 0;
}

QListWidget[overviewList="true"]::item:selected {
    background: $accent_soft;
    border-color: $accent_border;
}

QFrame#PlaceholderChart,
QChartView {
    background: $surface;
}

QFrame#PlaceholderChart QLabel {
    color: $muted;
}

QFrame#CarCard[selected="true"] {
    border: 1px solid $accent_border;
    background: $accent_soft;
}

QLabel#CardBadge {
    background: $accent;
    color: $accent_text;
    border-radius: 10px;
    padding: 1px 6px;
    font-weight: 700;
}

QLabel#CardCover,
QLabel#MediaPreview {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 12px;
}

QLabel#MediaPreview {
    padding: 12px;
}

QToolTip {
    background: $tooltip_bg;
    color: $tooltip_text;
    border: 1px solid $border;
    padding: 6px 8px;
    border-radius: 8px;
}

QCalendarWidget QWidget {
    background: $surface;
    alternate-background-color: $surface_alt;
}

QCalendarWidget QToolButton {
    background: $surface_alt;
    color: $text;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 6px 10px;
}

QCalendarWidget QAbstractItemView:enabled {
    background: $surface;
    color: $text;
    selection-background-color: $accent;
    selection-color: $accent_text;
}

QCalendarWidget QWidget#qt_calendar_navigationbar {
    background: $surface;
}
"""
)


def _settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def build_palette(theme: ThemeDefinition) -> QPalette:
    c = theme.colors
    palette = QPalette()

    palette.setColor(QPalette.ColorRole.Window, QColor(c["window_bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["tooltip_bg"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c["tooltip_text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(c["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(c["accent_text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(c["accent_text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["placeholder"]))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c["placeholder"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c["placeholder"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(c["placeholder"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(c["surface_alt"]))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(c["muted"]))

    return palette


def build_stylesheet(theme: ThemeDefinition) -> str:
    return STYLESHEET_TEMPLATE.substitute(theme.colors)


class ThemeController(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._current_theme = self._read_saved_theme()

    def _read_saved_theme(self) -> str:
        theme_name = str(_settings().value(SETTINGS_KEY, DEFAULT_THEME))
        return theme_name if theme_name in THEMES else DEFAULT_THEME

    def current_theme(self) -> str:
        return self._current_theme

    def current_definition(self) -> ThemeDefinition:
        return THEMES[self._current_theme]

    def definition(self, theme_name: str | None = None) -> ThemeDefinition:
        if theme_name is None:
            return self.current_definition()
        return THEMES.get(theme_name, THEMES[DEFAULT_THEME])

    def set_theme(self, theme_name: str, app: QApplication | None = None) -> None:
        theme_name = theme_name if theme_name in THEMES else DEFAULT_THEME
        self._current_theme = theme_name
        _settings().setValue(SETTINGS_KEY, theme_name)

        app = app or QApplication.instance()
        if app is not None:
            definition = THEMES[theme_name]
            app.setPalette(build_palette(definition))
            app.setStyleSheet(build_stylesheet(definition))

        self.theme_changed.emit(theme_name)

    def apply_saved_theme(self, app: QApplication | None = None) -> None:
        self.set_theme(self._current_theme, app)

    def toggle_theme(self, app: QApplication | None = None) -> None:
        next_theme = DARK_THEME.name if self._current_theme == LIGHT_THEME.name else LIGHT_THEME.name
        self.set_theme(next_theme, app)


theme_controller = ThemeController()


def theme_definition(theme_name: str | None = None) -> ThemeDefinition:
    return theme_controller.definition(theme_name)


def populate_theme_menu(menu: QMenu, parent) -> QActionGroup:
    group = QActionGroup(parent)
    group.setExclusive(True)
    actions: dict[str, QAction] = {}

    for name, theme in THEMES.items():
        action = QAction(theme.label, parent)
        action.setCheckable(True)
        action.triggered.connect(lambda _checked=False, theme_name=name: theme_controller.set_theme(theme_name))
        menu.addAction(action)
        group.addAction(action)
        actions[name] = action

    def sync_checked(theme_name: str) -> None:
        for name, action in actions.items():
            action.setChecked(name == theme_name)

    sync_checked(theme_controller.current_theme())
    theme_controller.theme_changed.connect(sync_checked)
    return group
