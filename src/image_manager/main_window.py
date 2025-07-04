from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QMessageBox, QStatusBar, QFileDialog, QSplitter, QInputDialog, QComboBox, QLineEdit, QProgressBar # Added QProgressBar

import uuid # Added for upscale_image_dialog
import time # Added for upscale_image_dialog
from pathlib import Path # Added for path operations

from .widgets.folder_selection_dialog import FolderSelectionDialog

from .config import LIBRARY_DIR, THUMBNAIL_SIZE, THUMBNAIL_DIR # Import LIBRARY_DIR, THUMBNAIL_SIZE, THUMBNAIL_DIR
from .config import ICONS
from .widgets.image_viewer import ImageViewer
from .widgets.thumbnail_gallery import ThumbnailGallery
from . import image_utils # Added for upscale functionality

from PySide6.QtCore import QThread, Signal # Import QThread and Signal

class UpscaleThread(QThread):
    finished = Signal(object, str) # Signal to emit when upscaling is done (upscaled_pil_image, original_path_str)
    error = Signal(str) # Signal to emit on error
    progress = Signal(str) # Signal to emit progress messages
    upscale_progress = Signal(int) # New signal for progress bar (0-100)

    def __init__(self, image_path, model_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.model_path = model_path

    def run(self):
        try:
            self.progress.emit("Upscaling image... This may take a while.")
            # Scale factor will be auto-detected from model name
            upscaled_pil_image = image_utils.upscale_image(
                self.image_path, 
                self.model_path, 
                progress_callback=self.upscale_progress.emit
            )
            if upscaled_pil_image:
                self.finished.emit(upscaled_pil_image, self.image_path)
            else:
                self.error.emit("Upscaling failed.")
        except Exception as e:
            self.error.emit(f"An error occurred during upscaling: {e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Manager")
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        self.setup_ui()
        self.setup_connections()
        self.load_thumbnails()
        self.load_upscale_models() # Load upscale models on startup

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
        left_panel_widget = QWidget()
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.setSpacing(8)

        self.thumbnail_gallery = ThumbnailGallery()
        left_panel_layout.addWidget(self.thumbnail_gallery)
        left_panel_widget.setFixedWidth(330) # Fixed width for two columns (2 * 138 + 2 * 9 for layout margins)
        main_layout.addWidget(left_panel_widget)

        # --- Right Panel (Image Viewer and Details) ---
        right_panel_widget = QWidget() # Create a widget to hold the right panel layout
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(8, 8, 8, 8) # Add some margin inside the right panel
        right_panel_layout.setSpacing(8) # Add spacing between widgets

        self.image_viewer = ImageViewer()
        right_panel_layout.addWidget(self.image_viewer, stretch=1)

        self.image_details_label = QLabel("Image details will be shown here.")
        self.image_details_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image_details_label.setWordWrap(True)
        right_panel_layout.addWidget(self.image_details_label)
        
        main_layout.addWidget(right_panel_widget, stretch=1) # Add the right panel widget to the main layout, stretching to fill space

        # --- Toolbar ---
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.import_folder_action)
        toolbar.addAction(self.new_category_action) # Add new category action to toolbar
        toolbar.addSeparator()
        
        # Upscale Model Selection
        self.upscale_model_combo = QComboBox(self)
        self.upscale_model_combo.setToolTip("Select RealESRGAN model (scale factor auto-detected)")
        toolbar.addWidget(self.upscale_model_combo)

        self.upscale_action = QAction(ICONS["upscale"], "Upscale Image", self) # New action for upscale
        toolbar.addAction(self.upscale_action)
        toolbar.addSeparator()

        toolbar.addAction(self.image_viewer.zoom_out_action)
        toolbar.addAction(self.image_viewer.zoom_in_action)
        toolbar.addAction(self.image_viewer.zoom_actual_action)
        toolbar.addAction(self.image_viewer.fit_to_window_action)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        
        # Add file name label for upscaling progress
        self.upscale_file_label = QLabel("")
        self.upscale_file_label.hide()
        self.status_bar.addPermanentWidget(self.upscale_file_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")  # Only show percentage
        self.progress_bar.hide() # Hide initially
        self.status_bar.addPermanentWidget(self.progress_bar)
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

    def on_image_selected(self, image_data):
        # Reset progress bar and file label when selecting a new image
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.upscale_file_label.setText("")
        self.upscale_file_label.hide()
        
        if image_data:
            self.image_viewer.set_image(image_data["library_path"], image_data)
            details = (
                f"<b>Name:</b> {image_data['original_filename']}<br>"
                f"<b>Path:</b> {image_data['library_path']}<br>"
                f"<b>Size:</b> {image_data['size_bytes'] / (1024 * 1024):.2f} MB<br>"
                f"<b>Dimensions:</b> {image_data['width']}x{image_data['height']}"
            )
            self.image_details_label.setText(details)
            # 更新导航按钮状态
            self.update_navigation_buttons_state()
        else:
            self.image_viewer.clear_image()
            self.image_details_label.setText("Image details will be shown here.")

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
        # 更新导航按钮状态
        self.update_navigation_buttons_state()

    def update_status_bar(self):
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
        available_models = image_utils.get_available_upscale_models()
        if not available_models:
            self.upscale_model_combo.addItem("No models found")
            self.upscale_action.setEnabled(False)
            return

        default_model_index = -1
        for i, (model_name, model_path) in enumerate(available_models):
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

    def upscale_image_dialog(self):
        current_image_data = self.image_viewer.image_data
        if not current_image_data:
            self.status_bar.showMessage("No image selected for upscaling.", 3000)
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
            
            selected_model_path = self.upscale_model_combo.currentData() # Get the full path stored in item data
            
            # Auto-detect scale factor from model name
            scale_factor = image_utils.get_model_scale_factor(selected_model_path)
            
            print(f"Using scale factor: {scale_factor}")
            print(f"Using model: {selected_model_path}")

            # Set file name label and progress bar with original filename from metadata
            original_filename = current_image_data.get("original_filename", original_path.name)
            self.upscale_file_label.setText(f"Upscaling {original_filename}")
            self.upscale_file_label.show()
            self.progress_bar.setValue(0)
            self.progress_bar.show()

            self.upscale_thread = UpscaleThread(str(original_path), selected_model_path)
            self.upscale_thread.finished.connect(self.on_upscale_finished)
            self.upscale_thread.error.connect(self.on_upscale_error)
            self.upscale_thread.progress.connect(self.status_bar.showMessage)
            self.upscale_thread.upscale_progress.connect(self.progress_bar.setValue) # Connect progress signal
            
            self.upscale_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during upscaling: {e}")
            self.status_bar.showMessage("Upscaling failed.", 3000)
            self.progress_bar.setValue(0) # Reset progress bar on error
            self.upscale_file_label.setText("Error")
            # Hide progress bar and label after a short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: (self.progress_bar.hide(), self.upscale_file_label.hide()))

    def on_upscale_finished(self, upscaled_pil_image, original_path_str):
        # Ensure progress bar reaches 100% and shows completion
        self.progress_bar.setValue(100)
        original_path = Path(original_path_str)
        current_image_data = self.image_viewer.image_data # Get current image data
        
        # Show completion with original filename from metadata
        original_filename = current_image_data.get("original_filename", original_path.name)
        self.upscale_file_label.setText(f"Completed: {original_filename}")
        
        # Keep progress bar and label visible to show completion status
        # They will be hidden when user selects another image

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
            
            # Delay thumbnail refresh to keep completion status visible
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self.thumbnail_gallery.load_thumbnails(self.thumbnail_gallery.current_folder))
        else:
            self.status_bar.showMessage("Upscaling failed.", 3000)

    def on_upscale_error(self, message):
        self.progress_bar.setValue(0) # Reset progress bar on error
        self.upscale_file_label.setText("Error")
        # Hide progress bar and label after a short delay
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: (self.progress_bar.hide(), self.upscale_file_label.hide()))
        
        QMessageBox.critical(self, "Error", message)
        self.status_bar.showMessage("Upscaling failed.", 3000)

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
            # 没有图片，禁用所有导航按钮
            self.image_viewer.set_navigation_enabled(False, False)
            return
            
        # 根据当前位置设置按钮状态
        prev_enabled = current_index > 0
        next_enabled = current_index < len(image_list) - 1
        
        self.image_viewer.set_navigation_enabled(prev_enabled, next_enabled)

    def keyPressEvent(self, event):
        """处理键盘事件"""
        if event.key() == Qt.Key_Left:
            self.navigate_to_previous_image()
        elif event.key() == Qt.Key_Right:
            self.navigate_to_next_image()
        elif event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            # Ctrl+D 切换导航区域调试模式
            self.image_viewer.toggle_navigation_zone_debug()
            debug_status = "ON" if getattr(self.image_viewer, 'show_nav_zones', False) else "OFF"
            self.status_bar.showMessage(f"Navigation zone debug mode: {debug_status}", 3000)
        else:
            super().keyPressEvent(event)
