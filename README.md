# 🖼️ Image Viewer 

> 一个功能强大的现代化图片查看应用程序，基于 PySide6 构建，集成 AI 图片超分辨率功能

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-6.9+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

## ✨ 核心特性

### 🎯 图片管理
- **智能分类**: 自动创建和管理图片文件夹
- **缩略图画廊**: 快速浏览和预览图片
- **拖拽导入**: 支持批量拖拽添加图片
- **重命名管理**: 批量重命名和整理功能

### 🔍 图片查看
-  **高级查看器**: 支持缩放、平移、旋转
-  **快速导航**: 键盘快捷键和鼠标操作
-  **全屏模式**: 沉浸式图片浏览体验
-  **智能缩放**: 自适应窗口大小和实际尺寸
-  **RealESRGAN 超分辨率**: 使用最先进的 AI 模型提升图片质量
-  **图片压缩**: 批量压缩图片减少文件大小
-  **内存优化**: 智能内存管理，处理大尺寸图片

## 🚀 快速开始

### 📋 系统要求

- **Python**: 3.9+ (推荐 3.11 或 3.12)
- **显卡**: 支持 CUDA 12.1 的 NVIDIA 显卡 (AI 功能)
- **内存**: 建议 8GB 以上 (处理大图片)
- **存储**: 至少 5GB 可用空间 (包含 AI 模型)

### 🔧 安装步骤

#### 方法一：使用 PDM (推荐)

```bash
# 克隆仓库
git clone https://github.com/Mrzhuo2022/imageviewer.git
cd imageviewer

# 安装 PDM (如果未安装)
pip install pdm

# 安装所有依赖
pdm install
```

#### 方法二：使用 pip

```bash
# 克隆仓库
git clone https://github.com/Mrzhuo2022/imageviewer.git
cd imageviewer

# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -r requirements.txt
```

### 🏃 运行应用

```bash
# 使用 PDM
pdm run python run.py

# 或直接运行
python run.py
```

### 📥 模型下载

首次运行时，应用会自动下载 AI 模型文件：
- `RealESRGAN_x4plus.pth` - 通用超分辨率模型
- `RealESRGAN_x4plus_anime_6B.pth` - 动画专用模型

> 💡 **提示**: 模型文件较大（约 65MB），首次下载需要一些时间

## 📁 项目结构

```
imageviewer/
├── src/
│   └── image_manager/          # 🏗️ 主要源码
│       ├── __init__.py
│       ├── config.py           # ⚙️ 配置文件
│       ├── image_utils.py      # 🛠️ 图片处理工具
│       ├── main_window.py      # 🖥️ 主窗口
│       └── widgets/            # 🧩 UI 组件
│           ├── image_viewer.py      # 🔍 图片查看器
│           ├── thumbnail_gallery.py # 🖼️ 缩略图画廊
│           ├── compression_dialog.py # 📦 压缩对话框
│           └── folder_selection_dialog.py # 📁 文件夹选择
├── icons/                      # 🎨 图标资源
│   ├── add.svg
│   ├── arrow-left.svg
│   ├── arrow-right.svg
│   ├── compress.svg
│   ├── delete.svg
│   ├── fit-to-window.svg
│   ├── fullscreen.svg
│   ├── import.svg
│   ├── info.svg
│   ├── panel-hide.svg
│   ├── panel-show.svg
│   ├── rename.svg
│   ├── upscale.svg
│   ├── zoom-actual.svg
│   ├── zoom-in.svg
│   └── zoom-out.svg
├── models/                     # 🤖 AI 模型文件
│   ├── RealESRGAN_x4plus.pth
│   └── RealESRGAN_x4plus_anime_6B.pth
├── image_library/              # 📚 图片库 (自动创建)
│   ├── 0/
│   ├── 1/
│   ├── 2/
│   └── 3/
├── pyproject.toml              # 📦 项目配置
├── pdm.lock                    # 🔒 依赖锁定
├── run.py                      # 🚀 启动入口
├── LICENSE                     # 📄 许可证
└── README.md                   # 📖 说明文档
```

## 🛠️ 技术栈

| 组件 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **GUI 框架** | PySide6 | 6.9+ | 现代化界面开发 |
| **图像处理** | Pillow | 11.3+ | 基础图像操作 |
| **AI 超分辨率** | RealESRGAN | 0.3+ | 图片质量提升 |
| **深度学习** | PyTorch | 2.3.1+cu121 | AI 模型运行 |
| **数值计算** | NumPy | <2.0 | 数组处理 |
| **系统监控** | psutil | 5.9+ | 系统资源监控 |
| **包管理** | PDM | - | 现代化包管理 |

## 🎮 使用指南

### 🖱️ 基本操作

#### 图片导入
1. **拖拽导入**: 直接拖拽图片或文件夹到应用窗口
2. **菜单导入**: 使用 `文件` → `导入` 菜单
3. **支持格式**: JPG, PNG, BMP, TIFF, WebP 等

#### 图片查看
- **缩放**: 鼠标滚轮或工具栏按钮
- **平移**: 鼠标拖拽或方向键
- **全屏**: 双击图片或按 `F11`
- **导航**: 左右箭头键或导航按钮

#### AI 超分辨率
1. 选择要处理的图片
2. 点击 `超分辨率` 按钮
3. 选择合适的模型（通用/动画）
4. 等待处理完成

### ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+O` | 打开文件 |
| `Ctrl+I` | 导入图片 |
| `F11` | 全屏/退出全屏 |
| `←/→` | 上一张/下一张 |
| `+/-` | 放大/缩小 |
| `Ctrl+0` | 实际尺寸 |
| `Ctrl+F` | 适应窗口 |
| `Delete` | 删除图片 |
| `F2` | 重命名 |

## 🔧 配置说明

### 配置文件位置
配置文件位于 `src/image_manager/config.py`，包含：

- **目录设置**: 图片库和缩略图目录
- **显示设置**: 缩略图大小、窗口样式
- **AI 设置**: 模型路径、处理参数
- **快捷键设置**: 自定义快捷键映射

### 环境变量
```bash
# 设置 Qt 图像内存限制 (MB)
QT_IMAGEIO_MAXALLOC=2048

# 设置 CUDA 设备 (可选)
CUDA_VISIBLE_DEVICES=0
```

## 🤖 故障排除

### 常见问题

#### 1. 模型加载失败
```bash
# 检查模型文件是否存在
ls models/
# 重新下载模型
# 应用会在启动时自动下载缺失的模型
```

#### 2. CUDA 相关错误
```bash
# 检查 CUDA 安装
nvidia-smi
# 检查 PyTorch CUDA 支持
python -c "import torch; print(torch.cuda.is_available())"
```

#### 3. 内存不足
- 关闭其他大型应用程序
- 降低图片分辨率
- 检查可用内存: `任务管理器` → `性能` → `内存`

#### 4. 图片显示异常
- 检查图片格式是否支持
- 尝试重新导入图片
- 清理缩略图缓存

### 性能优化

#### 提升处理速度
1. **使用 SSD**: 提高文件读写速度
2. **增加内存**: 处理大图片时减少交换
3. **升级显卡**: 使用更强的 GPU 进行 AI 处理

#### 减少内存使用
1. **关闭不必要的窗口**: 只保留当前使用的功能
2. **清理图片库**: 定期删除不需要的图片
3. **调整缩略图大小**: 在配置中减小缩略图尺寸

## 🤝 贡献指南

### 🐛 报告问题

如果您遇到任何问题，请在 [GitHub Issues](https://github.com/Mrzhuo2022/imageviewer/issues) 中报告，包含：

1. **系统信息**: 操作系统、Python 版本
2. **错误信息**: 完整的错误堆栈
3. **重现步骤**: 详细的操作步骤
4. **预期行为**: 您期望的结果

### 🔧 开发环境

1. Fork 本仓库
2. 创建功能分支: `git checkout -b feature/amazing-feature`
3. 安装开发依赖: `pdm install --dev`
4. 进行更改并添加测试
5. 提交更改: `git commit -m 'Add amazing feature'`
6. 推送到分支: `git push origin feature/amazing-feature`
7. 创建 Pull Request

### 📝 代码规范

- 使用 **Black** 进行代码格式化
- 遵循 **PEP 8** 编码规范
- 添加必要的文档字符串
- 编写单元测试

## 🙏 致谢

感谢以下开源项目和贡献者：

- [RealESRGAN](https://github.com/xinntao/Real-ESRGAN) - 强大的图片超分辨率算法
- [PySide6](https://wiki.qt.io/Qt_for_Python) - Python Qt 绑定
- [Pillow](https://pillow.readthedocs.io/) - Python 图像处理库
- [PyTorch](https://pytorch.org/) - 深度学习框架

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

<p align="center">
  <strong>⭐ 如果这个项目对您有帮助，请给我们一个 Star！</strong>
</p>

<p align="center">
  Made with ❤️ by <a href="https://github.com/Mrzhuo2022">evarle</a>
</p>
