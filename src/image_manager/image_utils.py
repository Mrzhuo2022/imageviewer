
import shutil
import uuid
import json
import time # Import time module
from pathlib import Path
from PIL import Image

from .config import LIBRARY_DIR, THUMBNAIL_DIR, THUMBNAIL_SIZE, METADATA_FILE, INTERNAL_DATA_DIR

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

