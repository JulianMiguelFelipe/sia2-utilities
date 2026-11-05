"""
ui/styles.py
One stylesheet (QSS, works like CSS) for the whole app.
Bordered boxes with red and white (or black, in light mode) buttons.

build_style(scale) builds it for the current theme (see theme.py) and makes it
bigger for large windows: every font size, padding and border is multiplied by `scale`.
"""

from ui.theme import colors


def build_style(scale=1.0):
    def s(n):
        """Scale a pixel size (always at least 1px)."""
        return max(1, round(n * scale))

    c = colors()
    BG, FG, BORDER, RED, GREEN, ORANGE = c["bg"], c["fg"], c["border"], c["red"], c["green"], c["orange"]

    return f"""
QWidget {{
    background-color: {BG};
    color: {FG};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: {s(13)}px;
}}

/* ----- White-bordered boxes ----- */
QFrame#box {{
    border: {s(2)}px solid {BORDER};
    background-color: {BG};
}}

/* ----- Text ----- */
QLabel {{ background: transparent; border: none; }}
QLabel#brand {{
    border: {s(2)}px solid {BORDER};
    padding: 0px {s(6)}px;
    font-size: {s(18)}px;
    font-weight: 800;
}}
QLabel#boxTitle  {{ font-size: {s(20)}px; font-weight: 800; }}
QLabel#sectionTitle {{ font-size: {s(17)}px; font-weight: 800; }}
QLabel#boxTitleBordered {{
    border: {s(2)}px solid {BORDER};
    padding: 0px {s(4)}px;
    font-size: {s(18)}px;
    font-weight: 800;
}}
QLabel#fieldLabel  {{ font-size: {s(12)}px; font-weight: 600; }}
QLabel#featureName {{ color: {GREEN}; font-size: {s(12)}px; font-weight: 800; }}
QLabel#featureDesc {{ font-size: {s(12)}px; padding-left: {s(28)}px; }}
QLabel#statValue   {{ font-size: {s(22)}px; font-weight: 800; }}
QLabel#infoText    {{ font-size: {s(12)}px; color: {c['info']}; }}
QLabel#error   {{ color: {RED}; font-size: {s(12)}px; }}
QLabel#success {{ color: {GREEN}; font-size: {s(12)}px; }}
QLabel#hint    {{ color: {c['muted']}; font-size: {s(11)}px; }}
QLabel#dotOff  {{ color: {c['muted2']}; font-size: {s(11)}px; font-weight: 800; }}
QLabel#dotOn   {{ color: {GREEN}; font-size: {s(11)}px; font-weight: 800; }}
QLabel#badge {{
    border: {s(2)}px solid {c['faint']};
    border-radius: {s(6)}px;
    font-size: {s(11)}px;
    font-weight: 800;
    padding: {s(4)}px 0px;
}}
QLabel#placeholder {{
    background-color: {ORANGE};
    color: #ffffff;
    font-size: {s(13)}px;
}}

/* ----- Inputs ----- */
QLineEdit {{
    background-color: {BG};
    color: {FG};
    border: {s(2)}px solid {BORDER};
    border-radius: {s(8)}px;
    padding: {s(2)}px {s(10)}px;
    selection-background-color: {RED};
}}
QLineEdit:focus {{ border-color: {RED}; }}
QLineEdit:disabled {{ border-color: {c['faint']}; color: {c['disabled_text']}; }}

QTextEdit {{
    background-color: {BG};
    color: {FG};
    border: {s(2)}px solid {BORDER};
    border-radius: {s(8)}px;
    padding: {s(4)}px {s(6)}px;
    selection-background-color: {RED};
}}
QTextEdit:focus {{ border-color: {RED}; }}
QToolTip {{ background-color: {BG}; color: {FG}; border: 1px solid {BORDER}; padding: {s(4)}px; }}

/* ----- Tables (history) ----- */
QTableWidget {{
    background-color: {BG};
    color: {FG};
    border: none;
    gridline-color: {c['line']};
    font-size: {s(12)}px;
}}
QTableWidget::item {{ padding: {s(2)}px {s(6)}px; border-bottom: 1px solid {c['line2']}; }}
QTableWidget::item:selected {{ background-color: {RED}; color: {c['on_red']}; }}
QHeaderView::section {{
    background-color: {BG};
    color: {FG};
    border: none;
    border-bottom: {s(2)}px solid {BORDER};
    padding: {s(4)}px {s(6)}px;
    font-size: {s(11)}px;
    font-weight: 800;
}}
QTableCornerButton::section {{ background-color: {BG}; border: none; }}

/* ----- Scrollbars ----- */
QScrollBar:vertical, QScrollBar:horizontal {{ background: {BG}; border: none; }}
QScrollBar:vertical   {{ width: {s(10)}px; }}
QScrollBar:horizontal {{ height: {s(10)}px; }}
QScrollBar::handle {{ background: {c['faint']}; border-radius: {s(5)}px; min-height: {s(24)}px; min-width: {s(24)}px; }}
QScrollBar::handle:hover {{ background: {FG}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ----- Buttons ----- */
QPushButton {{
    font-size: {s(12)}px;
    font-weight: 800;
    border-radius: {s(6)}px;
    padding: {s(6)}px {s(18)}px;
}}
QPushButton#primary {{ background-color: {RED}; color: {c['on_red']}; border: none; }}
QPushButton#primary:hover   {{ background-color: {c['red_hover']}; }}
QPushButton#primary:pressed {{ background-color: {c['red_press']}; }}

QPushButton#secondary {{ background-color: {c['alt_bg']}; color: {c['alt_fg']}; border: none; }}
QPushButton#secondary:hover   {{ background-color: {c['info']}; }}
QPushButton#secondary:pressed {{ background-color: {c['alt_press']}; }}
QPushButton:disabled {{ background-color: {c['disabled_bg']}; color: {c['disabled_fg']}; }}

/* Header: clock and username */
QLabel#headerInfo {{ color: {c['muted']}; font-size: {s(12)}px; font-weight: 600; }}
QLabel#headerUser {{ font-size: {s(13)}px; font-weight: 800; }}
QFrame#headerDivider {{ background-color: {c['line']}; border: none; }}

/* Top navigation tabs */
QPushButton#tab {{
    background: transparent;
    color: {FG};
    border: {s(2)}px solid transparent;
    border-radius: 0px;
    padding: {s(4)}px {s(10)}px;
}}
QPushButton#tab:hover   {{ border-color: {c['faint']}; }}
QPushButton#tab:checked {{ border-color: {RED}; }}

/* Sub-tabs inside SMS & EMAIL UI */
QWidget#subtabBar {{ border-bottom: 1px solid {c['line']}; }}
QPushButton#subtab {{
    background: transparent;
    color: {c['muted']};
    border: none;
    border-bottom: {s(3)}px solid transparent;
    border-radius: 0px;
    padding: {s(8)}px {s(14)}px;
}}
QPushButton#subtab:hover   {{ color: {FG}; }}
QPushButton#subtab:checked {{ color: {FG}; border-bottom-color: {RED}; }}
QLabel#countBadge {{
    background-color: {RED};
    color: {c['on_red']};
    border-radius: {s(9)}px;
    min-height: {s(18)}px; max-height: {s(18)}px;
    padding: 0px {s(7)}px;
    font-size: {s(10)}px;
    font-weight: 800;
}}

/* Lists (conversations, emails) */
QListWidget#itemList {{ background: {BG}; border: none; outline: none; }}
QListWidget#itemList::item {{
    border: {s(2)}px solid {c['line']};
    border-radius: {s(8)}px;
    margin-bottom: {s(6)}px;
}}
QListWidget#itemList::item:hover    {{ border-color: {c['muted2']}; }}
QListWidget#itemList::item:selected {{ border-color: {RED}; background-color: {c['surface']}; }}

/* Chat bubbles and email body */
QTextBrowser#chatView {{
    background-color: {BG};
    color: {FG};
    border: none;
    padding: {s(10)}px {s(14)}px;
    font-size: {s(13)}px;
}}
QWidget#chatHeader {{ border-bottom: {s(2)}px solid {BORDER}; }}
QWidget#chatFooter {{ border-top: {s(2)}px solid {BORDER}; }}

QCheckBox {{ background: transparent; font-size: {s(12)}px; spacing: {s(8)}px; }}
QCheckBox::indicator {{
    width: {s(16)}px; height: {s(16)}px;
    border: {s(2)}px solid {BORDER};
    border-radius: {s(4)}px;
    background-color: {BG};
}}
QCheckBox::indicator:checked {{ background-color: {RED}; border-color: {RED}; }}

/* Settings gear + its menu */
QToolButton#gear {{ background: transparent; border: none; padding: {s(2)}px; }}
QToolButton#gear::menu-indicator {{ image: none; }}
QMenu {{
    background-color: {BG};
    color: {FG};
    border: {s(2)}px solid {BORDER};
    padding: {s(4)}px;
}}
QMenu::item {{ padding: {s(6)}px {s(18)}px; }}
QMenu::item:selected {{ background-color: {RED}; color: {c['on_red']}; }}
QMenu::item:disabled {{ color: {c['muted']}; }}
QMenu::separator {{ height: 1px; background: {c['faint']}; margin: {s(4)}px {s(6)}px; }}

/* Pop-up messages and dialogs (rename, confirm) */
QMessageBox, QDialog {{ background-color: {BG}; }}
QMessageBox QPushButton, QDialog QPushButton {{
    background-color: {RED};
    color: {c['on_red']};
    border: none;
    min-width: {s(70)}px;
}}
"""


def app_style():
    """The normal-size stylesheet for the current theme."""
    return build_style(1.0)
