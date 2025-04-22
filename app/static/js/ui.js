// js/ui.js

// This module handles UI updates and interactions.
// It reads from the state module and updates the DOM via the elements module.
// It does NOT call API functions or modify state directly (except for UI-local state like modal visibility).

import { elements } from './dom.js'; // Import elements from dom.js
import * as state from './state.js'; // UI reads from state
import * as config from './config.js'; // Import config for keys
import { escapeHtml, formatFileSize } from './utils.js'; // Import utility functions
// No direct imports of api.js here to break the cycle.
// Event listeners will import api functions dynamically when needed.


// --- Render Functions (Read State, Update DOM) ---

/**
 * Renders the current status message in the status bar.
 */
export function renderStatus() {
    if (elements.statusBar) {
        elements.statusBar.textContent = `Status: ${state.statusMessage}`;
        if (state.isErrorStatus) {
            elements.statusBar.classList.add('text-red-500');
            elements.statusBar.classList.remove('text-gray-700'); // Assuming a default non-error color
        } else {
            elements.statusBar.classList.remove('text-red-500');
            elements.statusBar.classList.add('text-gray-700'); // Assuming a default non-error color
        }
    } else {
        console.warn("Status bar element not found.");
    }
}

/**
 * Updates the loading state of the UI elements.
 * Disables input, shows a loading indicator/message.
 */
export function updateLoadingState() {
    const isLoading = state.isLoading;

    if (elements.messageInput) elements.messageInput.disabled = isLoading;
    if (elements.sendButton) elements.sendButton.disabled = isLoading;
    if (elements.newChatButton) elements.newChatButton.disabled = isLoading;
    if (elements.saveChatNameButton) elements.saveChatNameButton.disabled = isLoading;
    if (elements.currentChatNameInput) elements.currentChatNameInput.disabled = isLoading;
    if (elements.newNoteButton) elements.newNoteButton.disabled = isLoading;
    if (elements.saveNoteNameButton) elements.saveNoteNameButton.disabled = isLoading;
    if (elements.currentNoteNameInput) elements.currentNoteNameInput.disabled = isLoading;
    if (elements.loadCalendarButton) elements.loadCalendarButton.disabled = isLoading;
    if (elements.manageFilesButton) elements.manageFilesButton.disabled = isLoading;
    // Enable/disable Attach buttons based on sidebar selection state, not just overall loading
    // if (elements.attachFullButton) elements.attachFullButton.disabled = isLoading;
    // if (elements.attachSummaryButton) elements.attachSummaryButton.disabled = isLoading;
    if (elements.fetchUrlButton) elements.fetchUrlButton.disabled = isLoading;
    if (elements.saveSummaryButton) elements.saveSummaryButton.disabled = isLoading;
    if (elements.settingsButton) elements.settingsButton.disabled = isLoading;
    if (elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = isLoading;
    if (elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.toggle('disabled', isLoading);
    if (elements.addUrlModalButton) elements.addUrlModalButton.disabled = isLoading;
    if (elements.editNoteButton) elements.editNoteButton.disabled = isLoading;
    if (elements.viewNoteButton) elements.viewNoteButton.disabled = isLoading;
    if (elements.markdownTipsButton) elements.markdownTipsButton.disabled = isLoading;


    // Disable/enable list items for chats/notes/files
    // File list items now also use the .list-item class
    document.querySelectorAll('.list-item').forEach(item => {
        if (isLoading) {
            item.classList.add('pointer-events-none', 'opacity-50');
        } else {
            item.classList.remove('pointer-events-none', 'opacity-50');
        }
    });

    elements.bodyElement?.classList.toggle('loading', isLoading); // Add a class to body for global loading styles

    // Update attach button state after loading state changes
    updateAttachButtonState();
}


/**
 * Renders the chat history from the state into the chatbox.
 */
export function renderChatHistory() {
    if (!elements.chatbox) {
        console.error("Chatbox element not found for rendering history.");
        return;
    }

    elements.chatbox.innerHTML = ''; // Clear current messages

    if (state.chatHistory.length === 0) {
        // Add a placeholder message if history is empty
        addMessage('system', state.isLoading ? 'Loading chat history...' : 'This chat is empty. Start typing!');
    } else {
        state.chatHistory.forEach(msg => {
            // Re-render each message. If it was streaming, the full content is now in state.
            addMessage(msg.role, msg.content, msg.isError);
        });
    }

    // Auto-scroll to the bottom after rendering
    elements.chatbox.scrollTop = elements.chatbox.scrollHeight;
}

/**
 * Adds a single message to the chatbox DOM.
 * This is a helper for renderChatHistory and potentially for immediate display
 * of user input before API response (though state-based rendering is preferred).
 * @param {'user' | 'assistant' | 'system'} role - The role of the message sender.
 * @param {string} content - The message content (can be markdown).
 * @param {boolean} [isError=false] - Whether the message indicates an error.
 * @returns {HTMLElement|null} The message element that was created.
 */
function addMessage(role, content, isError = false) {
     if (!elements.chatbox) {
        console.error("Chatbox element not found.");
        return null;
    }

    const messageElement = document.createElement('div');
    messageElement.classList.add('message', `${role}-msg`, 'p-3', 'mb-2', 'rounded-lg', 'whitespace-pre-wrap');

    if (isError) {
        messageElement.classList.add('bg-red-100', 'text-red-800', 'border', 'border-red-400');
        messageElement.innerHTML = `<strong>Error:</strong> ${escapeHtml(content)}`; // Escape HTML for error messages
    } else {
         // Render markdown immediately for non-streaming messages
         if (typeof marked !== 'undefined') {
             messageElement.innerHTML = marked.parse(content);
             messageElement.classList.add('prose', 'prose-sm', 'max-w-none');
         } else {
             messageElement.textContent = content; // Fallback
         }

        // Apply role-specific styling
        if (role === 'user') {
            messageElement.classList.add('bg-blue-100', 'self-end');
        } else if (role === 'assistant') {
            messageElement.classList.add('bg-gray-200', 'self-start');
        } else if (role === 'system') {
             messageElement.classList.add('bg-yellow-100', 'text-yellow-800', 'self-center', 'text-center', 'italic');
        }
    }
    elements.chatbox.appendChild(messageElement);

    // Auto-scroll to the bottom (might be handled better by a separate observer)
    // elements.chatbox.scrollTop = elements.chatbox.scrollHeight;

    return messageElement;
}


/**
 * Renders the list of saved chats from the state in the sidebar.
 */
export function renderSavedChats() {
    const { savedChatsList, currentChatNameInput, currentChatIdDisplay } = elements;
    if (!savedChatsList) return;

    savedChatsList.innerHTML = ''; // Clear current list

    const chats = state.savedChats; // Read from state

    if (!chats || chats.length === 0) {
        savedChatsList.innerHTML = '<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No saved chats yet.</p>';
        // Reset current chat display if no chats exist and one was selected
        if (state.currentChatId !== null) {
             currentChatNameInput.value = '';
             currentChatIdDisplay.textContent = 'ID: -';
             // State is already cleared by API/event listener
        }
        return;
    }

    // Sort chats by last_updated_at descending
    const sortedChats = chats.sort((a, b) => new Date(b.last_updated_at) - new Date(a.last_updated_at));

    sortedChats.forEach(chat => createChatItem(chat)); // Use helper

    // Update highlighting after rendering
    updateActiveChatListItem();
}

/**
 * Helper to create chat list item DOM element.
 * @param {Object} chat - The chat object { id, name, last_updated_at }.
 */
function createChatItem(chat) {
    const { savedChatsList } = elements;
    if (!savedChatsList) return;

    const listItem = document.createElement('div');
    // Use 'active' class for selection as per CORRECT HTML
    listItem.classList.add('list-item', 'chat-list-item', 'p-2', 'border-rz-sidebar-border', 'cursor-pointer', 'hover:bg-rz-sidebar-hover');
    listItem.dataset.chatId = chat.id;

    // Container for name and delete button (flex row)
    // Use 'name-container' class as per CORRECT HTML
    const nameDeleteContainer = document.createElement('div');
    nameDeleteContainer.classList.add('name-container'); // Use specific class

    const nameSpan = document.createElement('span');
    // Use only 'filename' class as per CORRECT HTML - color handled by CSS
    nameSpan.classList.add('filename'); // Use specific class
    nameSpan.textContent = chat.name || `Chat ${chat.id}`;
    nameSpan.title = chat.name || `Chat ${chat.id}`; // Add title for tooltip

    // Add delete button
    // Use only 'delete-btn' class as per CORRECT HTML - color handled by CSS
    const deleteButton = document.createElement('button');
    deleteButton.classList.add('delete-btn', 'text-rz-sidebar-text'); // Use specific class
    deleteButton.innerHTML = '<i class="fas fa-trash-alt fa-xs"></i>'; // Use fa-xs as per CORRECT HTML
    deleteButton.title = `Delete "${chat.name || `Chat ${chat.id}`}"`;
    // Event listener remains here, but calls API function
    // NOTE: This listener is now moved to eventListeners.js to centralize event handling
    // deleteButton.addEventListener('click', (event) => { ... });

    nameDeleteContainer.appendChild(nameSpan);
    nameDeleteContainer.appendChild(deleteButton); // Append delete button

    // Add timestamp div
    // Use 'div' and specific classes as per CORRECT HTML - color handled by CSS
    const timestampDiv = document.createElement('div');
    // Default color is text-rz-tab-background-text (greyish) based on provided HTML
    timestampDiv.classList.add('text-xs', 'mt-0.5', 'text-rz-toolbar-field-text'); // Use specific classes and mt-0.5 - color handled by CSS
    try {
        const date = new Date(chat.last_updated_at);
        // Format date nicely, e.g., "Oct 26, 10:30 AM" or "Yesterday, 3:15 PM"
        const now = new Date();
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);

        let formattedDate;
        if (date.toDateString() === now.toDateString()) {
            formattedDate = `Today, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        } else if (date.toDateString() === yesterday.toDateString()) {
            formattedDate = `Yesterday, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        } else {
            formattedDate = date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        }
        // Prepend "Last updated: " as per CORRECT HTML
        timestampDiv.textContent = `Last updated: ${formattedDate}`;
    } catch (e) {
        console.error("Error formatting date:", chat.last_updated_at, e);
        timestampDiv.textContent = 'Last updated: Invalid Date';
    }


    listItem.appendChild(nameDeleteContainer); // Append the container
    listItem.appendChild(timestampDiv); // Append the timestamp div

    // Add click listener to load chat
    // NOTE: This listener is now moved to eventListeners.js to centralize event handling
    // listItem.addEventListener('click', () => { ... });

    savedChatsList.appendChild(listItem);
}


/** Updates the highlighting for the currently active chat list item based on state. */
export function updateActiveChatListItem() {
    const { savedChatsList } = elements;
    if (!savedChatsList) return;

    savedChatsList.querySelectorAll('.chat-list-item').forEach(item => {
        const chatId = parseInt(item.dataset.chatId);
        // Find the timestamp div (it has text-xs class)
        const timestampDiv = item.querySelector('.text-xs');

        // Use 'active' class as per CORRECT HTML
        if (chatId === state.currentChatId) { // Read from state
            item.classList.add('active'); // Use 'active'
            item.classList.remove('active-selection'); // Remove old class

            // When active, timestamp should be gold (text-rz-sidebar-text)
            if (timestampDiv) {
                timestampDiv.classList.add('text-rz-sidebar-text', 'active-timestamp');
                timestampDiv.classList.remove('text-rz-tab-background-text');
            }
            // Trash can icon should also change color when selected
            const deleteButton = item.querySelector('.delete-btn');
            if (deleteButton) {
                deleteButton.classList.add('active-trash');
            }
        } else {
            item.classList.remove('active'); // Use 'active'
            item.classList.remove('active-selection'); // Remove old class

            // When inactive, timestamp should be greyish (text-rz-tab-background-text)
            if (timestampDiv) {
                timestampDiv.classList.remove('text-rz-sidebar-text', 'active-timestamp');
                timestampDiv.classList.add('text-rz-tab-background-text');
            }
            // Trash can icon should revert to default color when not selected
            const deleteButton = item.querySelector('.delete-btn');
            if (deleteButton) {
                deleteButton.classList.remove('active-trash');
            }
        }
    });
}

/**
 * Renders the current chat's name and ID from the state.
 */
export function renderCurrentChatDetails() {
    const { currentChatNameInput, currentChatIdDisplay, modelSelector } = elements;
    if (!currentChatNameInput || !currentChatIdDisplay || !modelSelector) return;

    currentChatNameInput.value = state.currentChatName || ''; // Read from state
    currentChatIdDisplay.textContent = state.currentChatId !== null ? `ID: ${state.currentChatId}` : 'ID: -'; // Read from state
    modelSelector.value = state.currentChatModel || modelSelector.options[0]?.value || ''; // Read from state
}


/**
 * Renders the list of saved notes from the state in the sidebar.
 */
export function renderSavedNotes() {
    const { savedNotesList, currentNoteNameInput, currentNoteIdDisplay } = elements;
    if (!savedNotesList) return;

    savedNotesList.innerHTML = ''; // Clear current list

    const notes = state.savedNotes; // Read from state

    if (!notes || notes.length === 0) {
        savedNotesList.innerHTML = '<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No saved notes yet.</p>';
         // Reset current note display if no notes exist and one was selected
        if (state.currentNoteId !== null) {
             currentNoteNameInput.value = '';
             currentNoteIdDisplay.textContent = 'ID: -';
             // State is already cleared by API/event listener
        }
        return;
    }

    // Sort notes by last_saved_at descending
    const sortedNotes = notes.sort((a, b) => new Date(b.last_saved_at) - new Date(a.last_saved_at));

    sortedNotes.forEach(note => createNoteItem(note)); // Use helper

    // Update highlighting after rendering
    updateActiveNoteListItem();
}

/**
 * Helper to create note list item DOM element.
 * @param {Object} note - The note object { id, name, last_saved_at }.
 */
function createNoteItem(note) {
    const { savedNotesList } = elements;
    if (!savedNotesList) return;

    const listItem = document.createElement('div');
    // Note items use 'active' class for selection as per provided HTML
    listItem.classList.add('list-item', 'note-list-item', 'p-2', 'border-rz-sidebar-border', 'cursor-pointer', 'hover:bg-rz-sidebar-hover');
    listItem.dataset.noteId = note.id;

    // Container for name and delete button (flex row)
    // Use 'name-container' class as per provided HTML
    const nameDeleteContainer = document.createElement('div');
    nameDeleteContainer.classList.add('name-container'); // Use specific class

    const nameSpan = document.createElement('span');
    // Use only 'filename' class as per provided HTML - color handled by CSS
    nameSpan.classList.add('filename'); // Use specific class
    nameSpan.textContent = note.name || `Note ${note.id}`;
    nameSpan.title = note.name || `Note ${note.id}`; // Add title for tooltip

    // Add delete button
    // Use only 'delete-btn' class as per provided HTML - color handled by CSS
    const deleteButton = document.createElement('button');
    deleteButton.classList.add('delete-btn', 'text-rz-sidebar-text'); // Use specific class
    deleteButton.innerHTML = '<i class="fas fa-trash-alt fa-xs"></i>'; // Use fa-xs as per provided HTML
    deleteButton.title = `Delete "${note.name || `Note ${note.id}`}"`;
    // Event listener remains here, but calls API function
    // NOTE: This listener is now moved to eventListeners.js to centralize event handling
    // deleteButton.addEventListener('click', (event) => { ... });

    nameDeleteContainer.appendChild(nameSpan);
    nameDeleteContainer.appendChild(deleteButton); // Append delete button

    // Add timestamp div
    // Use 'div' and specific classes as per provided HTML - color handled by CSS
    const timestampDiv = document.createElement('div');
    // Default color is text-rz-tab-background-text (greyish) based on provided HTML
    timestampDiv.classList.add('text-xs', 'mt-0.5', 'text-rz-toolbar-field-text'); // Use specific classes and mt-0.5 - color handled by CSS
    try {
        const date = new Date(note.last_saved_at);
        // Format date nicely, e.g., "Oct 26, 10:30 AM" or "Yesterday, 3:15 PM"
        const now = new Date();
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);

        let formattedDate;
        if (date.toDateString() === now.toDateString()) {
            formattedDate = `Today, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        } else if (date.toDateString() === yesterday.toDateString()) {
            formattedDate = `Yesterday, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        } else {
            formattedDate = date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        }
        // Prepend "Last saved: " as per provided HTML
        timestampDiv.textContent = `Last saved: ${formattedDate}`;
    } catch (e) {
        console.error("Error formatting date:", note.last_saved_at, e);
        timestampDiv.textContent = 'Last saved: Invalid Date';
    }

    listItem.appendChild(nameDeleteContainer); // Append the container
    listItem.appendChild(timestampDiv); // Append the timestamp div

    // Add click listener to load note
    // NOTE: This listener is now moved to eventListeners.js to centralize event handling
    // listItem.addEventListener('click', () => { ... });

    savedNotesList.appendChild(listItem);
}


/** Updates the highlighting for the currently active note list item based on state. */
export function updateActiveNoteListItem() {
    const { savedNotesList } = elements;
    if (!savedNotesList) return;

    savedNotesList.querySelectorAll('.note-list-item').forEach(item => {
        const noteId = parseInt(item.dataset.noteId);
        // Find the timestamp div (it has text-xs class)
        const timestampDiv = item.querySelector('.text-xs');

        // Use 'active' class as per provided HTML
        if (noteId === state.currentNoteId) { // Read from state
            item.classList.add('active'); // Use 'active'
            item.classList.remove('active-selection'); // Remove old class

            // When active, timestamp should be gold (text-rz-sidebar-text)
            if (timestampDiv) {
                timestampDiv.classList.add('text-rz-sidebar-text', 'active-timestamp');
                timestampDiv.classList.remove('text-rz-tab-background-text');
            }
             // Trash can icon should also change color when selected
            const deleteButton = item.querySelector('.delete-btn');
            if (deleteButton) {
                deleteButton.classList.add('active-trash');
            }
        } else {
            item.classList.remove('active'); // Use 'active'
            item.classList.remove('active-selection'); // Remove old class

            // When inactive, timestamp should be greyish (text-rz-tab-background-text)
            if (timestampDiv) {
                timestampDiv.classList.remove('text-rz-sidebar-text', 'active-timestamp');
                timestampDiv.classList.add('text-rz-tab-background-text');
            }
            // Trash can icon should revert to default color when not selected
            const deleteButton = item.querySelector('.delete-btn');
            if (deleteButton) {
                deleteButton.classList.remove('active-trash');
            }
        }
    });
}

/**
 * Renders the current note's name and ID from the state.
 */
export function renderCurrentNoteDetails() {
    const { currentNoteNameInput, currentNoteIdDisplay } = elements;
    if (!currentNoteNameInput || !currentNoteIdDisplay) return;

    currentNoteNameInput.value = state.currentNoteName || ''; // Read from state
    currentNoteIdDisplay.textContent = state.currentNoteId !== null ? `ID: ${state.currentNoteId}` : 'ID: -'; // Read from state
}

/**
 * Renders the current note's content from the state into the textarea and preview.
 */
export function renderNoteContent() {
    const { notesTextarea, notesPreview } = elements;
    if (!notesTextarea || !notesPreview) return;

    notesTextarea.value = state.noteContent || ''; // Read from state
    notesTextarea.placeholder = state.isLoading ? "Loading note..." : "Start typing your markdown notes here...";
    notesTextarea.disabled = state.isLoading || state.currentNoteId === null; // Disable if loading or no note loaded

    // Update preview based on current mode and content
    updateNotesPreview(); // This function already reads from state and renders preview
}


/**
 * Renders the list of uploaded files from the state in the plugins sidebar and manage files modal.
 */
export function renderUploadedFiles() {
    const { uploadedFilesList, manageFilesList } = elements;
    if (!uploadedFilesList || !manageFilesList) return;

    // Clear current lists
    uploadedFilesList.innerHTML = '';
    manageFilesList.innerHTML = '';

    const files = state.uploadedFiles; // Read from state

    if (!state.isFilePluginEnabled) {
         uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
         manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
         return;
    }

    if (!files || files.length === 0) {
        uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No files uploaded yet.</p>`;
        manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">No files uploaded yet.</p>`;
        return;
    }

    files.forEach(file => {
        // Check if the file is currently selected in the sidebar (using the correct state variable)
        const isSidebarSelected = state.sidebarSelectedFiles.some(sf => sf.id === file.id);
        createSidebarFileItem(file, isSidebarSelected); // Use helper
        // Modal list doesn't use checkboxes for selection anymore, only for management actions
        createModalFileItem(file); // Use helper
    });

    // After rendering, update the display of attached files and session file in the input area
    renderAttachedAndSessionFiles(); // Use state.attachedFiles and state.sessionFile
    updateAttachButtonState(); // Update state of attach buttons based on sidebar selection
}

/**
 * Creates a DOM element for a file item in the sidebar list.
 * @param {Object} file - The file object { id, filename, mimetype, filesize, has_summary }.
 * @param {boolean} isSelected - Whether the file is currently selected in the sidebar.
 * @returns {HTMLElement} The created div element.
 */
function createSidebarFileItem(file, isSelected) {
    const { uploadedFilesList } = elements;
    if (!uploadedFilesList) return;

    const itemDiv = document.createElement('div');
    // Add 'list-item' class and remove conflicting layout/padding classes
    // Remove flex, items-center, p-1, truncate, flex-grow as they conflict with list-item's column flex
    itemDiv.classList.add('list-item', 'file-list-item', 'p-2', 'border-rz-sidebar-border', 'cursor-pointer', 'hover:bg-rz-sidebar-hover'); // Removed flex, items-center, truncate, flex-grow, p-1
    itemDiv.dataset.fileId = file.id;
    itemDiv.dataset.filename = file.filename;
    itemDiv.dataset.hasSummary = file.has_summary; // Store summary status
    // Add 'active' class if currently selected in the sidebar
    if (isSelected) {
        itemDiv.classList.add('active'); // Corrected: Use itemDiv instead of item
    }


    // Container for name and potential future actions (flex row) - similar to chat item
    const nameContainer = document.createElement('div');
    nameContainer.classList.add('name-container'); // Use specific class

    const nameSpan = document.createElement('span');
    // Use only 'filename' class as per CORRECT HTML - color handled by CSS
    // Remove truncate and flex-grow as they conflict with list-item's column flex
    nameSpan.classList.add('filename'); // Use specific class
    nameSpan.textContent = file.filename;
    nameSpan.title = file.filename; // Add tooltip

    // No delete button or summary status indicator in sidebar file list as per request

    nameContainer.appendChild(nameSpan);
    // Append other action buttons here if needed in the future, similar to chat item

    // Add timestamp div
    // Use 'div' and specific classes as per chat list item
    const timestampDiv = document.createElement('div');
    // Default color is text-rz-tab-background-text (greyish) based on provided HTML
    timestampDiv.classList.add('text-xs', 'mt-0.5', 'text-rz-toolbar-field-text'); // Use specific classes and mt-0.5 - color handled by CSS
    try {
        const date = new Date(file.uploaded_at); // Use uploaded_at for files
        // Format date nicely, e.g., "Oct 26, 10:30 AM" or "Yesterday, 3:15 PM"
        const now = new Date();
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);

        let formattedDate;
        if (date.toDateString() === now.toDateString()) {
            formattedDate = `Today, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        } else if (date.toDateString() === yesterday.toDateString()) {
            formattedDate = `Yesterday, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
        } else {
            formattedDate = date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' + date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        }
        // Prepend "Uploaded: "
        timestampDiv.textContent = `Uploaded: ${formattedDate}`;
    } catch (e) {
        console.error("Error formatting date:", file.uploaded_at, e);
        timestampDiv.textContent = 'Uploaded: Invalid Date';
    }


    itemDiv.appendChild(nameContainer); // Append the container
    itemDiv.appendChild(timestampDiv); // Append the timestamp div

    // Add click listener to toggle selection (handled by eventListeners.js)
    // The event listener will update state, and state change will trigger UI re-render

    uploadedFilesList.appendChild(itemDiv);
}

/**
 * Updates the highlighting for selected file list items in the sidebar based on state.
 * Multiple files can be selected.
 */
export function updateSelectedFileListItemStyling() {
    const { uploadedFilesList } = elements;
    if (!uploadedFilesList) return;

    uploadedFilesList.querySelectorAll('.file-list-item').forEach(item => {
        const fileId = parseInt(item.dataset.fileId);
        if (isNaN(fileId)) return;

        // Check against sidebarSelectedFiles (using the correct state variable)
        const isSelected = state.sidebarSelectedFiles.some(f => f.id === fileId); // Read from state

        if (isSelected) {
            item.classList.add('active'); // Use 'active' class for selected state
            // Timestamp and other elements will inherit active styles via CSS
        } else {
            item.classList.remove('active'); // Remove 'active' class
            // Timestamp and other elements will revert to default styles via CSS
        }
    });
}

/**
 * Updates the enabled/disabled state of the Attach Full and Attach Summary buttons
 * based on the state of files selected in the sidebar.
 */
export function updateAttachButtonState() {
    const { attachFullButton, attachSummaryButton } = elements;
    if (!attachFullButton || !attachSummaryButton) return;

    const selectedCount = state.sidebarSelectedFiles.length; // Read from state
    // Check if any selected file in sidebarSelectedFiles has has_summary === true
    const hasSummarizable = state.sidebarSelectedFiles.some(f => f.has_summary); // Read from state

    // Attach Full is enabled if at least one file is selected in the sidebar AND not loading
    attachFullButton.disabled = state.isLoading || selectedCount === 0; // Read from state

    // Attach Summary is enabled if at least one file is selected in the sidebar AND at least one selected file has a summary AND not loading
    attachSummaryButton.disabled = state.isLoading || selectedCount === 0 || !hasSummarizable; // Read from state
}


/**
 * Creates a DOM element for a file item in the Manage Files modal list.
 * @param {Object} file - The file object { id, filename, mimetype, filesize, has_summary, uploaded_at }.
 */
function createModalFileItem(file) {
    const { manageFilesList } = elements;
     if (!manageFilesList) return;

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('file-list-item', 'grid', 'grid-cols-12', 'gap-2', 'items-center', 'p-2', 'border-b', 'border-gray-200', 'last:border-b-0', 'text-sm');
    itemDiv.dataset.fileId = file.id;
    itemDiv.dataset.filename = file.filename;
    itemDiv.dataset.hasSummary = file.has_summary;

    // Filename (col-span-7) - Increased span as checkbox is removed
    const nameCol = document.createElement('div');
    nameCol.classList.add('col-span-7', 'text-sm', 'text-gray-800', 'truncate');
    nameCol.textContent = file.filename;
    nameCol.title = file.filename; // Add tooltip

    // Size (col-span-2)
    const sizeCol = document.createElement('div');
    sizeCol.classList.add('col-span-2', 'text-xs', 'text-gray-500');
    sizeCol.textContent = formatFileSize(file.filesize);

    // Actions (col-span-3)
    const actionsCol = document.createElement('div');
    actionsCol.classList.add('col-span-3', 'flex', 'gap-1', 'justify-end');

    // Summary Button
    const summaryButton = document.createElement('button');
    summaryButton.classList.add('btn', 'btn-outline', 'btn-xs', 'p-1');
    summaryButton.innerHTML = '<i class="fas fa-list-alt"></i>';
    summaryButton.title = file.has_summary ? 'View/Edit Summary' : 'Generate Summary';
    // Event listener remains here, calls API function and shows modal
    // NOTE: This listener is now moved to eventListeners.js to centralize event handling
    // summaryButton.addEventListener('click', (e) => { ... });

    // Delete Button
    const deleteButton = document.createElement('button');
    deleteButton.classList.add('btn', 'btn-outline', 'btn-xs', 'p-1', 'text-red-500', 'hover:text-red-700');
    deleteButton.innerHTML = '<i class="fas fa-trash-alt"></i>';
    deleteButton.title = 'Delete File';
    // Event listener remains here, calls API function
    // NOTE: This listener is now moved to eventListeners.js to centralize event handling
    // deleteButton.addEventListener('click', (e) => { ... });

    actionsCol.appendChild(summaryButton);
    actionsCol.appendChild(deleteButton);

    // No checkbox column anymore
    itemDiv.appendChild(nameCol);
    itemDiv.appendChild(sizeCol);
    itemDiv.appendChild(actionsCol);

     // No click listener on the item div itself for modal items

    manageFilesList.appendChild(itemDiv);
}

/**
 * Renders the content of the summary modal based on state.
 */
export function renderSummaryModalContent() {
    const { summaryModalFilename, summaryTextarea, saveSummaryButton, summaryStatus } = elements;
    if (!summaryModalFilename || !summaryTextarea || !saveSummaryButton || !summaryStatus) return;

    const file = state.uploadedFiles.find(f => f.id === state.currentEditingFileId); // Read from state
    const filename = file ? file.filename : 'Unknown File';

    summaryModalFilename.textContent = filename;
    summaryTextarea.value = state.summaryContent; // Read from state
    summaryTextarea.placeholder = state.isLoading ? "Loading or generating summary..." : "Enter or edit summary here."; // Read from state
    saveSummaryButton.disabled = state.isLoading || state.currentEditingFileId === null; // Read from state

    // Update status message in the modal based on state
    if (state.isLoading && state.statusMessage.includes("Fetching Summary")) {
         summaryStatus.textContent = "Fetching...";
         summaryStatus.classList.remove('text-red-500');
    } else if (state.isLoading && state.statusMessage.includes("Saving Summary")) {
         summaryStatus.textContent = "Saving...";
         summaryStatus.classList.remove('text-red-500');
    } else if (state.isErrorStatus && state.statusMessage.includes("summary")) {
         summaryStatus.textContent = `Error: ${state.statusMessage}`; // Display the specific error from state
         summaryStatus.classList.add('text-red-500');
    } else if (state.summaryContent.startsWith("[Error") || state.summaryContent.startsWith("[Summary not applicable")) {
         summaryStatus.textContent = state.summaryContent; // Display error/not applicable from state content
         summaryStatus.classList.add('text-red-500');
         saveSummaryButton.disabled = state.summaryContent.startsWith("[Summary not applicable");
    }
    else {
         summaryStatus.textContent = "Summary loaded. You can edit and save changes.";
         summaryStatus.classList.remove('text-red-500');
    }
}


/**
 * Renders the list of currently attached files and the session file below the message input.
 */
export function renderAttachedAndSessionFiles() {
    const { selectedFilesContainer, fileUploadSessionInput } = elements;
    if (!selectedFilesContainer) return;

    selectedFilesContainer.innerHTML = ''; // Clear current display

    // Combine attached files and session file for rendering
    const filesToDisplay = [...state.attachedFiles]; // Read from state
    if (state.sessionFile) { // Read from state
        // Add session file with a distinct type for rendering
        filesToDisplay.push({
            // Session file doesn't have a backend ID, use a placeholder
            id: 'session',
            filename: state.sessionFile.filename, // Read from state
            type: 'session',
            // Include other session file details if needed for display
        });
    }


    if (filesToDisplay.length === 0) {
        selectedFilesContainer.classList.add('hidden');
        // If session file was cleared, reset the input value
        if (!state.sessionFile && fileUploadSessionInput) {
             fileUploadSessionInput.value = '';
        }
        return;
    }

    selectedFilesContainer.classList.remove('hidden');

    filesToDisplay.forEach(file => {
        const fileTag = document.createElement('span');
        // Use theme colors for tags
        fileTag.classList.add('selected-file-tag', 'inline-flex', 'items-center', 'text-xs', 'font-medium', 'px-2.5', 'py-0.5', 'rounded-full', 'mr-2', 'mb-1');
        // Use data attributes to store file info for removal
        fileTag.dataset.fileId = file.id; // Will be 'session' for session file
        fileTag.dataset.fileType = file.type; // 'full', 'summary', or 'session'

        // Apply color based on type (using theme variables)
        if (file.type === 'session') {
             fileTag.classList.add('bg-rz-tag-bg', 'text-rz-tag-text', 'border', 'border-rz-tag-border');
        } else { // 'full' or 'summary'
             fileTag.classList.add('bg-rz-button-primary-bg', 'text-rz-button-primary-text');
        }

        const filenameSpan = document.createElement('span');
        filenameSpan.textContent = file.filename;
        filenameSpan.classList.add('mr-1');

        // Add file type indicator
        const typeSpan = document.createElement('span');
        typeSpan.classList.add('file-type'); // Use specific class for styling
        typeSpan.textContent = file.type === 'full' ? 'Full' : (file.type === 'summary' ? 'Summary' : 'Session');
        filenameSpan.prepend(typeSpan); // Prepend type to filename span


        const removeButton = document.createElement('button');
        removeButton.classList.add('remove-file-btn', 'ml-1'); // Removed text-blue classes, use theme colors via CSS
        removeButton.innerHTML = '<i class="fas fa-times-circle"></i>';
        removeButton.title = `Remove ${file.type === 'session' ? 'session' : 'attached'} file`;
        // Event listener remains here, modifies state
        removeButton.addEventListener('click', () => {
            if (file.type === 'session') {
                state.setSessionFile(null); // Clear session file state
                // Also reset the file input element
                if (elements.fileUploadSessionInput) { // Use elements.fileUploadSessionInput
                    elements.fileUploadSessionInput.value = '';
                }
            } else { // Permanent file (full or summary)
                // Remove from attachedFiles state by ID *and* Type
                state.removeAttachedFileByIdAndType(parseInt(file.id), file.type);
            }
            renderAttachedAndSessionFiles(); // Re-render the display based on updated state
            // No need to update attach button state or sidebar styling here
        });

        fileTag.appendChild(filenameSpan);
        fileTag.appendChild(removeButton);
        selectedFilesContainer.appendChild(fileTag);
    });
}


/**
 * Shows a modal window.
 * @param {HTMLElement} modalElement - The modal element to show.
 * @param {string} [requiredPlugin=null] - Optional plugin key ('files', 'calendar', etc.) required to show the modal.
 * @param {string} [requiredTab=null] - Optional tab key ('chat', 'notes') required to show the modal.
 * @returns {boolean} True if the modal was shown, false otherwise.
 */
export function showModal(modalElement, requiredPlugin = null, requiredTab = null) {
    console.log(`[DEBUG] showModal called for element:`, modalElement, `Required Plugin: ${requiredPlugin}`, `Required Tab: ${requiredTab}`);

    if (!modalElement) {
        console.error("Modal element not found.");
        return false;
    }

    // Check if required plugin is enabled (Read from state)
    if (requiredPlugin) {
        let pluginEnabled = false;
        if (requiredPlugin === 'files' && state.isFilePluginEnabled) pluginEnabled = true;
        if (requiredPlugin === 'calendar' && state.isCalendarPluginEnabled) pluginEnabled = true;
        // Add checks for other plugins here
        if (!pluginEnabled) {
            console.log(`[DEBUG] showModal: Required plugin "${requiredPlugin}" not enabled.`);
            // Status update handled by event listener or caller
            return false;
        }
         console.log(`[DEBUG] showModal: Required plugin "${requiredPlugin}" is enabled.`);
    }

    // Check if required tab is active (Read from state)
    if (requiredTab && state.currentTab !== requiredTab) {
         console.log(`[DEBUG] showModal: Required tab "${requiredTab}" not active. Current tab: ${state.currentTab}`);
         // Status update handled by event listener or caller
         return false;
    }
     if (requiredTab) {
         console.log(`[DEBUG] showModal: Required tab "${requiredTab}" is active.`);
     }


    console.log(`[DEBUG] showModal: Checks passed. Adding 'show' class to modal.`);
    modalElement.classList.add('show');
    elements.bodyElement?.classList.add('modal-open'); // Prevent body scroll
    return true;
}


/**
 * Toggles the collapsed state of a sidebar.
 * @param {HTMLElement} sidebarElement - The sidebar element.
 * @param {HTMLElement} toggleButton - The button that toggles the sidebar.
 * @param {string} localStorageKey - The key to use for localStorage.
 * @param {'sidebar' | 'plugins'} type - The type of sidebar ('sidebar' or 'plugins').
 */
export function setSidebarCollapsed(sidebarElement, toggleButton, isCollapsed, localStorageKey, type) {
    if (!sidebarElement || !toggleButton) return;

    if (isCollapsed) {
        sidebarElement.classList.add('collapsed');
        if (type === 'sidebar') {
             toggleButton.classList.add('collapsed');
             toggleButton.querySelector('i')?.classList.replace('fa-chevron-left', 'fa-chevron-right');
        } else if (type === 'plugins') {
             toggleButton.classList.add('collapsed');
             toggleButton.querySelector('i')?.classList.replace('fa-chevron-right', 'fa-chevron-left');
        }
    } else {
        sidebarElement.classList.remove('collapsed');
         if (type === 'sidebar') {
            toggleButton.classList.remove('collapsed');
            toggleButton.querySelector('i')?.classList.replace('fa-chevron-right', 'fa-chevron-left');
         } else if (type === 'plugins') {
            toggleButton.classList.remove('collapsed');
            toggleButton.querySelector('i')?.classList.replace('fa-chevron-left', 'fa-chevron-right');
         }
    }
    localStorage.setItem(localStorageKey, isCollapsed);
}

/** Toggles the left sidebar (chat/notes list). */
export function toggleLeftSidebar() {
    setSidebarCollapsed(elements.sidebar, elements.sidebarToggleButton, !elements.sidebar.classList.contains('collapsed'), config.SIDEBAR_COLLAPSED_KEY, 'sidebar');
}

/** Toggles the right sidebar (plugins). */
export function toggleRightSidebar() {
    setSidebarCollapsed(elements.pluginsSidebar, elements.pluginsToggleButton, !elements.pluginsSidebar.classList.contains('collapsed'), config.PLUGINS_COLLAPSED_KEY, 'plugins');
}

/** Toggles the File Plugin section. */
export function toggleFilePlugin() {
    if (!elements.filePluginHeader || !elements.filePluginContent) return;
    const isCollapsed = elements.filePluginContent.classList.contains('hidden');
    setPluginSectionCollapsed(elements.filePluginHeader, elements.filePluginContent, !isCollapsed, config.FILE_PLUGIN_COLLAPSED_KEY);
}

/** Toggles the Calendar Plugin section. */
export function toggleCalendarPlugin() {
    if (!elements.calendarPluginHeader || !elements.calendarPluginContent) return;
    const isCollapsed = elements.calendarPluginContent.classList.contains('hidden');
    setPluginSectionCollapsed(elements.calendarPluginHeader, elements.calendarPluginContent, !isCollapsed, config.CALENDAR_PLUGIN_COLLAPSED_KEY);
}


/**
 * Updates the UI based on which plugins are enabled/disabled (reads from state).
 */
export function updatePluginUI() {
    // File Plugin
    if (elements.filePluginSection) {
        elements.filePluginSection.classList.toggle('hidden', !state.isFilePluginEnabled); // Read from state
    }
    // Hide file upload label and selected files container if plugin is disabled
    if (elements.fileUploadSessionLabel) {
         elements.fileUploadSessionLabel.classList.toggle('hidden', !state.isFilePluginEnabled); // Read from state
    }
     if (elements.selectedFilesContainer) {
         // Only hide if plugin is disabled AND there are no attached/session files
         const hasFilesToDisplay = state.attachedFiles.length > 0 || state.sessionFile !== null; // Read from state
         if (!state.isFilePluginEnabled && !hasFilesToDisplay) { // Read from state
             elements.selectedFilesContainer.classList.add('hidden');
         }
         // If plugin is enabled and there are files to display, ensure it's visible
         if (state.isFilePluginEnabled && hasFilesToDisplay) { // Read from state
              elements.selectedFilesContainer.classList.remove('hidden');
         }
         // If plugin is enabled but no files, hide it
         if (state.isFilePluginEnabled && !hasFilesToDisplay) { // Read from state
             elements.selectedFilesContainer.classList.add('hidden');
         }
     }


    // Calendar Plugin
    if (elements.calendarPluginSection) {
        elements.calendarPluginSection.classList.toggle('hidden', !state.isCalendarPluginEnabled); // Read from state
    }
    // Hide calendar toggle input area if plugin is disabled
    if (elements.calendarToggleInputArea) {
         elements.calendarToggleInputArea.classList.toggle('hidden', !state.isCalendarPluginEnabled); // Read from state
    }


    // Web Search Toggle (part of Chat input area)
    if (elements.webSearchToggleLabel) {
        elements.webSearchToggleLabel.classList.toggle('hidden', !state.isWebSearchPluginEnabled); // Read from state
    }

    // Re-render file lists if file plugin state changed
    if (elements.uploadedFilesList && elements.manageFilesList) {
        if (!state.isFilePluginEnabled) { // Read from state
             elements.uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
             elements.manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
             // State clearing is handled by eventListeners.js reacting to toggle change
             // renderAttachedAndSessionFiles(); // Called by renderUploadedFiles
             // updateAttachButtonState(); // Called by renderUploadedFiles
        } else {
            // If plugin was just enabled, the file list will be rendered when loadUploadedFiles is called
            // (triggered by eventListeners.js reacting to the toggle change).
        }
    }

    // Update calendar status if calendar plugin state changed
    if (elements.calendarStatus) {
        if (!state.isCalendarPluginEnabled) { // Read from state
            elements.calendarStatus.textContent = "Status: Plugin disabled";
            // State clearing is handled by eventListeners.js reacting to toggle change
            if(elements.calendarToggle) elements.calendarToggle.checked = false;
            if(elements.viewCalendarButton) elements.viewCalendarButton.classList.add('hidden');
        } else {
             // If plugin was just enabled, the status will be updated when loadCalendarEvents is called
             // (triggered by eventListeners.js reacting to the toggle change).
        }
    }

    // Update web search toggle state if plugin state changed
    if (elements.webSearchToggle) {
         if (!state.isWebSearchPluginEnabled) { // Read from state
             elements.webSearchToggle.checked = false; // Turn off toggle if plugin disabled
         }
         // The toggle's checked state is persisted/loaded in loadPersistedStates
         // The actual checked state is read from state.isWebSearchEnabled by renderChatInputArea
    }

    // Render the chat input area elements based on plugin states
    renderChatInputArea();
}

/**
 * Updates the calendar status text and view button visibility (reads from state).
 */
export function updateCalendarStatus() {
    const { calendarStatus, viewCalendarButton, calendarToggle } = elements;
    if (!calendarStatus || !viewCalendarButton || !calendarToggle) return;

    const context = state.calendarContext; // Read from state
    const isActive = state.isCalendarContextActive; // Read from state

    if (!state.isCalendarPluginEnabled) { // Read from state
         calendarStatus.textContent = "Status: Plugin disabled";
         viewCalendarButton.classList.add('hidden');
         calendarToggle.checked = false;
         calendarToggle.disabled = true;
         return;
    }

    calendarToggle.disabled = false; // Enable toggle if plugin is enabled

    if (context) {
        const eventCount = context.events ? context.events.length : 0;
        calendarStatus.textContent = `Status: Loaded ${eventCount} events (last updated: ${new Date(context.timestamp).toLocaleTimeString()})`;
        viewCalendarButton.classList.remove('hidden');
        calendarToggle.checked = isActive; // Reflect state
    } else {
        calendarStatus.textContent = "Status: Not loaded";
        viewCalendarButton.classList.add('hidden');
        calendarToggle.checked = false; // Ensure toggle is off if no context
        // State is already false if context is null
    }
}

/**
 * Renders the chat input area elements based on plugin states.
 */
export function renderChatInputArea() {
    const {
        fileUploadSessionLabel, selectedFilesContainer, calendarToggleInputArea,
        webSearchToggleLabel, webSearchToggle
    } = elements;

    if (!fileUploadSessionLabel || !selectedFilesContainer || !calendarToggleInputArea || !webSearchToggleLabel || !webSearchToggle) {
        console.warn("Missing elements for rendering chat input area.");
        return;
    }

    // File Upload (Paperclip) and Attached Files Container
    fileUploadSessionLabel.classList.toggle('hidden', !state.isFilePluginEnabled); // Read from state
    // Visibility of selectedFilesContainer is handled by renderAttachedAndSessionFiles

    // Calendar Toggle
    calendarToggleInputArea.classList.toggle('hidden', !state.isCalendarPluginEnabled); // Read from state
    calendarToggle.checked = state.isCalendarContextActive; // Read from state

    // Web Search Toggle
    webSearchToggleLabel.classList.toggle('hidden', !state.isWebSearchPluginEnabled); // Read from state
    webSearchToggle.checked = state.isWebSearchEnabled; // Read from state
}


/**
 * Switches between the Chat and Notes tabs (updates UI visibility).
 * @param {'chat' | 'notes'} tab - The desired tab ('chat' or 'notes').
 */
export function switchTab(tab) { // Made synchronous, state is already updated by event listener
    const {
        chatNavButton, notesNavButton, chatSection, notesSection,
        chatSidebarContent, notesSidebarContent, modelSelectorContainer,
        notesModeElements, messageInput, notesTextarea, notesPreview,
        currentChatNameInput, currentNoteNameInput, currentChatIdDisplay,
        currentNoteIdDisplay, inputArea, sidebar, sidebarToggleButton
    } = elements;

    if (!chatNavButton || !notesNavButton || !chatSection || !notesSection ||
        !chatSidebarContent || !notesSidebarContent || !modelSelectorContainer ||
        !notesModeElements || !messageInput || !notesTextarea || !notesPreview ||
        !currentChatNameInput || !currentNoteNameInput || !currentChatIdDisplay ||
        !currentNoteIdDisplay || !inputArea || !sidebar || !sidebarToggleButton) {
        console.error("Missing elements for tab switching.");
        // Status update handled by event listener or caller
        return;
    }

    // State is already updated by the event listener calling this function
    // state.setCurrentTab(tab);
    // localStorage.setItem(config.ACTIVE_TAB_KEY, tab);

    // Update navigation buttons
    chatNavButton.classList.toggle('active', tab === 'chat');
    notesNavButton.classList.toggle('active', tab === 'notes');

    // Toggle main content sections
    chatSection.classList.toggle('hidden', tab !== 'chat');
    notesSection.classList.toggle('hidden', tab !== 'notes');

    // Toggle sidebar content sections
    chatSidebarContent.classList.toggle('hidden', tab !== 'chat');
    notesSidebarContent.classList.toggle('hidden', tab !== 'notes');

    // Toggle header elements (Model Selector vs Notes Mode)
    modelSelectorContainer.classList.toggle('hidden', tab !== 'chat');
    notesModeElements.classList.toggle('hidden', tab !== 'notes');

    // Toggle input area visibility (Chat needs it, Notes uses textarea directly)
    inputArea.classList.toggle('hidden', tab !== 'chat');

    // Update current item display in sidebar header based on state
    renderCurrentChatDetails(); // Reads state.currentChatName, state.currentChatId, state.currentChatModel
    renderCurrentNoteDetails(); // Reads state.currentNoteName, state.currentNoteId

    // Ensure sidebar content visibility matches the active tab if sidebar is open
    if (!sidebar.classList.contains('collapsed')) {
        if (tab === 'chat') {
            chatSidebarContent.classList.remove('hidden');
            notesSidebarContent.classList.add('hidden');
        } else { // tab === 'notes'
            notesSidebarContent.classList.remove('hidden');
            chatSidebarContent.classList.add('hidden');
        }
    }

    // Render content specific to the new tab based on state
    if (tab === 'chat') {
        renderChatHistory(); // Reads state.chatHistory
        renderUploadedFiles(); // Reads state.uploadedFiles, state.sidebarSelectedFiles, state.attachedFiles, state.sessionFile
        updateCalendarStatus(); // Reads state.calendarContext, state.isCalendarContextActive, state.isCalendarPluginEnabled
        renderChatInputArea(); // Reads plugin states, web search state, calendar active state, file plugin state
    } else { // tab === 'notes'
        renderNoteContent(); // Reads state.noteContent, state.currentNoteId, state.isLoading
        setNoteMode(state.currentNoteMode); // Applies persisted/default mode from state
    }
}

/**
 * Sets the display mode for the notes section (edit or view) based on state.
 * @param {'edit' | 'view'} mode - The desired mode.
 */
export function setNoteMode(mode) { // Made synchronous, state is already updated by event listener
    const { notesTextarea, notesPreview, editNoteButton, viewNoteButton } = elements;
    if (!notesTextarea || !notesPreview || !editNoteButton || !viewNoteButton) {
        console.error("Missing elements for note mode switching.");
        return;
    }

    // State is already updated by the event listener calling this function
    // state.setCurrentNoteMode(mode);
    // localStorage.setItem(config.CURRENT_NOTE_MODE_KEY, mode);

    if (state.currentNoteMode === 'edit') { // Read from state
        notesTextarea.classList.remove('hidden');
        notesPreview.classList.add('hidden');
        editNoteButton.classList.add('active');
        viewNoteButton.classList.remove('active');
        // Ensure preview is updated if switching back to edit after viewing
        if (typeof marked !== 'undefined') {
             notesPreview.innerHTML = marked.parse(notesTextarea.value); // Read from DOM for immediate preview update
        } else {
             notesPreview.textContent = notesTextarea.value; // Read from DOM
        }
    } else { // state.currentNoteMode === 'view'
        notesTextarea.classList.add('hidden');
        notesPreview.classList.remove('hidden');
        editNoteButton.classList.remove('active');
        viewNoteButton.classList.add('active');
        // Render markdown in the preview area
        if (typeof marked !== 'undefined') {
             notesPreview.innerHTML = marked.parse(state.noteContent); // Read from state
        } else {
             notesPreview.textContent = state.noteContent; // Read from state
        }
    }
}

/**
 * Updates the notes preview area by rendering the markdown from the state.
 */
export function updateNotesPreview() {
    const { notesTextarea, notesPreview } = elements;
    if (!notesTextarea || !notesPreview) return;

    // This function is typically called when the textarea content changes (via event listener)
    // or when the mode switches to 'view'.
    // It should read the *current* content from the textarea for immediate feedback in edit mode,
    // but from state.noteContent if rendering the preview based on loaded state.
    // Let's adjust this to always read from state.noteContent for consistency,
    // assuming the event listener updates state.noteContent on textarea input.

    if (state.currentNoteMode === 'view') { // Read from state
        if (typeof marked !== 'undefined') {
             notesPreview.innerHTML = marked.parse(state.noteContent); // Read from state
        } else {
             notesPreview.textContent = state.noteContent; // Read from state
        }
    }
    // If in edit mode, the textarea is visible, no need to update preview constantly
    // The textarea value is updated directly by user input, which should ideally
    // also trigger a state update for noteContent.
}


// --- Modal Helpers (UI-local state) ---

/**
 * Generic function to open a modal.
 * @param {HTMLElement} modalElement - The modal element.
 */
export function openModal(modalElement) {
    if (modalElement) {
        modalElement.classList.add('show');
        elements.bodyElement?.classList.add('modal-open');
    }
}

/**
 * Generic function to close a modal.
 * @param {HTMLElement} modalElement - The modal element.
 */
export function closeModal(modalElement) {
    if (modalElement) {
        modalElement.classList.remove('show');
         // Check if any other modals are open before removing modal-open class
        const anyModalOpen = document.querySelectorAll('.modal.show').length > 0;
        if (!anyModalOpen) {
             elements.bodyElement?.classList.remove('modal-open');
        }
    }
}

// --- State Change Reaction Functions ---
// These functions are called by eventListeners.js or app.js when specific state
// variables change, triggering the necessary UI updates.

export function handleStateChange_isLoading() {
    updateLoadingState();
    renderStatus(); // Loading state affects status message
    updateAttachButtonState(); // Loading state affects button disabled state
    renderNoteContent(); // Loading state affects note textarea placeholder/disabled
}

export function handleStateChange_statusMessage() {
    renderStatus();
}

export function handleStateChange_savedChats() {
    renderSavedChats();
}

export function handleStateChange_currentChat() { // Called when currentChatId, Name, Model change
    renderCurrentChatDetails();
    updateActiveChatListItem(); // Highlight correct chat in sidebar
    renderChatHistory(); // Load history for the new chat
    // File/Calendar/Web Search context is reset by API loadChat, which triggers
    // renderAttachedAndSessionFiles, updateCalendarStatus, renderChatInputArea
}

export function handleStateChange_chatHistory() {
    renderChatHistory();
}

export function handleStateChange_savedNotes() {
    renderSavedNotes();
}

export function handleStateChange_currentNote() { // Called when currentNoteId, Name, Content change
    renderCurrentNoteDetails();
    updateActiveNoteListItem(); // Highlight correct note in sidebar
    renderNoteContent(); // Load content for the new note
}

export function handleStateChange_uploadedFiles() {
    renderUploadedFiles(); // Renders sidebar and modal lists
}

export function handleStateChange_sidebarSelectedFiles() {
    updateSelectedFileListItemStyling(); // Updates sidebar highlighting
    updateAttachButtonState(); // Updates attach button state
}

export function handleStateChange_attachedFiles() {
    renderAttachedAndSessionFiles(); // Updates the tags below the input
}

export function handleStateChange_sessionFile() {
    renderAttachedAndSessionFiles(); // Updates the tags below the input
}

export function handleStateChange_currentEditingFileId() {
    // When the file ID for summary editing changes, the modal content needs re-rendering
    renderSummaryModalContent();
}

export function handleStateChange_summaryContent() {
    // When the summary content changes (e.g., after fetch or user edit), update the modal textarea
    renderSummaryModalContent();
}

export function handleStateChange_calendarContext() {
    updateCalendarStatus(); // Updates status text and view button
}

export function handleStateChange_isCalendarContextActive() {
    updateCalendarStatus(); // Updates toggle state and status text
    renderChatInputArea(); // Updates calendar toggle checked state
}

export function handleStateChange_isWebSearchEnabled() {
    renderChatInputArea(); // Updates web search toggle checked state
}

export function handleStateChange_pluginEnabled(pluginName) {
    // This function is called when any plugin enabled state changes
    updatePluginUI(); // Updates visibility of plugin sections and related UI
    // Specific plugin state changes (files, calendar) might trigger further actions
    // handled by eventListeners.js reacting to the toggle change.
}

export function handleStateChange_currentTab() {
    // The switchTab function already handles rendering everything for the new tab
    // This handler might be redundant if switchTab is only called by eventListeners.js
    // reacting to the tab state change. Let's keep it simple and rely on eventListeners.js
    // calling switchTab directly for now.
}

export function handleStateChange_currentNoteMode() {
    setNoteMode(state.currentNoteMode); // Applies the correct mode (edit/view)
    renderNoteContent(); // Ensures content is rendered correctly for the mode
}

// Add more handlers for other state changes as needed...
