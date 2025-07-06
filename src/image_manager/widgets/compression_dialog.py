from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QSlider, QComboBox, QCheckBox, QPushButton, 
                               QGroupBox, QSpinBox, QProgressBar, QMessageBox)
from PySide6.QtGui import QFont
from pathlib import Path
from PIL import Image
from .. import image_utils

class PreviewWorker(QThread):
    preview_ready = Signal(dict)
    preview_error = Signal(str)
    
    def __init__(self, image_path, quality, output_format, max_size):
        super().__init__()
        self.image_path = image_path
        self.quality = quality
        self.output_format = output_format
        self.max_size = max_size
    
    def run(self):
        try:
            preview_info = image_utils.get_compression_preview(
                self.image_path, self.quality, self.output_format, self.max_size
            )
            if preview_info:
                self.preview_ready.emit(preview_info)
            else:
                self.preview_error.emit("Failed to calculate preview")
        except Exception as e:
            self.preview_error.emit(str(e))

class CompressionDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = Path(image_path)
        self.image_name = self.image_path.name
        self.preview_info = None
        self.preview_worker = None
        self.original_info = self._get_original_image_info()
        
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.update_preview)
        
        self.setWindowTitle(f"Compress Image - {self.image_name}")
        self.setModal(True)
        self.resize(520, 650)
        self.setMinimumSize(480, 600)
        
        self.init_ui()
        self.connect_signals()
        self.load_image_info()
        
        QTimer.singleShot(200, self.update_preview)
    
    def _get_original_image_info(self):
        try:
            with Image.open(self.image_path) as img:
                return {
                    'size': self.image_path.stat().st_size,
                    'dimensions': img.size,
                    'format': img.format or 'Unknown',
                    'mode': img.mode
                }
        except Exception:
            return {
                'size': self.image_path.stat().st_size if self.image_path.exists() else 0,
                'dimensions': (0, 0),
                'format': 'Unknown',
                'mode': 'Unknown'
            }
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        info_group = QGroupBox("Image Information")
        info_layout = QVBoxLayout(info_group)
        
        self.image_info_label = QLabel()
        self.image_info_label.setWordWrap(True)
        font = QFont()
        font.setFamily("Consolas, Monaco, monospace")
        font.setPointSize(9)
        self.image_info_label.setFont(font)
        info_layout.addWidget(self.image_info_label)
        
        layout.addWidget(info_group)
        
        settings_group = QGroupBox("Compression Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Output Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("Keep Original", None)
        self.format_combo.addItem("JPEG", "JPEG")
        self.format_combo.addItem("PNG", "PNG")  
        self.format_combo.addItem("WebP", "WEBP")
        self.format_combo.setCurrentIndex(1)
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        settings_layout.addLayout(format_layout)
        
        quality_group = QGroupBox("Quality")
        quality_layout = QVBoxLayout(quality_group)
        
        quality_header = QHBoxLayout()
        quality_header.addWidget(QLabel("Quality:"))
        self.quality_value_label = QLabel("85")
        self.quality_value_label.setStyleSheet("font-weight: bold; color: #3498db;")
        quality_header.addWidget(self.quality_value_label)
        quality_header.addStretch()
        quality_layout.addLayout(quality_header)
        
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(85)
        self.quality_slider.setTickPosition(QSlider.TicksBelow)
        self.quality_slider.setTickInterval(25)
        quality_layout.addWidget(self.quality_slider)
        
        preset_layout = QHBoxLayout()
        self.low_quality_btn = QPushButton("Low (30)")
        self.medium_quality_btn = QPushButton("Medium (70)")
        self.high_quality_btn = QPushButton("High (85)")
        self.max_quality_btn = QPushButton("Max (95)")
        
        for btn in [self.low_quality_btn, self.medium_quality_btn, 
                   self.high_quality_btn, self.max_quality_btn]:
            btn.setMaximumWidth(80)
            preset_layout.addWidget(btn)
        
        quality_layout.addLayout(preset_layout)
        settings_layout.addWidget(quality_group)
        
        resize_group = QGroupBox("Resize Options")
        resize_layout = QVBoxLayout(resize_group)
        
        self.resize_checkbox = QCheckBox("Resize Image")
        resize_layout.addWidget(self.resize_checkbox)
        
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Max Width:"))
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 20000)
        self.width_spinbox.setValue(1920)
        self.width_spinbox.setEnabled(False)
        self.width_spinbox.setSuffix(" px")
        size_layout.addWidget(self.width_spinbox)
        
        size_layout.addWidget(QLabel("Max Height:"))
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(1, 20000)
        self.height_spinbox.setValue(1080)
        self.height_spinbox.setEnabled(False)
        self.height_spinbox.setSuffix(" px")
        size_layout.addWidget(self.height_spinbox)
        resize_layout.addLayout(size_layout)
        
        size_preset_layout = QHBoxLayout()
        self.size_4k_btn = QPushButton("4K")
        self.size_1080p_btn = QPushButton("1080p")
        self.size_720p_btn = QPushButton("720p")
        self.size_480p_btn = QPushButton("480p")
        
        for btn in [self.size_4k_btn, self.size_1080p_btn, 
                   self.size_720p_btn, self.size_480p_btn]:
            btn.setEnabled(False)
            btn.setMaximumWidth(60)
            size_preset_layout.addWidget(btn)
        
        size_preset_layout.addStretch()
        resize_layout.addLayout(size_preset_layout)
        settings_layout.addWidget(resize_group)
        
        layout.addWidget(settings_group)
        
        preview_group = QGroupBox("Compression Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel("Calculating preview...")
        self.preview_label.setWordWrap(True)
        self.preview_label.setFont(font)
        self.preview_label.setMinimumHeight(100)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2c3e50;
                border: 1px solid #34495e;
                border-radius: 4px;
                padding: 8px;
                color: #ecf0f1;
            }
        """)
        preview_layout.addWidget(self.preview_label)
        
        self.preview_progress = QProgressBar()
        self.preview_progress.setRange(0, 0)
        self.preview_progress.hide()
        preview_layout.addWidget(self.preview_progress)
        
        layout.addWidget(preview_group)
        
        button_layout = QHBoxLayout()
        self.compress_btn = QPushButton("Compress && Save")
        self.compress_btn.setDefault(True)
        self.compress_btn.setMinimumHeight(32)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(32)
        
        button_layout.addStretch()
        button_layout.addWidget(self.compress_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def connect_signals(self):
        self.quality_slider.valueChanged.connect(self.on_quality_changed)
        self.low_quality_btn.clicked.connect(lambda: self.set_quality(30))
        self.medium_quality_btn.clicked.connect(lambda: self.set_quality(70))
        self.high_quality_btn.clicked.connect(lambda: self.set_quality(85))
        self.max_quality_btn.clicked.connect(lambda: self.set_quality(95))
        
        self.format_combo.currentTextChanged.connect(self.on_settings_changed)
        self.resize_checkbox.toggled.connect(self.on_resize_toggled)
        self.width_spinbox.valueChanged.connect(self.on_settings_changed)
        self.height_spinbox.valueChanged.connect(self.on_settings_changed)
        
        self.size_4k_btn.clicked.connect(lambda: self.set_size(3840, 2160))
        self.size_1080p_btn.clicked.connect(lambda: self.set_size(1920, 1080))
        self.size_720p_btn.clicked.connect(lambda: self.set_size(1280, 720))
        self.size_480p_btn.clicked.connect(lambda: self.set_size(854, 480))
        
        self.compress_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
    
    def load_image_info(self):
        info = self.original_info
        size_mb = info['size'] / (1024 * 1024)
        
        info_text = f"""File: {self.image_name}
Size: {size_mb:.2f} MB ({info['size']:,} bytes)
Dimensions: {info['dimensions'][0]} × {info['dimensions'][1]} pixels
Format: {info['format']}
Mode: {info['mode']}"""
        
        self.image_info_label.setText(info_text)
    
    def on_quality_changed(self, value):
        self.quality_value_label.setText(f"{value}")
        self.schedule_preview_update()
    
    def on_settings_changed(self):
        self.schedule_preview_update()
    
    def on_resize_toggled(self, checked):
        self.width_spinbox.setEnabled(checked)
        self.height_spinbox.setEnabled(checked)
        for btn in [self.size_4k_btn, self.size_1080p_btn, self.size_720p_btn, self.size_480p_btn]:
            btn.setEnabled(checked)
        self.schedule_preview_update()
    
    def set_quality(self, quality):
        self.quality_slider.setValue(quality)
    
    def set_size(self, width, height):
        self.width_spinbox.setValue(width)
        self.height_spinbox.setValue(height)
    
    def schedule_preview_update(self):
        if self.preview_worker and self.preview_worker.isRunning():
            return
            
        self.preview_timer.stop()
        self.preview_timer.start(300)
    
    def update_preview(self):
        if self.preview_worker and self.preview_worker.isRunning():
            return
            
        try:
            self.preview_progress.show()
            self.preview_label.setText("Calculating preview...")
            
            quality = self.quality_slider.value()
            output_format = self.format_combo.currentData()
            max_size = None
            
            if self.resize_checkbox.isChecked():
                max_size = (self.width_spinbox.value(), self.height_spinbox.value())
            
            self.preview_worker = PreviewWorker(self.image_path, quality, output_format, max_size)
            self.preview_worker.preview_ready.connect(self.on_preview_ready)
            self.preview_worker.preview_error.connect(self.on_preview_error)
            self.preview_worker.finished.connect(self.on_preview_finished)
            self.preview_worker.start()
            
        except Exception as e:
            self.on_preview_error(f"Preview error: {str(e)}")
    
    def on_preview_ready(self, preview_info):
        self.preview_info = preview_info
        self.display_preview_info()
    
    def on_preview_error(self, error_msg):
        self.preview_label.setText(f"Preview failed: {error_msg}")
        self.preview_label.setStyleSheet(self.preview_label.styleSheet() + "color: #e74c3c;")
    
    def on_preview_finished(self):
        self.preview_progress.hide()
        if self.preview_worker:
            self.preview_worker.deleteLater()
            self.preview_worker = None
    
    def display_preview_info(self):
        if not self.preview_info:
            return
            
        info = self.preview_info
        
        original_mb = info.get('original_size', 0) / (1024 * 1024)
        compressed_mb = info.get('compressed_size', 0) / (1024 * 1024)
        
        ratio = info.get('compression_ratio', 0)
        size_ratio = info.get('size_ratio', 1.0)
        
        format_str = info.get('format', 'Unknown')
        quality = info.get('quality', 0)
        dimensions = info.get('dimensions', (0, 0))
        
        preview_text = f"""📊 Compression Results:

Original: {original_mb:.2f} MB
Compressed: {compressed_mb:.2f} MB
Reduction: {ratio:.1f}% ({size_ratio:.2f}x smaller)

📋 Output Settings:
Format: {format_str}
Quality: {quality}
Dimensions: {dimensions[0]} × {dimensions[1]}"""
        
        if ratio > 60:
            color = "#27ae60"
            status = "Excellent compression"
        elif ratio > 30:
            color = "#f39c12"
            status = "Good compression"
        elif ratio > 10:
            color = "#e67e22"
            status = "Fair compression"
        else:
            color = "#e74c3c"
            status = "Limited compression"
        
        preview_text += f"\n\n🎯 Status: {status}"
        
        self.preview_label.setText(preview_text)
        
        style = self.preview_label.styleSheet()
        base_style = style.split("color:")[0] if "color:" in style else style
        self.preview_label.setStyleSheet(f"{base_style}color: {color};")
    
    def get_compression_settings(self):
        max_size = None
        if self.resize_checkbox.isChecked():
            max_size = (self.width_spinbox.value(), self.height_spinbox.value())
        
        return {
            'quality': self.quality_slider.value(),
            'output_format': self.format_combo.currentData(),
            'max_size': max_size
        }
    
    def closeEvent(self, event):
        if self.preview_worker and self.preview_worker.isRunning():
            self.preview_worker.quit()
            self.preview_worker.wait()
        super().closeEvent(event)