from PySide6.QtCore import Qt, QSize, Signal, QPoint, QRect
from PySide6.QtGui import QPixmap, QAction, QPainter, QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from ..config import ICONS

class ImageViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_pixmap = None
        self.zoom_factor = 1.0
        self.min_zoom_factor = 0.1 # Minimum zoom level (10% of actual size)
        self.max_zoom_factor = 10.0 # Maximum zoom level (1000% of actual size)
        self.is_fitted_to_window = True  # Flag to control fit-to-window on resize
        self.pan_offset = QPoint(0, 0)  # Current pan offset
        self.last_mouse_pos = None  # Last position for panning
        self.is_panning = False # Add this line to initialize is_panning
        self.image_data = None # Initialize image_data

        self.setMouseTracking(True)  # Enable mouse move events even when no button is pressed
        self.setCursor(Qt.OpenHandCursor) # Default cursor for panning

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.image_label = QLabel("Select an image to view")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label, stretch=1)

        # Actions for zoom, etc. (connected in MainWindow)
        self.zoom_in_action = QAction(ICONS["zoom-in"], "Zoom In", self)
        self.zoom_out_action = QAction(ICONS["zoom-out"], "Zoom Out", self)
        self.zoom_actual_action = QAction(ICONS["zoom-actual"], "Actual Size (1:1)", self)
        self.fit_to_window_action = QAction(ICONS["fit-to-window"], "Fit to Window", self)

    def update_pixmap_display(self):
        if not self.current_pixmap:
            return

        scaled_pixmap = self.current_pixmap.scaled(
            self.current_pixmap.size() * self.zoom_factor,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        # Calculate the top-left corner to draw the scaled image, considering pan_offset
        x = (self.image_label.width() - scaled_pixmap.width()) // 2 + self.pan_offset.x()
        y = (self.image_label.height() - scaled_pixmap.height()) // 2 + self.pan_offset.y()

        # Create a blank pixmap the size of the label
        display_pixmap = QPixmap(self.image_label.size())
        display_pixmap.fill(Qt.transparent) # Fill with transparent background

        painter = QPainter(display_pixmap)
        painter.drawPixmap(x, y, scaled_pixmap)
        painter.end()

        self.image_label.setPixmap(display_pixmap)

    def zoom_in(self):
        new_zoom_factor = self.zoom_factor * 1.25
        if new_zoom_factor <= self.max_zoom_factor:
            self.zoom_factor = new_zoom_factor
            self.is_fitted_to_window = False  # Manual zoom, so not fitted
            self.update_pixmap_display()

    def zoom_out(self):
        new_zoom_factor = self.zoom_factor / 1.25
        if new_zoom_factor >= self.min_zoom_factor:
            self.zoom_factor = new_zoom_factor
            self.is_fitted_to_window = False  # Manual zoom, so not fitted
            self.update_pixmap_display()

    def zoom_to_actual_size(self):
        self.zoom_factor = 1.0
        self.is_fitted_to_window = False  # Manual zoom, so not fitted
        self.pan_offset = QPoint(0, 0) # Reset pan offset
        self.update_pixmap_display()

    def fit_to_window(self):
        if self.current_pixmap and self.image_label.width() > 1 and self.image_label.height() > 1:
            label_size = self.image_label.size()
            pixmap_size = self.current_pixmap.size()

            if pixmap_size.width() == 0 or pixmap_size.height() == 0:
                return

            width_scale = label_size.width() / pixmap_size.width()
            height_scale = label_size.height() / pixmap_size.height()
            
            self.zoom_factor = min(width_scale, height_scale)
            self.is_fitted_to_window = True  # Image is now fitted to window
            self.pan_offset = QPoint(0, 0) # Reset pan offset
            self.update_pixmap_display()

    def set_image(self, image_path, image_data):
        self.current_pixmap = QPixmap(image_path)
        self.image_data = image_data # Store image_data
        self.zoom_factor = 1.0
        self.pan_offset = QPoint(0, 0)
        self.is_fitted_to_window = True
        
        # If image is smaller than label, display actual size and center
        if self.current_pixmap.width() <= self.image_label.width() and \
           self.current_pixmap.height() <= self.image_label.height():
            self.zoom_to_actual_size()
        else:
            self.fit_to_window()

    def clear_image(self):
        self.image_label.clear()
        self.image_label.setText("Select an image to view")
        self.current_pixmap = None
        self.image_data = None

    def wheelEvent(self, event):
        if not self.current_pixmap:
            return

        # Zoom in/out based on wheel delta
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'is_fitted_to_window') and self.is_fitted_to_window:
            self.fit_to_window()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_pannable():
            self.last_mouse_pos = event.pos()
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.is_panning:
            delta = event.pos() - self.last_mouse_pos
            self.pan_offset += delta
            self.constrain_pan_offset()
            self.last_mouse_pos = event.pos()
            self.update_pixmap_display()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.update_cursor()

    def is_pannable(self):
        if not self.current_pixmap:
            return False
        return self.get_scaled_pixmap_rect().width() > self.image_label.width() or \
               self.get_scaled_pixmap_rect().height() > self.image_label.height()

    def constrain_pan_offset(self):
        if not self.current_pixmap:
            return

        scaled_rect = self.get_scaled_pixmap_rect()
        label_rect = self.image_label.rect()

        # Calculate maximum allowed offsets
        delta_x = (scaled_rect.width() - label_rect.width()) / 2
        delta_y = (scaled_rect.height() - label_rect.height()) / 2

        # Clamp the pan offset
        if delta_x > 0:
            self.pan_offset.setX(max(-delta_x, min(self.pan_offset.x(), delta_x)))
        else:
            self.pan_offset.setX(0)

        if delta_y > 0:
            self.pan_offset.setY(max(-delta_y, min(self.pan_offset.y(), delta_y)))
        else:
            self.pan_offset.setY(0)

    def update_cursor(self):
        if self.is_panning:
            self.setCursor(Qt.ClosedHandCursor)
        elif self.is_pannable():
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def get_scaled_pixmap_rect(self):
        if not self.current_pixmap:
            return QRect()
        scaled_width = self.current_pixmap.width() * self.zoom_factor
        scaled_height = self.current_pixmap.height() * self.zoom_factor
        return QRect(0, 0, scaled_width, scaled_height)
