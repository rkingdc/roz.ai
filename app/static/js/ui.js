// js/ui.js

// This module handles UI updates and interactions.
// It imports the elements object from dom.js.

import { elements } from './dom.js'; // Import elements from dom.js
import * as state from './state.js'; // Import state to check plugin status
import * as config from './config.js'; // Import config for keys
import { escapeHtml, formatFileSize } from './utils.js'; // Import utility functions
// Import api functions dynamically where needed to avoid circular dependencies

/**
 * Updates the text content of the status bar.
 * @param {string} message - The message to display.
 * @param {boolean} [isError=false] - Whether the message indicates an error.
 */
export function updateStatus(message, isError = false) {
    if (elements.statusBar) {
        elements.statusBar.textContent = `Status: ${message}`;
        if (isError) {
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
 * Adds a message to the chatbox.
 * @param {'user' | 'assistant' | 'system'} role - The role of the message sender.
 * @param {string} content - The message content (can be markdown).
 * @param {boolean} [isError=false] - Whether the message indicates an error.
 * @param {HTMLElement} [existingElement=null] - Optional existing element to append content to (for streaming).
 * @returns {HTMLElement|null} The message element that was created or updated.
 */
export function addMessage(role, content, isError = false, existingElement = null) {
    if (!elements.chatbox) {
        console.error("Chatbox element not found.");
        return null;
    }

    let messageElement;
    if (existingElement) {
        messageElement = existingElement;
        // Append content for streaming
        if (typeof marked !== 'undefined') {
             // Append raw text for streaming, will render markdown at the end
             messageElement.dataset.rawContent = (messageElement.dataset.rawContent || '') + content;
        } else {
             messageElement.textContent += content;
        }

    } else {
        // Create new message element
        messageElement = document.createElement('div');
        messageElement.classList.add('message', `${role}-msg`, 'p-3', 'mb-2', 'rounded-lg', 'whitespace-pre-wrap');

        if (isError) {
            messageElement.classList.add('bg-red-100', 'text-red-800', 'border', 'border-red-400');
            messageElement.innerHTML = `<strong>Error:</strong> ${escapeHtml(content)}`; // Escape HTML for error messages
        } else {
             // Store raw content for potential markdown rendering later (especially for streaming)
             messageElement.dataset.rawContent = content;
             // For non-streaming or initial message, render immediately
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
    }


    // Auto-scroll to the bottom
    elements.chatbox.scrollTop = elements.chatbox.scrollHeight;

    return messageElement;
}

/**
 * Applies markdown rendering to a message element using its raw content.
 * Useful after streaming is complete.
 * @param {HTMLElement} messageElement - The message element to render.
 */
export function applyMarkdownToMessage(messageElement) {
    if (!messageElement || typeof marked === 'undefined') return;

    const rawContent = messageElement.dataset.rawContent;
    if (rawContent !== undefined) {
        messageElement.innerHTML = marked.parse(rawContent);
        messageElement.classList.add('prose', 'prose-sm', 'max-w-none');
        // Remove the raw content dataset after rendering
        delete messageElement.dataset.rawContent;
    }
}


/**
 * Clears all messages from the chatbox.
 */
export function clearChatbox() {
     if (elements.chatbox) {
        elements.chatbox.innerHTML = '';
     }
}

/**
 * Sets the loading state of the UI.
 * Disables input, shows a loading indicator/message.
 * @param {boolean} isLoading - Whether the app is currently loading/busy.
 * @param {string} [statusMessage="Busy..."] - Optional message to show in the status bar.
 */
export function setLoadingState(isLoading, statusMessage = "Busy...") {
    state.setIsLoading(isLoading); // Update state module

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
    if (elements.attachFullButton) elements.attachFullButton.disabled = isLoading;
    if (elements.attachSummaryButton) elements.attachSummaryButton.disabled = isLoading;
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
    document.querySelectorAll('.list-item, .file-list-item').forEach(item => {
        if (isLoading) {
            item.classList.add('pointer-events-none', 'opacity-50');
        } else {
            item.classList.remove('pointer-events-none', 'opacity-50');
        }
    });


    if (isLoading) {
        updateStatus(statusMessage);
        elements.bodyElement?.classList.add('loading'); // Add a class to body for global loading styles
    } else {
        updateStatus("Idle");
        elements.bodyElement?.classList.remove('loading');
    }
}

/**
 * Toggles the collapsed state of a sidebar.
 * @param {HTMLElement} sidebarElement - The sidebar element.
 * @param {HTMLElement} toggleButton - The button that toggles the sidebar.
 * @param {boolean} isCollapsed - The desired state (true for collapsed).
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

/**
 * Toggles the collapsed state of a plugin section within the plugins sidebar.
 * @param {HTMLElement} headerElement - The header element of the plugin section.
 * @param {HTMLElement} contentElement - The content element of the plugin section.
 * @param {boolean} isCollapsed - The desired state (true for collapsed).
 * @param {string} localStorageKey - The key to use for localStorage.
 */
export function setPluginSectionCollapsed(headerElement, contentElement, isCollapsed, localStorageKey) {
     if (!headerElement || !contentElement) return;

     const toggleIcon = headerElement.querySelector('.toggle-icon');

     if (isCollapsed) {
         contentElement.classList.add('hidden');
         headerElement.classList.add('collapsed');
         if (toggleIcon) toggleIcon.classList.replace('fa-chevron-down', 'fa-chevron-right');
     } else {
         contentElement.classList.remove('hidden');
         headerElement.classList.remove('collapsed');
         if (toggleIcon) toggleIcon.classList.replace('fa-chevron-right', 'fa-chevron-down');
     }
     localStorage.setItem(localStorageKey, isCollapsed);
}


/**
 * Renders the list of saved chats in the sidebar.
 * @param {Array<Object>} chats - An array of chat objects { id, name, last_updated_at }.
 */
export function renderSavedChats(chats) {
    const { savedChatsList, currentChatNameInput, currentChatIdDisplay } = elements;
    if (!savedChatsList) return;

    savedChatsList.innerHTML = ''; // Clear current list

    if (!chats || chats.length === 0) {
        savedChatsList.innerHTML = '<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No saved chats yet.</p>';
        // Reset current chat display if no chats exist and one was selected
        if (state.currentChatId !== null) {
             currentChatNameInput.value = '';
             currentChatIdDisplay.textContent = 'ID: -';
             state.setCurrentChatId(null); // Clear state
             localStorage.removeItem('currentChatId');
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
    // Removed flex, items-center, justify-between from listItem itself
    listItem.classList.add('list-item', 'chat-list-item', 'p-2', 'border-b', 'border-rz-sidebar-border', 'cursor-pointer', 'hover:bg-rz-sidebar-hover');
    listItem.dataset.chatId = chat.id;

    // Container for name and delete button (flex row)
    const nameDeleteContainer = document.createElement('div');
    nameDeleteContainer.classList.add('flex', 'items-center', 'justify-between', 'w-full');

    const nameSpan = document.createElement('span');
    nameSpan.classList.add('filename', 'text-sm', 'text-rz-sidebar-text', 'truncate', 'flex-grow'); // Added truncate and flex-grow
    nameSpan.textContent = chat.name || `Chat ${chat.id}`;

    // Add delete button
    const deleteButton = document.createElement('button');
    // Changed text-red-500 to text-rz-sidebar-text for gold color consistency
    deleteButton.classList.add('delete-btn', 'text-rz-sidebar-text', 'hover:text-red-700', 'ml-2', 'flex-shrink-0');
    deleteButton.innerHTML = '<i class="fas fa-trash-alt text-xs"></i>';
    deleteButton.title = `Delete "${chat.name || `Chat ${chat.id}`}"`;
    deleteButton.addEventListener('click', (event) => {
        event.stopPropagation(); // Prevent triggering the list item click
        // Use a dynamic import for api to avoid circular dependency if api imports ui
        import('./api.js').then(api => {
            api.handleDeleteChat(chat.id, listItem);
        }).catch(error => console.error("Failed to import api for delete:", error));
    });

    nameDeleteContainer.appendChild(nameSpan);
    nameDeleteContainer.appendChild(deleteButton); // Append delete button

    // Add timestamp span
    const timestampSpan = document.createElement('span');
    // Default color is text-rz-tab-background-text (greyish)
    timestampSpan.classList.add('timestamp', 'text-xs', 'text-rz-tab-background-text', 'mt-1'); // Added timestamp class and styling
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
        timestampSpan.textContent = formattedDate;
    } catch (e) {
        console.error("Error formatting date:", chat.last_updated_at, e);
        timestampSpan.textContent = 'Invalid Date';
    }


    listItem.appendChild(nameDeleteContainer); // Append the container
    listItem.appendChild(timestampSpan); // Append the timestamp

    // Add click listener to load chat
    listItem.addEventListener('click', () => {
         if (chat.id != state.currentChatId) {
             // Use a dynamic import for api to avoid circular dependency if api imports ui
             import('./api.js').then(api => {
                 api.loadChat(chat.id); // Load this chat
             }).catch(error => console.error("Failed to import api for load chat:", error));
         }
    });

    savedChatsList.appendChild(listItem);
}


/** Updates the highlighting for the currently active chat list item. */
export function updateActiveChatListItem() {
    const { savedChatsList } = elements;
    if (!savedChatsList) return;

    savedChatsList.querySelectorAll('.chat-list-item').forEach(item => {
        const chatId = parseInt(item.dataset.chatId);
        const timestampSpan = item.querySelector('.timestamp'); // Find the timestamp span

        if (chatId === state.currentChatId) {
            item.classList.add('active-selection');
            // Change timestamp color to gold when active
            if (timestampSpan) {
                timestampSpan.classList.add('text-rz-sidebar-text');
                timestampSpan.classList.remove('text-rz-tab-background-text');
            }
        } else {
            item.classList.remove('active-selection');
            // Change timestamp color back to greyish when inactive
            if (timestampSpan) {
                timestampSpan.classList.remove('text-rz-sidebar-text');
                timestampSpan.classList.add('text-rz-tab-background-text');
            }
        }
    });
}


/**
 * Renders the list of saved notes in the sidebar.
 * @param {Array<Object>} notes - An array of note objects { id, name, last_saved_at }.
 */
export function renderSavedNotes(notes) {
    const { savedNotesList, currentNoteNameInput, currentNoteIdDisplay } = elements;
    if (!savedNotesList) return;

    savedNotesList.innerHTML = ''; // Clear current list

    if (!notes || notes.length === 0) {
        savedNotesList.innerHTML = '<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No saved notes yet.</p>';
         // Reset current note display if no notes exist and one was selected
        if (state.currentNoteId !== null) {
             currentNoteNameInput.value = '';
             currentNoteIdDisplay.textContent = 'ID: -';
             state.setCurrentNoteId(null); // Clear state
             localStorage.removeItem(config.CURRENT_NOTE_ID_KEY);
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
    listItem.classList.add('list-item', 'note-list-item', 'flex', 'items-center', 'justify-between', 'p-2', 'border-b', 'border-rz-sidebar-border', 'cursor-pointer', 'hover:bg-rz-sidebar-hover');
    listItem.dataset.noteId = note.id;

    const nameSpan = document.createElement('span');
    nameSpan.classList.add('filename', 'text-sm', 'text-rz-sidebar-text', 'truncate', 'flex-grow'); // Added truncate and flex-grow
    nameSpan.textContent = note.name || `Note ${note.id}`;

    // Add delete button
    const deleteButton = document.createElement('button');
    deleteButton.classList.add('delete-btn', 'text-red-500', 'hover:text-red-700', 'ml-2', 'flex-shrink-0'); // Added ml-2 and flex-shrink-0
    deleteButton.innerHTML = '<i class="fas fa-trash-alt text-xs"></i>';
    deleteButton.title = `Delete "${note.name || `Note ${note.id}`}"`;
    deleteButton.addEventListener('click', (event) => {
        event.stopPropagation(); // Prevent triggering the list item click
         // Use a dynamic import for api to avoid circular dependency if api imports ui
        import('./api.js').then(api => {
            api.handleDeleteNote(note.id, listItem);
        }).catch(error => console.error("Failed to import api for delete:", error));
    });

    listItem.appendChild(nameSpan);
    listItem.appendChild(deleteButton); // Append delete button

    // Add click listener to load note
    listItem.addEventListener('click', () => {
         if (note.id != state.currentNoteId) {
             // Use a dynamic import for api to avoid circular dependency if api imports ui
             import('./api.js').then(api => {
                 api.loadNote(note.id); // Load this note
             }).catch(error => console.error("Failed to import api for load note:", error));
         }
    });

    savedNotesList.appendChild(listItem);
}


/** Updates the highlighting for the currently active note list item. */
export function updateActiveNoteListItem() {
    const { savedNotesList } = elements;
    if (!savedNotesList) return;

    savedNotesList.querySelectorAll('.note-list-item').forEach(item => {
        const noteId = parseInt(item.dataset.noteId);
        if (noteId === state.currentNoteId) {
            item.classList.add('active-selection');
        } else {
            item.classList.remove('active-selection');
        }
    });
}


/**
 * Renders the list of uploaded files in the plugins sidebar and manage files modal.
 * @param {Array<Object>} files - An array of file objects { id, filename, mimetype, filesize, has_summary, uploaded_at }.
 */
export function renderUploadedFiles(files) {
    const { uploadedFilesList, manageFilesList } = elements;
    if (!uploadedFilesList || !manageFilesList) return;

    // Clear current lists
    uploadedFilesList.innerHTML = '';
    manageFilesList.innerHTML = '';

    if (!files || files.length === 0) {
        uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No files uploaded yet.</p>`;
        manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">No files uploaded yet.</p>`;
        return;
    }

    files.forEach(file => {
        const isSelected = state.selectedFiles.some(sf => sf.id === file.id);
        createSidebarFileItem(file, isSelected); // Use helper
        createModalFileItem(file, isSelected); // Use helper
    });

    // After rendering, update the display of selected files in the input area
    renderSelectedFiles(); // Use state.selectedFiles directly
}

/**
 * Creates a DOM element for a file item in the sidebar list.
 * @param {Object} file - The file object { id, filename, mimetype, filesize, has_summary }.
 * @param {boolean} isSelected - Whether the file is currently selected.
 * @returns {HTMLElement} The created div element.
 */
function createSidebarFileItem(file, isSelected) {
    const { uploadedFilesList } = elements;
    if (!uploadedFilesList) return;

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('file-list-item', 'flex', 'items-center', 'p-1', 'border-b', 'border-rz-sidebar-border', 'cursor-pointer', 'hover:bg-rz-sidebar-hover');
    itemDiv.dataset.fileId = file.id;
    itemDiv.dataset.filename = file.filename;
    itemDiv.dataset.hasSummary = file.has_summary; // Store summary status

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.classList.add('file-checkbox', 'mr-2');
    checkbox.checked = isSelected;
    checkbox.addEventListener('change', handleSidebarFileCheckboxChange); // Attach listener

    const nameSpan = document.createElement('span');
    nameSpan.classList.add('filename', 'text-sm', 'text-rz-sidebar-text', 'truncate', 'flex-grow'); // Added truncate and flex-grow
    nameSpan.textContent = file.filename;
    nameSpan.title = file.filename; // Add tooltip

    // Add summary status indicator
    const summaryStatus = document.createElement('span');
    summaryStatus.classList.add('summary-status', 'text-xs', 'ml-1', file.has_summary ? 'text-green-600' : 'text-yellow-600');
    summaryStatus.innerHTML = file.has_summary ? '<i class="fas fa-check-circle" title="Summary available"></i>' : '<i class="fas fa-exclamation-circle" title="No summary"></i>';


    itemDiv.appendChild(checkbox);
    itemDiv.appendChild(nameSpan);
    itemDiv.appendChild(summaryStatus);

    // Add click listener to toggle checkbox when clicking the item div (but not the checkbox itself)
    itemDiv.addEventListener('click', (event) => {
        if (event.target !== checkbox) {
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event('change')); // Trigger the change event manually
        }
    });


    uploadedFilesList.appendChild(itemDiv);
}

/**
 * Helper to handle sidebar file checkbox change.
 * @param {Event} e - The change event.
 */
function handleSidebarFileCheckboxChange(e) {
    const checkbox = e.target;
    const fileId = parseInt(checkbox.closest('.file-list-item')?.dataset.fileId); // Get ID from dataset
    const listItem = checkbox.closest('.file-list-item');
    const filename = listItem?.dataset.filename;
    if (!listItem || !filename || isNaN(fileId)) return;

    // Find the corresponding item in the modal list
    const modalItem = elements.manageFilesList?.querySelector(`.file-list-item[data-file-id="${fileId}"]`);
    const modalCheckbox = modalItem?.querySelector('.file-checkbox');

    if (checkbox.checked) {
        // Add a placeholder entry, type will be determined later when attach button clicked
        state.addSelectedFile({ id: fileId, filename: filename, type: 'pending' });
        listItem.classList.add('active-selection');
        if (modalItem) modalItem.classList.add('active-selection'); // Sync modal styling
        if (modalCheckbox) modalCheckbox.checked = true; // Sync modal checkbox
    } else {
        // Remove ALL entries for this file ID from selectedFiles
        state.removeSelectedFileById(fileId);
        listItem.classList.remove('active-selection');
        if (modalItem) modalItem.classList.remove('active-selection'); // Sync modal styling
        if (modalCheckbox) modalCheckbox.checked = false; // Sync modal checkbox
    }
    renderSelectedFiles(); // Update the display below the message input
}


/**
 * Creates a DOM element for a file item in the Manage Files modal list.
 * @param {Object} file - The file object { id, filename, mimetype, filesize, has_summary, uploaded_at }.
 * @param {boolean} isSelected - Whether the file is currently selected.
 */
function createModalFileItem(file, isSelected) {
    const { manageFilesList } = elements;
     if (!manageFilesList) return;

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('file-list-item', 'grid', 'grid-cols-12', 'gap-2', 'items-center', 'p-2', 'border-b', 'border-gray-200', 'last:border-b-0', 'text-sm');
    itemDiv.dataset.fileId = file.id;
    itemDiv.dataset.filename = file.filename;
    itemDiv.dataset.hasSummary = file.has_summary;
    itemDiv.classList.toggle('active-selection', isSelected); // Keep styling sync

    // Checkbox (col-span-1)
    const checkboxCol = document.createElement('div');
    checkboxCol.classList.add('col-span-1', 'flex', 'items-center');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.classList.add('file-checkbox');
    checkbox.checked = isSelected;
     checkbox.addEventListener('change', handleModalFileCheckboxChange); // Attach listener
    checkboxCol.appendChild(checkbox);

    // Filename (col-span-6)
    const nameCol = document.createElement('div');
    nameCol.classList.add('col-span-6', 'text-sm', 'text-gray-800', 'truncate');
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
    summaryButton.addEventListener('click', (e) => {
         e.stopPropagation(); // Prevent triggering item click
         // Use a dynamic import for api to avoid circular dependency if api imports ui
        import('./api.js').then(api => {
            api.showSummaryModal(file.id, file.filename);
        }).catch(error => console.error("Failed to import api for summary:", error));
    });

    // Delete Button
    const deleteButton = document.createElement('button');
    deleteButton.classList.add('btn', 'btn-outline', 'btn-xs', 'p-1', 'text-red-500', 'hover:text-red-700');
    deleteButton.innerHTML = '<i class="fas fa-trash-alt"></i>';
    deleteButton.title = 'Delete File';
    deleteButton.addEventListener('click', (e) => {
         e.stopPropagation(); // Prevent triggering item click
         // Use a dynamic import for api to avoid circular dependency if api imports ui
        import('./api.js').then(api => {
            api.deleteFile(file.id); // Call the API function
        }).catch(error => console.error("Failed to import api for delete:", error));
    });

    actionsCol.appendChild(summaryButton);
    actionsCol.appendChild(deleteButton);

    itemDiv.appendChild(checkboxCol);
    itemDiv.appendChild(nameCol);
    itemDiv.appendChild(sizeCol);
    itemDiv.appendChild(actionsCol);

     // Add click listener to toggle checkbox when clicking the item div (but not the checkbox or buttons)
    itemDiv.addEventListener('click', (event) => {
        // Check if the click target is the checkbox or any button within the actions column
        const isActionElement = event.target === checkbox || actionsCol.contains(event.target);
        if (!isActionElement) {
            checkbox.checked = !checkbox.checked;
            checkbox.dispatchEvent(new Event('change')); // Trigger the change event manually
        }
    });

    manageFilesList.appendChild(itemDiv);
}

/**
 * Helper to handle modal file checkbox change.
 * @param {Event} e - The change event.
 */
function handleModalFileCheckboxChange(e) {
    const checkbox = e.target;
    const fileId = parseInt(checkbox.closest('.file-list-item')?.dataset.fileId); // Get ID from dataset
    const listItem = checkbox.closest('.file-list-item');
    const filename = listItem?.dataset.filename;
    if (!listItem || !filename || isNaN(fileId)) return;

    // Find the corresponding item in the sidebar list
    const sidebarItem = elements.uploadedFilesList?.querySelector(`.file-list-item[data-file-id="${fileId}"]`);
    const sidebarCheckbox = sidebarItem?.querySelector('.file-checkbox');


    if (checkbox.checked) {
        // Add a placeholder entry, type will be determined later when attach button clicked
        state.addSelectedFile({ id: fileId, filename: filename, type: 'pending' });
        listItem.classList.add('active-selection');
        if (sidebarItem) sidebarItem.classList.add('active-selection'); // Sync sidebar styling
        if (sidebarCheckbox) sidebarCheckbox.checked = true; // Sync sidebar checkbox
    } else {
        // Remove ALL entries for this file ID from selectedFiles
        state.removeSelectedFileById(fileId);
        listItem.classList.remove('active-selection');
        if (modalItem) modalItem.classList.remove('active-selection'); // Sync modal styling
        if (modalCheckbox) modalCheckbox.checked = false; // Sync modal checkbox
    }
    renderSelectedFiles(); // Update the display below the message input
}


/**
 * Renders the list of currently selected files below the message input.
 */
export function renderSelectedFiles() {
    const { selectedFilesContainer, fileUploadSessionInput } = elements;
    if (!selectedFilesContainer) return;

    selectedFilesContainer.innerHTML = ''; // Clear current display

    if (state.selectedFiles.length === 0) {
        selectedFilesContainer.classList.add('hidden');
        // If session file was cleared, reset the input value
        if (!state.sessionFile && fileUploadSessionInput) {
             fileUploadSessionInput.value = '';
        }
        return;
    }

    selectedFilesContainer.classList.remove('hidden');

    state.selectedFiles.forEach(file => {
        const fileTag = document.createElement('span');
        fileTag.classList.add('selected-file-tag', 'inline-flex', 'items-center', 'bg-blue-100', 'text-blue-800', 'text-xs', 'font-medium', 'px-2.5', 'py-0.5', 'rounded-full', 'mr-2', 'mb-1');
        fileTag.dataset.fileId = file.id;
        fileTag.dataset.fileType = file.type; // 'permanent' or 'session'

        const filenameSpan = document.createElement('span');
        filenameSpan.textContent = file.filename;
        filenameSpan.classList.add('mr-1');

        const removeButton = document.createElement('button');
        removeButton.classList.add('remove-file-btn', 'ml-1', 'text-blue-800', 'hover:text-blue-900');
        removeButton.innerHTML = '<i class="fas fa-times-circle"></i>';
        removeButton.title = `Remove ${file.type === 'session' ? 'session' : 'attached'} file`;
        removeButton.addEventListener('click', () => {
            if (file.type === 'session') {
                state.setSessionFile(null); // Clear session file state
                // Also reset the file input element
                if (elements.fileUploadSessionInput) { // Use elements.fileUploadSessionInput
                    elements.fileUploadSessionInput.value = '';
                }
            } else { // Permanent file
                state.removeSelectedFileById(file.id);
                 // Uncheck the corresponding checkbox in the sidebar/modal
                const sidebarCheckbox = elements.uploadedFilesList?.querySelector(`.file-list-item[data-file-id="${file.id}"] .file-checkbox`);
                if (sidebarCheckbox) sidebarCheckbox.checked = false;
                 const modalCheckbox = elements.manageFilesList?.querySelector(`.file-list-item[data-file-id="${file.id}"] .file-checkbox`);
                if (modalCheckbox) modalCheckbox.checked = false;
            }
            renderSelectedFiles(); // Re-render the display
        });

        fileTag.appendChild(filenameSpan);
        fileTag.appendChild(removeButton);
        selectedFilesContainer.appendChild(fileTag);
    });
}

/**
 * Renders the session file tag specifically.
 * This is a helper to ensure the session file is always the only 'session' type file displayed.
 * Called when a session file is added or removed.
 */
export function renderSessionFileTag() {
    const sessionFile = state.sessionFile;
    // Filter out any old session file tags before rendering the new one (or none)
    // CORRECTED: Use the state function to remove the session file from the array
    state.removeSessionFileFromSelected();

    if (sessionFile) {
        // Add the current session file to selectedFiles if it's not already there
        if (!state.selectedFiles.some(f => f.type === 'session')) {
             state.selectedFiles.push(sessionFile);
        }
    }
    renderSelectedFiles(); // Re-render the entire selected files container
}


/**
 * Shows a modal window.
 * @param {HTMLElement} modalElement - The modal element to show.
 * @param {string} [requiredPlugin=null] - Optional plugin key ('files', 'calendar', etc.) required to show the modal.
 * @param {string} [requiredTab=null] - Optional tab key ('chat', 'notes') required to show the modal.
 * @returns {boolean} True if the modal was shown, false otherwise.
 */
export function showModal(modalElement, requiredPlugin = null, requiredTab = null) {
    if (!modalElement) {
        console.error("Modal element not found.");
        return false;
    }

    // Check if required plugin is enabled
    if (requiredPlugin) {
        let pluginEnabled = false;
        if (requiredPlugin === 'files' && state.isFilePluginEnabled) pluginEnabled = true;
        if (requiredPlugin === 'calendar' && state.isCalendarPluginEnabled) pluginEnabled = true;
        // Add checks for other plugins here
        if (!pluginEnabled) {
            updateStatus(`${requiredPlugin.charAt(0).toUpperCase() + requiredPlugin.slice(1)} plugin is not enabled.`, true);
            return false;
        }
    }

    // Check if required tab is active
    if (requiredTab && state.currentTab !== requiredTab) {
         updateStatus(`This action is only available on the ${requiredTab.charAt(0).toUpperCase() + requiredTab.slice(1)} tab.`, true);
         return false;
    }


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
export function toggleSidebar(sidebarElement, toggleButton, localStorageKey, type) {
    if (!sidebarElement || !toggleButton) return;
    const isCollapsed = sidebarElement.classList.contains('collapsed');
    setSidebarCollapsed(sidebarElement, toggleButton, !isCollapsed, localStorageKey, type);
}

/** Toggles the left sidebar (chat/notes list). */
export function toggleLeftSidebar() {
    toggleSidebar(elements.sidebar, elements.sidebarToggleButton, config.SIDEBAR_COLLAPSED_KEY, 'sidebar');
}

/** Toggles the right sidebar (plugins). */
export function toggleRightSidebar() {
    toggleSidebar(elements.pluginsSidebar, elements.pluginsToggleButton, config.PLUGINS_COLLAPSED_KEY, 'plugins');
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
 * Updates the UI based on which plugins are enabled/disabled.
 */
export function updatePluginUI() {
    // File Plugin
    if (elements.filePluginSection) {
        elements.filePluginSection.classList.toggle('hidden', !state.isFilePluginEnabled);
    }
    // Hide file upload label and selected files container if plugin is disabled
    if (elements.fileUploadSessionLabel) {
         elements.fileUploadSessionLabel.classList.toggle('hidden', !state.isFilePluginEnabled);
    }
     if (elements.selectedFilesContainer) {
         // Only hide if plugin is disabled AND there are no selected files (to avoid hiding during transition)
         if (!state.isFilePluginEnabled && state.selectedFiles.length === 0) {
             elements.selectedFilesContainer.classList.add('hidden');
         }
         // If plugin is enabled and there are selected files, ensure it's visible
         if (state.isFilePluginEnabled && state.selectedFiles.length > 0) {
              elements.selectedFilesContainer.classList.remove('hidden');
         }
     }


    // Calendar Plugin
    if (elements.calendarPluginSection) {
        elements.calendarPluginSection.classList.toggle('hidden', !state.isCalendarPluginEnabled);
    }
    // Hide calendar toggle input area if plugin is disabled
    if (elements.calendarToggleInputArea) {
         elements.calendarToggleInputArea.classList.toggle('hidden', !state.isCalendarPluginEnabled);
    }


    // Web Search Toggle (part of Chat input area)
    if (elements.webSearchToggleLabel) {
        elements.webSearchToggleLabel.classList.toggle('hidden', !state.isWebSearchPluginEnabled);
    }

    // Re-render file lists if file plugin state changed
    if (elements.uploadedFilesList && elements.manageFilesList) {
        if (!state.isFilePluginEnabled) {
             elements.uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
             elements.manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
             state.clearSelectedFiles(); // Clear any selected files if plugin is disabled
             renderSelectedFiles(); // Update display
        } else {
            // If plugin was just enabled, trigger a reload of files
            // This is handled by loadUploadedFiles in api.js, which is called during init
            // or when the setting is toggled.
        }
    }

    // Update calendar status if calendar plugin state changed
    if (elements.calendarStatus) {
        if (!state.isCalendarPluginEnabled) {
            elements.calendarStatus.textContent = "Status: Plugin disabled";
            state.setCalendarContext(null); // Clear context if plugin disabled
            state.setCalendarContextActive(false); // Deactivate toggle
            if(elements.calendarToggle) elements.calendarToggle.checked = false;
            if(elements.viewCalendarButton) elements.viewCalendarButton.classList.add('hidden');
        } else {
             // If plugin was just enabled, the status will be updated when loadCalendarButton is clicked
             // or on initial load if context was persisted.
        }
    }

    // Update web search toggle state if plugin state changed
    if (elements.webSearchToggle) {
         if (!state.isWebSearchPluginEnabled) {
             elements.webSearchToggle.checked = false; // Turn off toggle if plugin disabled
         }
         // The toggle's checked state is persisted/loaded in loadPersistedStates
    }
}

/**
 * Updates the calendar status text and view button visibility.
 */
export function updateCalendarStatus() {
    const { calendarStatus, viewCalendarButton, calendarToggle } = elements;
    if (!calendarStatus || !viewCalendarButton || !calendarToggle) return;

    const context = state.calendarContext;
    const isActive = state.isCalendarContextActive;

    if (!state.isCalendarPluginEnabled) {
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
        state.setCalendarContextActive(false); // Ensure state is false
    }
}


/**
 * Switches between the Chat and Notes tabs.
 * @param {'chat' | 'notes'} tab - The desired tab ('chat' or 'notes').
 */
export async function switchTab(tab) {
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
        updateStatus("Error switching tabs: Missing UI elements.", true);
        return;
    }

    // Save current state before switching (e.g., auto-save note)
    // Note: Auto-save logic is not fully implemented here, just a placeholder
    if (state.currentTab === 'notes' && state.currentNoteId) {
        // Use dynamic import for api
        import('./api.js').then(api => {
             // await api.saveNote(); // Implement auto-save if needed
        }).catch(error => console.error("Failed to import api for auto-save:", error));
    }

    state.setCurrentTab(tab);
    localStorage.setItem(config.ACTIVE_TAB_KEY, tab);

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

    // Update current item display in sidebar header
    if (tab === 'chat') {
         const currentChat = state.savedChats.find(c => c.id === state.currentChatId);
         currentChatNameInput.value = currentChat ? (currentChat.name || `Chat ${currentChat.id}`) : '';
         currentChatIdDisplay.textContent = currentChat ? `ID: ${currentChat.id}` : 'ID: -';
         // Ensure chat list is visible if sidebar is open
         if (!sidebar.classList.contains('collapsed')) {
             chatSidebarContent.classList.remove('hidden');
             notesSidebarContent.classList.add('hidden');
         }

    } else { // tab === 'notes'
         const currentNote = state.savedNotes.find(n => n.id === state.currentNoteId);
         currentNoteNameInput.value = currentNote ? (currentNote.name || `Note ${currentNote.id}`) : '';
         currentNoteIdDisplay.textContent = currentNote ? `ID: ${currentNote.id}` : 'ID: -';

         // Ensure notes list is visible if sidebar is open
         if (!sidebar.classList.contains('collapsed')) {
             notesSidebarContent.classList.remove('hidden');
             chatSidebarContent.classList.add('hidden');
         }

         // Ensure notes mode is set correctly on switch
         setNoteMode(state.currentNoteMode);
    }

    // Load data specific to the new tab
    // Use dynamic imports for api functions to avoid circular dependencies
    if (tab === 'chat') {
        import('./api.js').then(api => {
            // If there's a persisted chat ID, load it. Otherwise, start a new chat.
            if (state.currentChatId !== null) {
                api.loadChat(state.currentChatId).catch(error => {
                    console.error("Error loading persisted chat:", error);
                    // Fallback to starting a new chat if loading fails
                    api.startNewChat();
                });
            } else {
                api.startNewChat();
            }
        }).catch(error => console.error("Failed to import api for chat tab:", error));
    } else { // tab === 'notes'
         import('./api.js').then(api => {
             // If there's a persisted note ID, load it. Otherwise, start a new note.
            if (state.currentNoteId !== null) {
                api.loadNote(state.currentNoteId).catch(error => {
                    console.error("Error loading persisted note:", error);
                    // Fallback to starting a new note if loading fails
                    api.startNewNote();
                });
            } else {
                api.startNewNote();
            }
         }).catch(error => console.error("Failed to import api for notes tab:", error));
    }
}

/**
 * Sets the display mode for the notes section (edit or view).
 * @param {'edit' | 'view'} mode - The desired mode.
 */
export function setNoteMode(mode) {
    const { notesTextarea, notesPreview, editNoteButton, viewNoteButton } = elements;
    if (!notesTextarea || !notesPreview || !editNoteButton || !viewNoteButton) {
        console.error("Missing elements for note mode switching.");
        return;
    }

    state.setCurrentNoteMode(mode);
    localStorage.setItem(config.CURRENT_NOTE_MODE_KEY, mode);

    if (mode === 'edit') {
        notesTextarea.classList.remove('hidden');
        notesPreview.classList.add('hidden');
        editNoteButton.classList.add('active');
        viewNoteButton.classList.remove('active');
        // Ensure preview is updated if switching back to edit after viewing
        if (typeof marked !== 'undefined') {
             notesPreview.innerHTML = marked.parse(notesTextarea.value);
        } else {
             notesPreview.textContent = notesTextarea.value;
        }
    } else { // mode === 'view'
        notesTextarea.classList.add('hidden');
        notesPreview.classList.remove('hidden');
        editNoteButton.classList.remove('active');
        viewNoteButton.classList.add('active');
        // Render markdown in the preview area
        if (typeof marked !== 'undefined') {
             notesPreview.innerHTML = marked.parse(notesTextarea.value);
        } else {
             notesPreview.textContent = notesTextarea.value;
        }
    }
}

/**
 * Updates the notes preview area by rendering the markdown from the textarea.
 */
export function updateNotesPreview() {
    const { notesTextarea, notesPreview } = elements;
    if (!notesTextarea || !notesPreview) return;

    if (state.currentNoteMode === 'view') {
        // Only update preview if in view mode
        if (typeof marked !== 'undefined') {
             notesPreview.innerHTML = marked.parse(notesTextarea.value);
        } else {
             notesPreview.textContent = notesTextarea.value;
        }
    }
    // If in edit mode, the textarea is visible, no need to update preview constantly
}


// --- Modal Helpers ---

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
