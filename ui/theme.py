"""Dark mode and light mode colors."""

from PySide6.QtCore import QObject, Signal

THEMES = {
    "dark": {
        "bg": "#000000", "fg": "#ffffff", "border": "#ffffff",
        "muted": "#999999", "muted2": "#777777", "faint": "#555555",
        "line": "#333333", "line2": "#222222",
        "surface": "#111111", "bubble_in": "#262626", "info": "#dddddd",
        "red": "#ff3333", "red_hover": "#ff5c5c", "red_press": "#d92626", "on_red": "#ffffff",
        "green": "#6fd65a", "orange": "#ff7a1f", "queued": "#bbbbbb",
        "alt_bg": "#ffffff", "alt_fg": "#000000",          # white buttons / your chat bubbles
        "alt_hover": "#dddddd", "alt_press": "#bbbbbb",
        "disabled_bg": "#444444", "disabled_fg": "#aaaaaa", "disabled_text": "#888888",
    },
    "light": {
        "bg": "#ffffff", "fg": "#000000", "border": "#000000",
        "muted": "#555555", "muted2": "#666666", "faint": "#aaaaaa",
        "line": "#cccccc", "line2": "#e6e6e6",
        "surface": "#f2f2f2", "bubble_in": "#e9e9e9", "info": "#222222",
        "red": "#e02424", "red_hover": "#f04343", "red_press": "#b91c1c", "on_red": "#ffffff",
        "green": "#1d8a36", "orange": "#ff7a1f", "queued": "#666666",
        "alt_bg": "#000000", "alt_fg": "#ffffff",          # black buttons / your chat bubbles
        "alt_hover": "#333333", "alt_press": "#555555",
        "disabled_bg": "#d4d4d4", "disabled_fg": "#666666", "disabled_text": "#888888",
    },
}


class _ThemeEvents(QObject):
    """Theme-changed signal."""
    changed = Signal(str)


theme_events = _ThemeEvents()
_state = {"name": "dark"}


def current_theme():
    """'dark' or 'light'."""
    return _state["name"]


def colors():
    """Current color palette."""
    return THEMES[_state["name"]]


def status_color(status):
    """Color for a message status."""
    c = colors()
    return {"queued": c["queued"], "sent": c["green"], "delivered": c["green"],
            "failed": c["red"]}.get(status, c["fg"])


def set_theme(name, save=True):
    """Switch theme and save it."""
    if name not in THEMES:
        name = "dark"
    _state["name"] = name
    from PySide6.QtWidgets import QApplication
    from ui.styles import build_style
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(build_style(1.0))
    if save:
        from services.settings_service import set_setting
        set_setting("theme", name)
    theme_events.changed.emit(name)


def toggle_theme():
    """Dark <-> light."""
    set_theme("light" if current_theme() == "dark" else "dark")
