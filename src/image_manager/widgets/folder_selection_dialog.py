
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QListView, QLabel, QMessageBox

from .. import image_utils
from ..config import LIBRARY_DIR
from pathlib import Path

class FolderSelectionDialog(QDialog):
    def __init__(self, current_gallery_folder="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select or Create Folder")
        self.current_gallery_folder = current_gallery_folder
        self.selected_folder_path = ""

        self.init_ui()
        self.load_folders()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        main_layout.addWidget(QLabel("Select an existing folder or enter a new one:"))

        # Existing folders list
        self.folder_list_view = QListView()
        self.folder_model = QStandardItemModel(self.folder_list_view)
        self.folder_list_view.setModel(self.folder_model)
        self.folder_list_view.clicked.connect(self.on_folder_selected)
        main_layout.addWidget(self.folder_list_view)

        # New folder input
        new_folder_layout = QHBoxLayout()
        self.new_folder_input = QLineEdit()
        self.new_folder_input.setPlaceholderText("Enter new folder name")
        new_folder_layout.addWidget(self.new_folder_input)
        self.create_button = QPushButton("Create & Select")
        self.create_button.clicked.connect(self.create_new_folder)
        new_folder_layout.addWidget(self.create_button)
        main_layout.addLayout(new_folder_layout)

        # Action buttons
        button_layout = QHBoxLayout()
        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(self.accept_selection)
        self.select_button.setEnabled(True) # Always enabled, as it can mean selecting root
        button_layout.addWidget(self.select_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def load_folders(self):
        self.folder_model.clear()
        
        # Add '.' option for root folder
        root_item = QStandardItem(".")
        root_item.setData("", Qt.UserRole) # Empty string for root
        root_item.setEditable(False) # Make it non-editable
        self.folder_model.appendRow(root_item)

        # Collect direct subfolders of LIBRARY_DIR
        top_level_folders = set()
        for entry in LIBRARY_DIR.iterdir():
            if entry.is_dir() and not entry.name.startswith("."): # Exclude hidden/internal folders
                # Check if this folder contains any subdirectories (to enforce two-level structure)
                has_subdirectories = False
                for sub_entry in entry.iterdir():
                    if sub_entry.is_dir():
                        has_subdirectories = True
                        break
                if not has_subdirectories: # Only add if it does not contain subdirectories
                    top_level_folders.add(entry.name)

        for folder_name in sorted(list(top_level_folders)):
            item = QStandardItem(folder_name)
            item.setData(folder_name, Qt.UserRole) # Data is just the folder name
            item.setEditable(False) # Make it non-editable
            self.folder_model.appendRow(item)

    def on_folder_selected(self, index):
        item = self.folder_model.itemFromIndex(index)
        self.selected_folder_path = item.data(Qt.UserRole)
        # Clear the new folder input when an existing folder is selected
        self.new_folder_input.clear()
        # Update placeholder to show what's selected, but still allow new input
        self.new_folder_input.setPlaceholderText("Enter new folder")

    def create_new_folder(self):
        new_name = self.new_folder_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Folder name cannot be empty.")
            return

        # Sanitize new_name to create a valid path segment
        sanitized_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).strip()
        sanitized_name = sanitized_name.replace(" ", "_")
        if not sanitized_name:
            QMessageBox.warning(self, "Invalid Name", "Sanitized folder name is empty. Please use valid characters.")
            return

        # Construct the full path for the new subfolder (always relative to LIBRARY_DIR)
        full_new_folder_path = sanitized_name # This will be the subfolder name directly under LIBRARY_DIR

        # Check if folder already exists (case-insensitive for user experience)
        existing_folders = [self.folder_model.item(row).text().lower() for row in range(self.folder_model.rowCount())]
        if sanitized_name.lower() in existing_folders:
            QMessageBox.warning(self, "Folder Exists", f"Folder '{new_name}' already exists.")
            return

        # No need to create actual directory here, image_utils will handle it
        self.selected_folder_path = full_new_folder_path
        self.accept()

    def accept_selection(self):
        # If user typed something in new_folder_input, treat it as new folder
        if self.new_folder_input.text().strip():
            self.create_new_folder()
        else:
            # If nothing is typed, and no existing folder is selected, default to root
            # The selected_folder_path is already set by on_folder_selected or is default empty
            self.accept()

    def get_selected_folder(self):
        return self.selected_folder_path
