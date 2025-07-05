import warnings
from PIL import Image
from PySide6.QtCore import Qt, QSize, Signal, QPoint, QRect, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPixmap, QAction, QPainter
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect

# Suppress PIL decompression bomb warnings since we handle large images ourselves
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

from ..config import ICONS

class ImageViewer(QWidget):
    # 添加导航信号
    navigate_previous = Signal()
    navigate_next = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_pixmap = None
        self.zoom_factor = 1.0
        self.fit_to_window_zoom = 1.0  # 保存fit to window时的缩放比例作为100%基准
        self.min_zoom_factor = 0.01 # Minimum zoom level (1% of actual size) - for very large images
        self.max_zoom_factor = 10.0 # Maximum zoom level (1000% of actual size)
        self.is_fitted_to_window = True  # Flag to control fit-to-window on resize
        self.pan_offset = QPoint(0, 0)  # Current pan offset
        self.last_mouse_pos = None  # Last position for panning
        self.is_panning = False # Add this line to initialize is_panning
        self.image_data = None # Initialize image_data
        self.mouse_over_image = False  # 跟踪鼠标是否在图片区域
        self.mouse_in_nav_zone = False  # 鼠标是否在任何导航区域内
        self.buttons_have_focus = False  # 按钮是否有焦点（被悬停或点击）
        self.nav_zone_width = 120  # 导航区域宽度（像素）
        self.current_image_path = None  # 当前图片路径
        
        # Performance optimization: cache scaled pixmaps
        self.scaled_pixmap_cache = {}
        self.max_cache_size = 5  # Maximum number of cached scales

        self.setMouseTracking(True)  # Enable mouse tracking
        self.setCursor(Qt.OpenHandCursor) # Default cursor for panning
        self.setFocusPolicy(Qt.StrongFocus)  # 允许接收键盘焦点

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.image_label = QLabel("Select an image to view")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label, stretch=1)

        # Actions for zoom, etc. (connected in MainWindow)
        self.zoom_in_action = QAction(ICONS["zoom-in"], "Zoom In", self)
        self.zoom_out_action = QAction(ICONS["zoom-out"], "Zoom Out", self)
        self.zoom_actual_action = QAction(ICONS["zoom-actual"], "Actual Size (1:1)", self)
        self.fit_to_window_action = QAction(ICONS["fit-to-window"], "Fit to Window", self)
        self.fullscreen_action = QAction(ICONS["fullscreen"], "Fullscreen Image View", self)
        self.fullscreen_action.setShortcut("F11")
        self.fullscreen_action.triggered.connect(self.show_fullscreen)
        
        # 创建浮动导航按钮
        self.create_navigation_buttons()
        
        # 创建缩放百分比显示
        self.create_zoom_indicator()

    def create_navigation_buttons(self):
        """创建浮动的导航按钮"""
        # 上一张按钮
        self.prev_button = QPushButton(self)
        self.prev_button.setIcon(ICONS["arrow-left"])
        self.prev_button.setIconSize(QSize(24, 24))
        self.prev_button.setFixedSize(50, 50)
        self.prev_button.setToolTip("Previous Image")
        self.prev_button.clicked.connect(self.navigate_previous.emit)
        
        # 下一张按钮
        self.next_button = QPushButton(self)
        self.next_button.setIcon(ICONS["arrow-right"])
        self.next_button.setIconSize(QSize(24, 24))
        self.next_button.setFixedSize(50, 50)
        self.next_button.setToolTip("Next Image")
        self.next_button.clicked.connect(self.navigate_next.emit)
        
        # 设置按钮样式 - 统一样式，通过透明度控制可见性
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
        
        # 创建透明度效果
        self.prev_opacity_effect = QGraphicsOpacityEffect()
        self.next_opacity_effect = QGraphicsOpacityEffect()
        
        self.prev_button.setGraphicsEffect(self.prev_opacity_effect)
        self.next_button.setGraphicsEffect(self.next_opacity_effect)
        
        # 创建透明度动画
        self.prev_opacity_animation = QPropertyAnimation(self.prev_opacity_effect, b"opacity")
        self.prev_opacity_animation.setDuration(300)  # 300毫秒动画
        self.prev_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self.next_opacity_animation = QPropertyAnimation(self.next_opacity_effect, b"opacity")
        self.next_opacity_animation.setDuration(300)  # 300毫秒动画
        self.next_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # 设置初始透明度
        self.prev_opacity_effect.setOpacity(0.0)
        self.next_opacity_effect.setOpacity(0.0)
        
        # 连接按钮的鼠标事件
        self.prev_button.enterEvent = self.on_button_enter
        self.prev_button.leaveEvent = self.on_button_leave
        self.next_button.enterEvent = self.on_button_enter
        self.next_button.leaveEvent = self.on_button_leave
        
        # 初始状态隐藏按钮
        self.prev_button.hide()
        self.next_button.hide()

    def create_zoom_indicator(self):
        """创建缩放百分比指示器"""
        # 创建缩放百分比标签
        self.zoom_label = QLabel("100%", self)
        self.zoom_label.setFixedSize(80, 25)  # 增加宽度以适应更长的文字
        self.zoom_label.setAlignment(Qt.AlignCenter)
        
        # 设置样式
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
        
        # 创建透明度效果
        self.zoom_opacity_effect = QGraphicsOpacityEffect()
        self.zoom_label.setGraphicsEffect(self.zoom_opacity_effect)
        
        # 创建透明度动画
        self.zoom_opacity_animation = QPropertyAnimation(self.zoom_opacity_effect, b"opacity")
        self.zoom_opacity_animation.setDuration(300)
        self.zoom_opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # 创建自动隐藏计时器
        self.zoom_hide_timer = QTimer()
        self.zoom_hide_timer.timeout.connect(self.hide_zoom_indicator)
        self.zoom_hide_timer.setSingleShot(True)
        
        # 初始状态隐藏
        self.zoom_opacity_effect.setOpacity(0.0)
        self.zoom_label.hide()

    def update_pixmap_display(self):
        if not self.current_pixmap:
            return

        # Calculate image memory usage
        original_width = self.current_pixmap.width()
        original_height = self.current_pixmap.height()
        image_size_mb = (original_width * original_height * 4) / (1024 * 1024)
        
        # Use the actual zoom factor for display
        actual_scale_factor = self.zoom_factor
        
        # Aggressive memory optimization for large images
        if image_size_mb > 50:  # For images larger than 50MB in memory
            # Calculate maximum safe scale factor - more conservative limits
            max_display_pixels = 25_000_000  # Limit to ~25MP display (roughly 400MB at 4 bytes/pixel)
            current_pixels = original_width * original_height
            
            if current_pixels * (actual_scale_factor ** 2) > max_display_pixels:
                max_scale_factor = (max_display_pixels / current_pixels) ** 0.5
                if actual_scale_factor > max_scale_factor:
                    print(f"Performance optimization: limiting scale {actual_scale_factor:.3f} → {max_scale_factor:.3f}")
                    actual_scale_factor = max_scale_factor

        # Calculate target size
        target_width = int(original_width * actual_scale_factor)
        target_height = int(original_height * actual_scale_factor)
        
        # Ensure minimum size to prevent invisible images
        if target_width < 1:
            target_width = 1
        if target_height < 1:
            target_height = 1
        
        # Check cache first
        cache_key = f"{target_width}x{target_height}"
        if cache_key in self.scaled_pixmap_cache:
            scaled_pixmap = self.scaled_pixmap_cache[cache_key]
        else:
            # Use fast transformation for all scaling to improve performance
            transformation_mode = Qt.FastTransformation if image_size_mb > 200 else Qt.SmoothTransformation
            
            scaled_pixmap = self.current_pixmap.scaled(
                target_width, target_height,
                Qt.KeepAspectRatio, transformation_mode
            )
            
            # Cache the scaled pixmap (with LRU-like management)
            if len(self.scaled_pixmap_cache) >= self.max_cache_size:
                # Remove oldest cache entry
                oldest_key = next(iter(self.scaled_pixmap_cache))
                del self.scaled_pixmap_cache[oldest_key]
            
            self.scaled_pixmap_cache[cache_key] = scaled_pixmap

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
            self.is_fitted_to_window = False
            self.update_pixmap_display()
            self.show_zoom_indicator()  # 显示缩放百分比

    def zoom_out(self):
        new_zoom_factor = self.zoom_factor / 1.25
        dynamic_min_zoom = self.get_dynamic_min_zoom()
        
        if new_zoom_factor >= dynamic_min_zoom:
            self.zoom_factor = new_zoom_factor
            self.is_fitted_to_window = False
            self.update_pixmap_display()
            self.show_zoom_indicator()  # 显示缩放百分比

    def zoom_to_actual_size(self):
        # 计算fit-to-window的缩放比例作为基准
        if self.current_pixmap and self.image_label.width() > 1 and self.image_label.height() > 1:
            label_size = self.image_label.size()
            pixmap_size = self.current_pixmap.size()
            if pixmap_size.width() > 0 and pixmap_size.height() > 0:
                width_scale = label_size.width() / pixmap_size.width()
                height_scale = label_size.height() / pixmap_size.height()
                self.fit_to_window_zoom = min(width_scale, height_scale)  # 保存基准
        
        self.zoom_factor = 1.0
        self.is_fitted_to_window = False
        self.pan_offset = QPoint(0, 0)
        self.update_pixmap_display()
        self.show_zoom_indicator()  # 显示缩放百分比

    def get_dynamic_min_zoom(self):
        """Calculate dynamic minimum zoom based on image size"""
        if not self.current_pixmap:
            return self.min_zoom_factor
            
        image_pixels = self.current_pixmap.width() * self.current_pixmap.height()
        
        if image_pixels > 100_000_000:  # > 100MP
            return 0.005
        elif image_pixels > 50_000_000:  # > 50MP  
            return 0.01
        elif image_pixels > 20_000_000:  # > 20MP
            return 0.02
        elif image_pixels > 10_000_000:  # > 10MP
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
            self.fit_to_window_zoom = self.zoom_factor  # 保存这个比例作为100%基准
            self.is_fitted_to_window = True
            self.pan_offset = QPoint(0, 0)
            self.update_pixmap_display()
            self.show_zoom_indicator()  # 显示缩放百分比

    def set_image(self, image_path, image_data):
        try:
            self.scaled_pixmap_cache.clear()
            self.image_label.setStyleSheet("")
            
            self.current_pixmap = QPixmap(image_path)
            self.current_image_path = image_path  # 保存当前图片路径
            
            if self.current_pixmap.isNull():
                self.show_image_error(image_path, "Failed to load image. File may be corrupted or too large.")
                return
                
            # Check for very large images and show warning
            image_size_mb = (self.current_pixmap.width() * self.current_pixmap.height() * 4) / (1024 * 1024)
            if image_size_mb > 500:
                self.show_image_warning(image_path, f"Very large image ({image_size_mb:.0f}MB in memory). Performance optimization enabled.")
            
            self.image_data = image_data
            self.zoom_factor = 1.0
            self.pan_offset = QPoint(0, 0)
            self.is_fitted_to_window = True
            
            # Auto-fit or center image
            if (self.current_pixmap.width() <= self.image_label.width() and 
                self.current_pixmap.height() <= self.image_label.height()):
                self.zoom_to_actual_size()
            else:
                self.fit_to_window()
            
            self.show_navigation_buttons()
            
        except Exception as e:
            self.show_image_error(image_path, f"Error loading image: {str(e)}")

    def show_image_error(self, image_path, error_message):
        """Display error message when image fails to load"""
        from pathlib import Path
        filename = Path(image_path).name
        error_text = f"Failed to load image: {filename}\n\n{error_message}\n\nTry:\n• Restart the application\n• Check available memory\n• Reduce image size"
        
        self.image_label.setText(error_text)
        self.image_label.setStyleSheet("color: #e74c3c; padding: 20px; font-size: 12pt;")
        self.current_pixmap = None
        self.image_data = None
        self.hide_navigation_buttons()

    def show_image_warning(self, image_path, warning_message):
        """Display warning for large images"""
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
        # 隐藏缩放指示器
        if hasattr(self, 'zoom_label'):
            self.zoom_label.hide()

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
        # 更新导航按钮位置
        self.update_navigation_buttons_position()
        # 更新缩放指示器位置
        if hasattr(self, 'zoom_label'):
            self.update_zoom_indicator_position()

    def enterEvent(self, event):
        """鼠标进入图片查看器区域"""
        super().enterEvent(event)
        self.mouse_over_image = True
        # 检查鼠标是否在导航区域
        if self.current_pixmap:
            in_nav_zone = self.check_mouse_in_nav_zones(event.pos())
            self.mouse_in_nav_zone = in_nav_zone
            self.check_and_update_button_visibility()
            
    def leaveEvent(self, event):
        """鼠标离开图片查看器区域"""
        super().leaveEvent(event)
        self.mouse_over_image = False
        self.mouse_in_nav_zone = False
        if self.current_pixmap:
            self.check_and_update_button_visibility()
            
    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        # 处理平移功能
        if event.buttons() == Qt.LeftButton and self.is_panning:
            delta = event.pos() - self.last_mouse_pos
            self.pan_offset += delta
            self.constrain_pan_offset()
            self.last_mouse_pos = event.pos()
            self.update_pixmap_display()
            return
            
        # 检查鼠标是否在导航区域
        if self.current_pixmap:
            in_nav_zone = self.check_mouse_in_nav_zones(event.pos())
            
            # 只有当状态改变时才更新按钮可见性
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

    def update_navigation_buttons_position(self):
        """更新导航按钮的位置"""
        if not self.current_pixmap:
            return
            
        # 计算按钮位置
        button_margin = 20
        button_y = (self.height() - self.prev_button.height()) // 2
        
        # 上一张按钮位置（左侧）
        prev_x = button_margin
        self.prev_button.move(prev_x, button_y)
        
        # 下一张按钮位置（右侧）
        next_x = self.width() - self.next_button.width() - button_margin
        self.next_button.move(next_x, button_y)
        
    def show_navigation_buttons(self):
        """显示导航按钮"""
        if self.current_pixmap:
            self.prev_button.show()
            self.next_button.show()
            self.update_navigation_buttons_position()
            # 初始状态隐藏按钮，等待鼠标移动触发
            self.check_and_update_button_visibility()
            
    def hide_navigation_buttons(self):
        """隐藏导航按钮"""
        self.prev_button.hide()
        self.next_button.hide()
        
    def set_navigation_enabled(self, prev_enabled, next_enabled):
        """设置导航按钮的启用状态"""
        self.prev_button.setEnabled(prev_enabled)
        self.next_button.setEnabled(next_enabled)

    def update_navigation_buttons_visibility(self, show_buttons):
        """更新导航按钮的可见性状态 - 两个按钮一起显示/隐藏"""
        target_opacity = 1.0 if show_buttons else 0.0
        
        # 两个按钮同时设置相同的透明度
        self.prev_opacity_animation.setEndValue(target_opacity)
        self.next_opacity_animation.setEndValue(target_opacity)
        
        # 启动动画
        self.prev_opacity_animation.start()
        self.next_opacity_animation.start()

    def check_mouse_in_nav_zones(self, pos):
        """检查鼠标位置是否在任何导航区域内（包括按钮区域）"""
        if not self.current_pixmap:
            return False
            
        # 获取widget的尺寸
        widget_width = self.width()
        widget_height = self.height()
        
        # 定义左右导航区域（稍微扩大以包含按钮）
        extended_width = self.nav_zone_width + 30  # 额外增加30像素以包含按钮
        left_zone = QRect(0, 0, extended_width, widget_height)
        right_zone = QRect(widget_width - extended_width, 0, extended_width, widget_height)
        
        # 检查鼠标是否在任何导航区域内
        in_any_nav_zone = left_zone.contains(pos) or right_zone.contains(pos)
        
        return in_any_nav_zone

    def paintEvent(self, event):
        """绘制事件 - 可选显示导航区域调试边框"""
        super().paintEvent(event)
        
        # 调试模式：绘制导航区域边框
        if hasattr(self, 'show_nav_zones') and self.show_nav_zones and self.current_pixmap:
            painter = QPainter(self)
            painter.setPen(Qt.red)
            painter.setBrush(Qt.transparent)
            
            # 绘制左侧导航区域
            left_zone = QRect(0, 0, self.nav_zone_width, self.height())
            painter.drawRect(left_zone)
            
            # 绘制右侧导航区域  
            right_zone = QRect(self.width() - self.nav_zone_width, 0, self.nav_zone_width, self.height())
            painter.drawRect(right_zone)
            
            # 在中央显示提示文本
            painter.setPen(Qt.yellow)
            painter.drawText(self.width()//2 - 100, self.height()//2, "Navigation zones active")
            
            painter.end()
            
    def toggle_navigation_zone_debug(self, show=None):
        """切换导航区域调试显示"""
        if show is None:
            self.show_nav_zones = not getattr(self, 'show_nav_zones', False)
        else:
            self.show_nav_zones = show
        self.update()
        
    def on_button_enter(self, event):
        """按钮鼠标进入事件"""
        self.buttons_have_focus = True
        
    def on_button_leave(self, event):
        """按钮鼠标离开事件"""
        self.buttons_have_focus = False
        # 检查是否需要隐藏按钮
        self.check_and_update_button_visibility()
        
    def should_show_buttons(self):
        """判断是否应该显示按钮"""
        return self.mouse_in_nav_zone or self.buttons_have_focus
        
    def check_and_update_button_visibility(self):
        """检查并更新按钮可见性"""
        should_show = self.should_show_buttons()
        current_opacity = self.prev_opacity_effect.opacity()
        
        # 只有当状态真正需要改变时才更新
        if (should_show and current_opacity < 1.0) or (not should_show and current_opacity > 0.0):
            self.update_navigation_buttons_visibility(should_show)

    def show_fullscreen(self):
        """显示全屏图片查看器"""
        if self.current_image_path and self.current_pixmap:
            print(f"显示全屏图片: {self.current_image_path}")  # 调试信息
            # 直接让主窗口全屏，而不是创建新窗口
            main_window = self.window()
            if not main_window.isFullScreen():
                # 进入全屏前调整图片显示
                self.fit_to_window()
                main_window.showFullScreen()
                # 全屏后再次调整图片适应
                QTimer.singleShot(100, self.fit_to_window)
            else:
                main_window.showNormal()
                # 退出全屏后调整图片显示
                QTimer.singleShot(100, self.fit_to_window)
        else:
            print(f"无法显示全屏: current_image_path={self.current_image_path}, current_pixmap={bool(self.current_pixmap)}")  # 调试信息

    def show_zoom_indicator(self):
        """显示缩放百分比指示器"""
        if not self.current_pixmap:
            return
            
        # 计算基于fit-to-window的缩放百分比
        if self.fit_to_window_zoom > 0:
            zoom_percent = int((self.zoom_factor / self.fit_to_window_zoom) * 100)
        else:
            zoom_percent = int(self.zoom_factor * 100)
        
        # 添加状态指示
        if abs(self.zoom_factor - self.fit_to_window_zoom) < 0.01:
            # fit to window状态
            display_text = "100%"
        elif abs(self.zoom_factor - 1.0) < 0.01:
            # 实际大小状态
            actual_percent = int((1.0 / self.fit_to_window_zoom) * 100) if self.fit_to_window_zoom > 0 else 100
            display_text = f"{actual_percent}%"
        else:
            # 其他缩放状态
            display_text = f"{zoom_percent}%"
            
        self.zoom_label.setText(display_text)
        
        # 更新位置
        self.update_zoom_indicator_position()
        
        # 显示指示器
        self.zoom_label.show()
        self.zoom_opacity_animation.setEndValue(0.9)
        self.zoom_opacity_animation.start()
        
        # 设置自动隐藏计时器
        self.zoom_hide_timer.stop()
        self.zoom_hide_timer.start(1500)  # 1.5秒后隐藏
        
    def hide_zoom_indicator(self):
        """隐藏缩放百分比指示器"""
        self.zoom_opacity_animation.setEndValue(0.0)
        self.zoom_opacity_animation.start()
        
    def update_zoom_indicator_position(self):
        """更新缩放指示器的位置"""
        if not self.current_pixmap:
            return
            
        # 放置在右上角
        margin = 15
        x = self.width() - self.zoom_label.width() - margin
        y = margin
        self.zoom_label.move(x, y)

    def mouseDoubleClickEvent(self, event):
        """双击事件 - 也可以触发全屏"""
        if event.button() == Qt.LeftButton:
            print("双击检测到，尝试全屏")  # 调试信息
            self.show_fullscreen()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """处理键盘事件"""
        if event.key() == Qt.Key_F11:
            self.show_fullscreen()
        else:
            super().keyPressEvent(event)
