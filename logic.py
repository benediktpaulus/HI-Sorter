import os
import shutil
import datetime
from PIL import Image
from PIL.ExifTags import TAGS

def get_sorted_image_list(folder_path):
    """Return list of image file paths in folder sorted by mtime (oldest first).

    Defensive checks:
      * Returns empty list if folder doesn't exist or inaccessible.
      * Skips files that raise OSError when obtaining mtime.
    """
    if not folder_path or not os.path.isdir(folder_path):
        return []
    images = []
    supported_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
    try:
        entries = os.listdir(folder_path)
    except OSError:
        return []
    for filename in entries:
        if filename.lower().endswith(supported_extensions):
            full_path = os.path.join(folder_path, filename)
            if os.path.isfile(full_path):
                try:
                    os.path.getmtime(full_path)  # pre-flight check
                    images.append(full_path)
                except OSError:
                    continue
    images.sort(key=lambda f: os.path.getmtime(f))
    return images

def get_year_from_image(image_path):
    """Gets the creation year from a single image file."""
    year = None
    try: # EXIF
        with Image.open(image_path) as img:
            exif = img._getexif()
            if exif:
                for tag, value in exif.items():
                    if TAGS.get(tag) == "DateTimeOriginal":
                        year = datetime.datetime.strptime(value, "%Y:%m:%d %H:%M:%S").year
                        break
    except Exception: pass
    
    if not year: # Fallback
        try:
            mtime = os.path.getmtime(image_path)
            year = datetime.datetime.fromtimestamp(mtime).year
        except Exception: pass
        
    return year

def get_folder_tree(root_path):
    """
    Recursively scans a directory and builds a nested dictionary
    representing the folder tree.
    """
    tree = []
    if not os.path.isdir(root_path):
        return tree
    for item in sorted(os.listdir(root_path)):
        path = os.path.join(root_path, item)
        if os.path.isdir(path):
            node = {
                'name': item,
                'path': path,
                'children': get_folder_tree(path)
            }
            tree.append(node)
    return tree

def move_single_file(source_path, destination_folder):
    """Moves a single file to a destination folder."""
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")
    
    filename = os.path.basename(source_path)
    destination_path = os.path.join(destination_folder, filename)
    shutil.move(source_path, destination_path)
    return destination_path

def delete_single_file(file_path):
    """Permanently deletes a single file."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File to delete not found: {file_path}")
    os.remove(file_path)

def create_folder(parent_path, name):
    """Create a new subfolder inside parent_path.

    Safety:
      * parent_path must exist and be a directory
      * name must be a simple relative folder name (no path separators)
      * returns the full created path
      * if already exists as directory -> returns path (idempotent)
    """
    if not parent_path or not os.path.isdir(parent_path):
        raise FileNotFoundError(f"Parent folder not found: {parent_path}")
    if not name or any(sep in name for sep in (os.sep, '/', '\\')):
        raise ValueError("Invalid folder name")
    new_path = os.path.join(parent_path, name)
    if os.path.isdir(new_path):
        return new_path
    os.makedirs(new_path, exist_ok=True)
    return new_path

def delete_folder(folder_path):
    """Delete an empty folder. Raises if not empty.

    We avoid recursive deletion to reduce risk of data loss. The caller
    should ensure the folder is empty (excluding system files).
    """
    if not folder_path or not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")
    # Check emptiness (ignore hidden system artifacts like .DS_Store, Thumbs.db)
    entries = [e for e in os.listdir(folder_path) if e not in ('.DS_Store', 'Thumbs.db')]
    if entries:
        raise OSError("Folder is not empty")
    os.rmdir(folder_path)