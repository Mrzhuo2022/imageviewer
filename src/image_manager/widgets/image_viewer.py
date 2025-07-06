import warnings
from PIL import Image
from PySide6.QtCore import Qt, QSize, Signal, QPoint, QRect, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPixmap, QAction, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect, QMenu, QFileDialog, QMessageBox

warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

from ..config import ICONS

class ImageViewer(QWidget):
    navigate_previous = Signal()
    navigate_next = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_pixmap = None
        self.zoom_factor = 1.0
        self.fit_to_window_zoom = 1.0
        self.min_zoom_factor = 0.01
        self.max_zoom_factor = 10.0
        self.is_fitted_to_window = True
        self.pan_offset = QPoint(0, 0)
        self.last_mouse_pos = None
        self.is_panning = False
        self.image_data = None
        self.mouse_over_image = False
        self.mouse_in_nav_zone = False
        self.buttons_have_focus = False
        self.nav_zone_width = 120
        self.current_image_path = None
        
        self.scaled_pixmap_cache = {}
        self.max_cache_size = 5

        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.image_label = QLabel("Select an image to view")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label, stretch=1)

        self.zoom_in_action = QAction(ICONS["zoom-in"], "Zoom In", self)
        self.zoom_out_action = QAction(ICONS["zoom-out"], "Zoom Out", self)
        self.zoom_actual_action = QAction(ICONS["zoom-actual"], "Actual Size (1:1)", self)
        self.fit_to_window_action = QAction(ICONS["fit-to-window"], "Fit to Window", self)
        self.fullscreen_action = QAction(ICONS["fullscreen"], "Fullscreen Image View", self)
        self.fullscreen_action.setShortcut("F11")
        self.fullscreen_action.triggered.connect(self.show_fullscreen)
        
        self.create_navigation_buttons()
        self.create_zoom_indicator()

    def create_navigation_buttons(self):
        self.prev_button = QPushButton(self)
        self.prev_button.setIcon(ICONS["arrow-left"])
        self.prev_button.setIconSize(QSize(24, 24))
        self.prev_button.setFixedSize(50, 50)
        self.prev_button.setToolTip("Previous Image")
        self.prev_button.clicked.connect(self.navigate_previous.emit)
        
        self.next_button = QPushButton(self)
        self.next_button.setIcon(ICONS["arrow-right"])
        self.next_button.setIconSize(QSize(24, 24))
        self.next_button.setFixedSize(50, 50)
        self.next_button.setToolTip("Next Image")
        self.next_button.clicked.connect(self.navigate_next.emit)
        
        nav_button_style = """
            QPushButton {
                background-color: rgba(52, 73, 94, 200);
                border: 2px solid rgba(149, 165, 166, 100);
                border-radius: 25px;
                color: #ecf0f1;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(52, 73, 94, 250);
                border: 2px solid rgba(149, 165, 166, 200);
            }
            QPushButton:pressed {
                background-color: rgba(44, 62, 80, 200);
            }
            QPushButton:disabled {
                background-color: rgba(52, 73, 94, 100);
                border: 2px solid rgba(149, 165, 166, 50);
                color: rgba(236, 240, 241, 100);
            }
        """
        
        self.prev_button.setStyleSheet(nav_button_style)
        self.next_button.setStyleSheet(nav_button_style)
        
        self.prev_opacity_effect = QGraphicsOpacityEffect()
        self.next_opacity_effect = QGraphicsOpacityEffect()
        
        self.prev_button.setGraphicsEffect(self.prev_opacity_effect)
        self.next_button.setGraphicsEffect(self.next_opacity_effect)
        
        self.prev_opacity_animation = QPropertyAnimation(self.prev_opacity_effect, b"opacity")
        self.prev_opacity_animation.setDuration(300)
        self.prev_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.next_opacity_animation = QPropertyAnimation(self.next_opacity_effect, b"opacity")
        self.next_opacity_animation.setDuration(300)
        self.next_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.prev_opacity_effect.setOpacity(0.0)
        self.next_opacity_effect.setOpacity(0.0)
        
        self.prev_button.enterEvent = self.on_button_enter
        self.prev_button.leaveEvent = self.on_button_leave
        self.next_button.enterEvent = self.on_button_enter
        self.next_button.leaveEvent = self.on_button_leave
        
        self.prev_button.hide()
        self.next_button.hide()

    def create_zoom_indicator(self):
        self.zoom_label = QLabel("100%", self)
        self.zoom_label.setFixedSize(80, 25)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        
        zoom_label_style = """
            QLabel {
                background-color: rgba(52, 73, 94, 220);
                border: 1px solid rgba(149, 165, 166, 150);
                border-radius: 12px;
                color: #ecf0f1;
                font-weight: bold;
                font-size: 10pt;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """
        self.zoom_label.setStyleSheet(zoom_label_style)
        
        self.zoom_opacity_effect = QGraphicsOpacityEffect()
        self.zoom_label.setGraphicsEffect(self.zoom_opacity_effect)
        
        self.zoom_opacity_animation = QPropertyAnimation(self.zoom_opacity_effect, b"opacity")
        self.zoom_opacity_animation.setDuration(300)
        self.zoom_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.zoom_hide_timer = QTimer()
        self.zoom_hide_timer.timeout.connect(self.hide_zoom_indicator)
        self.zoom_hide_timer.setSingleShot(True)
        
        self.zoom_opacity_effect.setOpacity(0.0)
        self.zoom_label.hide()

    def update_pixmap_display(self):
        if not self.current_pixmap:
            return

        original_width = self.current_pixmap.width()
        original_height = self.current_pixmap.height()
        image_size_mb = (original_width * original_height * 4) / (1024 * 1024)
        
        actual_scale_factor = self.zoom_factor
        
        if image_size_mb > 50:
            max_display_pixels = 25_000_000
            current_pixels = original_width * original_height
            
            if current_pixels * (actual_scale_factor ** 2) > max_display_pixels:
                max_scale_factor = (max_display_pixels / current_pixels) ** 0.5
                if actual_scale_factor > max_scale_factor:
                    actual_scale_factor = max_scale_factor

        target_width = int(original_width * actual_scale_factor)
        target_height = int(original_height * actual_scale_factor)
        
        if target_width < 1:
            target_width = 1
        if target_height < 1:
            target_height = 1
        
        cache_key = f"{target_width}x{target_height}"
        if cache_key in self.scaled_pixmap_cache:
            scaled_pixmap = self.scaled_pixmap_cache[cache_key]
        else:
            transformation_mode = Qt.FastTransformation if image_size_mb > 200 else Qt.SmoothTransformation
            
            scaled_pixmap = self.current_pixmap.scaled(
                target_width, target_height,
                Qt.KeepAspectRatio, transformation_mode
            )
            
            if len(self.scaled_pixmap_cache) >= self.max_cache_size:
                oldest_key = next(iter(self.scaled_pixmap_cache))
                del self.scaled_pixmap_cache[oldest_key]
            
            self.scaled_pixmap_cache[cache_key] = scaled_pixmap

        x = (self.image_label.width() - scaled_pixmap.width()) // 2 + self.pan_offset.x()
        y = (self.image_label.height() - scaled_pixmap.height()) // 2 + self.pan_offset.y()

        display_pixmap = QPixmap(self.image_label.size())
        display_pixmap.fill(Qt.transparent)

        painter = QPainter(display_pixmap)
        painter.drawPixmap(x, y, scaled_pixmap)
        painter.end()

        self.image_label.setPixmap(display_pixmap)

    def zoom_in(self):
        new_zoom_factor = self.zoom_factor * 1.25
        if new_zoom_factor <= self.max_zoom_factor:
            self.zoom_factor = new_zoom_factor
            self.is_fitted_to_window = False
            self.update_pixmap_display()
            self.show_zoom_indicator()

    def zoom_out(self):
        new_zoom_factor = self.zoom_factor / 1.25
        dynamic_min_zoom = self.get_dynamic_min_zoom()
        
        if new_zoom_factor >= dynamic_min_zoom:
            self.zoom_factor = new_zoom_factor
            self.is_fitted_to_window = False
            self.update_pixmap_display()
            self.show_zoom_indicator()

    def zoom_to_actual_size(self):
        if self.current_pixmap and self.image_label.width() > 1 and self.image_label.height() > 1:
            label_size = self.image_label.size()
            pixmap_size = self.current_pixmap.size()
            if pixmap_size.width() > 0 and pixmap_size.height() > 0:
                width_scale = label_size.width() / pixmap_size.width()
                height_scale = label_size.height() / pixmap_size.height()
                self.fit_to_window_zoom = min(width_scale, height_scale)
        
        self.zoom_factor = 1.0
        self.is_fitted_to_window = False
        self.pan_offset = QPoint(0, 0)
        self.update_pixmap_display()
        self.show_zoom_indicator()

    def get_dynamic_min_zoom(self):
        if not self.current_pixmap:
            return self.min_zoom_factor
            
        image_pixels = self.current_pixmap.width() * self.current_pixmap.height()
        
        if image_pixels > 100_000_000:
            return 0.005
        elif image_pixels > 50_000_000:
            return 0.01
        elif image_pixels > 20_000_000:
            return 0.02
        elif image_pixels > 10_000_000:
            return 0.05
        else:
            return 0.1

    def fit_to_window(self):
        if self.current_pixmap and self.image_label.width() > 1 and self.image_label.height() > 1:
            label_size = self.image_label.size()
            pixmap_size = self.current_pixmap.size()

            if pixmap_size.width() == 0 or pixmap_size.height() == 0:
                return

            width_scale = label_size.width() / pixmap_size.width()
            height_scale = label_size.height() / pixmap_size.height()
            
            self.zoom_factor = min(width_scale, height_scale)
            self.fit_to_window_zoom = self.zoom_factor
            self.is_fitted_to_window = True
            self.pan_offset = QPoint(0, 0)
            self.update_pixmap_display()
            self.show_zoom_indicator()

    def set_image(self, image_path, image_data):
        try:
            self.scaled_pixmap_cache.clear()
            self.image_label.setStyleSheet("")
            self.current_image_path = image_path
            self.image_data = image_data
            
            self.current_pixmap = QPixmap(image_path)
            
            if self.current_pixmap.isNull():
                self.show_image_error(image_path, "Failed to load image. File may be corrupted or format not supported.")
                return
            
            image_size_mb = (self.current_pixmap.width() * self.current_pixmap.height() * 4) / (1024 * 1024)
            if image_size_mb > 500:
                self.show_image_warning(image_path, f"Very large image ({image_size_mb:.0f}MB in memory). Performance optimization enabled.")
            
            self.zoom_factor = 1.0
            self.fit_to_window_zoom = 1.0
            self.pan_offset = QPoint(0, 0)
            self.is_fitted_to_window = True
            
            self.fit_to_window()
            self.show_navigation_buttons()
            
        except Exception as e:
            self.show_image_error(image_path, f"Error loading image: {str(e)}")

    def show_image_error(self, image_path, error_message):
        from pathlib import Path
        filename = Path(image_path).name
        error_text = f"Failed to load image: {filename}\n\n{error_message}\n\nTry:\n• Restart the application\n• Check available memory\n• Reduce image size"
        
        self.image_label.setText(error_text)
        self.image_label.setStyleSheet("color: #e74c3c; padding: 20px; font-size: 12pt;")
        self.current_pixmap = None
        self.image_data = None
        self.hide_navigation_buttons()

    def show_image_warning(self, image_path, warning_message):
        from pathlib import Path
        filename = Path(image_path).name
        print(f"Image warning {filename}: {warning_message}")

    def clear_image(self):
        self.scaled_pixmap_cache.clear()
        self.image_label.clear()
        self.image_label.setText("Select an image to view")
        self.current_pixmap = None
        self.image_data = None
        self.hide_navigation_buttons()
        
        if hasattr(self, 'zoom_label'):
            self.zoom_label.hide()

    def wheelEvent(self, event):
        if not self.current_pixmap:
            return

        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'is_fitted_to_window') and self.is_fitted_to_window:
            self.fit_to_window()
        self.update_navigation_buttons_position()
        if hasattr(self, 'zoom_label'):
            self.update_zoom_indicator_position()

    def enterEvent(self, event):
        super().enterEvent(event)
        self.mouse_over_image = True
        if self.current_pixmap:
            in_nav_zone = self.check_mouse_in_nav_zones(event.pos())
            self.mouse_in_nav_zone = in_nav_zone
            self.check_and_update_button_visibility()
            
    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.mouse_over_image = False
        self.mouse_in_nav_zone = False
        if self.current_pixmap:
            self.check_and_update_button_visibility()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.is_panning:
            delta = event.pos() - self.last_mouse_pos
            self.pan_offset += delta
            self.constrain_pan_offset()
            self.last_mouse_pos = event.pos()
            self.update_pixmap_display()
            return
            
        if self.current_pixmap:
            in_nav_zone = self.check_mouse_in_nav_zones(event.pos())
            
            if in_nav_zone != self.mouse_in_nav_zone:
                self.mouse_in_nav_zone = in_nav_zone
                self.check_and_update_button_visibility()
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_panning:
            self.is_panning = False
            self.update_cursor()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_pannable():
            self.last_mouse_pos = event.pos()
            self.is_panning = True
            self.setCursor(Qt.ClosedHandCursor)

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

        delta_x = (scaled_rect.width() - label_rect.width()) / 2
        delta_y = (scaled_rect.height() - label_rect.height()) / 2

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

    def update_navigation_buttons_position(self):
        if not self.current_pixmap:
            return
            
        button_margin = 20
        button_y = (self.height() - self.prev_button.height()) // 2
        
        prev_x = button_margin
        self.prev_button.move(prev_x, button_y)
        
        next_x = self.width() - self.next_button.width() - button_margin
        self.next_button.move(next_x, button_y)
        
    def show_navigation_buttons(self):
        if self.current_pixmap:
            self.prev_button.show()
            self.next_button.show()
            self.update_navigation_buttons_position()
            self.check_and_update_button_visibility()
            
    def hide_navigation_buttons(self):
        self.prev_button.hide()
        self.next_button.hide()
        
    def set_navigation_enabled(self, prev_enabled, next_enabled):
        self.prev_button.setEnabled(prev_enabled)
        self.next_button.setEnabled(next_enabled)

    def update_navigation_buttons_visibility(self, show_buttons):
        target_opacity = 1.0 if show_buttons else 0.0
        
        self.prev_opacity_animation.setEndValue(target_opacity)
        self.next_opacity_animation.setEndValue(target_opacity)
        
        self.prev_opacity_animation.start()
        self.next_opacity_animation.start()

    def check_mouse_in_nav_zones(self, pos):
        if not self.current_pixmap:
            return False
            
        widget_width = self.width()
        widget_height = self.height()
        
        extended_width = self.nav_zone_width + 30
        left_zone = QRect(0, 0, extended_width, widget_height)
        right_zone = QRect(widget_width - extended_width, 0, extended_width, widget_height)
        
        return left_zone.contains(pos) or right_zone.contains(pos)

    def on_button_enter(self, event):
        self.buttons_have_focus = True
        
    def on_button_leave(self, event):
        self.buttons_have_focus = False
        self.check_and_update_button_visibility()
        
    def should_show_buttons(self):
        return self.mouse_in_nav_zone or self.buttons_have_focus
        
    def check_and_update_button_visibility(self):
        should_show = self.should_show_buttons()
        current_opacity = self.prev_opacity_effect.opacity()
        
        if (should_show and current_opacity < 1.0) or (not should_show and current_opacity > 0.0):
            self.update_navigation_buttons_visibility(should_show)

    def show_fullscreen(self):
        if self.current_image_path and self.current_pixmap:
            main_window = self.window()
            if not main_window.isFullScreen():
                self.fit_to_window()
                main_window.showFullScreen()
                QTimer.singleShot(100, self.fit_to_window)
            else:
                main_window.showNormal()
                QTimer.singleShot(100, self.fit_to_window)

    def show_zoom_indicator(self):
        if not self.current_pixmap:
            return
            
        if self.fit_to_window_zoom > 0:
            zoom_percent = int((self.zoom_factor / self.fit_to_window_zoom) * 100)
        else:
            zoom_percent = int(self.zoom_factor * 100)
        
        if abs(self.zoom_factor - self.fit_to_window_zoom) < 0.01:
            display_text = "100%"
        elif abs(self.zoom_factor - 1.0) < 0.01:
            actual_percent = int((1.0 / self.fit_to_window_zoom) * 100) if self.fit_to_window_zoom > 0 else 100
            display_text = f"{actual_percent}%"
        else:
            display_text = f"{zoom_percent}%"
            
        self.zoom_label.setText(display_text)
        
        self.update_zoom_indicator_position()
        
        self.zoom_label.show()
        self.zoom_opacity_animation.setEndValue(0.9)
        self.zoom_opacity_animation.start()
        
        self.zoom_hide_timer.stop()
        self.zoom_hide_timer.start(1500)
        
    def hide_zoom_indicator(self):
        self.zoom_opacity_animation.setEndValue(0.0)
        self.zoom_opacity_animation.start()
        
    def update_zoom_indicator_position(self):
        if not self.current_pixmap:
            return
            
        margin = 15
        x = self.width() - self.zoom_label.width() - margin
        y = margin
        self.zoom_label.move(x, y)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.show_fullscreen()
        super().mouseDoubleClickEvent(event)
        
    def show_context_menu(self, position):
        if not self.current_pixmap or not self.current_image_path:
            return
            
        menu = QMenu(self)
        
        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut("Ctrl+S")
        save_as_action.triggered.connect(self.save_image_as)
        menu.addAction(save_as_action)
        
        menu.addSeparator()
        
        copy_action = QAction("Copy Image", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_image_to_clipboard)
        menu.addAction(copy_action)
        
        menu.exec(self.mapToGlobal(position))
        
    def save_image_as(self):
        if not self.current_image_path:
            return
            
        try:
            from pathlib import Path
            original_path = Path(self.current_image_path)
            
            if self.image_data and "original_filename" in self.image_data:
                original_filename = self.image_data["original_filename"]
                original_name = Path(original_filename).stem
                original_ext = Path(original_filename).suffix
            else:
                original_name = original_path.stem
                original_ext = original_path.suffix
            
            file_dialog = QFileDialog(self)
            file_dialog.setWindowTitle("Save As")
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setFileMode(QFileDialog.AnyFile)
            
            filters = [
                "JPEG Images (*.jpg *.jpeg)",
                "PNG Images (*.png)", 
                "BMP Images (*.bmp)",
                "TIFF Images (*.tiff *.tif)",
                "WebP Images (*.webp)",
                "All Files (*.*)"
            ]
            file_dialog.setNameFilters(filters)
            
            if original_ext.lower() in ['.jpg', '.jpeg']:
                file_dialog.selectNameFilter("JPEG Images (*.jpg *.jpeg)")
            elif original_ext.lower() == '.png':
                file_dialog.selectNameFilter("PNG Images (*.png)")
            elif original_ext.lower() == '.bmp':
                file_dialog.selectNameFilter("BMP Images (*.bmp)")
            elif original_ext.lower() in ['.tiff', '.tif']:
                file_dialog.selectNameFilter("TIFF Images (*.tiff *.tif)")
            elif original_ext.lower() == '.webp':
                file_dialog.selectNameFilter("WebP Images (*.webp)")
            
            file_dialog.selectFile(f"{original_name}{original_ext}")
            
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    save_path = selected_files[0]
                    self.save_image_to_path(save_path)
                    
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error opening save dialog: {str(e)}")
            
    def save_image_to_path(self, save_path):
        try:
            from pathlib import Path
            import shutil
            
            save_path = Path(save_path)
            original_path = Path(self.current_image_path)
            
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            save_ext = save_path.suffix.lower()
            original_ext = original_path.suffix.lower()
            
            if save_ext == original_ext:
                shutil.copy2(self.current_image_path, save_path)
                QMessageBox.information(self, "Success", f"Image saved to:\n{save_path}")
            else:
                self.convert_and_save_image(save_path, save_ext)
                
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Error saving image:\n{str(e)}")
            
    def convert_and_save_image(self, save_path, target_format):
        try:
            if self.current_pixmap and not self.current_pixmap.isNull():
                format_map = {
                    '.jpg': 'JPEG', '.jpeg': 'JPEG',
                    '.png': 'PNG', 
                    '.bmp': 'BMP',
                    '.tiff': 'TIFF', '.tif': 'TIFF',
                    '.webp': 'WEBP'
                }
                
                qt_format = format_map.get(target_format, 'PNG')
                
                success = self.current_pixmap.save(str(save_path), qt_format)
                
                if success:
                    QMessageBox.information(self, "Success", f"Image converted and saved to:\n{save_path}")
                else:
                    self.save_with_pil(save_path, target_format)
            else:
                QMessageBox.critical(self, "Error", "No image to save")
                
        except Exception as e:
            QMessageBox.critical(self, "Conversion Failed", f"Error converting image format:\n{str(e)}")
            
    def save_with_pil(self, save_path, target_format):
        try:
            with Image.open(self.current_image_path) as img:
                if target_format == '.png':
                    img.save(save_path, 'PNG')
                elif target_format in ['.jpg', '.jpeg']:
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'LA':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1])
                        background.save(save_path, 'JPEG', quality=95)
                    else:
                        img.convert('RGB').save(save_path, 'JPEG', quality=95)
                else:
                    img.save(save_path)
                    
            QMessageBox.information(self, "Success", f"Image saved to:\n{save_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", f"Error saving with PIL:\n{str(e)}")
            
    def copy_image_to_clipboard(self):
        try:
            if self.current_pixmap and not self.current_pixmap.isNull():
                from PySide6.QtGui import QClipboard
                from PySide6.QtWidgets import QApplication
                
                clipboard = QApplication.clipboard()
                clipboard.setPixmap(self.current_pixmap)
                
                self.parent().statusBar().showMessage("Image copied to clipboard", 2000)
            else:
                QMessageBox.warning(self, "Warning", "No image to copy")
                
        except Exception as e:
            QMessageBox.critical(self, "Copy Failed", f"Error copying image to clipboard:\n{str(e)}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.show_fullscreen()
        else:
            super().keyPressEvent(event)