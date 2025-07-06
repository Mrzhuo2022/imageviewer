import gc
import json
import logging
import shutil
import time
import uuid
from pathlib import Path

import numpy as np
import psutil
from PIL import Image

try:
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False

from .config import (
    INTERNAL_DATA_DIR,
    LIBRARY_DIR,
    METADATA_FILE,
    ROOT_DIR,
    THUMBNAIL_DIR,
    THUMBNAIL_SIZE,
)

log = logging.getLogger(__name__)
compression_log = logging.getLogger(f"{__name__}.compression")

if PYTORCH_AVAILABLE:
    logging.getLogger('basicsr').propagate = True
    logging.getLogger('basicsr').setLevel(logging.INFO)


def get_system_memory_info():
    ram = psutil.virtual_memory()
    available_ram_mb = ram.available / (1024**2)
    
    gpu_memory_mb = 0
    if PYTORCH_AVAILABLE and torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        gpu_memory_mb = props.total_memory / (1024**2)

    return {"ram_available_mb": available_ram_mb, "gpu_total_mb": gpu_memory_mb}


def clear_gpu_cache():
    gc.collect()
    if PYTORCH_AVAILABLE and torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        log.info("Cleared PyTorch GPU cache.")


def ensure_library_folders_exist():
    LIBRARY_DIR.mkdir(exist_ok=True)
    INTERNAL_DATA_DIR.mkdir(exist_ok=True)
    THUMBNAIL_DIR.mkdir(exist_ok=True)


def load_metadata():
    if METADATA_FILE.exists() and METADATA_FILE.stat().st_size > 0:
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.warning(f"Metadata file {METADATA_FILE} is corrupted. Starting fresh.")
            return {}
    return {}


def save_metadata(metadata):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)


def get_unique_filename(directory, base_name, suffix):
    file_path = directory / f"{base_name}{suffix}"
    counter = 1
    while file_path.exists():
        file_path = directory / f"{base_name}_{counter}{suffix}"
        counter += 1
    return file_path.name


def add_image_to_library(original_path, target_subfolder=""):
    original_path = Path(original_path)
    image_id = str(uuid.uuid4())
    suffix = original_path.suffix.lower()
    
    target_folder = LIBRARY_DIR / target_subfolder
    target_folder.mkdir(parents=True, exist_ok=True)

    library_file_name = get_unique_filename(target_folder, image_id, suffix)
    thumbnail_file_name = get_unique_filename(THUMBNAIL_DIR, image_id, ".webp")

    library_path = target_folder / library_file_name
    thumbnail_path = THUMBNAIL_DIR / thumbnail_file_name

    shutil.copy2(original_path, library_path)

    try:
        with Image.open(library_path) as img:
            width, height = img.size
            img.thumbnail(THUMBNAIL_SIZE)
            img.save(thumbnail_path, "WEBP", quality=85)
    except Exception as e:
        log.error(f"Could not process image {original_path.name}: {e}")
        library_path.unlink(missing_ok=True)
        return None

    metadata = load_metadata()
    metadata[image_id] = {
        "original_filename": original_path.name,
        "library_path": str(library_path.as_posix()),
        "thumbnail_path": str(thumbnail_path.as_posix()),
        "width": width,
        "height": height,
        "size_bytes": library_path.stat().st_size,
        "subfolder": target_subfolder,
        "timestamp": time.time()
    }
    save_metadata(metadata)
    
    item_data = metadata[image_id]
    item_data["image_id"] = image_id
    return item_data


def remove_image_from_library(image_id):
    metadata = load_metadata()
    if image_id in metadata:
        item_data = metadata.pop(image_id)
        Path(item_data["library_path"]).unlink(missing_ok=True)
        Path(item_data["thumbnail_path"]).unlink(missing_ok=True)
        save_metadata(metadata)
        log.info(f"Removed image: {image_id}")
    else:
        log.warning(f"Image ID {image_id} not found in metadata.")


def get_model_scale_factor(model_path):
    model_name = Path(model_path).stem.lower()
    if 'x8' in model_name:
        return 8
    if 'x4' in model_name:
        return 4
    if 'x2' in model_name:
        return 2
    return 4


def get_available_models():
    models_dir = ROOT_DIR / "models"
    available_models = []
    if models_dir.is_dir():
        for file in sorted(models_dir.iterdir()):
            if file.suffix.lower() == '.pth' and PYTORCH_AVAILABLE:
                available_models.append({"name": file.stem, "path": str(file), "type": 'PyTorch'})
    return available_models


def upscale_image(image_path, model_path, progress_callback=None, max_output_size=None):
    model_path = Path(model_path)
    log.info(f"Starting upscale task for {image_path} with model {model_path.name}")

    try:
        if model_path.suffix.lower() == '.pth':
            if PYTORCH_AVAILABLE:
                log.info("Using PyTorch RealESRGAN engine.")
                return _upscale_with_pytorch(image_path, str(model_path), progress_callback, max_output_size)
            else:
                log.error("Cannot process .pth model: PyTorch/RealESRGAN not available.")
                return None
        else:
            log.error(f"Unsupported model format: {model_path.suffix}. Only .pth models are supported.")
            return None
    except Exception as e:
        log.error(f"An unexpected error occurred during upscaling: {e}", exc_info=True)
        clear_gpu_cache()
        return None


def _upscale_with_pytorch(image_path, model_path, progress_callback=None, max_output_size=None):
    def run_upscale_attempt(tile_size):
        upsampler = None
        model = None
        try:
            log.info(f"Initializing PyTorch upsampler with tile size: {tile_size if tile_size > 0 else 'Disabled'}")
            if progress_callback:
                progress_callback(5)
            
            model_name = Path(model_path).stem.lower()
            scale = get_model_scale_factor(model_path)
            num_block = 6 if 'anime' in model_name else 23
            
            log.info(f"Loading image {Path(image_path).name}...")
            if progress_callback:
                progress_callback(10)
            
            img = Image.open(image_path).convert('RGB')
            img_np = np.array(img)
            
            original_size = (img.width, img.height)
            target_size = (img.width * scale, img.height * scale)
            
            if max_output_size:
                max_w, max_h = max_output_size
                if target_size[0] > max_w or target_size[1] > max_h:
                    scale_w = max_w / target_size[0]
                    scale_h = max_h / target_size[1]
                    limit_scale = min(scale_w, scale_h)
                    target_size = (int(target_size[0] * limit_scale), int(target_size[1] * limit_scale))
                    log.info(f"Limiting output size: {original_size} → {target_size}")
            
            log.info(f"Processing: {img.width}x{img.height} → {target_size[0]}x{target_size[1]}")
            if progress_callback:
                progress_callback(15)

            if progress_callback:
                progress_callback(20)
            
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=num_block, num_grow_ch=32, scale=scale)
            outscale = min(target_size[0] / img.width, target_size[1] / img.height)
            
            upsampler = RealESRGANer(
                scale=scale, model_path=model_path, model=model, tile=tile_size,
                tile_pad=10, pre_pad=0, half=True, device=torch.device('cuda')
            )
            
            if progress_callback:
                progress_callback(30)

            log.info("Starting PyTorch inference...")
            if progress_callback:
                progress_callback(35)
            
            start_time = time.time()
            if progress_callback:
                progress_callback(50)
            
            output, _ = upsampler.enhance(img_np, outscale=outscale)
            inference_time = time.time() - start_time
            log.info(f"PyTorch inference complete in {inference_time:.2f}s.")
            if progress_callback:
                progress_callback(85)
            
            if progress_callback:
                progress_callback(95)
            
            result_image = Image.fromarray(output)
            
            if result_image.size != target_size:
                result_image = result_image.resize(target_size, Image.Resampling.LANCZOS)
            
            log.info("Upscaling completed successfully")
            if progress_callback:
                progress_callback(100)
            
            return result_image
            
        except Exception as e:
            log.error(f"Upscaling error: {e}")
            raise
        finally:
            del upsampler, model
            clear_gpu_cache()

    log.info("Starting PyTorch upscaling process...")
    clear_gpu_cache()
    if not torch.cuda.is_available():
        log.error("CUDA is not available for PyTorch.")
        raise RuntimeError("CUDA is not available for PyTorch.")
    
    log.info("CUDA is available, proceeding with GPU acceleration")
    if progress_callback:
        progress_callback(2)

    try:
        log.info("Attempting upscaling without tiling...")
        result_img = run_upscale_attempt(tile_size=0)
        return result_img
    except torch.cuda.OutOfMemoryError:
        log.warning("CUDA out of memory on first attempt. Retrying with tiling...")
        if progress_callback:
            progress_callback(30)
        clear_gpu_cache()
        
        log.info("Attempting upscaling with tiling (512px tiles)...")
        result_img = run_upscale_attempt(tile_size=512)
        return result_img


def _get_optimal_compression_params(output_format, quality):
    if output_format == 'JPEG':
        return {
            'quality': max(1, min(100, quality)),
            'optimize': True,
            'progressive': quality >= 75,
            'subsampling': 0 if quality >= 95 else -1
        }
    elif output_format == 'PNG':
        return {
            'compress_level': max(0, min(9, int((100 - quality) / 10))),
            'optimize': True
        }
    elif output_format == 'WEBP':
        return {
            'quality': max(1, min(100, quality)),
            'optimize': True,
            'method': 6 if quality >= 80 else 4,
            'lossless': quality >= 98
        }
    return {}


def _convert_image_mode(img, target_format):
    if target_format == 'JPEG':
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'LA':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1])
            return background
        elif img.mode == 'P':
            if img.info.get('transparency') is not None:
                img = img.convert('RGBA')
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                return background
            else:
                return img.convert('RGB')
        elif img.mode not in ('RGB', 'L'):
            return img.convert('RGB')
    elif target_format == 'PNG':
        if img.mode == 'P' and len(img.getcolors() or []) <= 256:
            return img
        elif img.mode in ('LA', 'RGBA'):
            return img
        elif img.mode == 'L':
            return img
    elif target_format == 'WEBP':
        if img.mode in ('RGBA', 'LA'):
            return img.convert('RGBA')
        else:
            return img.convert('RGB')
    
    return img


def compress_image(image_path, quality=85, output_format=None, max_size=None, progress_callback=None):
    image_path = Path(image_path)
    
    if not image_path.exists():
        log.error(f"Image file not found: {image_path}")
        return None, None, None
        
    try:
        compression_log.info(f"Starting compression for {image_path.name}")
        if progress_callback:
            progress_callback(5)
        
        with Image.open(image_path) as original_img:
            if output_format is None:
                output_format = original_img.format or 'JPEG'
            
            if progress_callback:
                progress_callback(15)
            
            img = _convert_image_mode(original_img, output_format)
            
            if progress_callback:
                progress_callback(30)
            
            if max_size and (img.width > max_size[0] or img.height > max_size[1]):
                original_size = img.size
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                compression_log.info(f"Resized from {original_size} to {img.size}")
            
            if progress_callback:
                progress_callback(60)
            
            save_params = _get_optimal_compression_params(output_format, quality)
            
            if progress_callback:
                progress_callback(80)
            
            compressed_img = img.copy() if img is not original_img else original_img.copy()
            
            if progress_callback:
                progress_callback(100)
            
            compression_log.info(f"Compression prepared: {output_format}, quality {quality}, size {compressed_img.size}")
            return compressed_img, output_format, save_params
            
    except (OSError, IOError) as e:
        log.error(f"Failed to open/process image {image_path.name}: {e}")
        return None, None, None
    except Exception as e:
        log.error(f"Unexpected error during compression of {image_path.name}: {e}")
        return None, None, None


def get_compression_preview(image_path, quality=85, output_format=None, max_size=None):
    try:
        import io
        
        image_path = Path(image_path)
        if not image_path.exists():
            compression_log.error(f"Image file not found for preview: {image_path}")
            return None
        
        original_size = image_path.stat().st_size
        
        compressed_img, fmt, save_params = compress_image(
            image_path, quality, output_format, max_size
        )
        
        if compressed_img is None:
            return None
        
        with io.BytesIO() as buffer:
            compressed_img.save(buffer, format=fmt, **save_params)
            compressed_size = buffer.tell()
        
        if original_size > 0:
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
            size_ratio = compressed_size / original_size
        else:
            compression_ratio = 0
            size_ratio = 1
        
        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': max(0, compression_ratio),
            'size_ratio': size_ratio,
            'format': fmt,
            'quality': quality,
            'dimensions': compressed_img.size,
            'original_dimensions': None
        }
        
    except Exception as e:
        compression_log.error(f"Compression preview failed for {Path(image_path).name}: {e}")
        return None


def save_compressed_image(image_path, output_path, quality=85, output_format=None, max_size=None, progress_callback=None):
    try:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        compressed_img, fmt, save_params = compress_image(
            image_path, quality, output_format, max_size, progress_callback
        )
        
        if compressed_img is None:
            compression_log.error(f"Failed to compress image: {Path(image_path).name}")
            return False
        
        compressed_img.save(output_path, format=fmt, **save_params)
        
        if output_path.exists() and output_path.stat().st_size > 0:
            compression_log.info(f"Compressed image saved successfully: {output_path.name} ({output_path.stat().st_size} bytes)")
            return True
        else:
            compression_log.error(f"Failed to save compressed image or file is empty: {output_path}")
            return False
        
    except (OSError, IOError) as e:
        compression_log.error(f"I/O error saving compressed image to {output_path}: {e}")
        return False
    except Exception as e:
        compression_log.error(f"Unexpected error saving compressed image to {output_path}: {e}")
        return False