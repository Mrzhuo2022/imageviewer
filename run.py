
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImageReader

from src.image_manager.config import MODERN_QSS
from src.image_manager.main_window import MainWindow

from src.image_manager import image_utils

if __name__ == "__main__":
    image_utils.ensure_library_folders_exist()
    
    # Set Qt image allocation limit to 2GB (2048 MB) to handle large upscaled images
    # Default is 256MB which is too small for multiple upscaled images
    os.environ["QT_IMAGEIO_MAXALLOC"] = "2048"
    
    app = QApplication(sys.argv)
    
    # Also set the allocation limit programmatically
    QImageReader.setAllocationLimit(2048)  # 2048 MB = 2 GB
    
    app.setStyleSheet(MODERN_QSS)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
