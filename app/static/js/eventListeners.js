// js/eventListeners.js
import { elements } from './dom.js';
import * as ui from './ui.js';
import * as api from './api.js';
import * as state from './state.js';
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js';
import { formatFileSize } from './utils.js';

/**
 * Sets up all event listeners for the application.
 * MUST be called after DOMContentLoaded and populateElements.
 */
export function setupEventListeners() {
    // --- Chat Input & Sending ---
    elements.sendButton?.addEventListener('click', api.sendMessage);
    elements.messageInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            api.sendMessage();
        }
    });
    elements.modelSelector?.addEventListener('change', api.handleModelChange);

    // --- Sidebar & Chat Management ---
    elements.sidebarToggleButton?.addEventListener('click', ui.toggleLeftSidebar);
    elements.newChatButton?.addEventListener('click', api.startNewChat);
    elements.saveChatNameButton?.addEventListener('click', api.handleSaveChatName);
    elements.currentChatNameInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            api.handleSaveChatName();
            elements.currentChatNameInput.blur();
        }
    });

    // --- Plugins Sidebar & Sections ---
    elements.pluginsToggleButton?.addEventListener('click', ui.toggleRightSidebar);
    elements.filePluginHeader?.addEventListener('click', ui.toggleFilePlugin);
    elements.calendarPluginHeader?.addEventListener('click', ui.toggleCalendarPlugin);

    // --- File Plugin Interactions ---
    // Corrected: Call the API functions directly
    elements.attachFullButton?.addEventListener('click', api.attachSelectedFilesFull);
    elements.attachSummaryButton?.addEventListener('click', api.attachSelectedFilesSummary);
    elements.manageFilesButton?.addEventListener('click', () => ui.showModal(elements.manageFilesModal, 'files', 'chat')); // Use generic showModal

    // Session File Upload (Paperclip)
    elements.fileUploadSessionLabel?.addEventListener('click', () => {
        if (state.isFilePluginEnabled && state.currentTab === 'chat') {
            elements.fileUploadSessionInput?.click();
        } else if (!state.isFilePluginEnabled) {
            ui.updateStatus("Files plugin is disabled in settings.", true);
        }
    });
    // Corrected: Ensure the change listener calls the handler
    elements.fileUploadSessionInput?.addEventListener('change', handleSessionFileUpload);


    // --- Manage Files Modal ---
    elements.closeManageFilesModalButton?.addEventListener('click', () => ui.closeModal(elements.manageFilesModal));
    elements.manageFilesModal?.addEventListener('click', (event) => {
        if (event.target === elements.manageFilesModal) ui.closeModal(elements.manageFilesModal);
    });
    elements.fileUploadModalInput?.addEventListener('change', api.handleFileUpload);
    elements.addUrlModalButton?.addEventListener('click', () => ui.showModal(elements.urlModal, 'files', 'chat')); // Show URL modal

    // --- URL Modal ---
    elements.closeUrlModalButton?.addEventListener('click', () => ui.closeModal(elements.urlModal));
    elements.urlModal?.addEventListener('click', (event) => {
        if (event.target === elements.urlModal) ui.closeModal(elements.urlModal);
    });
    elements.fetchUrlButton?.addEventListener('click', () => api.addFileFromUrl(elements.urlInput?.value));
    elements.urlInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            api.addFileFromUrl(elements.urlInput?.value);
        }
    });

    // --- Summary Modal ---
    elements.closeSummaryModalButton?.addEventListener('click', () => ui.closeModal(elements.summaryModal));
    elements.summaryModal?.addEventListener('click', (event) => {
        if (event.target === elements.summaryModal) ui.closeModal(elements.summaryModal);
    });
    elements.saveSummaryButton?.addEventListener('click', api.saveSummary);

    // --- Calendar Plugin Interactions ---
    elements.loadCalendarButton?.addEventListener('click', api.loadCalendarEvents);
    elements.calendarToggle?.addEventListener('change', handleCalendarToggleChange);
    elements.viewCalendarButton?.addEventListener('click', () => ui.showModal(elements.calendarModal, 'calendar', 'chat'));
    elements.closeCalendarModalButton?.addEventListener('click', () => ui.closeModal(elements.calendarModal));
    elements.calendarModal?.addEventListener('click', (event) => {
        if (event.target === elements.calendarModal) ui.closeModal(elements.calendarModal);
    });

    // --- Settings Modal & Toggles ---
    elements.settingsButton?.addEventListener('click', () => ui.showModal(elements.settingsModal));
    elements.closeSettingsModalButton?.addEventListener('click', () => ui.closeModal(elements.settingsModal));
    elements.settingsModal?.addEventListener('click', (event) => {
        if (event.target === elements.settingsModal) ui.closeModal(elements.settingsModal);
    });
    elements.streamingToggle?.addEventListener('change', handleStreamingToggleChange);
    elements.filesPluginToggle?.addEventListener('change', handleFilesPluginToggleChange);
    elements.calendarPluginToggle?.addEventListener('change', handleCalendarPluginToggleChange);
    elements.webSearchPluginToggle?.addEventListener('change', handleWebSearchPluginToggleChange);
    elements.webSearchToggle?.addEventListener('change', () => { /* No immediate action needed, state read on send */ });


    // --- Tab Navigation ---
    elements.chatNavButton?.addEventListener('click', () => ui.switchTab('chat'));
    elements.notesNavButton?.addEventListener('click', () => ui.switchTab('notes'));

    // --- Notes Interactions ---
    elements.notesTextarea?.addEventListener('input', ui.updateNotesPreview);
    elements.newNoteButton?.addEventListener('click', api.startNewNote);
    elements.saveNoteNameButton?.addEventListener('click', api.saveNote); // Save button saves name and content
    elements.currentNoteNameInput?.addEventListener('keypress', (e) => { // Save on enter in name input
        if (e.key === 'Enter') {
            e.preventDefault();
            api.saveNote();
            elements.currentNoteNameInput.blur();
        }
    });
    // Corrected: Use ui.setNoteMode instead of ui.switchNoteMode
    elements.editNoteButton?.addEventListener('click', () => ui.setNoteMode('edit'));
    elements.viewNoteButton?.addEventListener('click', () => ui.setNoteMode('view'));
    elements.markdownTipsButton?.addEventListener('click', () => ui.showModal(elements.markdownTipsModal, null, 'notes')); // Show tips modal only on notes tab
    elements.closeMarkdownTipsModalButton?.addEventListener('click', () => ui.closeModal(elements.markdownTipsModal));
    elements.markdownTipsModal?.addEventListener('click', (event) => {
        if (event.target === elements.markdownTipsModal) ui.closeModal(elements.markdownTipsModal);
    });

    console.log("Event listeners set up.");
}


// --- Event Handler Helper Functions ---

/** Handles attaching selected files (full or summary). */
// This function is no longer needed here as the API functions handle the state and UI updates directly.
// The event listeners now call api.attachSelectedFilesFull and api.attachSelectedFilesSummary.


/** Handles the session file input change event. */
async function handleSessionFileUpload(e) { // Made async to await ui import
    const ui = await import('./ui.js'); // Dynamic import
    const file = e.target.files[0];
    // Clear any existing session file tag first
    // elements.selectedFilesContainer?.querySelector('.session-file-tag')?.remove(); // This is handled by renderAttachedAndSessionFiles
    state.setSessionFile(null); // Clear state first

    if (!file) {
        ui.renderAttachedAndSessionFiles(); // Re-render to update container visibility and remove old tag
        return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
        alert(`Skipping "${file.name}": File is too large (${formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset file input
        ui.renderAttachedAndSessionFiles(); // Re-render to ensure no tag is shown
        return;
    }

    // Show temporary loading state within the container
    if(elements.selectedFilesContainer) elements.selectedFilesContainer.classList.remove('hidden');
    const loadingTag = document.createElement('span');
    loadingTag.classList.add('selected-file-tag', 'session-file-tag', 'opacity-75');
    loadingTag.innerHTML = `<span class="text-xs">Loading ${escapeHtml(file.name)}...</span>`;
    elements.selectedFilesContainer?.prepend(loadingTag);

    const reader = new FileReader();
    reader.onload = function(event) {
        loadingTag.remove(); // Remove loading tag
        // Store file details AND content in state
        state.setSessionFile({
            filename: file.name,
            mimetype: file.type,
            content: event.target.result // Base64 content
        });
        // Corrected: Call the single function that renders all attached/session files
        ui.renderAttachedAndSessionFiles(); // Render the tag using state data
    }
    reader.onerror = function(error) {
        loadingTag.remove();
        console.error("Error reading session file:", error);
        const errorTag = document.createElement('span');
        errorTag.classList.add('selected-file-tag', 'session-file-tag', 'bg-red-100', 'text-red-700', 'border-red-300');
        errorTag.textContent = `Error loading ${escapeHtml(file.name)}`;
        elements.selectedFilesContainer?.prepend(errorTag);
        setTimeout(() => errorTag.remove(), 3000);

        state.setSessionFile(null);
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = '';
        ui.renderAttachedAndSessionFiles(); // Re-render to ensure no tag is shown
    }
    reader.readAsDataURL(file); // Read as Base64
}


/** Handles changes to the calendar context toggle switch. */
async function handleCalendarToggleChange() { // Made async to await ui import
    const ui = await import('./ui.js'); // Dynamic import
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Force off
        ui.updateStatus("Calendar context requires Calendar plugin enabled on Chat tab.", true);
        return;
    }
    const isActive = elements.calendarToggle?.checked || false;
    state.setCalendarContextActive(isActive); // Update state
    localStorage.setItem('calendarContextActive', isActive); // Persist
    ui.updateCalendarStatus(); // Update display text
}

/** Handles changes to the streaming toggle switch. */
async function handleStreamingToggleChange() { // Made async to await ui import
    const ui = await import('./ui.js'); // Dynamic import
    const isEnabled = elements.streamingToggle?.checked ?? true;
    state.setStreamingEnabled(isEnabled); // Update state
    localStorage.setItem('streamingEnabled', isEnabled); // Persist
    ui.updateStatus(`Streaming responses ${isEnabled ? 'enabled' : 'disabled'}.`);
}

/** Handles changes to the Files plugin toggle switch. */
async function handleFilesPluginToggleChange() { // Made async to await ui import
    const ui = await import('./ui.js'); // Dynamic import
    const isEnabled = elements.filesPluginToggle?.checked ?? true;
    state.setFilePluginEnabled(isEnabled); // Update state
    localStorage.setItem('filesPluginEnabled', isEnabled); // Persist
    ui.updatePluginUI(); // Update UI visibility
    ui.updateStatus(`Files plugin ${isEnabled ? 'enabled' : 'disabled'}.`);

    // If disabling, clear related state and UI elements
    if (!isEnabled) {
        state.clearSidebarSelectedFiles(); // Corrected: Use clearSidebarSelectedFiles
        state.clearAttachedFiles(); // Corrected: Use clearAttachedFiles
        state.setSessionFile(null);
        ui.renderAttachedAndSessionFiles(); // Corrected: Use renderAttachedAndSessionFiles
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = '';
        // Clear file lists
        if(elements.uploadedFilesList) elements.uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
        if(elements.manageFilesList) elements.manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;

        // Also clear visual selection in the sidebar (redundant with clearSidebarSelectedFiles + renderUploadedFiles, but safe)
        elements.uploadedFilesList?.querySelectorAll('.file-list-item.active').forEach(item => {
            item.classList.remove('active');
        });
        ui.updateAttachButtonState(); // Update button state

    } else {
        // If enabling, reload the file lists
        await api.loadUploadedFiles(); // Await the API call
    }
}

/** Handles changes to the Calendar plugin toggle switch. */
async function handleCalendarPluginToggleChange() { // Made async to await ui import
    const ui = await import('./ui.js'); // Dynamic import
    const isEnabled = elements.calendarPluginToggle?.checked ?? true;
    state.setCalendarPluginEnabled(isEnabled); // Update state
    localStorage.setItem('calendarPluginEnabled', isEnabled); // Persist
    ui.updatePluginUI(); // Update UI visibility
    ui.updateStatus(`Calendar plugin ${isEnabled ? 'enabled' : 'disabled'}.`);

    // If disabling, clear calendar context and related UI state
    if (!isEnabled) {
        state.setCalendarContext(null);
        state.setCalendarContextActive(false);
        if(elements.calendarToggle) elements.calendarToggle.checked = false;
        ui.updateCalendarStatus();
    }
    // No need to reload anything when enabling, just allows usage.
}

/** Handles changes to the Web Search plugin toggle switch. */
async function handleWebSearchPluginToggleChange() { // Made async to await ui import
    const ui = await import('./ui.js'); // Dynamic import
    const isEnabled = elements.webSearchPluginToggle?.checked ?? true;
    state.setWebSearchPluginEnabled(isEnabled); // Update state
    localStorage.setItem('webSearchPluginEnabled', isEnabled); // Persist
    ui.updatePluginUI(); // Update UI visibility
    ui.updateStatus(`Web Search plugin ${isEnabled ? 'enabled' : 'disabled'}.`);

    // If disabling, ensure the input area toggle is also off
    if (!isEnabled && elements.webSearchToggle) {
        elements.webSearchToggle.checked = false;
    }
}
