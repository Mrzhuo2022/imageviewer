import shutil
import uuid
import json
import time
import psutil
import gc
from pathlib import Path
from PIL import Image
import numpy as np
import logging

# --- PyTorch & RealESRGAN Support ---
try:
    import torch
    from realesrgan import RealESRGANer
    from basicsr.archs.rrdbnet_arch import RRDBNet
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False

from .config import ROOT_DIR, LIBRARY_DIR, INTERNAL_DATA_DIR, THUMBNAIL_DIR, METADATA_FILE, THUMBNAIL_SIZE

# Setup logger
log = logging.getLogger(__name__)
# Create separate logger for compression to avoid confusion with upscaling logs
compression_log = logging.getLogger(f"{__name__}.compression")
# Ensure basicsr logger (used by RealESRGANer) propagates to root logger
# This allows our custom LogEmitter in main_window.py to capture its messages
logging.getLogger('basicsr').propagate = True
logging.getLogger('basicsr').setLevel(logging.INFO) # Ensure basicsr logs are INFO level

# --- GPU & Environment Utilities ---

def get_system_memory_info():
    """
    Gets available system RAM and total GPU VRAM.
    """
    ram = psutil.virtual_memory()
    available_ram_mb = ram.available / (1024**2)
    
    gpu_memory_mb = 0
    if PYTORCH_AVAILABLE and torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        gpu_memory_mb = props.total_memory / (1024**2)

    return {"ram_available_mb": available_ram_mb, "gpu_total_mb": gpu_memory_mb}


def clear_gpu_cache():
    """
    Clears the GPU memory cache for PyTorch.
    """
    gc.collect()
    if PYTORCH_AVAILABLE and torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        log.info("Cleared PyTorch GPU cache.")


# --- File and Metadata Management ---

def ensure_library_folders_exist():
    """Creates the necessary library and thumbnail directories."""
    LIBRARY_DIR.mkdir(exist_ok=True)
    INTERNAL_DATA_DIR.mkdir(exist_ok=True)
    THUMBNAIL_DIR.mkdir(exist_ok=True)


def load_metadata():
    """Loads the image library metadata from the JSON file."""
    if METADATA_FILE.exists() and METADATA_FILE.stat().st_size > 0:
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.warning(f"Metadata file {METADATA_FILE} is corrupted. Starting fresh.")
            return {}
    return {}


def save_metadata(metadata):
    """Saves the image library metadata to the JSON file."""
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)


def get_unique_filename(directory, base_name, suffix):
    """Generates a unique filename to avoid collisions."""
    file_path = directory / f"{base_name}{suffix}"
    counter = 1
    while file_path.exists():
        file_path = directory / f"{base_name}_{counter}{suffix}"
        counter += 1
    return file_path.name


def add_image_to_library(original_path, target_subfolder=""):
    """Copies an image to the library, creates a thumbnail, and updates metadata."""
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

    width, height = 0, 0
    try:
        with Image.open(library_path) as img:
            width, height = img.size
            img.thumbnail(THUMBNAIL_SIZE)
            img.save(thumbnail_path, "WEBP", quality=85)
    except Exception as e:
        log.error(f"Could not process image {original_path.name}: {e}")
        # Clean up if thumbnail generation fails
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
    """Removes an image and its thumbnail from the library and metadata."""
    metadata = load_metadata()
    if image_id in metadata:
        item_data = metadata.pop(image_id)
        Path(item_data["library_path"]).unlink(missing_ok=True)
        Path(item_data["thumbnail_path"]).unlink(missing_ok=True)
        save_metadata(metadata)
        log.info(f"Removed image: {image_id}")
    else:
        log.warning(f"Image ID {image_id} not found in metadata.")


# --- Core Upscaling Logic ---

def get_model_scale_factor(model_path):
    """Infers the model's scale factor from its filename."""
    model_name = Path(model_path).stem.lower()
    if 'x8' in model_name: return 8
    if 'x4' in model_name: return 4
    if 'x2' in model_name: return 2
    return 4 # Default scale


def get_available_models():
    """Finds all available .pth models in the 'models' directory."""
    models_dir = ROOT_DIR / "models"
    available_models = []
    if models_dir.is_dir():
        for file in sorted(models_dir.iterdir()):
            if file.suffix.lower() == '.pth':
                if not PYTORCH_AVAILABLE:
                    continue # Skip PyTorch models if environment is not set up
                available_models.append({"name": file.stem, "path": str(file), "type": 'PyTorch'})
    return available_models


def upscale_image(image_path, model_path, progress_callback=None, max_output_size=None):
    """
    Dispatches the upscaling task to the appropriate engine based on model type.
    Args:
        image_path: Path to input image
        model_path: Path to model file
        progress_callback: Optional progress callback function
        max_output_size: Optional tuple (width, height) to limit output size
    """
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
    """
    Upscales an image using PyTorch and RealESRGAN, with optional output size limiting.
    Args:
        max_output_size: Optional tuple (width, height) to limit output size
    """

    def run_upscale_attempt(tile_size):
        """Inner function to run a single upscale attempt."""
        upsampler = None
        model = None
        try:
            log.info(f"Initializing PyTorch upsampler with tile size: {tile_size if tile_size > 0 else 'Disabled'}")
            if progress_callback: progress_callback(5)
            
            model_name = Path(model_path).stem.lower()
            scale = get_model_scale_factor(model_path)
            num_block = 6 if 'anime' in model_name else 23
            
            log.info(f"Loading image {Path(image_path).name}...")
            if progress_callback: progress_callback(10)
            img = Image.open(image_path).convert('RGB')
            img_np = np.array(img)
            
            # Check if we need to limit output size
            original_size = (img.width, img.height)
            target_size = (img.width * scale, img.height * scale)
            
            if max_output_size:
                max_w, max_h = max_output_size
                if target_size[0] > max_w or target_size[1] > max_h:
                    # Calculate scale factor to fit within limits
                    scale_w = max_w / target_size[0]
                    scale_h = max_h / target_size[1]
                    limit_scale = min(scale_w, scale_h)
                    
                    new_target_size = (int(target_size[0] * limit_scale), int(target_size[1] * limit_scale))
                    log.info(f"Limiting output size: {target_size} → {new_target_size}")
                    target_size = new_target_size
            
            log.info(f"Processing: {img.width}x{img.height} → {target_size[0]}x{target_size[1]}")
            if progress_callback: progress_callback(15)

            log.info(f"Initializing model: {Path(model_path).name}")
            if progress_callback: progress_callback(20)
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=num_block, num_grow_ch=32, scale=scale)
            
            # Calculate outscale based on target size vs model scale
            outscale = min(target_size[0] / img.width, target_size[1] / img.height)
            
            upsampler = RealESRGANer(
                scale=scale, model_path=model_path, model=model, tile=tile_size,
                tile_pad=10, pre_pad=0, half=True, device=torch.device('cuda')
            )
            log.info("RealESRGANer initialized successfully")
            if progress_callback: progress_callback(30)

            log.info("Starting PyTorch inference...")
            if progress_callback: progress_callback(35)
            start_time = time.time()
            
            # Enhanced progress tracking during inference
            log.info("Processing image with AI model...")
            if progress_callback: progress_callback(50)
            
            output, _ = upsampler.enhance(img_np, outscale=outscale)
            inference_time = time.time() - start_time
            log.info(f"PyTorch inference complete in {inference_time:.2f}s.")
            if progress_callback: progress_callback(85)
            
            log.info("Post-processing and converting image...")
            if progress_callback: progress_callback(95)
            result_image = Image.fromarray(output)
            
            # Final resize if needed to match exact target size
            if result_image.size != target_size:
                result_image = result_image.resize(target_size, Image.Resampling.LANCZOS)
                log.info(f"Resized to target: {result_image.size}")
            
            log.info("Upscaling completed successfully")
            if progress_callback: progress_callback(100)
            
            return result_image
            
        except Exception as e:
            log.error(f"Upscaling error: {e}")
            raise
        finally:
            log.info("Cleaning up GPU memory...")
            del upsampler, model
            clear_gpu_cache()

    # --- Main logic for _upscale_with_pytorch ---
    log.info("Starting PyTorch upscaling process...")
    clear_gpu_cache()
    if not torch.cuda.is_available():
        log.error("CUDA is not available for PyTorch.")
        raise RuntimeError("CUDA is not available for PyTorch.")
    
    log.info("CUDA is available, proceeding with GPU acceleration")
    if progress_callback: progress_callback(2)

    try:
        # Attempt 1: No tiling
        log.info("Attempting upscaling without tiling...")
        result_img = run_upscale_attempt(tile_size=0)
        return result_img
    except torch.cuda.OutOfMemoryError:
        log.warning("CUDA out of memory on first attempt. Retrying with tiling...")
        if progress_callback: progress_callback(30)  # Reset progress for retry
        clear_gpu_cache() # Clean up before the next attempt
        
        # Attempt 2: With tiling
        log.info("Attempting upscaling with tiling (512px tiles)...")
        result_img = run_upscale_attempt(tile_size=512)
        return result_img


# --- Image Compression Functions ---

def _get_optimal_compression_params(output_format, quality):
    """Get optimal compression parameters for different formats."""
    params = {}
    
    if output_format == 'JPEG':
        params = {
            'quality': max(1, min(100, quality)),
            'optimize': True,
            'progressive': quality >= 75,  # Progressive only for higher quality
            'subsampling': 0 if quality >= 95 else -1  # No subsampling for highest quality
        }
    elif output_format == 'PNG':
        # PNG compression level (0-9, higher = better compression but slower)
        compress_level = max(0, min(9, int((100 - quality) / 10)))
        params = {
            'compress_level': compress_level,
            'optimize': True
        }
    elif output_format == 'WEBP':
        params = {
            'quality': max(1, min(100, quality)),
            'optimize': True,
            'method': 6 if quality >= 80 else 4,  # Better method for higher quality
            'lossless': quality >= 98  # Lossless for very high quality
        }
    
    return params


def _convert_image_mode(img, target_format):
    """Convert image mode appropriately for target format."""
    if target_format == 'JPEG':
        if img.mode in ('RGBA', 'LA'):
            # Create white background for transparency
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'LA':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1])
            return background
        elif img.mode == 'P':
            # Convert palette to RGB/RGBA first
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
        # PNG supports all modes, but optimize for common cases
        if img.mode == 'P' and len(img.getcolors() or []) <= 256:
            return img  # Keep palette mode for small color count
        elif img.mode in ('LA', 'RGBA'):
            return img  # Keep alpha channel
        elif img.mode == 'L':
            return img  # Keep grayscale
    elif target_format == 'WEBP':
        # WebP supports RGB and RGBA
        if img.mode in ('RGBA', 'LA'):
            return img.convert('RGBA')
        else:
            return img.convert('RGB')
    
    return img


def compress_image(image_path, quality=85, output_format=None, max_size=None, progress_callback=None):
    """
    Compress an image with specified quality and optional resizing.
    
    Args:
        image_path: Path to input image
        quality: Compression quality (1-100)
        output_format: Output format ('JPEG', 'PNG', 'WEBP') or None to keep original
        max_size: Optional tuple (width, height) to resize image before compression
        progress_callback: Optional progress callback function
    
    Returns:
        Tuple of (PIL.Image, format_str, save_params) or (None, None, None) if failed
    """
    image_path = Path(image_path)
    
    if not image_path.exists():
        log.error(f"Image file not found: {image_path}")
        return None, None, None
        
    try:
        compression_log.info(f"Starting compression for {image_path.name}")
        if progress_callback:
            progress_callback(5)
        
        # Open image with context manager
        with Image.open(image_path) as original_img:
            # Determine output format
            if output_format is None:
                output_format = original_img.format or 'JPEG'
            
            if progress_callback:
                progress_callback(15)
            
            # Convert image mode if needed
            img = _convert_image_mode(original_img, output_format)
            
            if progress_callback:
                progress_callback(30)
            
            # Apply resizing if specified
            if max_size and (img.width > max_size[0] or img.height > max_size[1]):
                original_size = img.size
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                compression_log.info(f"Resized from {original_size} to {img.size}")
            
            if progress_callback:
                progress_callback(60)
            
            # Get compression parameters
            save_params = _get_optimal_compression_params(output_format, quality)
            
            if progress_callback:
                progress_callback(80)
            
            # Create a copy to avoid modifying original
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
    """
    Get compression preview with file size estimation.
    
    Args:
        image_path: Path to input image
        quality: Compression quality (1-100)
        output_format: Output format
        max_size: Optional resize dimensions
    
    Returns:
        Dictionary with compression info or None if failed
    """
    try:
        import io
        
        image_path = Path(image_path)
        if not image_path.exists():
            compression_log.error(f"Image file not found for preview: {image_path}")
            return None
        
        # Get original file size
        original_size = image_path.stat().st_size
        
        # Compress image
        compressed_img, fmt, save_params = compress_image(
            image_path, quality, output_format, max_size
        )
        
        if compressed_img is None:
            return None
        
        # Calculate compressed size by saving to memory buffer
        with io.BytesIO() as buffer:
            compressed_img.save(buffer, format=fmt, **save_params)
            compressed_size = buffer.tell()
        
        # Calculate compression metrics
        if original_size > 0:
            compression_ratio = ((original_size - compressed_size) / original_size) * 100
            size_ratio = compressed_size / original_size
        else:
            compression_ratio = 0
            size_ratio = 1
        
        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': max(0, compression_ratio),  # Ensure non-negative
            'size_ratio': size_ratio,
            'format': fmt,
            'quality': quality,
            'dimensions': compressed_img.size,
            'original_dimensions': None  # Will be filled by caller if needed
        }
        
    except Exception as e:
        compression_log.error(f"Compression preview failed for {Path(image_path).name}: {e}")
        return None


def save_compressed_image(image_path, output_path, quality=85, output_format=None, max_size=None, progress_callback=None):
    """
    Compress and save an image to specified path.
    
    Args:
        image_path: Path to input image
        output_path: Path to save compressed image
        quality: Compression quality (1-100)
        output_format: Output format
        max_size: Optional resize dimensions
        progress_callback: Optional progress callback function
    
    Returns:
        True if successful, False otherwise
    """
    try:
        output_path = Path(output_path)
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Get compressed image data
        compressed_img, fmt, save_params = compress_image(
            image_path, quality, output_format, max_size, progress_callback
        )
        
        if compressed_img is None:
            compression_log.error(f"Failed to compress image: {Path(image_path).name}")
            return False
        
        # Save compressed image
        compressed_img.save(output_path, format=fmt, **save_params)
        
        # Verify the file was saved successfully
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