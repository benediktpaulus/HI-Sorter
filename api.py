import os
import logging
import shutil
import tempfile
import uuid
import webview # Use pywebview for dialogs
from webview import FileDialog
import logic

logger = logging.getLogger(__name__)

class Api:
    def __init__(self):
        self.image_list = []
        self.current_index = -1
        self.last_move = None  # {'type': 'move'|'delete', ...}
        self.window = None
        self.current_year_root = None
        self.parent_folder = None
        # --- OPTIMIZATION: Add a cache for folder trees ---
        # This will store the folder structure for each year to prevent re-reading from disk
        self.folder_tree_cache = {}
        # Trash directory for safe deletes (enables undo)
        self.trash_dir = None

    def select_folder(self, title):
        """Uses pywebview's native folder dialog with defensive error handling."""
        if not self.window:
            logger.warning("select_folder called before window binding")
            return None
        try:
            logger.info("Opening folder dialog: %s", title)
            try:
                result = self.window.create_file_dialog(FileDialog.FOLDER)
            except AttributeError:
                result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            folder = result[0] if result else None
            logger.info("Folder selected: %s", folder)
            return folder
        except Exception as e:
            logger.exception("Folder dialog failed: %s", e)
            return None

    def initialize_session(self, unsorted_folder, parent_folder):
        try:
            if not unsorted_folder or not os.path.isdir(unsorted_folder):
                return {'error': f'Unsorted folder invalid or not found: {unsorted_folder}'}
            if not parent_folder or not os.path.isdir(parent_folder):
                return {'error': f'Parent folder invalid or not found: {parent_folder}'}

            self.image_list = logic.get_sorted_image_list(unsorted_folder)
            if not self.image_list:
                return {'error': 'No images found in the selected folder.'}
            
            # --- OPTIMIZATION: Reset state including the cache ---
            self.current_index = 0
            self.last_move = None
            self.folder_tree_cache = {} # Clear cache for new session
            # Persist trash under the selected parent folder
            self.parent_folder = parent_folder
            self.trash_dir = os.path.join(self.parent_folder, 'trash')
            os.makedirs(self.trash_dir, exist_ok=True)
            
            first_image_path = self.image_list[self.current_index]
            year = logic.get_year_from_image(first_image_path)
            if not year:
                return {'error': f'Could not determine year for: {os.path.basename(first_image_path)}'}

            year_folder_path = os.path.join(self.parent_folder, str(year))
            if not os.path.isdir(year_folder_path):
                os.makedirs(year_folder_path)
            self.current_year_root = year_folder_path

            # --- OPTIMIZATION: Initial population of the cache ---
            # The folder tree is fetched once and stored.
            folder_tree = logic.get_folder_tree(year_folder_path)
            self.folder_tree_cache[str(year)] = folder_tree
            
            return self._get_current_state(year=year, folder_tree=folder_tree)
        except Exception as e:
            logger.exception("initialize_session failed: %s", e)
            return {'error': str(e)}

    def create_folder(self, parent_path, name):
        """Create a new subfolder and return updated tree."""
        try:
            if not self.current_year_root:
                return {'error': 'Session not initialized'}
            if not parent_path or not os.path.isdir(parent_path):
                return {'error': f'Parent path invalid: {parent_path}'}
            
            normalized_parent = os.path.abspath(parent_path)
            root = os.path.abspath(self.current_year_root)
            if not normalized_parent.startswith(root):
                return {'error': 'Parent path outside of allowed root'}
            
            logic.create_folder(normalized_parent, name)
            
            # --- OPTIMIZATION: Update cache after modification ---
            # Instead of reading again on next image, we update the cache now.
            year = os.path.basename(root)
            self.folder_tree_cache[str(year)] = logic.get_folder_tree(root)
            
            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("create_folder failed: %s", e)
            return {'error': str(e)}

    def delete_folder(self, folder_path):
        """Delete an empty folder and return updated tree."""
        try:
            if not self.current_year_root:
                return {'error': 'Session not initialized'}
            if not folder_path or not os.path.isdir(folder_path):
                return {'error': f'Folder invalid: {folder_path}'}
            
            normalized = os.path.abspath(folder_path)
            root = os.path.abspath(self.current_year_root)
            if normalized == root:
                return {'error': 'Cannot delete the root year folder'}
            if not normalized.startswith(root):
                return {'error': 'Folder outside of allowed root'}
            
            logic.delete_folder(normalized)

            # --- OPTIMIZATION: Update cache after modification ---
            year = os.path.basename(root)
            self.folder_tree_cache[str(year)] = logic.get_folder_tree(root)

            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("delete_folder failed: %s", e)
            return {'error': str(e)}

    def delete_current_image(self):
        """Deletes the current image by moving it to the persistent trash (undoable)."""
        if self._is_queue_empty():
            return self._get_current_state()

        try:
            current_image = self.image_list[self.current_index]
            # Instead of hard delete, move to session trash to allow undo
            trash_name = f"{uuid.uuid4()}_{os.path.basename(current_image)}"
            if not self.trash_dir:
                # Prefer persistent trash under the selected parent folder
                if self.parent_folder:
                    self.trash_dir = os.path.join(self.parent_folder, 'trash')
                    os.makedirs(self.trash_dir, exist_ok=True)
                else:
                    # Fallback to a shared temp trash if parent is unknown (shouldn't happen in session)
                    base_trash = os.path.join(tempfile.gettempdir(), 'picture_sorter_trash')
                    os.makedirs(base_trash, exist_ok=True)
                    self.trash_dir = base_trash
            trash_path = os.path.join(self.trash_dir, trash_name)
            try:
                shutil.move(current_image, trash_path)
            except Exception:
                # Fallback: hard delete if move fails (undo won't be possible)
                try:
                    logic.delete_single_file(current_image)
                    trash_path = None
                except Exception:
                    # If even deletion fails, keep state unchanged and report
                    raise
            self.image_list.pop(self.current_index)
            # Record deletions for undo when we have a trash_path
            if trash_path:
                self.last_move = {'type': 'delete', 'source': current_image, 'trash': trash_path}
            else:
                self.last_move = None
            self._clamp_index()
            # This call is now fast because of the cache
            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("delete_current_image failed: %s", e)
            return {'error': str(e)}

    def delete_range(self, count):
        """
        Deletes a range of images starting from the current image (inclusive).
        Files are moved to the persistent trash under the Parent folder for safe undo.
        """
        if self._is_queue_empty():
            return self._get_current_state()

        try:
            try:
                n = int(count)
            except Exception:
                return {'error': f'Invalid count: {count}'}
            if n <= 0:
                return self._get_current_state()

            remaining = len(self.image_list) - max(self.current_index, 0)
            n = max(0, min(n, remaining))
            if n == 0:
                return self._get_current_state()

            # Ensure persistent trash dir exists
            if not self.trash_dir:
                if self.parent_folder:
                    self.trash_dir = os.path.join(self.parent_folder, 'trash')
                    os.makedirs(self.trash_dir, exist_ok=True)
                else:
                    base_trash = os.path.join(tempfile.gettempdir(), 'picture_sorter_trash')
                    os.makedirs(base_trash, exist_ok=True)
                    self.trash_dir = base_trash

            deleted = []  # entries with {'source', 'trash'} for undo
            for _ in range(n):
                current_image = self.image_list[self.current_index]
                trash_name = f"{uuid.uuid4()}_{os.path.basename(current_image)}"
                trash_path = os.path.join(self.trash_dir, trash_name)
                try:
                    shutil.move(current_image, trash_path)
                    deleted.append({'source': current_image, 'trash': trash_path})
                except Exception:
                    # Fallback: hard delete if move fails (undo won't be possible for this file)
                    try:
                        logic.delete_single_file(current_image)
                        # Do not append to 'deleted' for undo when permanently deleted
                    except Exception:
                        # If even deletion fails, stop batch and report error
                        raise
                # Remove from queue at current index
                self.image_list.pop(self.current_index)

            self._clamp_index()
            # Record batch deletion for undo when at least one file is in trash
            if deleted:
                self.last_move = {'type': 'batch-delete', 'deleted': deleted}
            else:
                # Nothing salvageable to undo
                self.last_move = None

            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("delete_range failed: %s", e)
            return {'error': str(e)}

    def sort_current_image(self, destination_path):
        """Moves the current image and prepares the undo action."""
        if self._is_queue_empty():
            return self._get_current_state()
        
        try:
            source_path = self.image_list[self.current_index]
            final_path = logic.move_single_file(source_path, destination_path)
            self.last_move = {'type': 'move', 'source': source_path, 'destination': final_path}
            self.image_list.pop(self.current_index)
            self._clamp_index()
            # This call is now fast because of the cache
            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("sort_current_image failed: %s", e)
            return {'error': str(e)}

    def sort_range(self, destination_path, count):
        """
        Moves a range of images starting from the current image (inclusive).
        - destination_path: target folder path
        - count: number of images to move (will be clamped to remaining queue)

        Returns updated state. Also records a batch move for undo.
        """
        try:
            if not destination_path:
                return {'error': 'Destination path is required'}
            if self._is_queue_empty():
                return self._get_current_state()

            # Normalize and clamp count
            try:
                n = int(count)
            except Exception:
                return {'error': f'Invalid count: {count}'}
            if n <= 0:
                return self._get_current_state()
            remaining = len(self.image_list) - max(self.current_index, 0)
            n = max(0, min(n, remaining))
            if n == 0:
                return self._get_current_state()

            moved = []
            # Always move from current_index repeatedly; after each pop, the next item becomes current
            for _ in range(n):
                src = self.image_list[self.current_index]
                dst = logic.move_single_file(src, destination_path)
                moved.append({'source': src, 'destination': dst})
                self.image_list.pop(self.current_index)
                # no need to increment index because list shrinks at current position
            self._clamp_index()
            self.last_move = {'type': 'batch-move', 'moved': moved}
            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("sort_range failed: %s", e)
            return {'error': str(e)}

    def undo_last_move(self):
        """Reverses the last file move action."""
        if not self.last_move:
            return {'error': 'There is no action to undo.'}
        
        try:
            if self.last_move.get('type') == 'move':
                # Move back from destination to original folder
                logic.move_single_file(self.last_move['destination'], os.path.dirname(self.last_move['source']))
                self.image_list.insert(self.current_index, self.last_move['source'])
                self.last_move = None
            elif self.last_move.get('type') == 'batch-move':
                # Restore all files in reverse order back to their original folders
                moved_list = self.last_move.get('moved') or []
                for item in reversed(moved_list):
                    src = item['destination']
                    dst_folder = os.path.dirname(item['source'])
                    restored_path = logic.move_single_file(src, dst_folder)
                    # Reinsert at current_index to maintain original order in queue
                    self.image_list.insert(self.current_index, restored_path)
                self.last_move = None
            elif self.last_move.get('type') == 'batch-delete':
                # Restore deleted files from trash (where available), reverse order
                deleted_list = self.last_move.get('deleted') or []
                for item in reversed(deleted_list):
                    src_trash = item['trash']
                    original = item['source']
                    target = original
                    if os.path.exists(target):
                        root, ext = os.path.splitext(original)
                        candidate = f"{root} (restored){ext}"
                        counter = 2
                        while os.path.exists(candidate):
                            candidate = f"{root} (restored {counter}){ext}"
                            counter += 1
                        target = candidate
                    shutil.move(src_trash, target)
                    self.image_list.insert(self.current_index, target)
                self.last_move = None
            elif self.last_move.get('type') == 'delete':
                # Restore from trash to original location
                src_trash = self.last_move['trash']
                original = self.last_move['source']
                target = original
                # Resolve name conflicts by appending " (restored)"
                if os.path.exists(target):
                    root, ext = os.path.splitext(original)
                    candidate = f"{root} (restored){ext}"
                    counter = 2
                    while os.path.exists(candidate):
                        candidate = f"{root} (restored {counter}){ext}"
                        counter += 1
                    target = candidate
                shutil.move(src_trash, target)
                # Insert back into queue so it becomes current
                self.image_list.insert(self.current_index, target)
                self.last_move = None
            else:
                return {'error': 'Unknown undo action type.'}
            # This call is now fast because of the cache
            return self._year_state_wrapper()
        except Exception as e:
            logger.exception("undo_last_move failed: %s", e)
            return {'error': f'Undo failed: {e}'}

    def _year_state_wrapper(self):
        """
        Ensure the response contains correct year & folder tree for current image.
        
        OPTIMIZED: This method now uses a cache to avoid slow, repetitive
        disk reads for the folder tree. It only queries the disk if the
        year changes to one not yet seen in the current session.
        """
        if self._is_queue_empty():
            return self._get_current_state()
        try:
            current_image = self.image_list[self.current_index]
            year = logic.get_year_from_image(current_image)
            
            if not year:
                # Use cached tree from the previous year if year can't be determined
                folder_tree = self.folder_tree_cache.get(os.path.basename(self.current_year_root))
                return self._get_current_state(folder_tree=folder_tree)
            
            desired_year_root = os.path.join(self.parent_folder, str(year))
            
            if desired_year_root != self.current_year_root:
                if not os.path.isdir(desired_year_root):
                    os.makedirs(desired_year_root)
                self.current_year_root = desired_year_root

            # --- THE CORE OPTIMIZATION ---
            # 1. Check if the tree for the current year is already in our cache.
            year_key = str(year)
            if year_key in self.folder_tree_cache:
                # 2. If yes, use the cached version (fast).
                folder_tree = self.folder_tree_cache[year_key]
            else:
                # 3. If no, read it from disk (slower) and save it to the cache for next time.
                folder_tree = logic.get_folder_tree(self.current_year_root)
                self.folder_tree_cache[year_key] = folder_tree
                
            return self._get_current_state(year=year, folder_tree=folder_tree)
        except Exception as e:
            logger.exception("_year_state_wrapper failed: %s", e)
            return self._get_current_state()

    # --- Helper methods ---
    def _is_queue_empty(self):
        return not self.image_list or self.current_index < 0
    
    def _clamp_index(self):
        """Ensures the index is valid after an item is removed."""
        if self.current_index >= len(self.image_list) and len(self.image_list) > 0:
            self.current_index = len(self.image_list) - 1

    def _get_current_state(self, year=None, folder_tree=None):
        """Packages the current state for the UI."""
        state = {'can_undo': self.last_move is not None}
        if self.current_year_root:
            state['current_year_root'] = self.current_year_root

        if self._is_queue_empty():
            state.update({
                'current_image_path': None,
                'current_index': -1,
                'total_images': 0,
                'next_image_paths': []  # Next previews
            })
        else:
            start = self.current_index + 1
            end = start + 30  # Show next 30 images in preview
            next_paths = self.image_list[start:end]
            
            state.update({
                'current_image_path': self.image_list[self.current_index],
                'current_index': self.current_index,
                'total_images': len(self.image_list),
                'next_image_paths': next_paths
            })
            
        if year: state['year'] = year
        if folder_tree is not None: state['folder_tree'] = folder_tree
        return state