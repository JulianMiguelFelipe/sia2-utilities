"""
ui/styles.py
One stylesheet (QSS, works like CSS) for the whole app.
Black and white, with white-bordered boxes and red/white buttons.
"""

BLACK = "#000000"
WHITE = "#ffffff"
RED = "#ff3333"
GREEN = "#6fd65a"
ORANGE = "#ff7a1f"

APP_STYLE = f"""
QWidget {{
    background-color: {BLACK};
    color: {WHITE};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}}

/* ----- White-bordered boxes ----- */
QFrame#box {{
    border: 2px solid {WHITE};
    background-color: {BLACK};
}}

/* ----- Text ----- */
QLabel {{ background: transparent; border: none; }}
QLabel#brand {{
    border: 2px solid {WHITE};
    padding: 0px 6px;
    font-size: 18px;
    font-weight: 800;
}}
QLabel#boxTitle  {{ font-size: 20px; font-weight: 800; }}
QLabel#sectionTitle {{ font-size: 17px; font-weight: 800; }}
QLabel#dotOff {{ color: #777777; font-size: 11px; font-weight: 800; }}
QLabel#dotOn  {{ color: {GREEN}; font-size: 11px; font-weight: 800; }}
QLabel#boxTitleBordered {{
    border: 2px solid {WHITE};
    padding: 0px 4px;
    font-size: 18px;
    font-weight: 800;
}}
QLabel#fieldLabel  {{ font-size: 12px; font-weight: 600; }}
QLabel#featureName {{ color: {GREEN}; font-size: 12px; font-weight: 800; }}
QLabel#featureDesc {{ font-size: 12px; padding-left: 28px; }}
QLabel#error   {{ color: {RED}; font-size: 12px; }}
QLabel#success {{ color: {GREEN}; font-size: 12px; }}
QLabel#placeholder {{
    background-color: {ORANGE};
    color: {WHITE};
    font-size: 13px;
}}

/* ----- Inputs ----- */
QLineEdit {{
    background-color: {BLACK};
    color: {WHITE};
    border: 2px solid {WHITE};
    border-radius: 8px;
    padding: 2px 10px;
    selection-background-color: {RED};
}}
QLineEdit:focus {{ border-color: {RED}; }}
QLineEdit:disabled {{ border-color: #555555; color: #888888; }}

QTextEdit {{
    background-color: {BLACK};
    color: {WHITE};
    border: 2px solid {WHITE};
    border-radius: 8px;
    padding: 4px 6px;
    selection-background-color: {RED};
}}
QTextEdit:focus {{ border-color: {RED}; }}
QToolTip {{ background-color: {BLACK}; color: {WHITE}; border: 1px solid {WHITE}; padding: 4px; }}

QLabel#hint {{ color: #999999; font-size: 11px; }}
QLabel#badge {{
    border: 2px solid #555555;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 800;
    padding: 4px 0px;
}}

/* ----- Tables (history) ----- */
QTableWidget {{
    background-color: {BLACK};
    color: {WHITE};
    border: none;
    gridline-color: #333333;
    font-size: 12px;
}}
QTableWidget::item {{ padding: 2px 6px; border-bottom: 1px solid #222222; }}
QTableWidget::item:selected {{ background-color: {RED}; color: {WHITE}; }}
QHeaderView::section {{
    background-color: {BLACK};
    color: {WHITE};
    border: none;
    border-bottom: 2px solid {WHITE};
    padding: 4px 6px;
    font-size: 11px;
    font-weight: 800;
}}
QTableCornerButton::section {{ background-color: {BLACK}; border: none; }}

/* ----- Scrollbars ----- */
QScrollBar:vertical, QScrollBar:horizontal {{ background: {BLACK}; border: none; }}
QScrollBar:vertical   {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{ background: #555555; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {WHITE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ----- Buttons ----- */
QPushButton {{
    font-size: 12px;
    font-weight: 800;
    border-radius: 6px;
    padding: 6px 18px;
}}
QPushButton#primary {{ background-color: {RED}; color: {WHITE}; border: none; }}
QPushButton#primary:hover   {{ background-color: #ff5c5c; }}
QPushButton#primary:pressed {{ background-color: #d92626; }}

QPushButton#secondary {{ background-color: {WHITE}; color: {BLACK}; border: none; }}
QPushButton#secondary:hover   {{ background-color: #dddddd; }}
QPushButton#secondary:pressed {{ background-color: #bbbbbb; }}
QPushButton:disabled {{ background-color: #444444; color: #aaaaaa; }}

/* Top navigation tabs */
QPushButton#tab {{
    background: transparent;
    color: {WHITE};
    border: 2px solid transparent;
    border-radius: 0px;
    padding: 4px 10px;
}}
QPushButton#tab:hover   {{ border-color: #555555; }}
QPushButton#tab:checked {{ border-color: {RED}; }}

/* Settings gear + its menu */
QToolButton#gear {{ background: transparent; border: none; padding: 2px; }}
QToolButton#gear::menu-indicator {{ image: none; }}
QMenu {{
    background-color: {BLACK};
    color: {WHITE};
    border: 2px solid {WHITE};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; }}
QMenu::item:selected {{ background-color: {RED}; }}
QMenu::item:disabled {{ color: #999999; }}
QMenu::separator {{ height: 1px; background: #555555; margin: 4px 6px; }}

/* Pop-up messages */
QMessageBox {{ background-color: {BLACK}; }}
QMessageBox QPushButton {{
    background-color: {RED};
    color: {WHITE};
    border: none;
    min-width: 70px;
}}
"""
