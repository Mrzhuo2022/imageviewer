
from pathlib import Path
from PySide6.QtGui import QIcon

# --- Base Paths ---
APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent.parent
ICONS_DIR = ROOT_DIR / "icons"
LIBRARY_DIR = ROOT_DIR / "image_library"
INTERNAL_DATA_DIR = ROOT_DIR / ".image_manager_data" # New internal data directory
THUMBNAIL_DIR = INTERNAL_DATA_DIR / "thumbnails"
METADATA_FILE = INTERNAL_DATA_DIR / "metadata.json"


# --- UI Constants ---
THUMBNAIL_SIZE = (128, 128)
GRID_SPACING = (138, 160) # Increased height for filenames

# --- Icons ---
ICONS = {
    "import": QIcon(str(ICONS_DIR / "import.svg")),
    "delete": QIcon(str(ICONS_DIR / "delete.svg")),
    "rename": QIcon(str(ICONS_DIR / "rename.svg")),
    "zoom-in": QIcon(str(ICONS_DIR / "zoom-in.svg")),
    "zoom-out": QIcon(str(ICONS_DIR / "zoom-out.svg")),
    "zoom-actual": QIcon(str(ICONS_DIR / "zoom-actual.svg")),
    "fit-to-window": QIcon(str(ICONS_DIR / "fit-to-window.svg")),
    "add": QIcon(str(ICONS_DIR / "add.svg")),
    "upscale": QIcon(str(ICONS_DIR / "upscale.svg")),
    "arrow-left": QIcon(str(ICONS_DIR / "arrow-left.svg")),
    "arrow-right": QIcon(str(ICONS_DIR / "arrow-right.svg")),
}

# --- Stylesheet ---
MODERN_QSS = '''
QWidget {
    background-color: #2c3e50;
    color: #ecf0f1;
    font-family: "Segoe UI", "Roboto", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
}
QMainWindow {
    background-color: #233140;
}
QMenuBar {
    background-color: #34495e;
    color: #ecf0f1;
}
QMenuBar::item:selected {
    background-color: #4e6a85;
}
QMenu {
    background-color: #34495e;
    border: 1px solid #4e6a85;
}
QMenu::item:selected {
    background-color: #3498db;
    color: #ffffff;
}
QSplitter::handle {
    background-color: #34495e;
    width: 4px;
}
QSplitter::handle:hover {
    background-color: #3498db;
}
QListView {
    background-color: #2c3e50;
    border: 1px solid #34495e;
    padding: 8px;
}
QListView::item {
    color: #ecf0f1;
    padding: 8px;
    border-radius: 4px;
}
QListView::item:selected {
    background-color: #3498db;
    color: #ffffff;
}
QLabel {
    color: #ecf0f1;
}
QMessageBox, QInputDialog {
    background-color: #34495e;
}
QLineEdit {
    background-color: #34495e;
    border: 1px solid #4e6a85;
    padding: 5px;
    border-radius: 4px;
}
QToolBar {
    background-color: #34495e;
    border: none;
    padding: 4px;
    spacing: 8px;
}
QToolBar QToolButton {
    background-color: transparent;
    padding: 4px;
    border-radius: 4px;
}
QToolBar QToolButton:hover {
    background-color: #4e6a85;
}
QToolBar QToolButton:pressed {
    background-color: #3498db;
}
QStatusBar {
    background-color: #34495e;
    color: #bdc3c7;
}

QScrollBar:vertical {
    border: none;
    background: #2c3e50;
    width: 8px; /* Smaller width */
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:vertical {
    background: #3498db; /* Blue handle */
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
    height: 0px;
}
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: #2c3e50;
    height: 8px; /* Smaller height */
    margin: 0px 0px 0px 0px;
}
QScrollBar::handle:horizontal {
    background: #3498db; /* Blue handle */
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    border: none;
    background: none;
    width: 0px;
}
QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
'''
