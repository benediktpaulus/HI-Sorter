const THEME_STORAGE_KEY = 'pictureSorterTheme';
const rootElement = document.documentElement;
const prefersDarkScheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
let currentTheme = localStorage.getItem(THEME_STORAGE_KEY) || (prefersDarkScheme ? 'dark' : 'light');

function setThemeAttribute(theme) {
    currentTheme = theme;
    if (rootElement) {
        rootElement.setAttribute('data-theme', theme);
    }
}

function persistTheme(theme) {
    try {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch (_) {
        /* no-op if storage blocked */
    }
}

function updateThemeToggleControl(theme) {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    const icon = toggle.querySelector('.theme-toggle__icon');
    const label = toggle.querySelector('.theme-toggle__label');
    const nextThemeLabel = theme === 'dark' ? 'Light mode' : 'Dark mode';
    if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
    if (label) label.textContent = nextThemeLabel;
    toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    toggle.setAttribute('title', `Switch to ${nextThemeLabel}`);
}

function setTheme(theme, { persist = true } = {}) {
    setThemeAttribute(theme);
    if (persist) persistTheme(theme);
    updateThemeToggleControl(theme);
}

function toggleTheme() {
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
}

setThemeAttribute(currentTheme);

function initThemeToggle() {
    updateThemeToggleControl(currentTheme);
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
        toggle.addEventListener('click', toggleTheme);
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeToggle);
} else {
    initThemeToggle();
}

if (window.matchMedia) {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    if (media?.addEventListener) {
        media.addEventListener('change', (event) => {
            const storedChoice = localStorage.getItem(THEME_STORAGE_KEY);
            if (storedChoice) return; // user preference overrides system changes
            setTheme(event.matches ? 'dark' : 'light', { persist: false });
        });
    }
}

window.addEventListener('pywebviewready', function () {
    const ui = {
        unsortedBtn: document.getElementById('select-unsorted-btn'),
        parentBtn: document.getElementById('select-parent-btn'),
        deleteBtn: document.getElementById('delete-btn'),
        undoBtn: document.getElementById('undo-btn'),
        unsortedPathEl: document.getElementById('unsorted-path'),
        parentPathEl: document.getElementById('parent-path'),
        treeEl: document.getElementById('folder-tree'),
        imageContainer: document.getElementById('image-container'),
        imageCounter: document.getElementById('image-counter'),
        loadingOverlay: document.getElementById('loading-overlay'),
        previewContainer: document.getElementById('preview-images-container'),
        selectionIndicator: document.getElementById('selection-indicator'),
    };
    let currentYearRootPath = null;
    let selectedCount = 0; // number of images selected from current to a clicked preview

    // Keep exactly one branch of the folder tree open across updates
    let openLeafPath = null; // deepest path that should remain open
    let isSyncingOpenState = false; // prevents re-entrant toggle handling

    function normalizePath(p) {
        if (!p) return '';
        return p.replace(/\\/g, '/').replace(/\/+$/, '');
    }
    function isAncestorOrEqual(ancestor, descendant) {
        const a = normalizePath(ancestor);
        const d = normalizePath(descendant);
        if (!a || !d) return false;
        return d === a || d.startsWith(a + '/');
    }
    function getParentPath(p) {
        const n = normalizePath(p);
        const i = n.lastIndexOf('/');
        return i > 0 ? n.slice(0, i) : '';
    }
    function syncTreeOpenState() {
        if (!ui.treeEl) return;
        isSyncingOpenState = true;
        const detailsList = ui.treeEl.querySelectorAll('details[data-path]');
        detailsList.forEach(det => {
            const nodePath = det.getAttribute('data-path');
            const shouldOpen = !!openLeafPath && isAncestorOrEqual(nodePath, openLeafPath);
            det.open = shouldOpen;
        });
        isSyncingOpenState = false;
    }

    // ================= Hotkey Mapping (1-9 / Numpad1-9) =================
    // We map up to 9 destination folders to digits 1..9. When a folder is clicked
    // it gets (or reuses) a hotkey. If all 9 are filled and a new folder is clicked,
    // we evict the least recently used folder (based solely on the oldest lastUsedTimestamp).
    const hotkeySlots = {}; // key -> { key, path, name, usageCount, lastUsedTimestamp }
    const pathToKey = new Map();
    const MAX_SLOTS = 9;

    function assignHotkeyForPath(folderPath, folderName) {
        if (!folderPath) return;
        if (pathToKey.has(folderPath)) {
            // Already mapped: bump usage stats
            const key = pathToKey.get(folderPath);
            const slot = hotkeySlots[key];
            slot.usageCount++;
            slot.lastUsedTimestamp = Date.now();
            refreshHotkeyBadges();
            return key;
        }
        const freeKey = findFirstFreeKey();
        if (freeKey) {
            hotkeySlots[freeKey] = {
                key: freeKey,
                path: folderPath,
                name: folderName,
                usageCount: 1,
                lastUsedTimestamp: Date.now()
            };
            pathToKey.set(folderPath, freeKey);
            refreshHotkeyBadges();
            return freeKey;
        }
        // Need eviction
        const victimKey = selectEvictionKey();
        if (victimKey) {
            pathToKey.delete(hotkeySlots[victimKey].path);
            hotkeySlots[victimKey] = {
                key: victimKey,
                path: folderPath,
                name: folderName,
                usageCount: 1,
                lastUsedTimestamp: Date.now()
            };
            pathToKey.set(folderPath, victimKey);
            refreshHotkeyBadges();
            return victimKey;
        }
    }

    function findFirstFreeKey() {
        for (let i = 1; i <= MAX_SLOTS; i++) {
            const k = String(i);
            if (!hotkeySlots[k]) return k;
        }
        return null;
    }

    function selectEvictionKey() {
        const slots = Object.values(hotkeySlots);
        if (slots.length < MAX_SLOTS) return null;
        // Evict the least recently used (LRU): the one with the oldest lastUsedTimestamp
        let oldest = slots[0];
        for (let i = 1; i < slots.length; i++) {
            if (slots[i].lastUsedTimestamp < oldest.lastUsedTimestamp) {
                oldest = slots[i];
            }
        }
        return oldest?.key;
    }

    function refreshHotkeyBadges() {
        // Clear old badges
        document.querySelectorAll('.folder-hotkey-badge').forEach(el => el.remove());
        // Annotate current tree
        const spans = ui.treeEl.querySelectorAll('span.folder-text');
        spans.forEach(span => {
            const path = span.getAttribute('data-path');
            if (!path) return;
            const key = pathToKey.get(path);
            if (!key) return;
            const badge = document.createElement('sup');
            badge.className = 'folder-hotkey-badge';
            badge.textContent = key;
            badge.style.marginLeft = '4px';
            badge.style.color = 'var(--color-hotkey-muted)';
            span.appendChild(badge);
        });
        renderHotkeyLegend();
    }

    function renderHotkeyLegend() {
        let legend = document.getElementById('hotkey-legend');
        if (!legend) {
            legend = document.createElement('div');
            legend.id = 'hotkey-legend';
            document.body.appendChild(legend);
        }
        // Clear content
        legend.innerHTML = '';
        const title = document.createElement('div');
        title.className = 'legend-title';
        title.textContent = 'Hotkeys';
        const entf_function = document.createElement('div');
        entf_function.textContent = '(Delete key = "Entf" on keyboards)'; 
        entf_function.style.fontSize = '12px';
        entf_function.style.color = 'var(--color-hotkey-muted)';
        legend.appendChild(title);
        legend.appendChild(entf_function);

        const slots = Object.values(hotkeySlots).sort((a, b) => a.key.localeCompare(b.key));
        if (slots.length === 0) {
            const empty = document.createElement('div');
            empty.style.fontSize = '12px';
            empty.style.color = 'var(--color-hotkey-muted)';
            empty.textContent = 'Press 1–9 (click folders to assign)';
            legend.appendChild(empty);
            return;
        }
        const grid = document.createElement('div');
        grid.className = 'hotkey-grid';
        slots.forEach(s => {
            const item = document.createElement('div');
            item.className = 'hotkey-item';
            const badge = document.createElement('span');
            badge.className = 'hotkey-badge';
            badge.textContent = s.key;
            const name = document.createElement('span');
            name.className = 'hotkey-name';
            name.textContent = s.name;
            item.appendChild(badge);
            item.appendChild(name);
            grid.appendChild(item);
        });
        legend.appendChild(grid);
    }

    function handleDigitKey(keyChar) {
        const slot = hotkeySlots[keyChar];
        if (!slot) return; // no mapping
        slot.usageCount++;
        slot.lastUsedTimestamp = Date.now();
        if (selectedCount > 0) {
            sortSelection(slot.path);
        } else {
            sortCurrentImage(slot.path);
        }
        refreshHotkeyBadges();
    }

    document.addEventListener('keydown', (e) => {
        if (e.repeat) return;
        let keyChar = null;
        if (e.code.startsWith('Numpad') && /^[1-9]$/.test(e.code.slice(-1))) {
            keyChar = e.code.slice(-1);
        } else if (/^[1-9]$/.test(e.key)) {
            keyChar = e.key;
        }
        if (keyChar) {
            handleDigitKey(keyChar);
            return;
        }
        // Handle Delete key (German keyboards label this "Entf")
        if (e.key === 'Delete' || e.code === 'Delete') {
            e.preventDefault();
            if (selectedCount > 0) {
                deleteSelectionFlow();
            } else {
                deleteCurrentImageFlow();
            }
        }
    });

    function showLoading() {
        ui.loadingOverlay.classList.add('visible');
    }
    function hideLoading() {
        ui.loadingOverlay.classList.remove('visible');
    }

    // --- MODIFIED: This is where the fix is implemented ---
    ui.unsortedBtn.onclick = async () => {
        const folder = await pywebview.api.select_folder('Select Unsorted Pictures');
        if (folder) {
            ui.unsortedPathEl.textContent = folder;
            ui.parentBtn.disabled = false;

            // NEW: Clear the parent path to force re-selection
            ui.parentPathEl.textContent = '...';

            resetUI();
        }
    };

    ui.parentBtn.onclick = async () => {
        const folder = await pywebview.api.select_folder('Select Parent Folder');
        if (folder) {
            ui.parentPathEl.textContent = folder;
            showLoading();
            try {
                // This now always runs with the latest unsorted path
                const result = await pywebview.api.initialize_session(ui.unsortedPathEl.textContent, folder);
                updateUI(result);
            } finally {
                hideLoading();
            }
        }
    };

    async function deleteCurrentImageFlow() {
        // No confirmation needed: deletions are undoable in this app
        showLoading();
        try {
            const result = await pywebview.api.delete_current_image();
            updateUI(result);
        } finally {
            hideLoading();
        }
    }

    async function deleteSelectionFlow() {
        const count = selectedCount;
        if (count <= 0) return deleteCurrentImageFlow();
        showLoading();
        try {
            const result = await pywebview.api.delete_range(count);
            updateUI(result);
        } finally { hideLoading(); }
    }

    ui.deleteBtn.onclick = deleteCurrentImageFlow;

    ui.undoBtn.onclick = async () => {
        showLoading();
        try {
            const result = await pywebview.api.undo_last_move();
            updateUI(result);
        } finally {
            hideLoading();
        }
    };

    function updateUI(data) {
        if (!data || data.error) {
            alert('Error: ' + (data ? data.error : 'No data received.'));
            return;
        }

        if (data.current_year_root) currentYearRootPath = data.current_year_root;

        ui.undoBtn.disabled = !data.can_undo;

        if (data.current_image_path) {
            const timestamp = new Date().getTime();
            ui.imageContainer.innerHTML = `<img src="/image?path=${encodeURIComponent(data.current_image_path)}&t=${timestamp}">`;
            ui.imageCounter.textContent = `${data.current_index + 1} of ${data.total_images}`;
            ui.imageContainer.appendChild(ui.imageCounter);
        } else {
            ui.imageContainer.innerHTML = '<span>All pictures sorted!</span>';
            ui.imageCounter.textContent = '0 of 0';
        }

    ui.previewContainer.innerHTML = ''; // Clear old previews
        selectedCount = 0; // reset selection when UI updates
    if (ui.selectionIndicator) ui.selectionIndicator.textContent = '';
        if (data.next_image_paths && data.next_image_paths.length > 0) {
            const timestamp = new Date().getTime();
            data.next_image_paths.forEach((path, idx) => {
                const img = document.createElement('img');
                img.src = `/image?path=${encodeURIComponent(path)}&t=${timestamp}`;
                img.className = 'preview-image';
                const filename = path.split(/[\\/]/).pop(); // Get filename from path
                img.title = filename; // Show filename on hover
                // Click to select range from current to this preview (inclusive)
                img.addEventListener('click', (e) => {
                    e.preventDefault();
                    // idx is 0 for first next image; selection count includes current image
                    // so total images to move = 1 (current) + (idx + 1) = idx + 2
                    selectedCount = idx + 2;
                    updatePreviewSelectionUI();
                    if (ui.selectionIndicator) {
                        ui.selectionIndicator.textContent = `${selectedCount} selected`;
                    }
                });
                ui.previewContainer.appendChild(img);
            });
        }

        if (data.folder_tree) {
            ui.treeEl.innerHTML = '';
            const header = document.createElement('div');
            header.style.display = 'flex';
            header.style.alignItems = 'center';
            header.style.gap = '8px';
            const h3 = document.createElement('h3');
            h3.textContent = `Destination (Year: ${data.year})`;
            const rootAddBtn = document.createElement('button');
            rootAddBtn.textContent = '+';
            rootAddBtn.title = 'Create folder in root';
            rootAddBtn.className = 'icon-btn'; // MINIMAL ICON BUTTON
            rootAddBtn.setAttribute('aria-label', 'Create folder in root');
            rootAddBtn.onclick = () => {
                // keep root branch open after creating a folder at root
                if (currentYearRootPath) openLeafPath = normalizePath(currentYearRootPath);
                promptCreateFolder();
            };
            header.appendChild(h3);
            header.appendChild(rootAddBtn);
            ui.treeEl.appendChild(header);
            ui.treeEl.appendChild(createTreeElement(data.folder_tree));
            // Re-apply persisted open branch state after rebuild
            syncTreeOpenState();
            refreshHotkeyBadges();
        }
    }

    function updatePreviewSelectionUI() {
        const imgs = ui.previewContainer.querySelectorAll('img.preview-image');
        imgs.forEach((img, i) => {
            // highlight only previews that are included (excludes current)
            const previewsSelected = Math.max(0, selectedCount - 1);
            if (previewsSelected > 0 && i < previewsSelected) {
                img.classList.add('selected');
            } else {
                img.classList.remove('selected');
            }
        });
    }

    function createTreeElement(nodes) {
        const ul = document.createElement('ul');
        nodes.forEach(node => {
            const li = document.createElement('li');
            const textSpan = document.createElement('span');
            textSpan.className = 'folder-text';
            textSpan.textContent = node.name;
            textSpan.setAttribute('data-path', node.path);
            textSpan.onclick = () => {
                assignHotkeyForPath(node.path, node.name);
                if (selectedCount > 0) {
                    sortSelection(node.path);
                } else {
                    sortCurrentImage(node.path);
                }
            };

            // Action buttons container (minimal icon-only)
            const actions = document.createElement('span');
            actions.className = 'folder-actions';

            // Add subfolder button
            const addBtn = document.createElement('button');
            addBtn.textContent = '+';
            addBtn.title = 'Create subfolder';
            addBtn.className = 'icon-btn';
            addBtn.setAttribute('aria-label', `Create subfolder in ${node.name}`);
            addBtn.onclick = (e) => {
                e.stopPropagation();
                // keep this node's branch open after folder creation
                openLeafPath = normalizePath(node.path);
                promptCreateFolder(node.path);
            };

            // Delete folder button
            const delBtn = document.createElement('button');
            delBtn.textContent = 'X';
            delBtn.title = 'Delete folder (must be empty)';
            delBtn.className = 'icon-btn icon-btn--danger';
            delBtn.setAttribute('aria-label', `Delete folder ${node.name}`);
            delBtn.onclick = (e) => {
                e.stopPropagation();
                promptDeleteFolder(node.path, node.name);
            };

            actions.appendChild(addBtn);
            actions.appendChild(delBtn);

            const labelWrapper = document.createElement('span');
            labelWrapper.style.cursor = 'pointer';
            labelWrapper.appendChild(textSpan);
            labelWrapper.appendChild(actions);

            if (node.children && node.children.length > 0) {
                const details = document.createElement('details');
                details.setAttribute('data-path', node.path);
                // open if part of the persisted branch
                if (openLeafPath && isAncestorOrEqual(node.path, openLeafPath)) {
                    details.open = true;
                }
                // keep only one branch open and update openLeafPath on toggle
                details.addEventListener('toggle', () => {
                    if (isSyncingOpenState) return;
                    if (details.open) {
                        openLeafPath = normalizePath(node.path);
                    } else {
                        if (openLeafPath && isAncestorOrEqual(node.path, openLeafPath)) {
                            openLeafPath = getParentPath(node.path) || null;
                        }
                    }
                    syncTreeOpenState();
                });
                const summary = document.createElement('summary');
                summary.appendChild(labelWrapper);
                details.appendChild(summary);
                details.appendChild(createTreeElement(node.children));
                li.appendChild(details);
            } else {
                li.appendChild(labelWrapper);
            }
            ul.appendChild(li);
        });
        return ul;
    }

    async function promptCreateFolder(parentPath) {
        // Preserve current selection count before any UI refresh
        const countToMove = selectedCount;
        const name = prompt('Enter new folder name:');
        if (!name || name.trim() === '') {
            return; // Exit if user cancels or enters empty name
        }

        // If parentPath is not provided, we create in the root.
        // Use the reliable path we saved from the backend.
        const targetParent = parentPath || currentYearRootPath;

        if (!targetParent) {
            alert('Error: Root folder path is not available. Cannot create folder.');
            return;
        }

        // Keep the branch of the parent open through the refresh
        openLeafPath = normalizePath(targetParent);

        showLoading();
        try {
            // 1) Create the folder
            await pywebview.api.create_folder(targetParent, name);

            // 2) Build the newly created folder's full path
            const sep = targetParent.includes('\\') ? '\\' : '/';
            const newFolderPath = targetParent.replace(/[\\/]+$/, '') + sep + name.trim();

            // Persist open branch to the newly created folder
            openLeafPath = normalizePath(newFolderPath);

            // 3) Move selection (or current image) into the new folder
            let sortResult;
            if (countToMove > 0) {
                sortResult = await pywebview.api.sort_range(newFolderPath, countToMove);
            } else {
                sortResult = await pywebview.api.sort_current_image(newFolderPath);
            }

            // 4) Refresh once with the final state
            updateUI(sortResult);
        } catch (e) {
            console.error("Folder creation or sorting failed:", e);
            // Fallback: try to refresh state from backend so UI isn't stale
            try {
                const refresh = await pywebview.api.refresh_state?.();
                if (refresh) updateUI(refresh);
            } catch {}
            alert("An error occurred while creating the folder or moving images.");
        } finally {
            hideLoading();
        }
    }

    async function promptDeleteFolder(path, name) {
        if (!confirm(`Delete folder '${name}'? It must be empty.`)) return;
        showLoading();
        try {
            // If we are deleting the currently open branch or an ancestor of it,
            // move the open marker up to the parent so UI won't collapse entirely
            if (openLeafPath && isAncestorOrEqual(path, openLeafPath)) {
                openLeafPath = getParentPath(path) || null;
            }
            const result = await pywebview.api.delete_folder(path);
            // Remove hotkey mapping if exists
            for (const [key, slot] of Object.entries(hotkeySlots)) {
                if (slot.path === path) {
                    delete hotkeySlots[key];
                    pathToKey.delete(path);
                }
            }
            updateUI(result);
        } finally { hideLoading(); }
    }

    // --- Sorting helpers ---
    async function sortSelection(targetPath) {
        if (!targetPath) return;
        const count = selectedCount;
        if (count <= 0) {
            // fallback to single
            return sortCurrentImage(targetPath);
        }
        showLoading();
        try {
            const result = await pywebview.api.sort_range(targetPath, count);
            updateUI(result);
        } finally {
            hideLoading();
        }
    }

    async function sortCurrentImage(targetPath) {
        if (!targetPath) return;
        showLoading();
        try {
            const result = await pywebview.api.sort_current_image(targetPath);
            updateUI(result);
        } finally { hideLoading(); }
    }

    function resetUI() {
        ui.treeEl.innerHTML = '<h3>Destination Folders</h3>';
        ui.imageContainer.innerHTML = '<span>Image Preview</span>';
        ui.imageCounter.textContent = '';
        ui.undoBtn.disabled = true;
        ui.previewContainer.innerHTML = ''; // ADD THIS LINE
        openLeafPath = null; // clear persisted open branch
        refreshHotkeyBadges();
    }
});