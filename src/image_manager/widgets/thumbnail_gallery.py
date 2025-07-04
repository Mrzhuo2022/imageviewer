from PySide6.QtCore import Qt, QSize, Signal, QSortFilterProxyModel
from PySide6.QtGui import QIcon, QStandardItemModel, QStandardItem, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListView, QLineEdit, QMenu, QMessageBox, QInputDialog, QLabel, QDialog, QScrollArea, QPushButton, QHBoxLayout
)

from .folder_selection_dialog import FolderSelectionDialog

class HorizontalScrollArea(QScrollArea):
    def wheelEvent(self, event):
        if event.modifiers() == Qt.NoModifier: # Only scroll horizontally if no modifier keys are pressed
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)


import os
import shutil
from pathlib import Path
from PIL import Image

from ..config import ICONS, THUMBNAIL_SIZE, GRID_SPACING, LIBRARY_DIR, THUMBNAIL_DIR, ROOT_DIR
from .. import image_utils

class ThumbnailGallery(QWidget):
    image_selected = Signal(object) # Emits image_data dict when an image is selected
    status_message = Signal(str, int) # Emits message and timeout for status bar
    library_updated = Signal() # Emits when images are added/deleted/renamed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_folder = "" # Represents the current folder being viewed
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        
        # Category buttons (horizontal scrollable)
        self.category_scroll_area = HorizontalScrollArea()
        self.category_scroll_area.setWidgetResizable(True)
        self.category_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # Hide horizontal scrollbar
        self.category_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_scroll_area.setFixedHeight(40) # Set fixed height for the button area

        self.category_buttons_widget = QWidget()
        self.category_buttons_layout = QHBoxLayout(self.category_buttons_widget)
        self.category_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.category_buttons_layout.setSpacing(5)
        self.category_scroll_area.setWidget(self.category_buttons_widget)
        self.layout.addWidget(self.category_scroll_area)

        # Set context menu policy for the category buttons widget
        self.category_buttons_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.category_buttons_widget.customContextMenuRequested.connect(self.show_category_context_menu)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search by filename...")
        self.layout.addWidget(self.search_bar)

        self.thumbnail_view = QListView()
        self.thumbnail_model = QStandardItemModel(self.thumbnail_view)
        
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.thumbnail_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(0) # Filter based on the text (filename)
        # Removed custom filter settings

        self.thumbnail_view.setModel(self.proxy_model) # Directly use thumbnail_model
        self.thumbnail_view.setViewMode(QListView.IconMode)
        self.thumbnail_view.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.thumbnail_view.setGridSize(QSize(*GRID_SPACING))
        self.thumbnail_view.setResizeMode(QListView.Adjust) # Changed to Adjust
        self.thumbnail_view.setDragEnabled(False) # Disable dragging
        self.thumbnail_view.setAcceptDrops(False) # Disable dropping
        self.thumbnail_view.setDropIndicatorShown(False) # Hide drop indicator
        self.thumbnail_view.setSelectionMode(QListView.ExtendedSelection) # Allow multiple selection
        self.thumbnail_view.setFlow(QListView.LeftToRight) # Arrange items from left to right
        self.thumbnail_view.setLayoutMode(QListView.Batched) # Use batched layout for better performance
        self.thumbnail_view.setWordWrap(True) # Revert to word wrap for two-column display
        self.thumbnail_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # No horizontal scroll for thumbnails
        self.thumbnail_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded) # Vertical scroll for thumbnails
        self.thumbnail_view.setContextMenuPolicy(Qt.CustomContextMenu) # Enable custom context menu
        self.layout.addWidget(self.thumbnail_view)

        self.setup_connections()

    def setup_connections(self):
        self.search_bar.textChanged.connect(self.proxy_model.setFilterRegularExpression)
        self.thumbnail_view.selectionModel().selectionChanged.connect(self.on_thumbnail_selected)
        self.thumbnail_view.customContextMenuRequested.connect(self.show_thumbnail_context_menu)
        self.thumbnail_view.doubleClicked.connect(self.on_item_double_clicked)
        # Removed category_filter_combo connection

    def on_thumbnail_selected(self, selected, deselected):
        indexes = selected.indexes()
        if not indexes:
            self.image_selected.emit(None)
            return
        
        # Only emit the first selected image for display in ImageViewer
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        item_data = self.thumbnail_model.itemFromIndex(source_index).data(Qt.UserRole)
        
        # Check if the selected item is an image (not a folder or '..')
        if isinstance(item_data, dict) and "library_path" in item_data:
            self.image_selected.emit(item_data)
        else:
            self.image_selected.emit(None)

    def load_thumbnails(self, folder_path=""):
        self.thumbnail_model.clear()
        self.current_folder = folder_path

        try:
            # Clear existing category buttons
            for i in reversed(range(self.category_buttons_layout.count())):
                widget = self.category_buttons_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()
            
            # Add "All" button
            all_button = QPushButton("All")
            all_button.setCheckable(True)
            all_button.setFixedWidth(100) # Fixed width for button
            all_button.setFixedHeight(30) # Fixed height for button
            all_button.clicked.connect(lambda: self.filter_by_category_button(""))
            self.category_buttons_layout.addWidget(all_button)

            metadata = image_utils.load_metadata()
            
            all_top_level_folders = set()
            # Collect top-level folders from file system (including empty ones)
            for entry in LIBRARY_DIR.iterdir():
                if entry.is_dir() and entry.name != THUMBNAIL_DIR.name and not entry.name.startswith("."):
                    # Check if this folder contains any subdirectories
                    has_subdirectories = False
                    for sub_entry in entry.iterdir():
                        if sub_entry.is_dir():
                            has_subdirectories = True
                            break
                    
                    if not has_subdirectories: # Only add if it does not contain subdirectories
                        all_top_level_folders.add(entry.name)
            
            # Add subfolder buttons
            for folder_name in sorted(list(all_top_level_folders)):
                folder_button = QPushButton(folder_name)
                folder_button.setCheckable(True)
                folder_button.setFixedWidth(100) # Fixed width for button
                folder_button.setFixedHeight(30) # Fixed height for button
                folder_button.clicked.connect(lambda checked, fn=folder_name: self.filter_by_category_button(fn))
                self.category_buttons_layout.addWidget(folder_button)

            # Add a stretch to push buttons to the left
            # self.category_buttons_layout.addStretch(1)

            # Ensure only one button is checked
            if not self.current_folder:
                all_button.setChecked(True)
            else:
                found_checked = False
                for i in range(self.category_buttons_layout.count()):
                    button = self.category_buttons_layout.itemAt(i).widget()
                    if button and button.text() == self.current_folder:
                        button.setChecked(True)
                        found_checked = True
                        break
                if not found_checked:
                    all_button.setChecked(True) # Fallback if current_folder not found in buttons

            # Filter images for display in QListView
            # Use the new function to get filtered metadata
            if self.current_folder == "": # "All" category
                images_to_display = image_utils.get_image_metadata_for_folder(recursive=True)
            else: # Specific folder
                images_to_display = image_utils.get_image_metadata_for_folder(self.current_folder, recursive=False)

            # Add image items, sorted by timestamp (newest first)
            for image_id, item_data in sorted(images_to_display.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True):
                # Ensure image_id is part of item_data for consistent access
                item_data["image_id"] = image_id

                thumbnail_path = Path(item_data["thumbnail_path"])
                print(f"Checking thumbnail path: {thumbnail_path}, exists: {thumbnail_path.exists()}") # Debug print
                
                pixmap = QPixmap(str(thumbnail_path))
                print(f"Pixmap null status: {pixmap.isNull()}") # Debug print
                if not pixmap.isNull():
                    icon = QIcon(pixmap)
                    item = QStandardItem(icon, item_data["original_filename"])
                else:
                    item = QStandardItem(QIcon(), item_data["original_filename"]) # Empty icon
                    self.status_message.emit(f"Warning: Could not load thumbnail for {item_data['original_filename']}", 3000)
                
                # Store image_id and all metadata for later use
                item.setData(item_data["image_id"], Qt.UserRole + 1) # Store image_id
                item.setData(item_data, Qt.UserRole) # Store full item_data
                item.setEditable(False)
                self.thumbnail_model.appendRow(item)

            self.library_updated.emit() # Notify main window that library count might have changed
        except Exception as e:
            self.status_message.emit(f"Error loading thumbnails: {e}", 0)

    def filter_by_category_button(self, category_folder):
        # Iterate through all buttons to manage their checked state
        for i in range(self.category_buttons_layout.count()):
            button = self.category_buttons_layout.itemAt(i).widget()
            if button and button.isCheckable():
                # Determine if this button should be checked
                should_be_checked = False
                if category_folder == "": # "All" category selected
                    if button.text() == "All":
                        should_be_checked = True
                else: # A specific folder category selected
                    if button.text() == category_folder:
                        should_be_checked = True
                
                button.setChecked(should_be_checked)
        
        self.load_thumbnails(category_folder)

    def show_category_context_menu(self, pos):
        # Get the button that was right-clicked
        button = self.category_buttons_widget.childAt(pos)
        if not isinstance(button, QPushButton):
            return

        folder_name = button.text()
        if folder_name == "All": # Cannot delete the "All" category
            return

        menu = QMenu()
        delete_action = menu.addAction("Delete Folder")
        action = menu.exec(self.category_buttons_widget.mapToGlobal(pos)) # Map position relative to the widget

        if action == delete_action:
            self.delete_category_folder(folder_name)

    def delete_category_folder(self, folder_name):
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Are you sure you want to delete the folder '{folder_name}' and all its contents (images and subfolders)? This action cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                # 1. Delete folder from file system
                folder_path_on_disk = LIBRARY_DIR / folder_name
                if folder_path_on_disk.exists():
                    shutil.rmtree(folder_path_on_disk)

                # 2. Remove associated images and metadata
                metadata = image_utils.load_metadata()
                image_ids_to_remove = []
                for image_id, item_data in metadata.items():
                    item_subfolder = item_data.get("subfolder", "")
                    if item_subfolder == folder_name or item_subfolder.startswith(f"{folder_name}/"):
                        # Delete thumbnail file
                        thumbnail_path = Path(item_data["thumbnail_path"])
                        if thumbnail_path.exists():
                            thumbnail_path.unlink()
                        image_ids_to_remove.append(image_id)
                
                for image_id in image_ids_to_remove:
                    del metadata[image_id]
                image_utils.save_metadata(metadata)

                self.status_message.emit(f"Folder '{folder_name}' and its contents deleted.", 5000)
                self.load_thumbnails("") # Reload to "All" view after deletion
            except Exception as e:
                self.status_message.emit(f"Error deleting folder '{folder_name}': {e}", 0)

    def on_item_double_clicked(self, index):
        # Double-click on image will select it (already handled by on_thumbnail_selected)
        # No longer handling folder navigation via double-click on items in QListView
        pass

    def go_to_folder(self, folder_path):
        pass

    def process_imported_paths(self, file_paths, target_subfolder=""):
        for path in file_paths:
            image_utils.process_and_copy_image(path, target_subfolder)
        self.load_thumbnails(self.current_folder) # Reload current view

    def process_imported_folder(self, folder_path, target_subfolder=""):
        # This function will now import only images directly from the selected folder
        # into the target_subfolder within the library.
        
        image_files = []
        for file in os.listdir(folder_path):
            full_path = os.path.join(folder_path, file)
            if os.path.isfile(full_path) and file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                image_files.append(full_path)
        
        if not image_files:
            self.status_message.emit(f"No images found directly in '{folder_path}'.", 3000)
            return

        for path in image_files:
            image_utils.process_and_copy_image(path, target_subfolder)
        self.load_thumbnails(self.current_folder) # Reload current view

    def show_thumbnail_context_menu(self, position):
        index = self.thumbnail_view.indexAt(position)
        print(f"Context menu requested. Index valid: {index.isValid()}") # Debug print
        if not index.isValid():
            return

        # Map the proxy index back to the source model index
        source_index = self.proxy_model.mapToSource(index)
        item = self.thumbnail_model.itemFromIndex(source_index)
        print(f"Item from index: {item}") # Debug print
        
        if item:
            image_data = item.data(Qt.UserRole)
            print(f"Image data from item: {image_data}") # Debug print
            if isinstance(image_data, dict) and "library_path" in image_data: # Ensure it's an image item
                menu = QMenu()
                rename_action = menu.addAction(ICONS["rename"], "Rename Image")
                change_category_action = menu.addAction(ICONS["import"], "Change Category") # Added icon
                delete_selected_action = menu.addAction(ICONS["delete"], "Delete Selected Images")
                
                action = menu.exec(self.thumbnail_view.mapToGlobal(position))

                if action == rename_action:
                    self.rename_image(image_data["image_id"], image_data["original_filename"])
                elif action == change_category_action:
                    self.change_image_category(image_data["image_id"])
                elif action == delete_selected_action:
                    self.delete_selected_images()

    def delete_selected_images(self):
        selected_indexes = self.thumbnail_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            self.status_message.emit("No images selected for deletion.", 3000)
            return

        reply = QMessageBox.question(self, "Confirm Batch Deletion",
                                     f"Are you sure you want to delete {len(selected_indexes)} selected images? This action cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                image_ids_to_delete = []
                for index in selected_indexes:
                    source_index = self.proxy_model.mapToSource(index)
                    item = self.thumbnail_model.itemFromIndex(source_index)
                    image_id = item.data(Qt.UserRole + 1) # Retrieve image_id
                    if image_id:
                        image_ids_to_delete.append(image_id)
                
                for image_id in image_ids_to_delete:
                    image_utils.remove_image_files(image_id)
                
                self.status_message.emit(f"Successfully deleted {len(image_ids_to_delete)} images.", 3000)
                self.load_thumbnails(self.current_folder) # Reload current view
            except Exception as e:
                self.status_message.emit(f"Error during batch deletion: {e}", 0)

    def change_image_category(self, image_id):
        metadata = image_utils.load_metadata()
        if image_id not in metadata:
            self.status_message.emit("Image not found for changing category.", 3000)
            return

        item_data = metadata[image_id]
        current_subfolder = item_data.get("subfolder", "")

        dialog = FolderSelectionDialog(current_gallery_folder=current_subfolder, parent=self)
        if dialog.exec():
            new_subfolder = dialog.get_selected_folder()

            if new_subfolder == current_subfolder:
                self.status_message.emit("Image is already in the selected category.", 3000)
                return

            try:
                old_library_path = Path(item_data["library_path"])
                
                # Construct new library path
                new_library_dir = LIBRARY_DIR / new_subfolder
                new_library_dir.mkdir(parents=True, exist_ok=True)
                new_library_path = new_library_dir / old_library_path.name

                # Move the file on disk
                shutil.move(str(old_library_path), str(new_library_path))

                # Update metadata
                item_data["library_path"] = str(new_library_path)
                item_data["subfolder"] = new_subfolder
                image_utils.save_metadata(metadata)

                self.status_message.emit(f"Image moved to category '{new_subfolder if new_subfolder else "Root Folder"}'.", 3000)
                self.load_thumbnails(self.current_folder) # Reload current view
            except Exception as e:
                self.status_message.emit(f"Error changing image category: {e}", 0)

    def rename_image(self, image_id, current_filename):
        new_filename, ok = QInputDialog.getText(self, "Rename Image", "Enter new filename:",
                                                 QLineEdit.Normal, current_filename)
        if ok and new_filename and new_filename != current_filename:
            metadata = image_utils.load_metadata()
            if image_id in metadata:
                item_data = metadata[image_id]
                old_library_path = Path(item_data["library_path"])
                old_thumbnail_path = Path(item_data["thumbnail_path"])

                # Ensure new filename has the same extension
                new_filename_with_ext = Path(new_filename).stem + old_library_path.suffix
                
                new_library_path = old_library_path.parent / new_filename_with_ext
                new_thumbnail_path = old_thumbnail_path.parent / new_filename_with_ext

                try:
                    # Rename files on disk
                    old_library_path.rename(new_library_path)
                    old_thumbnail_path.rename(new_thumbnail_path)

                    # Update metadata
                    item_data["original_filename"] = new_filename_with_ext
                    item_data["library_path"] = str(new_library_path)
                    item_data["thumbnail_path"] = str(new_thumbnail_path)
                    image_utils.save_metadata(metadata)
                    
                    self.status_message.emit(f"Image renamed to '{new_filename_with_ext}'.", 3000)
                    self.load_thumbnails(self.current_folder) # Reload current view
                except Exception as e:
                    self.status_message.emit(f"Error renaming image: {e}", 0)
            else:
                self.status_message.emit("Image not found for renaming.", 3000)

    def delete_image(self, image_id):
        reply = QMessageBox.question(self, "Confirm Deletion",
                                     "Are you sure you want to delete this image? This action cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                image_utils.remove_image_files(image_id)
                self.status_message.emit("Image deleted.", 3000)
                self.load_thumbnails(self.current_folder) # Reload current view
            except Exception as e:
                self.status_message.emit(f"Error deleting image: {e}", 0)