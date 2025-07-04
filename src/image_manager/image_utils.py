import shutil
import uuid
import json
import time # Import time module
from pathlib import Path
from PIL import Image
import numpy as np
import onnxruntime as ort

from .config import LIBRARY_DIR, THUMBNAIL_DIR, THUMBNAIL_SIZE, METADATA_FILE, INTERNAL_DATA_DIR, ROOT_DIR

def get_unique_filename(directory, base_name, suffix):
    """Generate a unique filename by adding a number suffix if the file already exists."""
    file_path = directory / f"{base_name}{suffix}"
    counter = 1
    while file_path.exists():
        file_path = directory / f"{base_name}_{counter}{suffix}"
        counter += 1
    return file_path.name

def ensure_library_folders_exist():
    """Creates the necessary image and thumbnail directories if they don't exist."""
    LIBRARY_DIR.mkdir(exist_ok=True)
    INTERNAL_DATA_DIR.mkdir(exist_ok=True) # Create the internal data directory
    THUMBNAIL_DIR.mkdir(exist_ok=True)

def load_metadata():
    """Loads image metadata from the JSON file."""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {METADATA_FILE} is empty or contains invalid JSON. Returning empty metadata.")
                return {}
    return {}

def save_metadata(metadata):
    """Saves image metadata to the JSON file."""
    print("Saving metadata...") # Debug print
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4)
    print("Metadata saved.") # Debug print

def process_and_copy_image(original_path, target_subfolder=""):
    """Copies an image to the library, creates a thumbnail, and returns all relevant data."""
    original_path = Path(original_path)
    
    # Generate a unique ID for the image
    image_id = str(uuid.uuid4())
    suffix = original_path.suffix.lower()
    
    # Determine paths for the new image and thumbnail
    target_folder = LIBRARY_DIR / target_subfolder
    target_folder.mkdir(parents=True, exist_ok=True) # Ensure subfolder exists

    library_file_name = f"{image_id}{suffix}"
    thumbnail_file_name = f"{image_id}{suffix}"

    library_path = target_folder / library_file_name
    thumbnail_path = THUMBNAIL_DIR / thumbnail_file_name

    # Ensure unique file names
    library_file_name = get_unique_filename(target_folder, image_id, suffix)
    thumbnail_file_name = get_unique_filename(THUMBNAIL_DIR, image_id, suffix)

    library_path = target_folder / library_file_name
    thumbnail_path = THUMBNAIL_DIR / thumbnail_file_name

    # 1. Copy file to library
    shutil.copy2(original_path, library_path)

    # 2. Create thumbnail and get metadata
    width, height = 0, 0
    try:
        with Image.open(library_path) as img:
            width, height = img.size
            img.thumbnail(THUMBNAIL_SIZE)
            img.save(thumbnail_path)
            print(f"Thumbnail saved to: {thumbnail_path}") # Debug print
    except Exception as e:
        print(f"Warning: Could not process image {original_path.name}: {e}")
        # If image processing fails, still record basic metadata
        pass

    # 3. Update metadata
    metadata = load_metadata()
    metadata[image_id] = {
        "original_filename": original_path.name,
        "library_path": str(library_path),
        "thumbnail_path": str(thumbnail_path),
        "width": width,
        "height": height,
        "size_bytes": library_path.stat().st_size,
        "subfolder": target_subfolder, # Store the subfolder information
        "timestamp": time.time() # Add timestamp
    }
    save_metadata(metadata)

    # 4. Return data for UI update (optional, as UI will reload from metadata)
    item_data = metadata[image_id]
    item_data["image_id"] = image_id # Add image_id to the item_data dictionary
    return item_data

def get_model_scale_factor(model_path):
    """Determine the scale factor based on the model filename."""
    model_name = Path(model_path).stem.lower()
    if 'x2' in model_name:
        return 2
    elif 'x4' in model_name:
        return 4
    else:
        # Default to 4 if can't determine
        return 4

def upscale_image(image_path, model_path, progress_callback=None):
    """
    Upscale an image using ONNX RealESRGAN model.
    
    Args:
        image_path: Path to the input image
        model_path: Path to the ONNX model
        progress_callback: Optional progress callback function
    
    Returns:
        PIL Image or None if failed
    """
    try:
        # Determine device - prioritize CPU to avoid memory issues
        providers = ['CPUExecutionProvider']  # Force CPU for stability
        print("Using CPUExecutionProvider (CPU) for stability")

        # Determine scale factor from model name
        scale_factor = get_model_scale_factor(model_path)
        print(f"Scale factor: {scale_factor}")

        # Load ONNX model
        if not Path(model_path).exists():
            raise FileNotFoundError(f"ONNX model not found at {model_path}")
        
        try:
            session = ort.InferenceSession(str(model_path), providers=providers)
        except Exception as e:
            print(f"Failed to load ONNX model: {e}")
            return None
            
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        
        # Get input shape requirements
        input_shape = session.get_inputs()[0].shape
        print(f"Model input shape: {input_shape}")

        # Load and prepare image
        img = Image.open(image_path).convert("RGB")
        original_width, original_height = img.size
        print(f"Original image dimensions: {original_width}x{original_height}")
        
        # Calculate expected output size
        expected_output_width = original_width * scale_factor
        expected_output_height = original_height * scale_factor
        expected_memory_mb = (expected_output_width * expected_output_height * 3 * 4) / (1024 * 1024)
        
        print(f"Expected output dimensions: {expected_output_width}x{expected_output_height}")
        print(f"Expected memory usage: {expected_memory_mb:.1f} MB")
        
        # If image is too large, use tiling
        max_memory_mb = 100  # Limit to 100MB to be safe
        use_tiling = expected_memory_mb > max_memory_mb
        
        if use_tiling:
            print(f"Image too large ({expected_memory_mb:.1f}MB), using tiling...")
            return upscale_image_tiled(img, session, input_name, output_name, scale_factor, progress_callback)
        else:
            return upscale_image_direct(img, session, input_name, output_name, scale_factor, progress_callback)
        
    except Exception as e:
        print(f"Error during upscaling: {e}")
        import traceback
        traceback.print_exc()
        return None

def upscale_image_direct(img, session, input_name, output_name, scale_factor, progress_callback=None):
    """Direct upscaling without tiling"""
    try:
        original_width, original_height = img.size
        
        # Ensure image dimensions are multiples of scale_factor
        width, height = img.size
        
        # Calculate padding needed
        pad_width = (scale_factor - (width % scale_factor)) % scale_factor
        pad_height = (scale_factor - (height % scale_factor)) % scale_factor
        
        print(f"Padding needed: {pad_width}x{pad_height}")

        if pad_width > 0 or pad_height > 0:
            # Create padded image
            padded_img = Image.new('RGB', (width + pad_width, height + pad_height), (0, 0, 0))
            padded_img.paste(img, (0, 0))
            img = padded_img
            print(f"Padded image dimensions: {img.size}")

        if progress_callback:
            progress_callback(20)

        # Convert to numpy array and normalize
        img_np = np.array(img).astype(np.float32) / 255.0
        img_np = np.transpose(img_np, (2, 0, 1))  # HWC to CHW
        img_np = np.expand_dims(img_np, axis=0)  # Add batch dimension
        
        print(f"Input tensor shape: {img_np.shape}")
        
        if progress_callback:
            progress_callback(40)

        # Run inference
        try:
            output = session.run([output_name], {input_name: img_np})[0]
            print(f"Output tensor shape: {output.shape}")
        except Exception as e:
            print(f"Inference failed: {e}")
            return None
            
        if progress_callback:
            progress_callback(80)

        # Post-process output
        output = np.squeeze(output, axis=0)  # Remove batch dimension
        output = np.transpose(output, (1, 2, 0))  # CHW to HWC
        
        # Process in chunks to avoid memory issues
        try:
            output = np.clip(output * 255.0, 0, 255).astype(np.uint8)
        except Exception as e:
            print(f"Memory error during post-processing: {e}")
            print("Trying chunk-wise processing...")
            # Process in horizontal chunks
            chunk_size = 500  # Smaller chunks for better memory management
            processed_chunks = []
            try:
                for i in range(0, output.shape[0], chunk_size):
                    chunk = output[i:i+chunk_size]
                    chunk = np.clip(chunk * 255.0, 0, 255).astype(np.uint8)
                    processed_chunks.append(chunk)
                output = np.concatenate(processed_chunks, axis=0)
            except Exception as chunk_error:
                print(f"Chunk processing also failed: {chunk_error}")
                return None
        
        upscaled_img = Image.fromarray(output)
        print(f"Upscaled image dimensions: {upscaled_img.size}")

        # Crop back to the expected dimensions (remove padding effects)
        expected_width = original_width * scale_factor
        expected_height = original_height * scale_factor
        
        print(f"Expected final dimensions: {expected_width}x{expected_height}")
        
        if upscaled_img.size[0] >= expected_width and upscaled_img.size[1] >= expected_height:
            upscaled_img = upscaled_img.crop((0, 0, expected_width, expected_height))
            print(f"Final cropped dimensions: {upscaled_img.size}")

        if progress_callback:
            progress_callback(100)

        return upscaled_img
        
    except Exception as e:
        print(f"Error during direct upscaling: {e}")
        import traceback
        traceback.print_exc()
        return None

def upscale_image_tiled(img, session, input_name, output_name, scale_factor, progress_callback=None):
    """Upscale image using tiling to reduce memory usage"""
    try:
        original_width, original_height = img.size
        tile_size = 512  # Process in 512x512 tiles
        overlap = 64     # Overlap between tiles to avoid seams
        
        print(f"Using tiling with tile size: {tile_size}x{tile_size}, overlap: {overlap}")
        
        # Calculate number of tiles
        tiles_x = (original_width + tile_size - 1) // tile_size
        tiles_y = (original_height + tile_size - 1) // tile_size
        total_tiles = tiles_x * tiles_y
        
        print(f"Processing {total_tiles} tiles ({tiles_x}x{tiles_y})")
        
        # Create output image
        output_width = original_width * scale_factor
        output_height = original_height * scale_factor
        output_img = Image.new('RGB', (output_width, output_height))
        
        tile_count = 0
        
        for y in range(tiles_y):
            for x in range(tiles_x):
                # Calculate tile boundaries
                x_start = x * tile_size
                y_start = y * tile_size
                x_end = min(x_start + tile_size, original_width)
                y_end = min(y_start + tile_size, original_height)
                
                # Extract tile with overlap
                tile_x_start = max(0, x_start - overlap)
                tile_y_start = max(0, y_start - overlap)
                tile_x_end = min(original_width, x_end + overlap)
                tile_y_end = min(original_height, y_end + overlap)
                
                tile = img.crop((tile_x_start, tile_y_start, tile_x_end, tile_y_end))
                
                # Pad tile if necessary
                tile_width, tile_height = tile.size
                pad_width = (scale_factor - (tile_width % scale_factor)) % scale_factor
                pad_height = (scale_factor - (tile_height % scale_factor)) % scale_factor
                
                if pad_width > 0 or pad_height > 0:
                    padded_tile = Image.new('RGB', (tile_width + pad_width, tile_height + pad_height), (0, 0, 0))
                    padded_tile.paste(tile, (0, 0))
                    tile = padded_tile
                
                # Process tile
                tile_np = np.array(tile).astype(np.float32) / 255.0
                tile_np = np.transpose(tile_np, (2, 0, 1))
                tile_np = np.expand_dims(tile_np, axis=0)
                
                try:
                    tile_output = session.run([output_name], {input_name: tile_np})[0]
                    
                    # Post-process tile
                    tile_output = np.squeeze(tile_output, axis=0)
                    tile_output = np.transpose(tile_output, (1, 2, 0))
                    tile_output = np.clip(tile_output * 255.0, 0, 255).astype(np.uint8)
                    
                    upscaled_tile = Image.fromarray(tile_output)
                    
                    # Calculate where to paste in output image
                    output_x_start = x_start * scale_factor
                    output_y_start = y_start * scale_factor
                    output_x_end = x_end * scale_factor
                    output_y_end = y_end * scale_factor
                    
                    # Calculate crop area from upscaled tile (remove overlap)
                    crop_x_start = (x_start - tile_x_start) * scale_factor
                    crop_y_start = (y_start - tile_y_start) * scale_factor
                    crop_x_end = crop_x_start + (output_x_end - output_x_start)
                    crop_y_end = crop_y_start + (output_y_end - output_y_start)
                    
                    cropped_tile = upscaled_tile.crop((crop_x_start, crop_y_start, crop_x_end, crop_y_end))
                    
                    # Paste into output image
                    output_img.paste(cropped_tile, (output_x_start, output_y_start))
                    
                except Exception as e:
                    print(f"Error processing tile {tile_count}: {e}")
                    continue
                
                tile_count += 1
                
                # Update progress
                if progress_callback:
                    progress = int(20 + (tile_count / total_tiles) * 80)
                    progress_callback(progress)
        
        if progress_callback:
            progress_callback(100)
        
        print(f"Tiled upscaling completed. Final size: {output_img.size}")
        return output_img
        
    except Exception as e:
        print(f"Error during tiled upscaling: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_image_metadata_for_folder(folder_name="", recursive=False):
    """
    Retrieves image metadata for a specific folder or all images.
    If recursive is True, includes images from subfolders.
    """
    all_metadata = load_metadata()
    filtered_metadata = {}

    if folder_name == "": # "All" category
        if recursive:
            return all_metadata # Return all metadata if recursive is true for "All"
        else: # Non-recursive "All" (should not happen with current logic, but for completeness)
            for image_id, item_data in all_metadata.items():
                item_subfolder = item_data.get("subfolder", "")
                if '/' not in item_subfolder and '\\' not in item_subfolder: # Only top-level images
                    filtered_metadata[image_id] = item_data
            return filtered_metadata
    else: # Specific folder
        target_folder_path = Path(folder_name).as_posix()
        for image_id, item_data in all_metadata.items():
            item_subfolder = Path(item_data.get("subfolder", "")).as_posix()
            if recursive:
                if item_subfolder == target_folder_path or item_subfolder.startswith(f"{target_folder_path}/"):
                    filtered_metadata[image_id] = item_data
            else:
                if item_subfolder == target_folder_path:
                    filtered_metadata[image_id] = item_data
        return filtered_metadata

def get_available_upscale_models():
    """
    Lists available ONNX upscale models in the 'models' directory.
    Returns a list of (model_name, file_path) tuples.
    """
    models_dir = ROOT_DIR / "models"
    available_models = []
    if models_dir.exists() and models_dir.is_dir():
        for file in models_dir.iterdir():
            if file.suffix == ".onnx":
                available_models.append((file.stem, str(file)))
    return available_models

def remove_image_files(image_id):

    """Deletes the main image and its thumbnail file from the library and removes metadata."""
    metadata = load_metadata()
    if image_id in metadata:
        item_data = metadata[image_id]
        Path(item_data["library_path"]).unlink(missing_ok=True)
        Path(item_data["thumbnail_path"]).unlink(missing_ok=True)
        del metadata[image_id]
        save_metadata(metadata)
    else:
        print(f"Warning: Image ID {image_id} not found in metadata.")

