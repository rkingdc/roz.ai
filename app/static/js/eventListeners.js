// js/eventListeners.js
// This module sets up all event listeners and acts as the orchestrator.
// It captures user interactions, calls API functions or state setters,
// and subscribes UI rendering functions to state changes.

import { elements } from './dom.js';
import * as ui from './ui.js'; // Import ui to call rendering functions
import * as api from './api.js'; // Import api to call backend functions
import * as state from './state.js'; // Import state to update state directly for UI-only changes or read values
import * as config from './config.js'; // Import config
import * as voice from './voice.js'; // Import voice recording functions
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js'; // Import file size constants
import { formatFileSize } from './utils.js';
import { escapeHtml } from './utils.js'; // Need escapeHtml for session file loading

/**
 * Sets up all event listeners for the application.
 * MUST be called after DOMContentLoaded and populateElements.
 */
export function setupEventListeners() {
    // --- Subscribe UI Renderers to State Changes ---
    subscribeStateChangeListeners();

    // --- Global Keyboard Shortcuts ---
    document.addEventListener('keydown', async (event) => {
        // Check for Ctrl+S or Cmd+S
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
            event.preventDefault(); // Prevent the default browser save action

            if (state.isLoading) {
                state.setStatusMessage("Cannot save while busy.", true);
                return;
            }

            if (state.currentTab === 'notes' && state.currentNoteId !== null) {
                await api.saveNote(); // Save the current note
                // --- NEW: Return focus to notes textarea after save ---
                elements.notesTextarea?.focus();
                // ----------------------------------------------------
            } else if (state.currentTab === 'chat' && state.currentChatId !== null) {
                 // Trigger the save chat name button click, which handles getting the name from the input
                 // Use the correct element reference from dom.js
                 if (elements.saveChatNameButton) {
                     elements.saveChatNameButton.click();
                     // --- NEW: Return focus to message input after save ---
                     elements.messageInput?.focus();
                     // ----------------------------------------------------
                 } else {
                     console.error("Save chat name button element not found!");
                     state.setStatusMessage("Error: Save button element missing.", true);
                 }
            } else {
                console.log("[DEBUG] Ctrl+S detected, but no active chat or note to save.");
                state.setStatusMessage("Nothing to save.", true);
            }
        }
    });
    console.log("Global keyboard listeners set up.");


    // --- Chat Input & Sending ---
    elements.sendButton?.addEventListener('click', async () => {
        await api.sendMessage(); // Updates state (chatHistory, isLoading, statusMessage, sessionFile)
        // UI updates are triggered by state notifications within api.sendMessage
    });
    elements.messageInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            await elements.sendButton?.click(); // Trigger send button click
        }
    });
    elements.modelSelector?.addEventListener('change', async () => {
        await api.handleModelChange(); // Updates state (currentChatModel, isLoading, statusMessage)
        // UI updates are triggered by state notifications within api.handleModelChange
    });
    elements.micButton?.addEventListener('click', () => {
        console.log("[DEBUG] Chat Mic Button CLICKED!"); // Log mic click too
        if (state.currentTab !== 'chat') return; // Only allow in chat

        if (state.isRecording) {
            voice.stopRecording(); // Will update state internally
        } else {
            voice.startRecording('chat'); // Will update state internally
        }
        // UI updates are triggered by state notifications (isRecording)
    });

    // --- Chat Cleanup Button Listener (REMOVED - Using Delegation Below) ---

    // --- Chat Input Listeners for Cleanup Button State ---
    if (elements.messageInput) {
        const updateCleanupState = () => ui.updateChatCleanupButtonState(); // Alias for brevity
        // Update button state when selection changes within the document
        document.addEventListener('selectionchange', () => {
            // Check if the message input is the active element when selection changes
            if (document.activeElement === elements.messageInput) {
                // Log the button element reference *when selection changes*
                console.log("[DEBUG] selectionchange (Chat): Checking chatCleanupButton ref:", elements.cleanupTranscriptButton);
                updateCleanupState();
            } else {
                // If selection changes outside the input, disable the button
                if (elements.cleanupTranscriptButton) elements.cleanupTranscriptButton.disabled = true;
            }
        });
        // Also update when typing or clicking within the input might clear selection
        elements.messageInput.addEventListener('input', updateCleanupState);
        elements.messageInput.addEventListener('click', updateCleanupState); // Handle clicks that might clear selection
        elements.messageInput.addEventListener('focus', updateCleanupState); // Update on focus
        elements.messageInput.addEventListener('blur', () => { // Disable when focus leaves
             if (elements.cleanupTranscriptButton) elements.cleanupTranscriptButton.disabled = true;
        });
    }
    // -------------------------------------------------------


    // --- Notes Textarea Listeners for Cleanup Button State ---
    if (elements.notesTextarea) {
        const updateCleanupState = () => ui.updateNotesCleanupButtonState(); // Alias for brevity
        // Update button state when selection changes within the document
        document.addEventListener('selectionchange', () => {
            // Check if the notes textarea is the active element when selection changes
            if (document.activeElement === elements.notesTextarea) {
                 // Log the button element reference *when selection changes*
                console.log("[DEBUG] selectionchange (Notes): Checking notesCleanupButton ref:", elements.cleanupTranscriptButtonNotes);
                updateCleanupState();
            } else {
                // If selection changes outside the textarea, disable the button
                if (elements.cleanupTranscriptButtonNotes) elements.cleanupTranscriptButtonNotes.disabled = true;
            }
        });
        // Also update when typing or clicking within the textarea might clear selection
        elements.notesTextarea.addEventListener('input', updateCleanupState);
        elements.notesTextarea.addEventListener('click', updateCleanupState); // Handle clicks that might clear selection
        elements.notesTextarea.addEventListener('focus', updateCleanupState); // Update on focus
        elements.notesTextarea.addEventListener('blur', () => { // Disable when focus leaves
             if (elements.cleanupTranscriptButtonNotes) elements.cleanupTranscriptButtonNotes.disabled = true;
        });
        // Initial state check might be needed after elements are populated, or rely on tab switch
    }
    // -------------------------------------------------------

    elements.micButtonNotes?.addEventListener('click', () => {
        console.log("[DEBUG] Notes Mic Button CLICKED!"); // Log mic click too
        if (state.currentTab !== 'notes') return; // Only allow in notes

        if (state.isRecording) {
            voice.stopRecording(); // Will update state internally
        } else {
            voice.startRecording('notes'); // Will update state internally
        }
        // UI updates are triggered by state notifications (isRecording)
    });

    // --- Notes Cleanup Button Listener (REMOVED - Using Delegation Below) ---

    // --- Sidebar & Chat Management ---
    elements.sidebarToggleButton?.addEventListener('click', ui.toggleLeftSidebar); // UI-only toggle
    elements.newChatButton?.addEventListener('click', async () => {
        await api.startNewChat(); // Updates state (currentChatId, savedChats, chatHistory, isLoading, statusMessage, etc.)
        // UI updates are triggered by state notifications within api.startNewChat
    });
    elements.saveChatNameButton?.addEventListener('click', async () => {
        // Name is updated in state by input handler or here before API call
        const newName = elements.currentChatNameInput?.value.trim() || 'New Chat';
        state.setCurrentChatName(newName); // Update state immediately (notifies currentChatName, currentChat)

        await api.handleSaveChatName(); // Updates state (savedChats, isLoading, statusMessage)
        // UI updates are triggered by state notifications within api.handleSaveChatName
    });
    elements.currentChatNameInput?.addEventListener('input', (e) => { // Add input listener for name
        state.setCurrentChatName(e.target.value); // Update state (notifies currentChatName, currentChat)
        // UI updates are triggered by state notifications
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
        // UI updates are triggered by state notifications within api.loadChat
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
        // UI updates are triggered by state notifications within api.handleDeleteChat
    });


    // --- Plugins Sidebar & Sections ---
    elements.pluginsToggleButton?.addEventListener('click', ui.toggleRightSidebar); // UI-only toggle
    elements.filePluginHeader?.addEventListener('click', ui.toggleFilePlugin); // UI-only toggle
    elements.calendarPluginHeader?.addEventListener('click', ui.toggleCalendarPlugin); // UI-only toggle
    // Add listener for history plugin header if it's collapsible
    if (elements.historyPluginHeader && elements.historyPluginContent) {
         elements.historyPluginHeader.addEventListener('click', () => {
             const isCollapsed = elements.historyPluginContent.classList.contains('hidden');
             ui.setPluginSectionCollapsed(elements.historyPluginHeader, elements.historyPluginContent, !isCollapsed, config.HISTORY_PLUGIN_COLLAPSED_KEY); // Assuming a new config key
         });
    }


    // --- File Plugin Interactions ---
    elements.attachFullButton?.addEventListener('click', () => {
        api.attachSelectedFilesFull(); // Updates state (attachedFiles, sidebarSelectedFiles)
        // UI updates are triggered by state notifications within api.attachSelectedFilesFull
    });
    elements.attachSummaryButton?.addEventListener('click', () => {
        api.attachSelectedFilesSummary(); // Updates state (attachedFiles, sidebarSelectedFiles)
        // UI updates are triggered by state notifications within api.attachSelectedFilesSummary
    });
    elements.manageFilesButton?.addEventListener('click', () => {
        ui.showModal(elements.manageFilesModal, 'files', 'chat'); // UI-only modal show
        // File list rendering in modal is handled by ui.renderUploadedFiles,
        // which is triggered by state.uploadedFiles notification (e.g., from api.loadUploadedFiles)
    });

    // Session File Upload (Paperclip)
    elements.fileUploadSessionLabel?.addEventListener('click', () => {
        if (state.isFilePluginEnabled && state.currentTab === 'chat') { // Use getters
            elements.fileUploadSessionInput?.click();
        } else if (!state.isFilePluginEnabled) { // Use getter
            state.setStatusMessage("Files plugin is disabled in settings.", true); // Update state (notifies statusMessage)
            // UI update is triggered by statusMessage notification
        }
    });
    elements.fileUploadSessionInput?.addEventListener('change', handleSessionFileUpload); // Handler updates state and triggers UI

    // Add click listener for sidebar file list items (delegated)
    elements.uploadedFilesList?.addEventListener('click', (event) => {
        const itemDiv = event.target.closest('.file-list-item');
        if (!itemDiv) return;

        const fileId = parseInt(itemDiv.dataset.fileId);
        const filename = itemDiv.dataset.filename;
        const hasSummaryDataset = itemDiv.dataset.hasSummary; // Get raw dataset value
        // Convert to boolean, accepting 'true' or '1' as true
        const hasSummary = hasSummaryDataset === 'true' || hasSummaryDataset === '1';
        if (isNaN(fileId) || !filename) return;

        const isCurrentlySelected = state.sidebarSelectedFiles.some(f => f.id === fileId);

        if (isCurrentlySelected) {
            state.removeSidebarSelectedFileById(fileId); // Update state (notifies sidebarSelectedFiles)
        } else {
            const fileToAdd = { id: fileId, filename: filename, has_summary: hasSummary };
            state.addSidebarSelectedFile(fileToAdd); // Update state (notifies sidebarSelectedFiles)
        }
        // UI updates are triggered by sidebarSelectedFiles notification
    });


    // --- Manage Files Modal ---
    elements.closeManageFilesModalButton?.addEventListener('click', () => ui.closeModal(elements.manageFilesModal)); // UI-only modal close
    elements.manageFilesModal?.addEventListener('click', (event) => {
        if (event.target === elements.manageFilesModal) ui.closeModal(elements.manageFilesModal); // UI-only modal close
    });
    elements.fileUploadModalInput?.addEventListener('change', async (event) => {
        await api.handleFileUpload(event); // Updates state (uploadedFiles, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
        // Closing modal after successful upload should be handled here based on state.
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
        // UI updates are triggered by state notifications.
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

        // Show modal immediately (UI concern)
        ui.showModal(elements.summaryModal, 'files', 'chat');

        await api.fetchSummary(fileId); // Updates state (currentEditingFileId, summaryContent, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
        // renderSummaryModalContent is called by currentEditingFileId and summaryContent notifications
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
        // UI updates are triggered by state notifications.
    });


    // --- Summary Modal ---
    elements.closeSummaryModalButton?.addEventListener('click', () => ui.closeModal(elements.summaryModal)); // UI-only modal close
    elements.summaryModal?.addEventListener('click', (event) => {
        if (event.target === elements.summaryModal) ui.closeModal(elements.summaryModal); // UI-only modal close
    });
    elements.saveSummaryButton?.addEventListener('click', async () => {
        // Read content from DOM input for immediate state update
        const updatedSummary = elements.summaryTextarea?.value || '';
        state.setSummaryContent(updatedSummary); // Update state immediately (notifies summaryContent)
        // UI update is triggered by summaryContent notification

        await api.saveSummary(); // Updates state (uploadedFiles, isLoading, statusMessage, summaryContent)
        // UI updates are triggered by state notifications.
        // Closing modal after successful save should be handled here.
        if (!state.isErrorStatus) { // Check global state after API call
             ui.closeModal(elements.summaryModal);
        }
    });
    // Summary textarea input updates state.summaryContent - handler already does this and calls ui.renderSummaryModalContent
    elements.summaryTextarea?.addEventListener('input', (e) => {
        state.setSummaryContent(e.target.value); // Update state (notifies summaryContent)
        // UI update is triggered by summaryContent notification
    });


    // --- Calendar Plugin Interactions ---
    elements.loadCalendarButton?.addEventListener('click', async () => {
        await api.loadCalendarEvents(); // Updates state (calendarContext, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
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
        state.setWebSearchEnabled(e.target.checked); // Update state (notifies isWebSearchEnabled)
        // UI update is triggered by isWebSearchEnabled notification
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
        if (state.currentTab === tab) {
            return; // Already on this tab
        }

        // Save current state before switching (e.g., auto-save note)
        // Auto-save note on tab switch is a potential feature, but not requested yet.
        // If implemented, it would go here:
        // if (state.currentTab === 'notes' && state.currentNoteId) {
        //     console.log("[DEBUG] Auto-saving note before switching tabs...");
        //     await api.saveNote(); // Implement auto-save if needed
        // }

        state.setCurrentTab(tab); // Update state (notifies currentTab)
        localStorage.setItem(config.ACTIVE_TAB_KEY, tab); // Persist

        // UI update for tab switch is triggered by currentTab notification

        // Load data for the new tab if needed
        if (tab === 'chat') {
            // loadInitialChatData checks if currentChatId is null and loads accordingly
            // It also loads savedChats and uploadedFiles if needed
            await api.loadInitialChatData(); // Updates state
            // UI updates triggered by state changes within loadInitialChatData (loadChat, startNewChat)
        } else { // tab === 'notes'
            // loadInitialNotesData checks if currentNoteId is null and loads accordingly
            // It also loads savedNotes if needed
            await api.loadInitialNotesData(); // Updates state
            // UI updates triggered by state changes within loadInitialNotesData (loadNote, startNewNote)
        }
    }

    // --- Notes Interactions ---
    // Note textarea input updates state.noteContent - handler already does this and calls ui.updateNotesPreview
    elements.notesTextarea?.addEventListener('input', (e) => {
        state.setNoteContent(e.target.value); // Update state (notifies noteContent, currentNote)
        // UI update is triggered by state notifications
    });
    elements.newNoteButton?.addEventListener('click', async () => {
        await api.startNewNote(); // Updates state (currentNoteId, savedNotes, noteContent, isLoading, statusMessage, etc.)
        // UI updates are triggered by state notifications.
    });
    // Note name input updates state.currentNoteName
    elements.currentNoteNameInput?.addEventListener('input', (e) => {
        state.setCurrentNoteName(e.target.value); // Update state (notifies currentNoteName, currentNote)
        // UI update is triggered by state notifications
    });
    elements.saveNoteNameButton?.addEventListener('click', async () => {
        // Name is already in state from input handler
        await api.saveNote(); // Updates state (savedNotes, isLoading, statusMessage)
        // UI updates are triggered by state notifications.
    });
    elements.currentNoteNameInput?.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            elements.saveNoteNameButton?.click(); // Trigger save button click
        }
    });
    elements.editNoteButton?.addEventListener('click', () => {
        state.setCurrentNoteMode('edit'); // Update state (notifies currentNoteMode)
        // UI update is triggered by currentNoteMode notification
    });
    elements.viewNoteButton?.addEventListener('click', () => {
        state.setCurrentNoteMode('view'); // Update state (notifies currentNoteMode)
        // UI update is triggered by currentNoteMode notification
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
        // UI updates are triggered by state notifications.
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
        // UI updates are triggered by state notifications.
    });


    // --- NEW: Add click listener for history list items (delegated) ---
    elements.noteHistoryList?.addEventListener('click', async (event) => {
        const listItem = event.target.closest('.history-list-item');
        if (!listItem) return;
        const historyId = parseInt(listItem.dataset.historyId);
        if (isNaN(historyId)) return;

        // Find the history entry in the state
        const historyEntry = state.noteHistory.find(entry => entry.id === historyId);

        if (historyEntry) {
            // Update the state with the history entry's content and name
            state.setNoteContent(historyEntry.content); // Notifies noteContent, currentNote
            state.setCurrentNoteName(historyEntry.name); // Notifies currentNoteName, currentNote

            // --- REMOVED: Do NOT change the note mode when loading history ---
            // state.setCurrentNoteMode('edit'); // Notifies currentNoteMode
            // -----------------------------------------------------------------

            state.setStatusMessage(`Loaded history version ${historyId}.`); // Update state
            // UI updates are triggered by state notifications
        } else {
            console.warn(`[DEBUG] History entry with ID ${historyId} not found in state.noteHistory.`);
            state.setStatusMessage(`Error: History version ${historyId} not found.`, true); // Update state
            // UI update is triggered by statusMessage notification
        }
    });
    // -----------------------------------------------------------------

    // --- Delegated Click Listener for Cleanup Buttons ---
    document.body.addEventListener('click', async (event) => {
        // Log *every* click target on the body first, including its ID and classes
        console.log(`[DEBUG] Body Click Detected. Target Element: <${event.target.tagName} id="${event.target.id}" class="${event.target.className}">`);

        // Check if the clicked element *is* the button OR is *inside* the button
        const chatCleanupBtn = event.target.id === 'cleanup-transcript-btn' ? event.target : event.target.closest('#cleanup-transcript-btn');
        const notesCleanupBtn = event.target.id === 'cleanup-transcript-btn-notes' ? event.target : event.target.closest('#cleanup-transcript-btn-notes');

        // Log results of the check
        console.log("[DEBUG] Body Click - chatCleanupBtn match:", chatCleanupBtn);
        console.log("[DEBUG] Body Click - notesCleanupBtn match:", notesCleanupBtn);


        if (chatCleanupBtn) {
            console.log(`[DEBUG] Delegated Chat Cleanup Button CLICKED! Disabled: ${chatCleanupBtn.disabled}`);
            if (state.isLoading || chatCleanupBtn.disabled || !elements.messageInput) {
                 console.log(`[DEBUG] Delegated Chat Cleanup: Click ignored (isLoading: ${state.isLoading}, isDisabled: ${chatCleanupBtn.disabled}, hasInput: ${!!elements.messageInput}).`);
                 return;
            }

            const inputField = elements.messageInput;
            const selectionStart = inputField.selectionStart;
            const selectionEnd = inputField.selectionEnd;
            const selectedText = inputField.value.substring(selectionStart, selectionEnd);

            if (!selectedText) {
                state.setStatusMessage("No text selected to clean.", true);
                return;
            }

            console.log(`[DEBUG] Delegated Chat Cleanup: Selected text: "${selectedText}"`);
            try {
                const cleanedText = await api.cleanupTranscript(selectedText);
                console.log(`[DEBUG] Delegated Chat Cleanup: Received cleaned text: "${cleanedText}"`);
                const currentFullText = inputField.value;
                const textBefore = currentFullText.substring(0, selectionStart);
                const textAfter = currentFullText.substring(selectionEnd);
                const newFullText = textBefore + cleanedText + textAfter;
                console.log(`[DEBUG] Delegated Chat Cleanup: Replacing with new full text: "${newFullText}"`);
                inputField.value = newFullText;
                inputField.focus();
                inputField.setSelectionRange(selectionStart, selectionStart + cleanedText.length);
                if (cleanedText === selectedText) { state.setStatusMessage("Cleanup did not change the selected text."); } else { state.setStatusMessage("Selected text cleaned."); }
            } catch (error) { console.error("Error cleaning selected text (Chat):", error); }
            finally { ui.updateChatCleanupButtonState(); }

        } else if (notesCleanupBtn) {
            console.log(`[DEBUG] Delegated Notes Cleanup Button CLICKED! Disabled: ${notesCleanupBtn.disabled}`);
            if (state.isLoading || notesCleanupBtn.disabled || !elements.notesTextarea) {
                 console.log(`[DEBUG] Delegated Notes Cleanup: Click ignored (isLoading: ${state.isLoading}, isDisabled: ${notesCleanupBtn.disabled}, hasTextarea: ${!!elements.notesTextarea}).`);
                 return;
            }

            const textarea = elements.notesTextarea;
            const selectionStart = textarea.selectionStart;
            const selectionEnd = textarea.selectionEnd;
            const selectedText = textarea.value.substring(selectionStart, selectionEnd);

            if (!selectedText) {
                state.setStatusMessage("No text selected to clean.", true);
                return;
            }

            console.log(`[DEBUG] Delegated Notes Cleanup: Selected text: "${selectedText}"`);
            try {
                const cleanedText = await api.cleanupTranscript(selectedText);
                console.log(`[DEBUG] Delegated Notes Cleanup: Received cleaned text: "${cleanedText}"`);
                const currentFullText = textarea.value;
                const textBefore = currentFullText.substring(0, selectionStart);
                const textAfter = currentFullText.substring(selectionEnd);
                const newFullText = textBefore + cleanedText + textAfter;
                console.log(`[DEBUG] Delegated Notes Cleanup: Replacing with new full text: "${newFullText}"`);
                textarea.value = newFullText;
                state.setNoteContent(newFullText); // Update state for notes
                textarea.focus();
                textarea.setSelectionRange(selectionStart, selectionStart + cleanedText.length);
                 if (cleanedText === selectedText) { state.setStatusMessage("Cleanup did not change the selected text."); } else { state.setStatusMessage("Selected text cleaned."); }
            } catch (error) { console.error("Error cleaning selected text (Notes):", error); }
            finally { ui.updateNotesCleanupButtonState(); }
        }
        // Add else block for logging if neither button matched
        else {
             // console.log("[DEBUG] Body Click - Neither cleanup button matched."); // Optional: Can be noisy
        }
    });
    // ----------------------------------------------------

    console.log("[DEBUG] setupEventListeners finished."); // Log completion
    // } // <-- REMOVE the potentially spurious closing brace added previously
}


/**
 * Subscribes UI rendering functions to state changes.
 * This function is called once during setupEventListeners.
 */
function subscribeStateChangeListeners() {
    // Subscribe UI functions to state changes they should react to
    state.subscribe('isLoading', ui.handleStateChange_isLoading);
    state.subscribe('statusMessage', ui.handleStateChange_statusMessage);

    state.subscribe('savedChats', ui.handleStateChange_savedChats);
    state.subscribe('currentChat', ui.handleStateChange_currentChat); // Combined chat details
    state.subscribe('chatHistory', ui.handleStateChange_chatHistory);
    state.subscribe('isRecording', ui.handleStateChange_isRecording); // Subscribe mic button UI to recording state

    state.subscribe('savedNotes', ui.handleStateChange_savedNotes);
    state.subscribe('currentNote', ui.handleStateChange_currentNote); // Combined note details
    // --- REMOVED REDUNDANT SUBSCRIPTION ---
    // state.subscribe('noteContent', ui.handleStateChange_currentNote); // Note content changes also trigger currentNote handler
    // --------------------------------------
    state.subscribe('currentNoteMode', ui.handleStateChange_currentNoteMode);

    state.subscribe('uploadedFiles', ui.handleStateChange_uploadedFiles);
    state.subscribe('sidebarSelectedFiles', ui.handleStateChange_sidebarSelectedFiles);
    state.subscribe('attachedFiles', ui.handleStateChange_attachedFiles);
    state.subscribe('sessionFile', ui.handleStateChange_sessionFile);

    state.subscribe('currentEditingFileId', ui.handleStateChange_currentEditingFileId);
    state.subscribe('summaryContent', ui.handleStateChange_summaryContent);

    state.subscribe('calendarContext', ui.handleStateChange_calendarContext);
    state.subscribe('isCalendarContextActive', ui.handleStateChange_isCalendarContextActive);
    state.subscribe('isWebSearchEnabled', ui.handleStateChange_isWebSearchEnabled);

    // Generic plugin enabled state change handler
    state.subscribe('pluginEnabled', ui.handleStateChange_pluginEnabled);

    // Subscribe the UI handler to the currentTab state change
    state.subscribe('currentTab', ui.handleStateChange_currentTab); // Corrected event name

    // --- NEW: Subscribe UI to noteHistory state change ---
    state.subscribe('noteHistory', ui.handleStateChange_noteHistory); // Corrected handler name
    // ----------------------------------------------------

    // --- Subscribe UI to streaming transcript state change ---
    state.subscribe('streamingTranscript', ui.handleStateChange_streamingTranscript);
    // -------------------------------------------------------
}


// --- Event Handler Helper Functions ---
// (Keep these helper functions below setupEventListeners)

/** Handles the session file input change event. */
async function handleSessionFileUpload(e) {
    const file = e.target.files[0];

    state.setSessionFile(null); // Clear state first (notifies sessionFile)
    // UI will react to this state change to remove the old tag

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
        // UI update is triggered by sessionFile notification
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

        state.setSessionFile(null); // Ensure state is null on error (notifies sessionFile)
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
        // UI update is triggered by sessionFile notification
    }
    reader.readAsDataURL(file); // Read as Base64
}


/** Handles changes to the calendar context toggle switch. */
function handleCalendarToggleChange() {
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Force off
        state.setStatusMessage("Calendar context requires Calendar plugin enabled on Chat tab.", true); // Update state (notifies statusMessage)
        // UI update is triggered by statusMessage notification
        return;
    }
    const isActive = elements.calendarToggle?.checked || false;
    state.setCalendarContextActive(isActive); // Update state (notifies isCalendarContextActive)
    localStorage.setItem('calendarContextActive', isActive); // Persist
    // UI update is triggered by isCalendarContextActive notification
}

/** Handles changes to the streaming toggle switch. */
function handleStreamingToggleChange() {
    const isEnabled = elements.streamingToggle?.checked ?? true;
    state.setStreamingEnabled(isEnabled); // Update state (notifies isStreamingEnabled, pluginEnabled)
    localStorage.setItem('streamingEnabled', isEnabled); // Persist
    state.setStatusMessage(`Streaming responses ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)
    // UI updates are triggered by state notifications
}

/** Handles changes to the Files plugin toggle switch. */
async function handleFilesPluginToggleChange() {
    const isEnabled = elements.filesPluginToggle?.checked ?? true;
    state.setFilePluginEnabled(isEnabled); // Update state (notifies isFilePluginEnabled, pluginEnabled)
    localStorage.setItem('filesPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Files plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)

    // UI updates are triggered by state notifications (isFilePluginEnabled, statusMessage)

    // If disabling, clear related state
    if (!isEnabled) {
        state.clearSidebarSelectedFiles(); // Update state (notifies sidebarSelectedFiles)
        state.clearAttachedFiles(); // Update state (notifies attachedFiles)
        state.setSessionFile(null); // Update state (notifies sessionFile)
        if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
    } else {
        // If enabling, reload the file lists
        await api.loadUploadedFiles(); // Updates state.uploadedFiles, isLoading, statusMessage
        // UI updates are triggered by state notifications.
    }
}

/** Handles changes to the Calendar plugin toggle switch. */
async function handleCalendarPluginToggleChange() {
    const isEnabled = elements.calendarPluginToggle?.checked ?? true;
    state.setCalendarPluginEnabled(isEnabled); // Update state (notifies isCalendarPluginEnabled, pluginEnabled)
    localStorage.setItem('calendarPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Calendar plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)

    // UI updates are triggered by state notifications (isCalendarPluginEnabled, statusMessage)

    // If disabling, clear calendar context state
    if (!isEnabled) {
        state.setCalendarContext(null); // Update state (notifies calendarContext)
        state.setCalendarContextActive(false); // Update state (notifies isCalendarContextActive)
        if(elements.calendarToggle) elements.calendarToggle.checked = false; // Update DOM directly for immediate feedback
    }
    // No need to reload anything when enabling, just allows usage.
}

/** Handles changes to the Web Search plugin toggle switch. */
async function handleWebSearchPluginToggleChange() {
    const isEnabled = elements.webSearchPluginToggle?.checked ?? true;
    state.setWebSearchPluginEnabled(isEnabled); // Update state (notifies isWebSearchPluginEnabled, pluginEnabled)
    localStorage.setItem('webSearchPluginEnabled', isEnabled); // Persist
    state.setStatusMessage(`Web Search plugin ${isEnabled ? 'enabled' : 'disabled'}.`); // Update state (notifies statusMessage)

    // UI updates are triggered by state notifications (isWebSearchPluginEnabled, statusMessage)

    // If disabling, ensure the input area toggle state is also off
    if (!isEnabled) {
        state.setWebSearchEnabled(false); // Update state (notifies isWebSearchEnabled)
        if (elements.webSearchToggle) {
            elements.webSearchToggle.checked = false; // Update DOM directly for immediate feedback
        }
    }
}
