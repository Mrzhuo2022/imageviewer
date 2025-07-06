from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QListView, QLabel, QMessageBox
from ..config import LIBRARY_DIR

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
        
        self.folder_list_view = QListView()
        self.folder_model = QStandardItemModel(self.folder_list_view)
        self.folder_list_view.setModel(self.folder_model)
        self.folder_list_view.clicked.connect(self.on_folder_selected)
        main_layout.addWidget(self.folder_list_view)

        new_folder_layout = QHBoxLayout()
        self.new_folder_input = QLineEdit()
        self.new_folder_input.setPlaceholderText("Enter new folder name")
        new_folder_layout.addWidget(self.new_folder_input)
        self.create_button = QPushButton("Create & Select")
        self.create_button.clicked.connect(self.create_new_folder)
        new_folder_layout.addWidget(self.create_button)
        main_layout.addLayout(new_folder_layout)

        button_layout = QHBoxLayout()
        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(self.accept_selection)
        self.select_button.setEnabled(True)
        button_layout.addWidget(self.select_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def load_folders(self):
        self.folder_model.clear()
        
        root_item = QStandardItem(".")
        root_item.setData("", Qt.UserRole)
        root_item.setEditable(False)
        self.folder_model.appendRow(root_item)

        top_level_folders = set()
        for entry in LIBRARY_DIR.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                has_subdirectories = any(sub_entry.is_dir() for sub_entry in entry.iterdir())
                if not has_subdirectories:
                    top_level_folders.add(entry.name)

        for folder_name in sorted(top_level_folders):
            item = QStandardItem(folder_name)
            item.setData(folder_name, Qt.UserRole)
            item.setEditable(False)
            self.folder_model.appendRow(item)

    def on_folder_selected(self, index):
        item = self.folder_model.itemFromIndex(index)
        self.selected_folder_path = item.data(Qt.UserRole)
        self.new_folder_input.clear()
        self.new_folder_input.setPlaceholderText("Enter new folder")

    def create_new_folder(self):
        new_name = self.new_folder_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Folder name cannot be empty.")
            return

        sanitized_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(" ", "_")
        if not sanitized_name:
            QMessageBox.warning(self, "Invalid Name", "Sanitized folder name is empty. Please use valid characters.")
            return

        full_new_folder_path = sanitized_name
        existing_folders = [self.folder_model.item(row).text().lower() for row in range(self.folder_model.rowCount())]
        if sanitized_name.lower() in existing_folders:
            QMessageBox.warning(self, "Folder Exists", f"Folder '{new_name}' already exists.")
            return

        self.selected_folder_path = full_new_folder_path
        self.accept()

    def accept_selection(self):
        if self.new_folder_input.text().strip():
            self.create_new_folder()
        else:
            self.accept()

    def get_selected_folder(self):
        return self.selected_folder_path