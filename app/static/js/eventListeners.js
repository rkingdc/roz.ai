// js/eventListeners.js
// This module sets up all event listeners and acts as the orchestrator.
// It captures user interactions, calls API functions or state setters,
// and then triggers UI rendering functions based on state changes.

import { elements } from './dom.js';
import * as ui from './ui.js'; // Import ui to call rendering functions
import * as api from './api.js'; // Import api to call backend functions
import * as state from './state.js'; // Import state to update state directly for UI-only changes or read values
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js';
import { formatFileSize } from './utils.js';
import { escapeHtml } from './utils.js'; // Need escapeHtml for session file loading

/**
 * Sets up all event listeners for the application.
 * MUST be called after DOMContentLoaded and populateElements.
 */
export function setupEventListeners() {
    // --- Chat Input & Sending ---
    elements.sendButton?.addEventListener('click', async () => {
        await api.sendMessage(); // Updates state (chatHistory, isLoading, statusMessage, sessionFile)
        // Trigger UI updates based on state changes
        ui.handleStateChange_chatHistory();
        ui.handleStateChange_isLoading(); // Updates loading, status, attach buttons
        ui.handleStateChange_sessionFile(); // Updates attached/session file display
    });
    elements.messageInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            await api.sendMessage(); // Updates state
            // Trigger UI updates based on state changes
            ui.handleStateChange_chatHistory();
            ui.handleStateChange_isLoading(); // Updates loading, status, attach buttons
            ui.handleStateChange_sessionFile(); // Updates attached/session file display
        }
    });
    elements.modelSelector?.addEventListener('change', async () => {
        await api.handleModelChange(); // Updates state (currentChatModel, isLoading, statusMessage)
        // Trigger UI updates based on state changes
        ui.handleStateChange_currentChat(); // Updates chat details (name, id, model)
        ui.handleStateChange_isLoading(); // Updates loading, status, attach buttons
    });

    // --- Sidebar & Chat Management ---
    elements.sidebarToggleButton?.addEventListener('click', ui.toggleLeftSidebar); // UI-only toggle
    elements.newChatButton?.addEventListener('click', async () => {
        await api.startNewChat(); // Updates state (currentChatId, savedChats, chatHistory, isLoading, statusMessage, etc.)
        // Trigger UI updates based on state changes
        ui.handleStateChange_savedChats(); // Updates chat list
        ui.handleStateChange_currentChat(); // Updates chat details, history, context UI
        ui.handleStateChange_isLoading(); // Updates loading, status, attach buttons
    });
    elements.saveChatNameButton?.addEventListener('click', async () => {
        // Name is updated in state by input handler or here before API call
        const newName = elements.currentChatNameInput?.value.trim() || 'New Chat';
        state.setCurrentChatName(newName); // Update state immediately
        ui.handleStateChange_currentChat(); // Update name display immediately

        await api.handleSaveChatName(); // Updates state (savedChats, isLoading, statusMessage)
        // Trigger UI updates based on state changes
        ui.handleStateChange_savedChats(); // Updates chat list (timestamp)
        ui.handleStateChange_isLoading(); // Updates loading, status, attach buttons
        ui.handleStateChange_statusMessage(); // Ensure final status is shown
    });
    elements.currentChatNameInput?.addEventListener('input', (e) => { // Add input listener for name
        state.setCurrentChatName(e.target.value); // Update state
        ui.handleStateChange_currentChat(); // Update name display immediately
    });
    elements.currentChatNameInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.saveChatNameButton?.click(); // Trigger save button click
        }
    });
    // Add click listener for chat list items (delegated)
    elements.savedChatsList?.addEventListener('click', async (event) => {
        const listItem = event.target.closest('.chat-list-item');
        if (!listItem) return;
        const chatId = parseInt(listItem.dataset.chatId);
        if (isNaN(chatId)) return;

        // Prevent loading the same chat again
        if (chatId === state.currentChatId) return;

        await api.loadChat(chatId); // Updates state (currentChatId, chatHistory, etc.)
        // Trigger UI updates based on state changes
        ui.handleStateChange_currentChat(); // Updates chat details, history, context UI
        ui.handleStateChange_isLoading(); // Updates loading, status, attach buttons
        ui.handleStateChange_uploadedFiles(); // Updates file lists
        ui.handleStateChange_calendarContext(); // Updates calendar status
        ui.handleStateChange_isCalendarContextActive(); // Updates calendar toggle
        ui.handleStateChange_isWebSearchEnabled(); // Updates web search toggle
    });
    // Add click listener for delete chat button (delegated)
    elements.savedChatsList?.addEventListener('click', async (event) => {
        const deleteButton = event.target.closest('.delete-btn');
        if (!deleteButton) return;
        event.stopPropagation(); // Prevent triggering the list item click

        const listItem = deleteButton.closest('.chat-list-item');
        if (!listItem) return;
        const chatId = parseInt(listItem.dataset.chatId);
        if (isNaN(chatId)) return;

        await api.handleDeleteChat(chatId); // Updates state (savedChats, currentChatId, etc.)
        // Trigger UI updates based on state changes
        ui.handleStateChange_savedChats(); // Updates chat list
        // If current chat changed, handleStateChange_currentChat will be triggered by api.handleDeleteChat's call to loadChat/startNewChat
        ui.handleStateChange_isLoading(); // Updates loading, status
        ui.handleStateChange_statusMessage(); // Ensure final status is shown
    });


    // --- Plugins Sidebar & Sections ---
    elements.pluginsToggleButton?.addEventListener('click', ui.toggleRightSidebar); // UI-only toggle
    elements.filePluginHeader?.addEventListener('click', ui.toggleFilePlugin); // UI-only toggle
    elements.calendarPluginHeader?.addEventListener('click', ui.toggleCalendarPlugin); // UI-only toggle

    // --- File Plugin Interactions ---
    elements.attachFullButton?.addEventListener('click', () => {
        api.attachSelectedFilesFull(); // Updates state (attachedFiles, sidebarSelectedFiles)
        // Trigger UI updates based on state changes
        ui.handleStateChange_sidebarSelectedFiles(); // Updates sidebar highlighting and attach button state
        ui.handleStateChange_attachedFiles(); // Updates the tags below input
        ui.handleStateChange_statusMessage(); // Status message updated by API
    });
    elements.attachSummaryButton?.addEventListener('click', () => {
        api.attachSelectedFilesSummary(); // Updates state (attachedFiles, sidebarSelectedFiles)
        // Trigger UI updates based on state changes
        ui.handleStateChange_sidebarSelectedFiles(); // Updates sidebar highlighting and attach button state
        ui.handleStateChange_attachedFiles(); // Updates the tags below input
        ui.handleStateChange_statusMessage(); // Status message updated by API
    });
    elements.manageFilesButton?.addEventListener('click', () => {
        ui.showModal(elements.manageFilesModal, 'files', 'chat'); // UI-only modal show
        // File list rendering in modal is handled by ui.renderUploadedFiles,
        // which is called when state.uploadedFiles changes (e.g., by api.loadUploadedFiles)
    });

    // Session File Upload (Paperclip)
    elements.fileUploadSessionLabel?.addEventListener('click', () => {
        if (state.isFilePluginEnabled && state.currentTab === 'chat') {
            elements.fileUploadSessionInput?.click();
        } else if (!state.isFilePluginEnabled) {
            state.setStatusMessage("Files plugin is disabled in settings.", true); // Update state
            ui.handleStateChange_statusMessage(); // Explicitly trigger UI update
        }
    });
    elements.fileUploadSessionInput?.addEventListener('change', handleSessionFileUpload); // Handler updates state and triggers UI

    // Add click listener for sidebar file list items (delegated)
    elements.uploadedFilesList?.addEventListener('click', (event) => {
        const itemDiv = event.target.closest('.file-list-item');
        if (!itemDiv) return;

        const fileId = parseInt(itemDiv.dataset.fileId);
        const filename = itemDiv.dataset.filename;
        const hasSummary = itemDiv.dataset.hasSummary === 'true';
        if (isNaN(fileId) || !filename) return;

        const isCurrentlySelected = state.sidebarSelectedFiles.some(f => f.id === fileId);

        if (isCurrentlySelected) {
            state.removeSidebarSelectedFileById(fileId); // Update state
        } else {
            state.addSidebarSelectedFile({ id: fileId, filename: filename, has_summary: hasSummary }); // Update state
        }

        // Trigger UI updates based on state change
        ui.handleStateChange_sidebarSelectedFiles(); // Updates sidebar highlighting and attach button state
    });


    // --- Manage Files Modal ---
    elements.closeManageFilesModalButton?.addEventListener('click', () => ui.closeModal(elements.manageFilesModal)); // UI-only modal close
    elements.manageFilesModal?.addEventListener('click', (event) => {
        if (event.target === elements.manageFilesModal) ui.closeModal(elements.manageFilesModal); // UI-only modal close
    });
    elements.fileUploadModalInput?.addEventListener('change', async (event) => {
        await api.handleFileUpload(event); // Updates state (uploadedFiles, isLoading, statusMessage)
        // UI updates for uploadedFiles, isLoading, statusMessage are handled by UI reacting to state changes.
        // Closing modal after successful upload should be handled here or by reacting to state
        if (!state.isErrorStatus) { // Check state after API call
             ui.closeModal(elements.manageFilesModal);
        }
    });
    elements.addUrlModalButton?.addEventListener('click', () => {
        ui.showModal(elements.urlModal, 'files', 'chat'); // UI-only modal show
        // Status update for URL modal handled by its own input listener or fetch button handler
        if(elements.urlStatus) {
             elements.urlStatus.textContent = ""; // Clear previous status
             elements.urlStatus.classList.remove('text-red-500');
        }
    });

    // --- URL Modal ---
    elements.closeUrlModalButton?.addEventListener('click', () => ui.closeModal(elements.urlModal)); // UI-only modal close
    elements.urlModal?.addEventListener('click', (event) => {
        if (event.target === elements.urlModal) ui.closeModal(elements.urlModal); // UI-only modal close
    });
    elements.fetchUrlButton?.addEventListener('click', async () => {
        const url = elements.urlInput?.value;
        // Validation and status updates for modal are handled here before API call
        if (!url || !url.startsWith('http')) {
            if(elements.urlStatus) {
                elements.urlStatus.textContent = "Please enter a valid URL (http/https).";
                elements.urlStatus.classList.add('text-red-500');
            }
            return;
        }
        if(elements.urlStatus) {
            elements.urlStatus.textContent = "Fetching content...";
            elements.urlStatus.classList.remove('text-red-500');
        }
        await api.addFileFromUrl(url); // Updates state (uploadedFiles, isLoading, statusMessage)
        // UI updates for uploadedFiles, isLoading, statusMessage are handled by UI reacting to state changes.
        // Status update for URL modal is handled by API's setStatus, which updates state.statusMessage
        // We need a way for the modal to specifically show the status related to the URL fetch.
        // This might require adding modal-specific status state or reading the global status carefully.
        // For now, let's rely on the global status bar and close the modal on success.
        if (!state.isErrorStatus) { // Check global state after API call
             ui.closeModal(elements.urlModal);
        } else {
             // If there was an error, update the modal's status text
             if(elements.urlStatus) {
                 elements.urlStatus.textContent = `Error: ${state.statusMessage}`;
                 elements.urlStatus.classList.add('text-red-500');
             }
        }
    });
    elements.urlInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.fetchUrlButton?.click(); // Trigger the fetch button click
        }
    });

    // Add click listener for modal file list summary button (delegated)
    elements.manageFilesList?.addEventListener('click', async (event) => {
        const summaryButton = event.target.closest('.btn i.fa-list-alt')?.parentElement;
        if (!summaryButton) return;
        event.stopPropagation(); // Prevent triggering item click

        const itemDiv = summaryButton.closest('.file-list-item');
        if (!itemDiv) return;
        const fileId = parseInt(itemDiv.dataset.fileId);
        const filename = itemDiv.dataset.filename;
        if (isNaN(fileId) || !filename) return;

        await api.fetchSummary(fileId); // Updates state (currentEditingFileId, summaryContent, isLoading, statusMessage)
        // UI updates for state changes are handled by UI reacting to state changes.
        // Show modal is handled by the initial click listener for the button in createModalFileItem
        // ui.showModal(elements.summaryModal, 'files', 'chat'); // This is called in createModalFileItem listener
    });

    // Add click listener for modal file list delete button (delegated)
    elements.manageFilesList?.addEventListener('click', async (event) => {
        const deleteButton = event.target.closest('.btn i.fa-trash-alt')?.parentElement;
        if (!deleteButton) return;
        event.stopPropagation(); // Prevent triggering item click

        const itemDiv = deleteButton.closest('.file-list-item');
        if (!itemDiv) return;
        const fileId = parseInt(itemDiv.dataset.fileId);
        if (isNaN(fileId)) return;

        await api.deleteFile(fileId); // Updates state (uploadedFiles, sidebarSelectedFiles, attachedFiles, sessionFile, isLoading, statusMessage)
        // UI updates for state changes are handled by UI reacting to state changes.
    });


    // --- Summary Modal ---
    elements.closeSummaryModalButton?.addEventListener('click', () => ui.closeModal(elements.summaryModal)); // UI-only modal close
    elements.summaryModal?.addEventListener('click', (event) => {
        if (event.target === elements.summaryModal) ui.closeModal(elements.summaryModal); // UI-only modal close
    });
    elements.saveSummaryButton?.addEventListener('click', async () => {
        // Read content from DOM input for immediate state update
        const updatedSummary = elements.summaryTextarea?.value || '';
        state.setSummaryContent(updatedSummary); // Update state immediately

        await api.saveSummary(); // Updates state (uploadedFiles, isLoading, statusMessage, summaryContent)
        // UI updates for uploadedFiles, isLoading, statusMessage, summaryContent are handled by UI reacting to state changes.
        // Closing modal after successful save should be handled here.
        if (!state.isErrorStatus) { // Check global state after API call
             ui.closeModal(elements.summaryModal);
        }
    });
    // Summary textarea input updates state.summaryContent - handler already does this and calls ui.renderSummaryModalContent
    elements.summaryTextarea?.addEventListener('input', (e) => {
        state.setSummaryContent(e.target.value); // Update state
        ui.renderSummaryModalContent(); // Call UI function to update modal preview/content
    });


    // --- Calendar Plugin Interactions ---
    elements.loadCalendarButton?.addEventListener('click', async () => {
        await api.loadCalendarEvents(); // Updates state (calendarContext, isLoading, statusMessage)
        // UI updates for calendarContext, isLoading, statusMessage are handled by UI reacting to state changes.
    });
    elements.calendarToggle?.addEventListener('change', handleCalendarToggleChange); // Handler updates state and triggers UI
    elements.viewCalendarButton?.addEventListener('click', () => {
        ui.showModal(elements.calendarModal, 'calendar', 'chat'); // UI-only modal show
        // Calendar content rendering in modal is handled by UI reacting to state.calendarContext
    });
    elements.closeCalendarModalButton?.addEventListener('click', () => ui.closeModal(elements.calendarModal)); // UI-only modal close
    elements.calendarModal?.addEventListener('click', (event) => {
        if (event.target === elements.calendarModal) ui.closeModal(elements.calendarModal); // UI-only modal close
    });

    // --- Settings Modal & Toggles ---
    elements.settingsButton?.addEventListener('click', () => ui.showModal(elements.settingsModal)); // UI-only modal show
    elements.closeSettingsModalButton?.addEventListener('click', () => ui.closeModal(elements.settingsModal)); // UI-only modal close
    elements.settingsModal?.addEventListener('click', (event) => {
        if (event.target === elements.settingsModal) ui.closeModal(elements.settingsModal); // UI-only modal close
    });
    elements.streamingToggle?.addEventListener('change', handleStreamingToggleChange); // Handler updates state and triggers UI
    elements.filesPluginToggle?.addEventListener('change', handleFilesPluginToggleChange); // Handler updates state and triggers UI
    elements.calendarPluginToggle?.addEventListener('change', handleCalendarPluginToggleChange); // Handler updates state and triggers UI
    elements.webSearchPluginToggle?.addEventListener('change', handleWebSearchPluginToggleChange); // Handler updates state and triggers UI
    elements.webSearchToggle?.addEventListener('change', (e) => {
        state.setWebSearchEnabled(e.target.checked); // Update state
        // UI will react to state change (renderChatInputArea)
        ui.handleStateChange_isWebSearchEnabled(); // Explicitly trigger UI update
    });


    // --- Tab Navigation ---
    elements.chatNavButton?.addEventListener('click', () => {
        handleTabSwitchClick('chat'); // Call new handler
    });
    elements.notesNavButton?.addEventListener('click', () => {
        handleTabSwitchClick('notes'); // Call new handler
    });

    // New handler for tab button clicks
    async function handleTabSwitchClick(tab) {
        if (state.currentTab === tab) return; // Already on this tab

        // Save current state before switching (e.g., auto-save note)
        if (state.currentTab === 'notes' && state.currentNoteId) {
            // Use dynamic import for api
            import('./api.js').then(api => {
                 // await api.saveNote(); // Implement auto-save if needed
            }).catch(error => console.error("Failed to import api for auto-save:", error));
        }

        state.setCurrentTab(tab); // Update state
        localStorage.setItem(config.ACTIVE_TAB_KEY, tab); // Persist

        // Trigger UI update for tab switch immediately (shows correct sections, etc.)
        ui.switchTab(state.currentTab);

        // Load data for the new tab if needed
        if (tab === 'chat') {
            // loadInitialChatData checks if currentChatId is null and loads accordingly
            // It also loads savedChats and uploadedFiles if needed
            await api.loadInitialChatData(); // Updates state
            // UI updates triggered by state changes within loadInitialChatData (loadChat, startNewChat)
            // These will call handleStateChange_currentChat, handleStateChange_savedChats, handleStateChange_uploadedFiles, etc.
        } else { // tab === 'notes'
            // loadInitialNotesData checks if currentNoteId is null and loads accordingly
            // It also loads savedNotes if needed
            await api.loadInitialNotesData(); // Updates state
            // UI updates triggered by state changes within loadInitialNotesData (loadNote, startNewNote)
            // These will call handleStateChange_currentNote, handleStateChange_savedNotes, etc.
        }
    }

    // --- Notes Interactions ---
    // Note textarea input updates state.noteContent - handler already does this and calls ui.updateNotesPreview
    elements.notesTextarea?.addEventListener('input', (e) => {
        state.setNoteContent(e.target.value); // Update state
        ui.updateNotesPreview(); // Call UI function to update preview immediately in edit mode
        // UI will react to state change (renderNoteContent, updateNotesPreview)
    });
    elements.newNoteButton?.addEventListener('click', async () => {
        await api.startNewNote(); // Updates state (currentNoteId, savedNotes, noteContent, isLoading, statusMessage, etc.)
        // Trigger UI updates based on state changes
        ui.handleStateChange_savedNotes(); // Updates note list
        ui.handleStateChange_currentNote(); // Updates note details, content
        ui.handleStateChange_isLoading(); // Updates loading, status
    });
    // Note name input updates state.currentNoteName
    elements.currentNoteNameInput?.addEventListener('input', (e) => {
        state.setCurrentNoteName(e.target.value); // Update state
        ui.renderCurrentNoteDetails(); // Update name display in sidebar header
    });
    elements.saveNoteNameButton?.addEventListener('click', async () => {
        // Name is already in state from input handler
        await api.saveNote(); // Updates state (savedNotes, isLoading, statusMessage)
        // Trigger UI updates based on state changes
        ui.handleStateChange_savedNotes(); // Updates note list (timestamp)
        ui.handleStateChange_isLoading(); // Updates loading, status
        ui.handleStateChange_statusMessage(); // Ensure final status is shown
    });
    elements.currentNoteNameInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.saveNoteNameButton?.click(); // Trigger save button click
        }
    });
    elements.editNoteButton?.addEventListener('click', () => {
        state.setCurrentNoteMode('edit'); // Update state
        // UI will react to state change (setNoteMode)
        ui.handleStateChange_currentNoteMode(); // Explicitly trigger UI update
    });
    elements.viewNoteButton?.addEventListener('click', () => {
        state.setCurrentNoteMode('view'); // Update state
        // UI will react to state change (setNoteMode)
        ui.handleStateChange_currentNoteMode(); // Explicitly trigger UI update
    });
    elements.markdownTipsButton?.addEventListener('click', () => ui.showModal(elements.markdownTipsModal, null, 'notes')); // UI-only modal show
    elements.closeMarkdownTipsModalButton?.addEventListener('click', () => ui.closeModal(elements.markdownTipsModal)); // UI-only modal close
    elements.markdownTipsModal?.addEventListener('click', (event) => {
        if (event.target === elements.markdownTipsModal) ui.closeModal(elements.markdownTipsModal); // UI-only modal close
    });

    // Add click listener for note list items (delegated)
    elements.savedNotesList?.addEventListener('click', async (event) => {
        const listItem = event.target.closest('.note-list-item');
        if (!listItem) return;
        const noteId = parseInt(listItem.dataset.noteId);
        if (isNaN(noteId)) return;

        // Prevent loading the same note again
        if (noteId === state.currentNoteId) return;

        await api.loadNote(noteId); // Updates state (currentNoteId, noteContent, isLoading, statusMessage)
        // Trigger UI updates based on state changes
        ui.handleStateChange_currentNote(); // Updates note details, content
        ui.handleStateChange_isLoading(); // Updates loading, status
    });
    // Add click listener for delete note button (delegated)
    elements.savedNotesList?.addEventListener('click', async (event) => {
        const deleteButton = event.target.closest('.delete-btn');
        if (!deleteButton) return;
        event.stopPropagation(); // Prevent triggering the list item click

        const listItem = deleteButton.closest('.note-list-item');
        if (!listItem) return;
        const noteId = parseInt(listItem.dataset.noteId);
        if (isNaN(noteId)) return;

        await api.handleDeleteNote(noteId); // Updates state (savedNotes, currentNoteId, noteContent, isLoading, statusMessage)
        // Trigger UI updates based on state changes
        ui.handleStateChange_savedNotes(); // Updates note list
        // If current note changed, handleStateChange_currentNote will be triggered by api.handleDeleteNote's call to loadNote/startNewNote
        ui.handleStateChange_isLoading(); // Updates loading, status
        ui.handleStateChange_statusMessage(); // Ensure final status is shown
    });


    console.log("Event listeners set up.");
}


// --- Event Handler Helper Functions ---
// (Keep these helper functions below setupEventListeners)

/** Handles the session file input change event. */
async function handleSessionFileUpload(e) {
    const file = e.target.files[0];

    state.setSessionFile(null); // Clear state first
    // UI will react to this state change to remove the old tag (via handleStateChange_sessionFile)

    if (!file) {
        // If no file selected (e.g., user cancelled), state is already null, UI is updated.
        return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
        alert(`Skipping "${file.name}": File is too large (${formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset file input
        // State is already null, UI is updated.
        return;
    }

    // Show temporary loading state within the container (UI concern)
    // This could be handled by a state variable like `isSessionFileLoading`
    // For now, let's keep the direct DOM manipulation here as it's a very specific UI feedback.
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
        // UI will react to state change (renderAttachedAndSessionFiles)
        ui.handleStateChange_sessionFile(); // Explicitly trigger UI update
    }
    reader.onerror = function(error) {
        loadingTag.remove();
        console.error("Error reading session file:", error);
        // Update state with an error status? Or just rely on the alert?
        // Let's add a temporary error tag in the UI for immediate feedback.
        const errorTag = document.createElement('span');
        errorTag.classList.add('selected-file-tag', 'session-file-tag', 'bg-red-100', 'text-red-700', 'border-red-300');
        errorTag.textContent = `Error loading ${escapeHtml(file.name)}`;
        elements.selectedFilesContainer?.prepend(errorTag);
        setTimeout(() => errorTag.remove(), 3000);

        state.setSessionFile(null); // Ensure state is null on error
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
        // UI will react to state change (renderAttachedAndSessionFiles)
        ui.handleStateChange_sessionFile(); // Explicitly trigger UI update
    }
    reader.readAsDataURL(file); // Read as Base64
}


/** Handles changes to the calendar context toggle switch. */
function handleCalendarToggleChange() {
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Force off
        state.setStatusMessage("Calendar context requires Calendar plugin enabled on Chat tab.", true); // Update state
        ui.handleStateChange_statusMessage(); // Explicitly trigger UI update
        return;
    }
    const isActive = elements.calendarToggle?.checked || false;
    state.setCalendarContextActive(isActive); // Update state
    localStorage.setItem('calendarContextActive', isActive); // Persist
    // UI will react to state change (isCalendarContextActive, calendarContext)
    ui.handleStateChange_isCalendarContextActive(); // Explicitly trigger UI update
}

/** Handles changes to the streaming toggle switch. */
function handleStreamingToggleChange() {
    const isEnabled = elements.streamingToggle?.checked ?? true;
    state.setStreamingEnabled(isEnabled); // Update state
    localStorage.setItem('streamingEnabled', isEnabled); // Persist
    state.setStatusMessage(`Streaming responses ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state
    // UI will react to state change (statusMessage)
    ui.handleStateChange_statusMessage(); // Explicitly trigger UI update
}

/** Handles changes to the Files plugin toggle switch. */
async function handleFilesPluginToggleChange() {
    const isEnabled = elements.filesPluginToggle?.checked ?? true;
    state.setFilePluginEnabled(isEnabled); // Update state
    localStorage.setItem('filesPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Files plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state

    // Trigger UI updates based on state change
    ui.handleStateChange_pluginEnabled('files'); // Updates UI visibility

    // If disabling, clear related state
    if (!isEnabled) {
        state.clearSidebarSelectedFiles(); // Update state
        state.clearAttachedFiles(); // Update state
        state.setSessionFile(null); // Update state
        // UI will react to these state changes (sidebarSelectedFiles, attachedFiles, sessionFile)
        // ui.handleStateChange_sidebarSelectedFiles(); // Called by handleStateChange_pluginEnabled -> updatePluginUI -> renderUploadedFiles
        // ui.handleStateChange_attachedFiles(); // Called by handleStateChange_pluginEnabled -> updatePluginUI -> renderAttachedAndSessionFiles
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
    } else {
        // If enabling, reload the file lists
        await api.loadUploadedFiles(); // Updates state.uploadedFiles, isLoading, statusMessage
        // UI will react to these state changes
        // ui.handleStateChange_uploadedFiles(); // Called by api.loadUploadedFiles -> setUploadedFiles
        // ui.handleStateChange_isLoading(); // Called by api.loadUploadedFiles -> setLoading
        // ui.handleStateChange_statusMessage(); // Called by api.loadUploadedFiles -> setStatus
    }
    ui.handleStateChange_statusMessage(); // Ensure final status is shown
}

/** Handles changes to the Calendar plugin toggle switch. */
async function handleCalendarPluginToggleChange() {
    const isEnabled = elements.calendarPluginToggle?.checked ?? true;
    state.setCalendarPluginEnabled(isEnabled); // Update state
    localStorage.setItem('calendarPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Calendar plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state

    // Trigger UI updates based on state change
    ui.handleStateChange_pluginEnabled('calendar'); // Updates UI visibility

    // If disabling, clear calendar context state
    if (!isEnabled) {
        state.setCalendarContext(null); // Update state
        state.setCalendarContextActive(false); // Update state
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Update DOM directly for immediate feedback
        // UI will react to these state changes (calendarContext, isCalendarContextActive)
        // ui.handleStateChange_calendarContext(); // Called by handleStateChange_pluginEnabled -> updatePluginUI -> updateCalendarStatus
        // ui.handleStateChange_isCalendarContextActive(); // Called by handleStateChange_pluginEnabled -> updatePluginUI -> updateCalendarStatus
    }
    // No need to reload anything when enabling, just allows usage.
    ui.handleStateChange_statusMessage(); // Ensure final status is shown
}

/** Handles changes to the Web Search plugin toggle switch. */
async function handleWebSearchPluginToggleChange() {
    const isEnabled = elements.webSearchPluginToggle?.checked ?? true;
    state.setWebSearchPluginEnabled(isEnabled); // Update state
    localStorage.setItem('webSearchPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Web Search plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state

    // Trigger UI updates based on state change
    ui.handleStateChange_pluginEnabled('websearch'); // Updates UI visibility

    // If disabling, ensure the input area toggle state is also off
    if (!isEnabled) {
        state.setWebSearchEnabled(false); // Update state
        if (elements.webSearchToggle) {
            elements.webSearchToggle.checked = false; // Update DOM directly for immediate feedback
        }
        // UI will react to state change (isWebSearchEnabled)
        // ui.handleStateChange_isWebSearchEnabled(); // Called by handleStateChange_pluginEnabled -> updatePluginUI -> renderChatInputArea
    }
    ui.handleStateChange_statusMessage(); // Ensure final status is shown
}
