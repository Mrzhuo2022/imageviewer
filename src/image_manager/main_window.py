import logging
import re
import uuid
import time
from pathlib import Path

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                              QLabel, QMessageBox, QStatusBar, QFileDialog, 
                              QInputDialog, QComboBox, QProgressBar, QDialog)

from .widgets.folder_selection_dialog import FolderSelectionDialog
from .widgets.compression_dialog import CompressionDialog
from .config import LIBRARY_DIR, THUMBNAIL_SIZE, THUMBNAIL_DIR, ICONS
from .widgets.image_viewer import ImageViewer
from .widgets.thumbnail_gallery import ThumbnailGallery
from . import image_utils

class LogEmitter(logging.Handler, QThread):
    log_signal = Signal(str)

    def __init__(self):
        super().__init__()
        QThread.__init__(self)
        self.setFormatter(logging.Formatter('%(message)s')) # Only care about the message

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

class UpscaleThread(QThread):
    finished = Signal(object, str) # Signal to emit when upscaling is done (upscaled_pil_image, original_path_str)
    error = Signal(str) # Signal to emit on error
    progress = Signal(str) # Signal to emit progress messages
    upscale_progress = Signal(int) # Signal for progress bar (0-100)
    status_update = Signal(str) # Signal for status updates

    def __init__(self, image_path, model_path, max_output_size=None, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.model_path = model_path
        self.max_output_size = max_output_size

    def run(self):
        try:
            self.status_update.emit("Starting image upscaling...")
            self.progress.emit("Upscaling image... This may take a while.")
            
            # Custom progress callback that emits both signals
            def progress_callback(value):
                self.upscale_progress.emit(value)
                if value == 100:
                    self.status_update.emit("Upscaling completed!")
                
            # Scale factor will be auto-detected from model name
            upscaled_pil_image = image_utils.upscale_image(
                self.image_path, 
                self.model_path, 
                progress_callback=progress_callback,
                max_output_size=self.max_output_size
            )
            
            if upscaled_pil_image:
                self.finished.emit(upscaled_pil_image, self.image_path)
            else:
                self.error.emit("Upscaling failed.")
                
        except Exception as e:
            import traceback
            error_msg = f"An error occurred during upscaling: {e}"
            print(f"Error: {error_msg}")
            print(f"Details: {traceback.format_exc()}")
            self.error.emit(error_msg)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Manager")
        self.resize(1000, 700)  # Reduced from 1400x900 to 1000x700
        self.setMinimumSize(800, 600)
        self.setAcceptDrops(True)
        
        # Track upscaling status
        self.is_upscaling = False
        self.upscale_thread = None
        self.upscale_completed_recently = False  # Track if upscaling just completed
        self.upscale_start_time = None  # Track start time for duration calculation
        self.has_tiles = False  # Track if current upscaling uses tiling
        
        # UI state
        self.left_panel_visible = True  # 左侧面板是否可见
        self.image_details_visible = True  # 图片详细信息是否可见

        self.setup_ui()
        self.setup_connections()
        self.load_thumbnails()
        self.load_upscale_models() # Load upscale models on startup

        # Setup logging for RealESRGAN progress
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.handle_log_message)
        logging.getLogger().addHandler(self.log_emitter)
        logging.getLogger().setLevel(logging.INFO) # Ensure INFO level messages are captured

    def setup_ui(self):
        # --- Menu Bar ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        self.import_action = QAction(ICONS["import"], "Import Images...", self)
        file_menu.addAction(self.import_action)
        self.import_folder_action = QAction(ICONS["import"], "Import Folder...", self)
        file_menu.addAction(self.import_folder_action)

        self.new_category_action = QAction(ICONS["add"], "New Category...", self) # New action for creating category
        file_menu.addAction(self.new_category_action)

        # --- Main Widget and Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8) # Add some margin around the main layout
        main_layout.setSpacing(8) # Add spacing between widgets

        # --- Left Panel (Category Buttons and Thumbnail Gallery) ---
        self.left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(self.left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(8)

        self.thumbnail_gallery = ThumbnailGallery()
        left_panel_layout.addWidget(self.thumbnail_gallery)
        # Set size constraints for left panel
        self.left_panel_widget.setFixedWidth(330) # Fixed width for two columns (2 * 138 + 2 * 9 for layout margins)
        self.left_panel_widget.setMinimumHeight(400) # Ensure minimum height
        main_layout.addWidget(self.left_panel_widget)

        # --- Right Panel (Image Viewer and Details) ---
        right_panel_widget = QWidget() # Create a widget to hold the right panel layout
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(8, 8, 8, 8) # Add some margin inside the right panel
        right_panel_layout.setSpacing(8) # Add spacing between widgets
        
        # Set size constraints for right panel
        right_panel_widget.setMinimumWidth(400) # Ensure minimum width
        right_panel_widget.setMinimumHeight(400) # Ensure minimum height

        self.image_viewer = ImageViewer()
        right_panel_layout.addWidget(self.image_viewer, stretch=1)

        # --- View Menu (after image_viewer is created) ---
        view_menu = menu_bar.addMenu("&View")
        
        # 创建切换面板的Action
        self.toggle_panel_action = QAction(ICONS["panel-hide"], "Hide Sidebar", self)
        self.toggle_panel_action.setShortcut("F9")
        self.toggle_panel_action.triggered.connect(self.toggle_left_panel)
        view_menu.addAction(self.toggle_panel_action)
        
        # 创建切换图片详细信息的Action
        self.toggle_info_action = QAction(ICONS["info"], "Hide Image Details", self)
        self.toggle_info_action.setShortcut("F10")
        self.toggle_info_action.triggered.connect(self.toggle_image_details)
        view_menu.addAction(self.toggle_info_action)
        
        view_menu.addSeparator()
        view_menu.addAction(self.image_viewer.fullscreen_action)
        
        # 将Action添加到主窗口以确保快捷键工作
        self.addAction(self.toggle_panel_action)
        self.addAction(self.toggle_info_action)
        self.addAction(self.image_viewer.fullscreen_action)

        # Image details label with size constraints
        self.image_details_label = QLabel("Image details will be shown here.")
        self.image_details_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image_details_label.setWordWrap(True)
        # Set maximum height to prevent the label from pushing the status bar off-screen
        self.image_details_label.setMaximumHeight(120)
        self.image_details_label.setMinimumHeight(80)
        # Add scroll area capability for long text
        self.image_details_label.setStyleSheet("""
            QLabel {
                background-color: #34495e;
                border: 1px solid #4e6a85;
                border-radius: 4px;
                padding: 8px;
                margin: 4px 0px;
            }
        """)
        right_panel_layout.addWidget(self.image_details_label)
        
        main_layout.addWidget(right_panel_widget, stretch=1) # Add the right panel widget to the main layout, stretching to fill space

        # --- Toolbar ---
        toolbar = self.addToolBar("Main Toolbar")
        
        # 视图控制
        toolbar.addAction(self.toggle_panel_action)
        toolbar.addAction(self.toggle_info_action)
        toolbar.addSeparator()
        
        # 文件操作
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.import_folder_action)
        toolbar.addAction(self.new_category_action) # Add new category action to toolbar
        toolbar.addSeparator()
        
        # Upscale Model Selection
        self.upscale_model_combo = QComboBox(self)
        self.upscale_model_combo.setToolTip("Select RealESRGAN model (scale factor auto-detected)")
        toolbar.addWidget(self.upscale_model_combo)
        
        # Output Size Limit Selection
        self.output_size_combo = QComboBox(self)
        self.output_size_combo.setToolTip("Limit output resolution for better performance")
        self.output_size_combo.addItem("No Limit", None)
        self.output_size_combo.addItem("4K (3840x2160)", (3840, 2160))
        self.output_size_combo.addItem("2K (2560x1440)", (2560, 1440))
        self.output_size_combo.addItem("1080p (1920x1080)", (1920, 1080))
        self.output_size_combo.addItem("720p (1280x720)", (1280, 720))
        self.output_size_combo.setCurrentIndex(1)  # Default to 4K
        toolbar.addWidget(self.output_size_combo)

        self.upscale_action = QAction(ICONS["upscale"], "Upscale Image", self) # New action for upscale
        toolbar.addAction(self.upscale_action)
        
        self.compress_action = QAction(ICONS["compress"], "Compress Image", self) # New action for compress
        toolbar.addAction(self.compress_action)
        toolbar.addSeparator()

        toolbar.addAction(self.image_viewer.zoom_out_action)
        toolbar.addAction(self.image_viewer.zoom_in_action)
        toolbar.addAction(self.image_viewer.zoom_actual_action)
        toolbar.addAction(self.image_viewer.fit_to_window_action)
        toolbar.addSeparator()
        toolbar.addAction(self.image_viewer.fullscreen_action)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        # Ensure status bar has minimum height and is always visible
        self.status_bar.setMinimumHeight(28)
        self.status_bar.setMaximumHeight(35)
        self.status_bar.setSizeGripEnabled(True)  # Allow window resizing from status bar
        
        # Create a container widget for progress-related widgets
        self.progress_container = QWidget()
        progress_layout = QHBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(8, 2, 8, 2)
        progress_layout.setSpacing(12)
        
        # Add file name label for upscaling progress
        self.upscale_file_label = QLabel("")
        self.upscale_file_label.setStyleSheet("color: #3498db; font-weight: 600;")
        self.upscale_file_label.hide()
        progress_layout.addWidget(self.upscale_file_label)
        
        # Add progress bar with improved sizing
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setMinimumHeight(18)
        self.progress_bar.setMaximumHeight(20)
        self.progress_bar.hide()
        progress_layout.addWidget(self.progress_bar)

        # Add detailed progress label
        self.detailed_progress_label = QLabel("")
        self.detailed_progress_label.setStyleSheet("color: #95a5a6; font-style: italic;")
        self.detailed_progress_label.setMinimumWidth(150)
        self.detailed_progress_label.setMaximumWidth(250)
        self.detailed_progress_label.hide()
        progress_layout.addWidget(self.detailed_progress_label)
        
        # Add spacer to push progress widgets to the right
        progress_layout.addStretch()
        
        # Set fixed minimum size for the container to maintain layout stability
        self.progress_container.setMinimumHeight(24)
        self.progress_container.setMaximumHeight(30)
        
        # Add the progress container to status bar (always visible container)
        self.status_bar.addPermanentWidget(self.progress_container)
        
        # Add a default status message
        self.status_bar.showMessage("Ready - Select an image to start")
        
        self.setStatusBar(self.status_bar)

    def setup_connections(self):
        self.import_action.triggered.connect(self.import_images_dialog)
        self.import_folder_action.triggered.connect(self.import_folder_dialog)
        self.thumbnail_gallery.image_selected.connect(self.on_image_selected)
        self.thumbnail_gallery.status_message.connect(self.status_bar.showMessage)
        self.thumbnail_gallery.library_updated.connect(self.update_status_bar)

        # Connect ImageViewer actions
        self.image_viewer.zoom_in_action.triggered.connect(self.image_viewer.zoom_in)
        self.image_viewer.zoom_out_action.triggered.connect(self.image_viewer.zoom_out)
        self.image_viewer.zoom_actual_action.triggered.connect(self.image_viewer.zoom_to_actual_size)
        self.image_viewer.fit_to_window_action.triggered.connect(self.image_viewer.fit_to_window)
        
        # Connect navigation signals
        self.image_viewer.navigate_previous.connect(self.navigate_to_previous_image)
        self.image_viewer.navigate_next.connect(self.navigate_to_next_image)

        self.new_category_action.triggered.connect(self.create_new_category_dialog) # Connect new action
        self.upscale_action.triggered.connect(self.upscale_image_dialog) # Connect upscale action
        self.compress_action.triggered.connect(self.compress_image_dialog) # Connect compress action

    def show_progress_widgets(self):
        """显示进度相关的控件"""
        self.progress_bar.show()
        self.upscale_file_label.show()
        
    def hide_progress_widgets(self):
        """隐藏进度相关的控件"""
        self.progress_bar.hide()
        self.upscale_file_label.hide()
        self.detailed_progress_label.hide()

    def on_status_update(self, status_message):
        """处理状态更新信号"""
        self.status_bar.showMessage(status_message, 3000)

    def on_image_selected(self, image_data):
        # Only reset progress bar if no upscaling is currently running AND not recently completed
        if not self.is_upscaling and not self.upscale_completed_recently:
            self.progress_bar.setValue(0)
            self.hide_progress_widgets()
        
        if image_data:
            self.image_viewer.set_image(image_data["library_path"], image_data)
            
            # 更新全屏图片查看器的导航状态
            self.update_fullscreen_navigation_state()
            
            # Calculate image memory usage and additional info for display
            try:
                from PIL import Image
                import os
                from datetime import datetime
                
                with Image.open(image_data["library_path"]) as img:
                    memory_mb = (img.width * img.height * 4) / (1024 * 1024)  # 4 bytes per pixel (RGBA)
                    memory_info = f" (~{memory_mb:.0f}MB)"
                    
                    # 获取图片格式
                    format_info = img.format if img.format else "Unknown"
                    
                    # 获取颜色模式
                    mode_info = img.mode if img.mode else "Unknown"
                
                # 获取文件修改时间
                try:
                    mod_time = os.path.getmtime(image_data["library_path"])
                    mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
                except:
                    mod_date = "Unknown"
                    
            except:
                memory_info = ""
                format_info = "Unknown"
                mode_info = "Unknown"
                mod_date = "Unknown"
            
            # 计算纵横比
            try:
                aspect_ratio = image_data['width'] / image_data['height']
                if abs(aspect_ratio - 16/9) < 0.1:
                    ratio_desc = "16:9"
                elif abs(aspect_ratio - 4/3) < 0.1:
                    ratio_desc = "4:3"
                elif abs(aspect_ratio - 1) < 0.1:
                    ratio_desc = "1:1"
                else:
                    ratio_desc = f"{aspect_ratio:.2f}:1"
            except:
                ratio_desc = "Unknown"
            
            details = (
                f"<div style='font-family: monospace; font-size: 9pt;'>"
                f"<b style='color: #3498db;'>📁 {image_data['original_filename']}</b><br>"
                f"<span style='color: #95a5a6;'>📏 {image_data['width']} × {image_data['height']} ({ratio_desc})</span><br>"
                f"<span style='color: #95a5a6;'>💾 {image_data['size_bytes'] / (1024 * 1024):.2f} MB{memory_info}</span><br>"
                f"<span style='color: #95a5a6;'>🎨 {format_info} • {mode_info}</span><br>"
                f"<span style='color: #95a5a6;'>🕐 {mod_date}</span>"
                f"</div>"
            )
            self.image_details_label.setText(details)
            
            # Update status bar with image info
            if not self.is_upscaling and not self.upscale_completed_recently:
                self.status_bar.showMessage(
                    f"Image loaded: {image_data['original_filename']} "
                    f"({image_data['width']}x{image_data['height']})"
                )
            
            # 更新导航按钮状态
            self.update_navigation_buttons_state()
        else:
            self.image_viewer.clear_image()
            self.image_details_label.setText("Image details will be shown here.")
            if not self.is_upscaling and not self.upscale_completed_recently:
                self.status_bar.showMessage("Ready - Select an image to start")

    def import_images_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Images to Import", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if file_paths:
            dialog = FolderSelectionDialog(current_gallery_folder=self.thumbnail_gallery.current_folder, parent=self)
            if dialog.exec():
                target_subfolder = dialog.get_selected_folder()
                self.thumbnail_gallery.process_imported_paths(file_paths, target_subfolder)

    def import_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Import")
        if folder_path:
            dialog = FolderSelectionDialog(current_gallery_folder=self.thumbnail_gallery.current_folder, parent=self)
            if dialog.exec():
                target_subfolder = dialog.get_selected_folder()
                self.thumbnail_gallery.process_imported_folder(folder_path, target_subfolder)

    def load_thumbnails(self):
        self.thumbnail_gallery.load_thumbnails()
        
        self.update_navigation_buttons_state()

    def update_status_bar(self):
        # Show library update message and system memory info
        try:
            import psutil
            memory = psutil.virtual_memory()
            memory_info = f"RAM: {memory.percent:.1f}% used"
            self.status_bar.showMessage(f"Library updated. {memory_info}", 3000)
        except:
            self.status_bar.showMessage("Library updated.", 3000)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.isLocalFile() and url.toLocalFile().lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')) for url in urls):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls if url.isLocalFile() and url.toLocalFile().lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]
        if file_paths:
            # For drag and drop, import to current folder
            self.thumbnail_gallery.process_imported_paths(file_paths, self.thumbnail_gallery.current_folder)

    def create_new_category_dialog(self):
        new_category_name, ok = QInputDialog.getText(self, "New Category", "Enter new category name:")
        if ok and new_category_name:
            sanitized_name = "".join(c for c in new_category_name if c.isalnum() or c in (' ', '-', '_')).strip()
            sanitized_name = sanitized_name.replace(" ", "_")
            if not sanitized_name:
                QMessageBox.warning(self, "Invalid Name", "Sanitized category name is empty. Please use valid characters.")
                return

            new_category_path = LIBRARY_DIR / sanitized_name
            if new_category_path.exists():
                QMessageBox.warning(self, "Category Exists", f"Category '{sanitized_name}' already exists.")
                return
            
            try:
                new_category_path.mkdir(parents=True, exist_ok=True)
                self.status_bar.showMessage(f"Category '{sanitized_name}' created.", 3000)
                self.thumbnail_gallery.load_thumbnails(self.thumbnail_gallery.current_folder) # Reload categories
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create category: {e}")

    def load_upscale_models(self):
        self.upscale_model_combo.clear()
        available_models = image_utils.get_available_models()
        if not available_models:
            self.upscale_model_combo.addItem("No models found")
            self.upscale_action.setEnabled(False)
            return

        default_model_index = -1
        for i, model_info in enumerate(available_models):
            model_name = model_info["name"]
            model_path = model_info["path"]
            # Get scale factor from model name for display
            scale_factor = image_utils.get_model_scale_factor(model_path)
            display_name = f"{model_name} ({scale_factor}x)"
            self.upscale_model_combo.addItem(display_name, model_path) # Store full path as user data
            
            # Set default model to realesrgan-x4plus_anime_6B
            if "realesrgan-x4plus_anime_6b" in model_name.lower():
                default_model_index = i
        
        # Set default selection
        if default_model_index >= 0:
            self.upscale_model_combo.setCurrentIndex(default_model_index)
        
        self.upscale_action.setEnabled(True)


    def handle_log_message(self, message):
        # Print log message to terminal for real-time feedback
        if "compression" in message.lower():
            print(f"Compression: {message}")
        else:
            print(f"Upscaling: {message}")
        
        # Update progress bar based on log content - display English messages in GUI
        if "Starting PyTorch upscaling process" in message:
            self.upscale_start_time = time.time()
            self.has_tiles = False
            self.show_progress_widgets()
            self.update_progress_smoothly(0)
            self.detailed_progress_label.setText("Starting PyTorch upscaling process...")
            self.detailed_progress_label.show()
        elif "CUDA is available" in message:
            self.update_progress_smoothly(3)
            self.detailed_progress_label.setText("CUDA is available, proceeding with GPU acceleration")
        elif "Loading image" in message:
            self.update_progress_smoothly(8)
            self.detailed_progress_label.setText(message)
        elif "Image loaded successfully" in message:
            self.update_progress_smoothly(12)
            self.detailed_progress_label.setText(message)
        elif "Initializing RealESRGANer" in message:
            self.update_progress_smoothly(18)
            self.detailed_progress_label.setText(message)
        elif "RealESRGANer initialized successfully" in message:
            self.update_progress_smoothly(25)
            self.detailed_progress_label.setText(message)
        elif "Starting PyTorch inference" in message:
            self.update_progress_smoothly(30)
            self.detailed_progress_label.setText(message)
        elif "Processing image with AI model" in message:
            if not self.has_tiles:
                self.update_progress_smoothly(35)
            self.detailed_progress_label.setText(message)
        elif "PyTorch inference complete" in message:
            elapsed_time = time.time() - self.upscale_start_time if self.upscale_start_time else 0
            
            if not self.has_tiles:
                self.update_progress_smoothly(85)
            else:
                self.update_progress_smoothly(90)
            
            time_msg = f"PyTorch inference complete in {elapsed_time:.1f}s"
            self.detailed_progress_label.setText(time_msg)
            print(f"Timing: {time_msg}")
        elif "Post-processing and converting image" in message:
            self.update_progress_smoothly(95)
            self.detailed_progress_label.setText(message)
        elif "Image upscaling completed successfully" in message:
            total_elapsed = time.time() - self.upscale_start_time if self.upscale_start_time else 0
            
            self.update_progress_smoothly(100)
            completion_msg = f"Image upscaling completed successfully in {total_elapsed:.1f}s"
            self.detailed_progress_label.setText(completion_msg)
            print(f"Total time: {total_elapsed:.1f}s")
        elif "Cleaning up GPU memory" in message:
            self.detailed_progress_label.setText(message)
        elif "CUDA out of memory" in message:
            self.detailed_progress_label.setText("CUDA out of memory, retrying with tiling...")
        elif "Attempting upscaling with tiling" in message:
            self.has_tiles = True
            self.update_progress_smoothly(32)
            self.detailed_progress_label.setText(message)
        elif "Error during upscaling" in message:
            self.detailed_progress_label.setText(message)
            self.detailed_progress_label.show()
        elif "Initializing PyTorch upsampler" in message:
            if "tile size: 0" in message or "Disabled" in message:
                self.update_progress_smoothly(15)
                self.detailed_progress_label.setText("Initializing upsampler (no tiling)")
            else:
                self.has_tiles = True
                self.update_progress_smoothly(15)
                self.detailed_progress_label.setText("Initializing upsampler (with tiling)")
        
        # Handle tile processing messages
        match = re.search(r"Tile (\d+)/(\d+)", message)
        if match:
            current_tile = int(match.group(1))
            total_tiles = int(match.group(2))
            self.has_tiles = True
            
            min_progress = 35
            max_progress = 85
            
            tile_percentage = (current_tile / total_tiles) * (max_progress - min_progress)
            overall_progress = min_progress + tile_percentage
            
            self.update_progress_smoothly(int(overall_progress))
            
            # Show ETA for tiles
            if self.upscale_start_time and current_tile > 1:
                elapsed = time.time() - self.upscale_start_time
                avg_time_per_tile = elapsed / (current_tile - 1)
                remaining_tiles = total_tiles - current_tile
                eta = avg_time_per_tile * remaining_tiles
                
                tile_msg = f"Tile {current_tile}/{total_tiles} (ETA: {eta:.0f}s)"
                self.detailed_progress_label.setText(tile_msg)
                print(f"Tile progress: {current_tile}/{total_tiles} ({overall_progress:.1f}%) ETA: {eta:.0f}s")
            else:
                self.detailed_progress_label.setText(f"Tile {current_tile}/{total_tiles}")
                print(f"Tile progress: {current_tile}/{total_tiles} ({overall_progress:.1f}%)")
            
            self.detailed_progress_label.show()
        
        # Force GUI update
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()


    def update_progress_smoothly(self, value):
        if self.progress_bar.isHidden():
            self.show_progress_widgets()

        # Stop any existing animation
        if hasattr(self, 'progress_animation') and self.progress_animation.state() == QPropertyAnimation.Running:
            self.progress_animation.stop()

        self.progress_animation = QPropertyAnimation(self.progress_bar, b"value")
        self.progress_animation.setDuration(250) # Animation duration in milliseconds
        self.progress_animation.setStartValue(self.progress_bar.value())
        self.progress_animation.setEndValue(value)
        self.progress_animation.setEasingCurve(QEasingCurve.InOutQuad) # Smooth easing curve
        self.progress_animation.start()

    def upscale_image_dialog(self):
        current_image_data = self.image_viewer.image_data
        if not current_image_data:
            self.status_bar.showMessage("No image selected for upscaling.", 3000)
            return

        # Check if already upscaling
        if self.is_upscaling:
            self.status_bar.showMessage("Upscaling already in progress.", 3000)
            return

        original_path = Path(current_image_data["library_path"])
        if not original_path.exists():
            self.status_bar.showMessage("Selected image file not found.", 3000)
            return

        try:
            selected_model_index = self.upscale_model_combo.currentIndex()
            if selected_model_index == -1:
                QMessageBox.warning(self, "No Model Selected", "Please select an upscale model.")
                return
            
            selected_model_path = self.upscale_model_combo.currentData()
            
            # Get output size limit
            max_output_size = self.output_size_combo.currentData()
            
            # Set upscaling status and clear completion flag
            self.is_upscaling = True
            self.upscale_completed_recently = False
            self.upscale_start_time = None
            self.has_tiles = False
            
            # Stop any existing completion timer
            if hasattr(self, 'completion_timer') and self.completion_timer.isActive():
                self.completion_timer.stop()
            
            original_filename = current_image_data.get("original_filename", original_path.name)
            self.upscale_file_label.setText(f"Upscaling: {original_filename}")
            self.show_progress_widgets()
            self.progress_bar.setValue(0)
            self.detailed_progress_label.setText("Initializing upscaler...")
            self.detailed_progress_label.show()

            self.upscale_thread = UpscaleThread(str(original_path), selected_model_path, max_output_size)
            self.upscale_thread.finished.connect(self.on_upscale_finished)
            self.upscale_thread.error.connect(self.on_upscale_error)
            self.upscale_thread.progress.connect(self.status_bar.showMessage)
            self.upscale_thread.upscale_progress.connect(self.update_progress_smoothly)
            self.upscale_thread.status_update.connect(self.on_status_update)
            
            self.upscale_thread.start()

        except Exception as e:
            self.is_upscaling = False
            QMessageBox.critical(self, "Error", f"An error occurred during upscaling: {e}")
            self.status_bar.showMessage("Upscaling failed.", 3000)
            self.progress_bar.setValue(0)
            self.upscale_file_label.setText("Error")
            self.detailed_progress_label.setText("")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, self.hide_progress_widgets)

    def on_status_update(self, status_message):
        """处理状态更新信号"""
        self.status_bar.showMessage(status_message, 3000)

    def on_upscale_finished(self, upscaled_pil_image, original_path_str):
        # Reset upscaling status and set completed flag
        self.is_upscaling = False
        self.upscale_completed_recently = True
        
        # Ensure progress bar reaches 100% and shows completion
        self.progress_bar.setValue(100)
        original_path = Path(original_path_str)
        current_image_data = self.image_viewer.image_data # Get current image data
        
        # Show completion with original filename from metadata
        original_filename = current_image_data.get("original_filename", original_path.name)
        self.upscale_file_label.setText(f"Completed: {original_filename}")
        
        # Calculate and display total time
        if self.upscale_start_time:
            total_time = time.time() - self.upscale_start_time
            completion_msg = f"Image upscaling completed successfully in {total_time:.1f}s"
            self.detailed_progress_label.setText(completion_msg)
        else:
            self.detailed_progress_label.setText("Image upscaling completed successfully")
        
        self.detailed_progress_label.show()
        
        # Keep progress bar visible for 10 seconds
        from PySide6.QtCore import QTimer
        self.completion_timer = QTimer()
        self.completion_timer.timeout.connect(self.clear_completion_status)
        self.completion_timer.setSingleShot(True)
        self.completion_timer.start(10000)

        if upscaled_pil_image:
            # Generate a new unique ID for the upscaled image
            image_id = str(uuid.uuid4())
            suffix = original_path.suffix.lower()
            
            # Determine paths for the new upscaled image
            target_subfolder = current_image_data.get("subfolder", "")
            target_folder = LIBRARY_DIR / target_subfolder
            target_folder.mkdir(parents=True, exist_ok=True) # Ensure subfolder exists

            # Generate filename based on original image's original_filename
            original_filename = current_image_data.get("original_filename", original_path.name)
            original_stem = Path(original_filename).stem
            original_suffix = Path(original_filename).suffix
            base_name = f"{original_stem}_upscaled"
            upscaled_file_name = image_utils.get_unique_filename(target_folder, base_name, original_suffix)
            upscaled_thumbnail_name = image_utils.get_unique_filename(THUMBNAIL_DIR, base_name, original_suffix)
            
            upscaled_library_path = target_folder / upscaled_file_name
            upscaled_thumbnail_path = THUMBNAIL_DIR / upscaled_thumbnail_name

            # Save the upscaled image
            upscaled_pil_image.save(upscaled_library_path)

            # Create thumbnail for the upscaled image
            upscaled_pil_image.thumbnail(THUMBNAIL_SIZE)
            upscaled_pil_image.save(upscaled_thumbnail_path)

            # Update metadata
            metadata = image_utils.load_metadata()
            metadata[image_id] = {
                "original_filename": upscaled_file_name,  # Use the actual generated filename
                "library_path": str(upscaled_library_path),
                "thumbnail_path": str(upscaled_thumbnail_path),
                "width": upscaled_pil_image.width,
                "height": upscaled_pil_image.height,
                "size_bytes": upscaled_library_path.stat().st_size,
                "subfolder": target_subfolder,
                "timestamp": time.time()
            }
            image_utils.save_metadata(metadata)

            self.status_bar.showMessage("Image upscaled successfully!", 5000)
            
            # Refresh thumbnail gallery after 3 seconds
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self.thumbnail_gallery.load_thumbnails(self.thumbnail_gallery.current_folder))
        else:
            self.status_bar.showMessage("Upscaling failed.", 3000)
            self.detailed_progress_label.setText("Upscaling failed")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, self.detailed_progress_label.hide)

    def clear_completion_status(self):
        """清除完成状态并隐藏进度控件"""
        self.upscale_completed_recently = False
        self.hide_progress_widgets()
        
    def force_clear_progress(self):
        """强制清除进度显示（用户手动操作）"""
        if hasattr(self, 'completion_timer') and self.completion_timer.isActive():
            self.completion_timer.stop()
        self.clear_completion_status()

    def on_upscale_error(self, message):
        self.is_upscaling = False
        self.upscale_completed_recently = False
        
        self.progress_bar.setValue(0)
        self.upscale_file_label.setText("Error")
        
        # Show error message with timing if available
        if self.upscale_start_time:
            error_time = time.time() - self.upscale_start_time
            error_msg = f"Error after {error_time:.1f}s: {message}"
            self.detailed_progress_label.setText(error_msg)
        else:
            self.detailed_progress_label.setText(f"Error: {message}")
        
        self.detailed_progress_label.show()
        
        # Hide progress widgets after delay
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self.hide_progress_widgets)
        
        QMessageBox.critical(self, "Error", message)
        self.status_bar.showMessage("Upscaling failed.", 3000)

    def compress_image_dialog(self):
        """显示图片压缩对话框"""
        current_image_data = self.image_viewer.image_data
        if not current_image_data:
            self.status_bar.showMessage("No image selected for compression.", 3000)
            return

        original_path = Path(current_image_data["library_path"])
        if not original_path.exists():
            self.status_bar.showMessage("Selected image file not found.", 3000)
            return

        try:
            # Show compression dialog
            dialog = CompressionDialog(str(original_path), self)
            if dialog.exec() == QDialog.Accepted:
                settings = dialog.get_compression_settings()
                self.perform_compression(original_path, current_image_data, settings)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open compression dialog: {e}")
            self.status_bar.showMessage("Compression dialog error.", 3000)

    def perform_compression(self, original_path, current_image_data, settings):
        """执行图片压缩"""
        try:
            # Generate output filename
            original_filename = current_image_data.get("original_filename", original_path.name)
            original_stem = Path(original_filename).stem
            
            # Determine output format and extension
            output_format = settings['output_format']
            if output_format == 'JPEG':
                extension = '.jpg'
            elif output_format == 'PNG':
                extension = '.png'
            elif output_format == 'WEBP':
                extension = '.webp'
            else:
                extension = original_path.suffix
                
            # Create output filename
            target_subfolder = current_image_data.get("subfolder", "")
            target_folder = LIBRARY_DIR / target_subfolder
            target_folder.mkdir(parents=True, exist_ok=True)
            
            base_name = f"{original_stem}_compressed"
            compressed_filename = image_utils.get_unique_filename(target_folder, base_name, extension)
            compressed_path = target_folder / compressed_filename
            
            # Show progress
            self.status_bar.showMessage("Compressing image...", 3000)
            
            # Perform compression
            def progress_callback(value):
                # Could add progress bar here if needed
                pass
                
            success = image_utils.save_compressed_image(
                str(original_path), 
                str(compressed_path),
                quality=settings['quality'],
                output_format=settings['output_format'],
                max_size=settings['max_size'],
                progress_callback=progress_callback
            )
            
            if success:
                # Add compressed image to library
                compressed_item = image_utils.add_image_to_library(
                    str(compressed_path), 
                    target_subfolder
                )
                
                if compressed_item:
                    self.status_bar.showMessage(
                        f"Image compressed successfully! Saved as {compressed_filename}", 
                        5000
                    )
                    
                    # Refresh thumbnail gallery
                    QTimer.singleShot(1000, 
                        lambda: self.thumbnail_gallery.load_thumbnails(self.thumbnail_gallery.current_folder)
                    )
                else:
                    self.status_bar.showMessage("Compression completed but failed to add to library.", 3000)
            else:
                self.status_bar.showMessage("Image compression failed.", 3000)
                # Clean up failed compression file
                if compressed_path.exists():
                    compressed_path.unlink()
                    
        except Exception as e:
            QMessageBox.critical(self, "Compression Error", f"An error occurred during compression: {e}")
            self.status_bar.showMessage("Compression failed.", 3000)

    def get_current_image_index(self):
        """获取当前显示图片在图片列表中的索引"""
        if not self.image_viewer.image_data:
            return -1
            
        current_path = self.image_viewer.image_data["library_path"]
        image_list = self.thumbnail_gallery.get_current_image_list()
        
        for i, image_data in enumerate(image_list):
            if image_data["library_path"] == current_path:
                return i
        return -1
        
    def navigate_to_previous_image(self):
        """导航到上一张图片"""
        current_index = self.get_current_image_index()
        if current_index > 0:
            image_list = self.thumbnail_gallery.get_current_image_list()
            prev_image = image_list[current_index - 1]
            self.thumbnail_gallery.select_image_by_data(prev_image)
            
    def navigate_to_next_image(self):
        """导航到下一张图片"""
        current_index = self.get_current_image_index()
        image_list = self.thumbnail_gallery.get_current_image_list()
        if current_index < len(image_list) - 1:
            next_image = image_list[current_index + 1]
            self.thumbnail_gallery.select_image_by_data(next_image)
            
    def update_navigation_buttons_state(self):
        """更新导航按钮的启用状态"""
        current_index = self.get_current_image_index()
        image_list = self.thumbnail_gallery.get_current_image_list()
        
        if current_index == -1 or not image_list:
            self.image_viewer.set_navigation_enabled(False, False)
            return
            
        prev_enabled = current_index > 0
        next_enabled = current_index < len(image_list) - 1
        
        self.image_viewer.set_navigation_enabled(prev_enabled, next_enabled)
        
    def update_fullscreen_navigation_state(self):
        """更新全屏导航状态（别名方法）"""
        self.update_navigation_buttons_state()
        
    def toggle_left_panel(self):
        """切换左侧面板的显示/隐藏"""
        if self.left_panel_visible:
            # 隐藏左侧面板
            self.left_panel_widget.hide()
            self.left_panel_visible = False
            self.toggle_panel_action.setIcon(ICONS["panel-show"])
            self.toggle_panel_action.setText("Show Sidebar")
        else:
            # 显示左侧面板
            self.left_panel_widget.show()
            self.left_panel_visible = True
            self.toggle_panel_action.setIcon(ICONS["panel-hide"])
            self.toggle_panel_action.setText("Hide Sidebar")
            
    def toggle_image_details(self):
        """切换图片详细信息的显示/隐藏"""
        if self.image_details_visible:
            # 隐藏图片详细信息
            self.image_details_label.hide()
            self.image_details_visible = False
            self.toggle_info_action.setText("Show Image Details")
        else:
            # 显示图片详细信息
            self.image_details_label.show()
            self.image_details_visible = True
            self.toggle_info_action.setText("Hide Image Details")

    def keyPressEvent(self, event):
        """处理键盘事件"""
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            # ESC键退出全屏
            self.showNormal()
        elif event.key() == Qt.Key_Left:
            self.navigate_to_previous_image()
        elif event.key() == Qt.Key_Right:
            self.navigate_to_next_image()
        elif event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            
            self.image_viewer.toggle_navigation_zone_debug()
            debug_status = "ON" if getattr(self.image_viewer, 'show_nav_zones', False) else "OFF"
            self.status_bar.showMessage(f"Navigation zone debug mode: {debug_status}", 3000)
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """处理窗口大小变化事件，确保状态栏始终可见"""
        super().resizeEvent(event)
        
        # Ensure minimum window height to keep status bar visible
        min_height = 600  # Minimum height to show all UI elements
        if self.height() < min_height:
            self.resize(self.width(), min_height)
        
        # Ensure minimum window width
        min_width = 800
        if self.width() < min_width:
            self.resize(min_width, self.height())
