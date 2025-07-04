from PySide6.QtCore import Qt, QSize, Signal, QPoint, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QAction, QPainter, QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect

from ..config import ICONS

class ImageViewer(QWidget):
    # 添加导航信号
    navigate_previous = Signal()
    navigate_next = Signal()
    
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
        self.mouse_over_image = False  # 跟踪鼠标是否在图片区域
        self.mouse_in_nav_zone = False  # 鼠标是否在任何导航区域内
        self.buttons_have_focus = False  # 按钮是否有焦点（被悬停或点击）
        self.nav_zone_width = 120  # 导航区域宽度（像素）

        self.setMouseTracking(True)  # Enable mouse tracking
        self.setCursor(Qt.OpenHandCursor) # Default cursor for panning

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
        
        # 创建浮动导航按钮
        self.create_navigation_buttons()

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
        
        # 显示导航按钮
        self.show_navigation_buttons()

    def clear_image(self):
        self.image_label.clear()
        self.image_label.setText("Select an image to view")
        self.current_pixmap = None
        self.image_data = None
        # 隐藏导航按钮
        self.hide_navigation_buttons()

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
