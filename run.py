
import sys
from PySide6.QtWidgets import QApplication

from src.image_manager.config import MODERN_QSS
from src.image_manager.main_window import MainWindow

from src.image_manager import image_utils

if __name__ == "__main__":
    image_utils.ensure_library_folders_exist()
    

    app = QApplication(sys.argv)
    app.setStyleSheet(MODERN_QSS)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
