
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QMessageBox, QStatusBar, QFileDialog, QSplitter, QInputDialog

from .widgets.folder_selection_dialog import FolderSelectionDialog

from .config import ICONS
from .widgets.image_viewer import ImageViewer
from .widgets.thumbnail_gallery import ThumbnailGallery

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Manager")
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        self.setup_ui()
        self.setup_connections()
        self.load_thumbnails()

    def setup_ui(self):
        # --- Menu Bar ---
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        self.import_action = QAction(ICONS["import"], "Import Images...", self)
        file_menu.addAction(self.import_action)
        self.import_folder_action = QAction(ICONS["import"], "Import Folder...", self)
        file_menu.addAction(self.import_folder_action)

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
        toolbar.addSeparator()
        
        toolbar.addAction(self.image_viewer.zoom_out_action)
        toolbar.addAction(self.image_viewer.zoom_in_action)
        toolbar.addAction(self.image_viewer.zoom_actual_action)
        toolbar.addAction(self.image_viewer.fit_to_window_action)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
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

    def on_image_selected(self, image_data):
        if image_data:
            self.image_viewer.set_image(image_data["library_path"], image_data)
            details = (
                f"<b>Name:</b> {image_data['original_filename']}<br>"
                f"<b>Path:</b> {image_data['library_path']}<br>"
                f"<b>Size:</b> {image_data['size_bytes'] / (1024 * 1024):.2f} MB<br>"
                f"<b>Dimensions:</b> {image_data['width']}x{image_data['height']}"
            )
            self.image_details_label.setText(details)
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
