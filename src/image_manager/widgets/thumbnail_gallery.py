from PySide6.QtCore import Qt, QSize, Signal, QSortFilterProxyModel
from PySide6.QtGui import QIcon, QStandardItemModel, QStandardItem, QPixmap, QKeyEvent
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

        self.thumbnail_view.setModel(self.proxy_model)
        self.thumbnail_view.setViewMode(QListView.IconMode)
        self.thumbnail_view.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.thumbnail_view.setGridSize(QSize(*GRID_SPACING))
        self.thumbnail_view.setResizeMode(QListView.Adjust)
        self.thumbnail_view.setDragEnabled(False)
        self.thumbnail_view.setAcceptDrops(False)
        self.thumbnail_view.setDropIndicatorShown(False)
        self.thumbnail_view.setSelectionMode(QListView.ExtendedSelection)
        self.thumbnail_view.setFlow(QListView.LeftToRight)
        self.thumbnail_view.setLayoutMode(QListView.Batched)
        self.thumbnail_view.setWordWrap(True)
        self.thumbnail_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbnail_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumbnail_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layout.addWidget(self.thumbnail_view)

        self.setup_connections()

    def setup_connections(self):
        self.search_bar.textChanged.connect(self.proxy_model.setFilterRegularExpression)
        self.thumbnail_view.selectionModel().selectionChanged.connect(self.on_thumbnail_selected)
        self.thumbnail_view.customContextMenuRequested.connect(self.show_thumbnail_context_menu)
        self.thumbnail_view.doubleClicked.connect(self.on_item_double_clicked)

    def on_thumbnail_selected(self, selected, deselected):
        indexes = selected.indexes()
        if not indexes:
            self.image_selected.emit(None)
            return
        
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        item_data = self.thumbnail_model.itemFromIndex(source_index).data(Qt.UserRole)
        
        if isinstance(item_data, dict) and "library_path" in item_data:
            self.image_selected.emit(item_data)
        else:
            self.image_selected.emit(None)

    def load_thumbnails(self, folder_path=""):
        self.thumbnail_model.clear()
        self.current_folder = folder_path

        try:
            for i in reversed(range(self.category_buttons_layout.count())):
                widget = self.category_buttons_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()
            
            all_button = QPushButton("All")
            all_button.setCheckable(True)
            all_button.setFixedWidth(100)
            all_button.setFixedHeight(30)
            all_button.clicked.connect(lambda: self.filter_by_category_button(""))
            self.category_buttons_layout.addWidget(all_button)

            metadata = image_utils.load_metadata()
            
            all_top_level_folders = set()
            for entry in LIBRARY_DIR.iterdir():
                if entry.is_dir() and entry.name != THUMBNAIL_DIR.name and not entry.name.startswith("."):
                    has_subdirectories = any(sub_entry.is_dir() for sub_entry in entry.iterdir())
                    if not has_subdirectories:
                        all_top_level_folders.add(entry.name)
            
            for folder_name in sorted(list(all_top_level_folders)):
                folder_button = QPushButton(folder_name)
                folder_button.setCheckable(True)
                folder_button.setFixedWidth(100)
                folder_button.setFixedHeight(30)
                folder_button.clicked.connect(lambda checked, fn=folder_name: self.filter_by_category_button(fn))
                self.category_buttons_layout.addWidget(folder_button)

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
                    all_button.setChecked(True)

            images_to_display = {}
            if self.current_folder == "":
                images_to_display = metadata
            else:
                for img_id, data in metadata.items():
                    if data.get("subfolder") == self.current_folder:
                        images_to_display[img_id] = data

            for image_id, item_data in sorted(images_to_display.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True):
                item_data["image_id"] = image_id
                thumbnail_path = Path(item_data["thumbnail_path"])
                pixmap = QPixmap(str(thumbnail_path))
                if not pixmap.isNull():
                    icon = QIcon(pixmap)
                    item = QStandardItem(icon, item_data["original_filename"])
                else:
                    item = QStandardItem(QIcon(), item_data["original_filename"])
                    self.status_message.emit(f"Warning: Could not load thumbnail for {item_data['original_filename']}", 3000)
                
                item.setData(item_data["image_id"], Qt.UserRole + 1)
                item.setData(item_data, Qt.UserRole)
                item.setEditable(False)
                self.thumbnail_model.appendRow(item)

            self.library_updated.emit()
        except Exception as e:
            self.status_message.emit(f"Error loading thumbnails: {e}", 0)

    def filter_by_category_button(self, category_folder):
        for i in range(self.category_buttons_layout.count()):
            button = self.category_buttons_layout.itemAt(i).widget()
            if button and button.isCheckable():
                should_be_checked = (button.text() == "All" and category_folder == "") or (button.text() == category_folder)
                button.setChecked(should_be_checked)
        
        self.load_thumbnails(category_folder)

    def show_category_context_menu(self, pos):
        button = self.category_buttons_widget.childAt(pos)
        if not isinstance(button, QPushButton) or button.text() == "All":
            return

        folder_name = button.text()
        menu = QMenu()
        rename_action = menu.addAction(ICONS["rename"], "Rename Category")
        delete_action = menu.addAction(ICONS["delete"], "Delete Category")
        action = menu.exec(self.category_buttons_widget.mapToGlobal(pos))

        if action == delete_action:
            self.delete_category_folder(folder_name)
        elif action == rename_action:
            self.rename_category_folder(folder_name)

    def rename_category_folder(self, old_folder_name):
        new_folder_name, ok = QInputDialog.getText(self, "Rename Category", "Enter new category name:", QLineEdit.Normal, old_folder_name)
        if ok and new_folder_name and new_folder_name != old_folder_name:
            sanitized_name = "".join(c for c in new_folder_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(" ", "_")
            if not sanitized_name:
                self.status_message.emit("Invalid new category name.", 3000)
                return

            old_path = LIBRARY_DIR / old_folder_name
            new_path = LIBRARY_DIR / sanitized_name

            if new_path.exists():
                self.status_message.emit(f"Category '{sanitized_name}' already exists.", 3000)
                return

            try:
                old_path.rename(new_path)
                metadata = image_utils.load_metadata()
                for image_id, item_data in metadata.items():
                    if item_data.get("subfolder") == old_folder_name:
                        item_data["subfolder"] = sanitized_name
                        old_library_path = Path(item_data["library_path"])
                        item_data["library_path"] = str(new_path / old_library_path.name)
                image_utils.save_metadata(metadata)
                self.status_message.emit(f"Category '{old_folder_name}' renamed to '{sanitized_name}'.", 5000)
                self.load_thumbnails(self.current_folder)
            except Exception as e:
                self.status_message.emit(f"Error renaming category: {e}", 0)

    def delete_category_folder(self, folder_name):
        reply = QMessageBox.question(self, "Confirm Deletion", f"Are you sure you want to delete the folder '{folder_name}' and all its contents?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                folder_path_on_disk = LIBRARY_DIR / folder_name
                if folder_path_on_disk.exists():
                    shutil.rmtree(folder_path_on_disk)

                metadata = image_utils.load_metadata()
                image_ids_to_remove = [img_id for img_id, data in metadata.items() if data.get("subfolder", "").startswith(folder_name)]
                
                for image_id in image_ids_to_remove:
                    thumbnail_path = Path(metadata[image_id]["thumbnail_path"])
                    thumbnail_path.unlink(missing_ok=True)
                    del metadata[image_id]
                
                image_utils.save_metadata(metadata)
                self.status_message.emit(f"Folder '{folder_name}' and its contents deleted.", 5000)
                self.load_thumbnails("")
            except Exception as e:
                self.status_message.emit(f"Error deleting folder '{folder_name}': {e}", 0)

    def on_item_double_clicked(self, index):
        pass

    def go_to_folder(self, folder_path):
        pass

    def process_imported_paths(self, file_paths, target_subfolder=""):
        for path in file_paths:
            image_utils.add_image_to_library(path, target_subfolder)
        self.load_thumbnails(self.current_folder)

    def process_imported_folder(self, folder_path, target_subfolder=""):
        image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]
        if not image_files:
            self.status_message.emit(f"No images found directly in '{folder_path}'.", 3000)
            return

        for path in image_files:
            image_utils.add_image_to_library(path, target_subfolder)
        self.load_thumbnails(self.current_folder)

    def show_thumbnail_context_menu(self, position):
        index = self.thumbnail_view.indexAt(position)
        if not index.isValid():
            return

        source_index = self.proxy_model.mapToSource(index)
        item = self.thumbnail_model.itemFromIndex(source_index)
        if item:
            image_data = item.data(Qt.UserRole)
            if isinstance(image_data, dict) and "library_path" in image_data:
                menu = QMenu()
                rename_action = menu.addAction(ICONS["rename"], "Rename Image")
                change_category_action = menu.addAction(ICONS["import"], "Change Category")
                delete_action = menu.addAction(ICONS["delete"], "Delete Images")
                
                action = menu.exec(self.thumbnail_view.mapToGlobal(position))

                if action == rename_action:
                    self.rename_image(image_data["image_id"], image_data["original_filename"])
                elif action == change_category_action:
                    self.change_selected_images_category()
                elif action == delete_action:
                    self.delete_selected_images()

    def change_selected_images_category(self):
        selected_indexes = self.thumbnail_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            self.status_message.emit("No images selected.", 3000)
            return

        dialog = FolderSelectionDialog(parent=self)
        if dialog.exec():
            new_subfolder = dialog.get_selected_folder()
            metadata = image_utils.load_metadata()
            moved_count = 0

            for index in selected_indexes:
                source_index = self.proxy_model.mapToSource(index)
                item = self.thumbnail_model.itemFromIndex(source_index)
                image_id = item.data(Qt.UserRole + 1)

                if image_id and image_id in metadata:
                    item_data = metadata[image_id]
                    if new_subfolder == item_data.get("subfolder", ""):
                        continue

                    try:
                        old_library_path = Path(item_data["library_path"])
                        new_library_dir = LIBRARY_DIR / new_subfolder
                        new_library_dir.mkdir(parents=True, exist_ok=True)
                        new_library_path = new_library_dir / old_library_path.name
                        shutil.move(str(old_library_path), str(new_library_path))
                        item_data["library_path"] = str(new_library_path)
                        item_data["subfolder"] = new_subfolder
                        moved_count += 1
                    except Exception as e:
                        self.status_message.emit(f"Error moving {item_data['original_filename']}: {e}", 0)
            
            if moved_count > 0:
                image_utils.save_metadata(metadata)
                self.status_message.emit(f"Moved {moved_count} images to '{new_subfolder if new_subfolder else "Root"}'.", 5000)
                self.load_thumbnails(self.current_folder)

    def delete_selected_images(self):
        selected_indexes = self.thumbnail_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            self.status_message.emit("No images selected.", 3000)
            return

        reply = QMessageBox.question(self, "Confirm Deletion", f"Delete {len(selected_indexes)} images?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            image_ids_to_delete = [self.thumbnail_model.itemFromIndex(self.proxy_model.mapToSource(index)).data(Qt.UserRole + 1) for index in selected_indexes]
            for image_id in image_ids_to_delete:
                if image_id:
                    image_utils.remove_image_from_library(image_id)
            self.status_message.emit(f"Deleted {len(image_ids_to_delete)} images.", 3000)
            self.load_thumbnails(self.current_folder)

    def get_current_image_list(self):
        return [self.thumbnail_model.itemFromIndex(self.proxy_model.mapToSource(self.proxy_model.index(row, 0))).data(Qt.UserRole) for row in range(self.proxy_model.rowCount())]
    
    def select_image_by_data(self, image_data):
        target_path = image_data["library_path"]
        for row in range(self.proxy_model.rowCount()):
            proxy_index = self.proxy_model.index(row, 0)
            source_index = self.proxy_model.mapToSource(proxy_index)
            item_data = self.thumbnail_model.itemFromIndex(source_index).data(Qt.UserRole)
            if isinstance(item_data, dict) and item_data.get("library_path") == target_path:
                self.thumbnail_view.setCurrentIndex(proxy_index)
                self.thumbnail_view.scrollTo(proxy_index)
                self.image_selected.emit(item_data)
                break

    def rename_image(self, image_id, current_filename):
        new_filename, ok = QInputDialog.getText(self, "Rename Image", "Enter new filename:", QLineEdit.Normal, current_filename)
        if ok and new_filename and new_filename != current_filename:
            metadata = image_utils.load_metadata()
            if image_id in metadata:
                item_data = metadata[image_id]
                old_library_path = Path(item_data["library_path"])
                old_thumbnail_path = Path(item_data["thumbnail_path"])
                new_filename_with_ext = Path(new_filename).stem + old_library_path.suffix
                new_library_path = old_library_path.parent / new_filename_with_ext
                new_thumbnail_path = old_thumbnail_path.parent / new_filename_with_ext

                try:
                    old_library_path.rename(new_library_path)
                    old_thumbnail_path.rename(new_thumbnail_path)
                    item_data["original_filename"] = new_filename_with_ext
                    item_data["library_path"] = str(new_library_path)
                    item_data["thumbnail_path"] = str(new_thumbnail_path)
                    image_utils.save_metadata(metadata)
                    self.status_message.emit(f"Image renamed to '{new_filename_with_ext}'.", 3000)
                    self.load_thumbnails(self.current_folder)
                except Exception as e:
                    self.status_message.emit(f"Error renaming image: {e}", 0)

    def delete_image(self, image_id):
        reply = QMessageBox.question(self, "Confirm Deletion", "Delete this image?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            image_utils.remove_image_from_library(image_id)
            self.status_message.emit("Image deleted.", 3000)
            self.load_thumbnails(self.current_folder)
