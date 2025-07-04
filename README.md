# Image Manager

> 一个基于 PySide6 的现代化图片管理应用程序

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-6.0+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## ✨ 特性

- 🖼️ 缩略图浏览和分类管理
- 🔍 图片查看器（缩放、平移、导航）
- 🤖 AI 图片超分辨率（RealESRGAN）
- 📁 拖拽导入支持

## 🚀 快速开始

### 环境要求

- Python 3.8+
- PDM (推荐) 或 pip

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/image-manager.git
cd image-manager

# 使用 PDM 安装依赖
pdm install

# 或使用 pip
pip install -r requirements.txt
```

### 运行

```bash
# 使用 PDM
pdm run python run.py

# 或直接运行
python run.py
```

## 📁 项目结构

```
├── src/image_manager/    # 主要源码
├── icons/               # 图标资源
├── models/              # AI 模型文件
├── pyproject.toml       # 项目配置
└── run.py              # 启动入口
```

## 🛠️ 技术栈

- **GUI**: PySide6 (Qt6)
- **图像处理**: Pillow
- **AI 模型**: ONNX Runtime
- **包管理**: PDM

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
