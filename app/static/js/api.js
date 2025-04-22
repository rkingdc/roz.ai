// js/api.js
import { elements } from './dom.js';
import * as state from './state.js';
import * as ui from './ui.js';
import { escapeHtml } from './utils.js';
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js';

// --- File API ---

/** Deletes a file from the backend and updates the UI lists. */
export async function deleteFile(fileId) {
    if (state.isLoading) return;
    if (!confirm("Are you sure you want to delete this file? This action cannot be undone.")) {
        return;
    }

    ui.setLoadingState(true, "Deleting File");
    try {
        const response = await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        ui.updateStatus(`File ${fileId} deleted.`);
        await loadUploadedFiles(); // Reload file lists
        state.removeSelectedFileById(fileId); // Remove from selected state
        ui.renderSelectedFiles(); // Update attached files display
    } catch (error) {
        console.error('Error deleting file:', error);
        ui.updateStatus(`Error deleting file: ${error.message}`, true);
    } finally {
        ui.setLoadingState(false);
    }
}

/** Loads uploaded files and populates the lists in both the sidebar and the modal. */
export async function loadUploadedFiles() {
    const { uploadedFilesList, manageFilesList } = elements;
    if (!uploadedFilesList || !manageFilesList) return;

    // Only load if Files plugin is enabled
    if (!state.isFilePluginEnabled) {
        uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
        manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
        // Don't set loading state here, as this might be called when plugin is toggled off
        // ui.updateStatus("Files plugin disabled. File list not loaded.");
        return;
    }

    // Set loading state only if not already loading (might be called during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) ui.setLoadingState(true, "Loading Files");

    uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;
    manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Loading...</p>`;

    try {
        const response = await fetch('/api/files');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const files = await response.json();

        uploadedFilesList.innerHTML = '';
        manageFilesList.innerHTML = '';

        if (files.length === 0) {
            uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No files uploaded yet.</p>`;
            manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">No files uploaded yet.</p>`;
        } else {
            files.forEach(file => {
                const isSelected = state.selectedFiles.some(f => f.id === file.id);
                // --- Create Sidebar List Item ---
                createSidebarFileItem(file, isSelected);
                // --- Create Modal List Item ---
                createModalFileItem(file, isSelected);
            });
        }
        ui.updateStatus("Uploaded files loaded.");
    } catch (error) {
        console.error('Error loading uploaded files:', error);
        uploadedFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
        manageFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
        ui.updateStatus("Error loading files.", true);
        // Don't re-throw here, let the caller handle UI state if needed
    } finally {
        // Only turn off loading if this function set it
        if (!wasLoading) ui.setLoadingState(false);
    }
}

// Helper to create sidebar file item
function createSidebarFileItem(file, isSelected) {
    const { uploadedFilesList } = elements;
    if (!uploadedFilesList) return;

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('file-list-item', 'flex', 'items-center', 'p-1', 'border-b', 'border-rz-sidebar-border', 'last:border-b-0');
    itemDiv.dataset.fileId = file.id;
    itemDiv.dataset.filename = file.filename;
    itemDiv.classList.toggle('active-selection', isSelected);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = file.id;
    checkbox.classList.add('file-checkbox', 'mr-2');
    checkbox.title = "Select file for attachment";
    checkbox.checked = isSelected;
    checkbox.addEventListener('change', handleSidebarFileCheckboxChange); // Attach listener

    const nameSpan = document.createElement('span');
    nameSpan.textContent = file.filename;
    nameSpan.classList.add('filename', 'truncate', 'flex-grow', 'text-sm', 'text-rz-sidebar-text');
    nameSpan.title = file.filename;

    itemDiv.appendChild(checkbox);
    itemDiv.appendChild(nameSpan);
    uploadedFilesList.appendChild(itemDiv);
}

// Helper to handle sidebar checkbox change
function handleSidebarFileCheckboxChange(e) {
    const checkbox = e.target;
    const fileId = parseInt(checkbox.value);
    const listItem = checkbox.closest('.file-list-item');
    const filename = listItem?.dataset.filename;
    if (!listItem || !filename) return;

    // Find the corresponding item in the modal list
    const modalItem = elements.manageFilesList?.querySelector(`.file-list-item[data-file-id="${fileId}"]`);

    if (checkbox.checked) {
        // Add a placeholder entry, type will be determined later when attach button clicked
        state.addSelectedFile({ id: fileId, filename: filename, type: 'pending' });
        listItem.classList.add('active-selection');
        modalItem?.classList.add('active-selection'); // Sync modal styling
    } else {
        // Remove ALL entries for this file ID from selectedFiles
        state.removeSelectedFileById(fileId);
        listItem.classList.remove('active-selection');
        modalItem?.classList.remove('active-selection'); // Sync modal styling
    }
    ui.renderSelectedFiles(); // Update the display below the message input
}


// Helper to create modal file item
function createModalFileItem(file, isSelected) {
    const { manageFilesList } = elements;
     if (!manageFilesList) return;

    const itemDiv = document.createElement('div');
    itemDiv.classList.add('file-list-item', 'grid', 'grid-cols-12', 'gap-2', 'items-center', 'p-2', 'border-b', 'border-gray-200', 'last:border-b-0', 'text-sm');
    itemDiv.dataset.fileId = file.id;
    itemDiv.dataset.filename = file.filename;
    itemDiv.dataset.hasSummary = file.has_summary;
    itemDiv.classList.toggle('active-selection', isSelected); // Keep styling sync

    // Col 1: Filename and Type
    const fileInfoDiv = document.createElement('div');
    fileInfoDiv.classList.add('col-span-5', 'flex', 'flex-col', 'min-w-0');
    fileInfoDiv.innerHTML = `
        <span class="filename truncate font-medium" title="${escapeHtml(file.filename)}">${escapeHtml(file.filename)}</span>
        <span class="file-type-display text-xs text-gray-500">Type: ${escapeHtml(file.mimetype ? file.mimetype.split('/')[1] || file.mimetype : 'unknown')}</span>
    `;

    // Col 2: Upload Date and Summary Status
    const detailsDiv = document.createElement('div');
    detailsDiv.classList.add('col-span-4', 'flex', 'flex-col', 'min-w-0');
    let formattedDate = 'Date N/A';
    if (file.uploaded_at) {
        try {
            const date = new Date(file.uploaded_at.replace(' ', 'T')); // Try to make it ISO-like
            if (!isNaN(date.getTime())) {
                 formattedDate = date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
            }
        } catch (e) { /* Ignore date parsing errors */ }
    }
    detailsDiv.innerHTML = `
        <span class="text-xs text-gray-500">Uploaded: ${formattedDate}</span>
        <span class="text-xs ${file.has_summary ? 'text-green-600' : 'text-gray-500'}">${file.has_summary ? 'Summary: Yes' : 'Summary: No'}</span>
    `;

    // Col 3: Actions
    const actionsDiv = document.createElement('div');
    actionsDiv.classList.add('col-span-3', 'flex', 'items-center', 'justify-end', 'gap-1');

    const summaryBtn = document.createElement('button');
    summaryBtn.classList.add('btn', 'btn-outline', 'btn-xs', 'p-1');
    summaryBtn.innerHTML = '<i class="fas fa-file-alt"></i>';
    summaryBtn.title = file.has_summary ? "View/Edit Summary" : "Generate Summary";
    summaryBtn.onclick = (e) => {
        e.stopPropagation();
        showSummaryModal(file.id, file.filename); // Call function below
    };
    actionsDiv.appendChild(summaryBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.classList.add('btn', 'btn-outline', 'btn-xs', 'delete-btn', 'p-1');
    deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
    deleteBtn.title = "Delete File";
    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        deleteFile(file.id); // Call API function
    };
    actionsDiv.appendChild(deleteBtn);

    itemDiv.appendChild(fileInfoDiv);
    itemDiv.appendChild(detailsDiv);
    itemDiv.appendChild(actionsDiv);
    manageFilesList.appendChild(itemDiv);
}


/** Handles file upload triggered from the modal. */
export async function handleFileUpload(event) {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
        ui.updateStatus("File uploads only allowed when Files plugin is enabled and on Chat tab.", true);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }

    const files = event.target.files;
    if (!files || files.length === 0) {
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }

    ui.setLoadingState(true, "Uploading");
    const formData = new FormData();
    let fileCount = 0;
    for (const file of files) {
        if (file.size > MAX_FILE_SIZE_BYTES) {
            alert(`Skipping "${file.name}": File is too large (${ui.formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
            continue;
        }
        formData.append('file', file);
        fileCount++;
    }

    if (fileCount === 0) {
        ui.setLoadingState(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        ui.updateStatus("No valid files selected for upload.", true);
        return;
    }

    try {
        const response = await fetch('/api/files', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        const successfulUploads = data.uploaded_files?.length || 0;
        const errors = data.errors || [];
        let statusMsg = `Uploaded ${successfulUploads} file(s).`;
        if (errors.length > 0) {
            statusMsg += ` ${errors.length} failed: ${errors.join('; ')}`;
        }
        ui.updateStatus(statusMsg, errors.length > 0);
    } catch (error) {
        console.error('Error uploading files:', error);
        ui.updateStatus(`Error uploading files: ${error.message}`, true);
    } finally {
        await loadUploadedFiles(); // Reload lists
        ui.setLoadingState(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = ''; // Reset input
    }
}

/** Adds a file by fetching content from a URL. */
export async function addFileFromUrl(url) {
     if (state.isLoading) return;
     if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         if(elements.urlStatus) {
             elements.urlStatus.textContent = "Adding from URL requires Files plugin enabled on Chat tab.";
             elements.urlStatus.classList.add('text-red-500');
         }
         return;
     }
     if (!url || !url.startsWith('http')) {
         if(elements.urlStatus) {
             elements.urlStatus.textContent = "Please enter a valid URL (http/https).";
             elements.urlStatus.classList.add('text-red-500');
         }
         return;
     }

     ui.setLoadingState(true, "Fetching URL");
     if(elements.urlStatus) {
         elements.urlStatus.textContent = "Fetching content...";
         elements.urlStatus.classList.remove('text-red-500');
     }

     try {
         const response = await fetch('/api/files/from_url', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ url: url })
         });
         const data = await response.json();
         if (!response.ok) {
             throw new Error(data.error || `HTTP error! status: ${response.status}`);
         }
         ui.updateStatus(`Successfully added file from URL: ${data.filename}`);
         if(elements.urlStatus) elements.urlStatus.textContent = `Successfully added file: ${data.filename}`;
         if(elements.urlInput) elements.urlInput.value = ''; // Clear input
         await loadUploadedFiles(); // Reload lists
         ui.closeModal(elements.urlModal); // Close the URL modal
     } catch (error) {
         console.error('Error adding file from URL:', error);
         ui.updateStatus(`Error adding file from URL: ${error.message}`, true);
         if(elements.urlStatus) {
             elements.urlStatus.textContent = `Error: ${error.message}`;
             elements.urlStatus.classList.add('text-red-500');
         }
     } finally {
         ui.setLoadingState(false);
     }
}

/** Shows the summary modal and fetches/displays the summary. */
export async function showSummaryModal(fileId, filename) {
    // Use the generic showModal helper
    if (!ui.showModal(elements.summaryModal, 'files', 'chat')) return;

    state.setCurrentEditingFileId(fileId);
    if(elements.summaryModalFilename) elements.summaryModalFilename.textContent = filename;
    if(elements.summaryTextarea) {
        elements.summaryTextarea.value = "";
        elements.summaryTextarea.placeholder = "Loading or generating summary...";
    }
    if(elements.summaryStatus) {
        elements.summaryStatus.textContent = "";
        elements.summaryStatus.classList.remove('text-red-500');
    }
    if(elements.saveSummaryButton) elements.saveSummaryButton.disabled = true;

    ui.setLoadingState(true, "Fetching Summary");
    try {
        const response = await fetch(`/api/files/${fileId}/summary`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        const data = await response.json();
        if(elements.summaryTextarea) {
            elements.summaryTextarea.value = data.summary;
            elements.summaryTextarea.placeholder = "Enter or edit summary here.";
        }
        if(elements.saveSummaryButton) elements.saveSummaryButton.disabled = false;
        ui.updateStatus(`Summary loaded for ${filename}.`);

        if (data.summary.startsWith("[Error") || data.summary.startsWith("[Summary not applicable")) {
             if(elements.summaryStatus) {
                 elements.summaryStatus.textContent = data.summary;
                 elements.summaryStatus.classList.add('text-red-500');
             }
             if(elements.saveSummaryButton) elements.saveSummaryButton.disabled = data.summary.startsWith("[Summary not applicable");
        } else if (elements.summaryStatus) {
             elements.summaryStatus.textContent = "Summary loaded. You can edit and save changes.";
        }
    } catch (error) {
        console.error("Error fetching summary:", error);
        if(elements.summaryTextarea) {
            elements.summaryTextarea.value = `[Error loading summary: ${error.message}]`;
            elements.summaryTextarea.placeholder = "Could not load summary.";
        }
        ui.updateStatus(`Error fetching summary for ${filename}.`, true);
        if(elements.summaryStatus) {
            elements.summaryStatus.textContent = `Error: ${error.message}`;
            elements.summaryStatus.classList.add('text-red-500');
        }
    } finally {
        ui.setLoadingState(false);
    }
}

/** Saves the edited summary. */
export async function saveSummary() {
    if (!state.currentEditingFileId || state.isLoading) return;
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         ui.updateStatus("Saving summaries requires Files plugin enabled on Chat tab.", true);
         return;
    }

    const updatedSummary = elements.summaryTextarea?.value || '';
    ui.setLoadingState(true, "Saving Summary");
    if(elements.summaryStatus) {
        elements.summaryStatus.textContent = "Saving...";
        elements.summaryStatus.classList.remove('text-red-500');
    }

    try {
        const response = await fetch(`/api/files/${state.currentEditingFileId}/summary`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ summary: updatedSummary })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        ui.updateStatus("Summary saved successfully.");
        if(elements.summaryStatus) elements.summaryStatus.textContent = "Summary saved!";
        await loadUploadedFiles(); // Reload file lists to update summary status display
        ui.closeModal(elements.summaryModal);
    } catch (error) {
        console.error("Error saving summary:", error);
        ui.updateStatus("Error saving summary.", true);
        if(elements.summaryStatus) {
            elements.summaryStatus.textContent = `Error saving: ${error.message}`;
            elements.summaryStatus.classList.add('text-red-500');
        }
    } finally {
        ui.setLoadingState(false);
    }
}


// --- Calendar API ---

/** Fetches calendar events and updates state/UI. */
export async function loadCalendarEvents() {
    if (state.isLoading) return;
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        ui.updateStatus("Loading calendar events requires Calendar plugin enabled on Chat tab.", true);
        return;
    }

    ui.setLoadingState(true, "Loading Events");
    try {
        const response = await fetch('/api/calendar/events');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error ${response.status}`);
        }
        state.setCalendarContext(data.events || "[No event data received]");
        ui.updateCalendarStatus();
        elements.viewCalendarButton?.classList.remove('hidden');
        if(elements.viewCalendarButton) elements.viewCalendarButton.disabled = false;
        ui.updateStatus("Calendar events loaded.");
    } catch (error) {
        console.error('Error loading calendar events:', error);
        state.setCalendarContext(null); // Clear context on error
        ui.updateCalendarStatus();
        elements.viewCalendarButton?.classList.add('hidden');
        if(elements.viewCalendarButton) elements.viewCalendarButton.disabled = true;
        ui.addMessage('system', `[Error loading calendar events: ${error.message}]`, true);
        ui.updateStatus(`Error loading calendar events: ${error.message}`, true);
    } finally {
        ui.setLoadingState(false);
    }
}


// --- Chat API ---

/** Loads the list of saved chats into the sidebar. */
export async function loadSavedChats() {
    if (!elements.savedChatsList) return;

    // Set loading only if not already loading (e.g., during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) ui.setLoadingState(true, "Loading Chats");

    elements.savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;

    try {
        const response = await fetch('/api/chats');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const chats = await response.json();
        elements.savedChatsList.innerHTML = ''; // Clear loading message

        if (chats.length === 0) {
            elements.savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved chats yet.</p>`;
        } else {
            chats.forEach(chat => createChatItem(chat)); // Use helper
        }
        ui.updateActiveChatListItem(); // Highlight after loading
        ui.updateStatus("Saved chats loaded.");
    } catch (error) {
        console.error('Error loading saved chats:', error);
        elements.savedChatsList.innerHTML = '<p class="text-red-500 text-sm p-1">Error loading chats.</p>';
        ui.updateStatus("Error loading saved chats.", true);
        throw error; // Re-throw for initializeApp to catch
    } finally {
        if (!wasLoading) ui.setLoadingState(false);
    }
}

// Helper to create chat list item
function createChatItem(chat) {
    const { savedChatsList } = elements;
    if (!savedChatsList) return;

    const listItem = document.createElement('div');
    listItem.classList.add('list-item', 'chat-list-item');
    listItem.dataset.chatId = chat.id;

    const nameSpan = document.createElement('span');
    nameSpan.textContent = chat.name || `Chat ${chat.id}`;
    nameSpan.classList.add('filename');
    nameSpan.title = chat.name || `Chat ${chat.id}`;

    const timestampElement = document.createElement('div');
    let formattedDate = 'Date N/A';
    try {
        const date = new Date(chat.last_updated_at);
        formattedDate = date.toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    } catch (e) { /* ignore */ }
    timestampElement.textContent = `Last updated: ${formattedDate}`;
    timestampElement.classList.add('text-xs', 'text-rz-tab-background-text', 'mt-0.5');

    const deleteButton = document.createElement('button');
    deleteButton.classList.add('delete-btn');
    deleteButton.innerHTML = '<i class="fas fa-trash-alt fa-xs"></i>';
    deleteButton.title = "Delete Chat";
    deleteButton.onclick = (e) => {
        e.stopPropagation();
        handleDeleteChat(chat.id, listItem); // Call handler below
    };

    const nameContainer = document.createElement('div');
    nameContainer.classList.add('name-container');
    nameContainer.appendChild(nameSpan);
    nameContainer.appendChild(deleteButton);

    listItem.appendChild(nameContainer);
    listItem.appendChild(timestampElement);

    listItem.onclick = () => {
        if (chat.id != state.currentChatId) {
            loadChat(chat.id); // Load this chat
        }
    };
    savedChatsList.appendChild(listItem);
}


/** Starts a new chat session. */
export async function startNewChat() {
    ui.setLoadingState(true, "Creating Chat");
    try {
        const response = await fetch('/api/chat', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newChat = await response.json();

        // Load the new chat (this handles state updates and UI)
        await loadChat(newChat.id); // loadChat sets currentChatId, loads history, resets context

        // Reload the chat list to include the new chat
        await loadSavedChats(); // This will also call updateActiveChatListItem

        ui.updateStatus(`New chat created (ID: ${newChat.id}).`);
        // Optionally expand sidebar
        // ui.setSidebarCollapsed(elements.sidebar, elements.sidebarToggleButton, false, SIDEBAR_COLLAPSED_KEY, 'sidebar');

    } catch (error) {
        console.error('Error starting new chat:', error);
        ui.addMessage('system', `[Error creating new chat: ${error.message}]`, true);
        ui.updateStatus("Error creating new chat.", true);
        // Don't re-throw, allow UI to remain usable if possible
    } finally {
        ui.setLoadingState(false);
    }
}

/** Loads a specific chat's history and details. */
export async function loadChat(chatId) {
    console.log(`[DEBUG] loadChat(${chatId}) called.`);
    ui.setLoadingState(true, "Loading Chat");
    ui.clearChatbox();
    ui.addMessage('system', `Loading chat (ID: ${chatId})...`);

    try {
        const response = await fetch(`/api/chat/${chatId}`);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status} ${response.statusText} - ${errorText}`);
        }
        const data = await response.json();

        state.setCurrentChatId(data.details.id); // Set current chat ID *first*
        console.log(`[DEBUG] currentChatId set to ${state.currentChatId}.`);

        ui.clearChatbox(); // Clear loading message
        if(elements.currentChatNameInput) elements.currentChatNameInput.value = data.details.name || '';
        if(elements.currentChatIdDisplay) elements.currentChatIdDisplay.textContent = `ID: ${state.currentChatId}`;
        if(elements.modelSelector) elements.modelSelector.value = data.details.model_name || elements.modelSelector.options[0]?.value || ''; // Fallback needed

        // Populate history
        if (data.history.length === 0) {
            ui.addMessage('system', 'This chat is empty. Start typing!');
        } else {
            data.history.forEach(msg => ui.addMessage(msg.role, msg.content));
        }

        // Reset chat-specific context
        resetChatContext(); // Helper function below

        // Ensure plugin UI reflects current enabled state
        ui.updatePluginUI();

        // Load files list if plugin is enabled
        if (state.isFilePluginEnabled) {
            await loadUploadedFiles(); // Load files for the new chat context
        } else {
             if(elements.uploadedFilesList) elements.uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
             if(elements.manageFilesList) elements.manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
        }

        // Update highlighting *after* everything else
        ui.updateActiveChatListItem();

        ui.updateStatus(`Chat ${state.currentChatId} loaded.`);
        console.log(`[DEBUG] loadChat(${chatId}) finished successfully.`);

    } catch (error) {
        console.error(`Error loading chat ${chatId}:`, error);
        ui.clearChatbox();
        ui.addMessage('system', `[Error loading chat ${chatId}: ${error.message}]`, true);

        // Reset state on error
        state.setCurrentChatId(null);
        if(elements.currentChatNameInput) elements.currentChatNameInput.value = '';
        if(elements.currentChatIdDisplay) elements.currentChatIdDisplay.textContent = 'ID: -';
        if(elements.modelSelector) elements.modelSelector.value = elements.modelSelector.options[0]?.value || '';
        resetChatContext();
        ui.updatePluginUI();
        ui.updateActiveChatListItem(); // Remove highlight
        ui.updateStatus(`Error loading chat ${chatId}.`, true);

        // Clear file lists if plugin enabled
        if (state.isFilePluginEnabled) {
            if(elements.uploadedFilesList) elements.uploadedFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
            if(elements.manageFilesList) elements.manageFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
        }
        throw error; // Re-throw for initializeApp or switchTab to handle
    } finally {
        ui.setLoadingState(false);
    }
}

// Helper to reset context when switching chats or starting new
function resetChatContext() {
    state.clearSelectedFiles(); // Clear permanent file selections
    state.setSessionFile(null); // Clear session file state
    ui.renderSessionFileTag(); // Remove session tag (renderSelectedFiles called within)
    if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset file input

    state.setCalendarContext(null);
    state.setCalendarContextActive(false);
    if(elements.calendarToggle) elements.calendarToggle.checked = false;
    ui.updateCalendarStatus();
    elements.viewCalendarButton?.classList.add('hidden');

    if(elements.webSearchToggle) elements.webSearchToggle.checked = false; // Reset web search toggle
}


/** Sends the user message and context to the backend. */
export async function sendMessage() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        ui.updateStatus("Cannot send: No active chat, busy, or not on Chat tab.", true);
        return;
    }

    const message = elements.messageInput?.value.trim() || '';

    // Filter selectedFiles to only include those marked for attachment
    const filesToAttach = state.isFilePluginEnabled ? state.selectedFiles.filter(f => f.type !== 'pending') : [];
    const sessionFileToSend = state.isFilePluginEnabled ? state.sessionFile : null;
    const calendarContextToSend = (state.isCalendarPluginEnabled && state.isCalendarContextActive && state.calendarContext) ? state.calendarContext : null;
    const webSearchEnabledToSend = state.isWebSearchPluginEnabled && elements.webSearchToggle?.checked;

    if (!message && filesToAttach.length === 0 && !sessionFileToSend && !calendarContextToSend && !webSearchEnabledToSend) {
        ui.updateStatus("Cannot send: Empty message and no context/files attached.", true);
        return;
    }

    if (elements.messageInput) elements.messageInput.value = ''; // Clear input

    // Display user message + UI markers immediately
    let displayMessage = message || "(Context attached)";
    let uiMarkers = "";
    if (filesToAttach.length > 0) uiMarkers += filesToAttach.map(f => `\\[UI-MARKER:file:${f.filename}:${f.type}\\]`).join('');
    if (sessionFileToSend) uiMarkers += `\\[UI-MARKER:file:${sessionFileToSend.filename}:session\\]`;
    if (calendarContextToSend) uiMarkers += `\\[UI-MARKER:calendar\\]`;
    if (webSearchEnabledToSend) uiMarkers += `\\[UI-MARKER:websearch\\]`;
    displayMessage = uiMarkers + (uiMarkers ? "\n" : "") + displayMessage;
    ui.addMessage('user', displayMessage);

    ui.setLoadingState(true, "Sending");

    const payload = {
        chat_id: state.currentChatId,
        message: message,
        attached_files: filesToAttach,
        calendar_context: calendarContextToSend,
        session_files: sessionFileToSend ? [{ filename: sessionFileToSend.filename, content: sessionFileToSend.content, mimetype: sessionFileToSend.mimetype }] : [],
        enable_web_search: webSearchEnabledToSend,
        enable_streaming: state.isStreamingEnabled,
        enable_files_plugin: state.isFilePluginEnabled,
        enable_calendar_plugin: state.isCalendarPluginEnabled,
        enable_web_search_plugin: state.isWebSearchPluginEnabled
    };

    const sentSessionFile = state.sessionFile; // Store to clear later
    let assistantMessageElement = null;

    try {
        const response = await fetch(`/api/chat/${state.currentChatId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }

        if (state.isStreamingEnabled && response.headers.get('Content-Type')?.includes('text/plain')) {
            // Handle Streaming Response
            assistantMessageElement = ui.addMessage('assistant', ''); // Add empty element
            if (!assistantMessageElement) throw new Error("Failed to create assistant message element.");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                ui.addMessage('assistant', chunk, false, assistantMessageElement); // Append chunk
            }
            ui.applyMarkdownToMessage(assistantMessageElement); // Apply markdown at the end
            ui.updateStatus("Assistant replied (streaming finished).");
        } else {
            // Handle Non-Streaming Response
            const data = await response.json();
            ui.addMessage('assistant', data.reply);
            ui.updateStatus("Assistant replied.");
        }

        await loadSavedChats(); // Reload chats to update timestamp

        // Clear ALL selected files (state and UI) after successful send
        state.clearSelectedFiles();
        ui.renderSelectedFiles();
        elements.uploadedFilesList?.querySelectorAll('.file-checkbox').forEach(checkbox => {
            checkbox.checked = false;
            checkbox.closest('.file-list-item')?.classList.remove('active-selection');
        });
        elements.manageFilesList?.querySelectorAll('.file-list-item').forEach(item => {
            item.classList.remove('active-selection');
        });

    } catch (error) {
        console.error('Error sending message:', error);
        const errorMessage = `[Error: ${error.message}]`;
        if (assistantMessageElement) {
            ui.addMessage('assistant', errorMessage, true, assistantMessageElement);
            ui.applyMarkdownToMessage(assistantMessageElement);
        } else {
            ui.addMessage('assistant', errorMessage, true);
        }
        ui.updateStatus("Error sending message.", true);
    } finally {
        // Clear the session file state and tag if it was the one sent
        if (sentSessionFile && state.sessionFile === sentSessionFile) {
             state.setSessionFile(null);
             ui.renderSessionFileTag(); // This calls renderSelectedFiles internally
             if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = '';
        }
        ui.setLoadingState(false);
    }
}


/** Saves the current chat's name. */
export async function handleSaveChatName() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') return;

    const newName = elements.currentChatNameInput?.value.trim() || 'New Chat';
    ui.setLoadingState(true, "Saving Name");
    try {
        const response = await fetch(`/api/chat/${state.currentChatId}/name`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName }),
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        ui.updateStatus(`Chat ${state.currentChatId} name saved.`);
        await loadSavedChats(); // Reload list to show new name/timestamp
    } catch (error) {
        console.error('Error saving chat name:', error);
        ui.updateStatus(`Error saving name: ${error.message}`, true);
    } finally {
        ui.setLoadingState(false);
    }
}

/** Deletes a chat. */
export async function handleDeleteChat(chatId, listItemElement) {
    if (state.isLoading || state.currentTab !== 'chat') return;

    const chatName = listItemElement?.querySelector('span.filename')?.textContent || `Chat ${chatId}`;
    if (!confirm(`Are you sure you want to delete "${chatName}"? This cannot be undone.`)) {
        return;
    }
    ui.setLoadingState(true, "Deleting Chat");
    try {
        const response = await fetch(`/api/chat/${chatId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        ui.updateStatus(`Chat ${chatId} deleted.`);
        listItemElement?.remove(); // Remove from UI list

        if (!elements.savedChatsList?.querySelector('.list-item')) {
             if(elements.savedChatsList) elements.savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved chats yet.</p>`;
        }

        if (chatId == state.currentChatId) {
            await startNewChat(); // Start a new chat if the current one was deleted
        } else {
            await loadSavedChats(); // Otherwise, just reload the list
        }
    } catch (error) {
        console.error(`Error deleting chat ${chatId}:`, error);
        ui.updateStatus(`Error deleting chat: ${error.message}`, true);
        ui.addMessage('system', `[Error deleting chat ${chatId}: ${error.message}]`, true);
        // Reload list on failure to ensure UI consistency
        await loadSavedChats();
    } finally {
        ui.setLoadingState(false);
    }
}

/** Handles changing the model for the current chat. */
export async function handleModelChange() {
    if (!state.currentChatId || state.isLoading || state.currentTab !== 'chat') return;

    const newModel = elements.modelSelector?.value;
    if (!newModel) return;

    const originalModel = state.currentChatId ? (await fetch(`/api/chat/${state.currentChatId}`).then(res => res.json()).catch(() => ({ details: {} }))).details.model_name : elements.modelSelector.options[0]?.value;


    ui.setLoadingState(true, "Updating Model");
    try {
        const response = await fetch(`/api/chat/${state.currentChatId}/model`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_name: newModel })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        ui.updateStatus(`Model updated to ${newModel} for this chat.`);
    } catch (error) {
        console.error("Error updating model:", error);
        ui.updateStatus(`Error updating model: ${error.message}`, true);
        // Revert selector on error
        if (elements.modelSelector && originalModel) elements.modelSelector.value = originalModel;
    } finally {
        ui.setLoadingState(false);
    }
}


// --- Notes API ---

/** Loads the list of saved notes into the sidebar. */
export async function loadSavedNotes() {
     if (!elements.savedNotesList) return;

     const wasLoading = state.isLoading;
     if (!wasLoading) ui.setLoadingState(true, "Loading Notes");
     elements.savedNotesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;

     try {
         const response = await fetch('/api/notes');
         if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
         const notes = await response.json();
         elements.savedNotesList.innerHTML = ''; // Clear loading

         if (notes.length === 0) {
             elements.savedNotesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved notes yet.</p>`;
         } else {
             notes.forEach(note => createNoteItem(note)); // Use helper
         }
         ui.updateActiveNoteListItem(); // Highlight
         ui.updateStatus("Saved notes loaded.");
     } catch (error) {
         console.error('Error loading saved notes:', error);
         elements.savedNotesList.innerHTML = '<p class="text-red-500 text-sm p-1">Error loading notes.</p>';
         ui.updateStatus("Error loading saved notes.", true);
         throw error; // Re-throw for initializeApp
     } finally {
         if (!wasLoading) ui.setLoadingState(false);
     }
}

// Helper to create note list item
function createNoteItem(note) {
    const { savedNotesList } = elements;
    if (!savedNotesList) return;

    const listItem = document.createElement('div');
    listItem.classList.add('list-item', 'note-list-item');
    listItem.dataset.noteId = note.id;

    const nameSpan = document.createElement('span');
    nameSpan.textContent = note.name || `Note ${note.id}`;
    nameSpan.classList.add('filename');
    nameSpan.title = note.name || `Note ${note.id}`;

    const timestampElement = document.createElement('div');
    let formattedDate = 'Date N/A';
     try {
        const date = new Date(note.last_saved_at);
        formattedDate = date.toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    } catch (e) { /* ignore */ }
    timestampElement.textContent = `Last saved: ${formattedDate}`;
    timestampElement.classList.add('text-xs', 'text-rz-tab-background-text', 'mt-0.5');

    const deleteButton = document.createElement('button');
    deleteButton.classList.add('delete-btn');
    deleteButton.innerHTML = '<i class="fas fa-trash-alt fa-xs"></i>';
    deleteButton.title = "Delete Note";
    deleteButton.onclick = (e) => {
        e.stopPropagation();
        handleDeleteNote(note.id, listItem); // Call handler below
    };

    const nameContainer = document.createElement('div');
    nameContainer.classList.add('name-container');
    nameContainer.appendChild(nameSpan);
    nameContainer.appendChild(deleteButton);

    listItem.appendChild(nameContainer);
    listItem.appendChild(timestampElement);

    listItem.onclick = () => {
        if (note.id != state.currentNoteId) {
            loadNote(note.id); // Load this note
        }
    };
    savedNotesList.appendChild(listItem);
}


/** Creates a new note entry and loads it. */
export async function startNewNote() {
    console.log(`[DEBUG] startNewNote called.`);
    if (state.isLoading) return;
    ui.setLoadingState(true, "Creating Note");
    if(elements.notesTextarea) {
        elements.notesTextarea.value = "";
        elements.notesTextarea.placeholder = "Creating new note...";
    }
    if(elements.notesPreview) elements.notesPreview.innerHTML = "";
    if(elements.currentNoteNameInput) elements.currentNoteNameInput.value = "New Note";
    if(elements.currentNoteIdDisplay) elements.currentNoteIdDisplay.textContent = "ID: -";
    ui.switchNoteMode('edit'); // Always start in edit mode

    try {
        const response = await fetch('/api/notes', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newNote = await response.json();
        console.log(`[DEBUG] startNewNote: Received new note ID ${newNote.id}. Loading it...`);
        await loadNote(newNote.id); // Load the new note (sets state, loads content)
        await loadSavedNotes(); // Reload the list
        ui.updateStatus(`New note created (ID: ${newNote.id}).`);
        console.log(`[DEBUG] startNewNote: Successfully created and loaded note ${newNote.id}.`);
    } catch (error) {
        console.error('Error starting new note:', error);
        if(elements.notesTextarea) {
            elements.notesTextarea.value = `[Error creating new note: ${error.message}]`;
            elements.notesTextarea.placeholder = "Could not create note.";
        }
         if(elements.notesPreview) elements.notesPreview.innerHTML = `<p class="text-red-500">Error creating new note: ${escapeHtml(error.message)}</p>`;
        ui.updateStatus("Error creating new note.", true);
        state.setCurrentNoteId(null); // Reset state
        localStorage.removeItem('currentNoteId'); // Clear persisted ID
    } finally {
        ui.setLoadingState(false);
    }
}

/** Loads the content of a specific note. */
export async function loadNote(noteId) {
    console.log(`[DEBUG] loadNote(${noteId}) called.`);
    if (state.isLoading) return;
    ui.setLoadingState(true, "Loading Note");
    if(elements.notesTextarea) {
        elements.notesTextarea.value = "";
        elements.notesTextarea.placeholder = "Loading note...";
    }
    if(elements.notesPreview) elements.notesPreview.innerHTML = "";
    if(elements.currentNoteNameInput) elements.currentNoteNameInput.value = "";
    if(elements.currentNoteIdDisplay) elements.currentNoteIdDisplay.textContent = `ID: ${noteId}`;
    // Don't force mode switch here, apply persisted mode after load

    try {
        const response = await fetch(`/api/note/${noteId}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        state.setCurrentNoteId(data.id); // Set current note ID
        localStorage.setItem('currentNoteId', data.id); // Persist
        console.log(`[DEBUG] loadNote(${noteId}): Set currentNoteId to ${state.currentNoteId}`);

        if(elements.currentNoteNameInput) elements.currentNoteNameInput.value = data.name || '';
        if(elements.notesTextarea) {
            elements.notesTextarea.value = data.content || '';
            elements.notesTextarea.placeholder = "Start typing your markdown notes here...";
        }

        // Apply the current mode *after* loading content
        ui.switchNoteMode(state.currentNoteMode); // Applies persisted/default mode

        ui.updateStatus(`Note ${state.currentNoteId} loaded.`);
        ui.updateActiveNoteListItem(); // Highlight

    } catch (error) {
        console.error(`Error loading note ${noteId}:`, error);
        if(elements.notesTextarea) {
            elements.notesTextarea.value = `[Error loading note ${noteId}: ${error.message}]`;
            elements.notesTextarea.placeholder = "Could not load note.";
        }
        if(elements.notesPreview) elements.notesPreview.innerHTML = `<p class="text-red-500">Error loading note: ${escapeHtml(error.message)}</p>`;
        ui.updateStatus(`Error loading note ${noteId}.`, true);
        state.setCurrentNoteId(null); // Reset state
        localStorage.removeItem('currentNoteId'); // Clear persisted ID
        if(elements.currentNoteNameInput) elements.currentNoteNameInput.value = '';
        if(elements.currentNoteIdDisplay) elements.currentNoteIdDisplay.textContent = 'ID: -';
        ui.updateActiveNoteListItem(); // Remove highlight
        ui.switchNoteMode('edit'); // Default to edit mode on error
        if(elements.notesTextarea) elements.notesTextarea.disabled = true;
        throw error; // Re-throw for switchTab to handle
    } finally {
        ui.setLoadingState(false);
    }
}

/** Saves the current note content and name. */
export async function saveNote() {
    console.log(`[DEBUG] saveNote called.`);
    if (state.isLoading || !state.currentNoteId || state.currentTab !== 'notes') {
        ui.updateStatus("Cannot save: No active note, busy, or not on Notes tab.", true);
        return;
    }
    ui.setLoadingState(true, "Saving Note");

    const noteName = elements.currentNoteNameInput?.value.trim() || 'New Note';
    const noteContent = elements.notesTextarea?.value || '';

    try {
        const response = await fetch(`/api/note/${state.currentNoteId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: noteName, content: noteContent })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        ui.updateStatus(`Note ${state.currentNoteId} saved successfully.`);
        await loadSavedNotes(); // Reload list to update timestamp/name
        ui.updateActiveNoteListItem(); // Ensure highlighting remains correct
    } catch (error) {
        console.error(`Error saving note ${state.currentNoteId}:`, error);
        ui.updateStatus(`Error saving note: ${error.message}`, true);
    } finally {
        ui.setLoadingState(false);
    }
}

/** Deletes a specific note. */
export async function handleDeleteNote(noteId, listItemElement) {
    if (state.isLoading || state.currentTab !== 'notes') return;
    const noteName = listItemElement?.querySelector('span.filename')?.textContent || `Note ${noteId}`;
    if (!confirm(`Are you sure you want to delete "${noteName}"? This cannot be undone.`)) {
        return;
    }
    ui.setLoadingState(true, "Deleting Note");
    try {
        const response = await fetch(`/api/note/${noteId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        ui.updateStatus(`Note ${noteId} deleted.`);
        listItemElement?.remove(); // Remove from UI list

        // If the deleted note was the currently active one, load another or start new
        if (noteId == state.currentNoteId) {
            state.setCurrentNoteId(null); // Clear current note state
            localStorage.removeItem('currentNoteId');
            await loadSavedNotes(); // Reload the list first
            const firstNoteElement = elements.savedNotesList?.querySelector('.list-item');
            if (firstNoteElement) {
                await loadNote(parseInt(firstNoteElement.dataset.noteId));
            } else {
                await startNewNote(); // Create and load a new note
            }
        } else {
            await loadSavedNotes(); // Otherwise, just reload the list
        }
    } catch (error) {
        console.error(`Error deleting note ${noteId}:`, error);
        ui.updateStatus(`Error deleting note: ${error.message}`, true);
        if (noteId == state.currentNoteId) {
             if(elements.notesTextarea) elements.notesTextarea.value = `[Error deleting note ${noteId}: ${error.message}]`;
             if(elements.notesPreview) elements.notesPreview.innerHTML = `<p class="text-red-500">Error deleting note: ${escapeHtml(error.message)}</p>`;
             ui.switchNoteMode('edit');
             if(elements.notesTextarea) elements.notesTextarea.disabled = true;
        }
        // Reload list on failure
        await loadSavedNotes();
    } finally {
        ui.setLoadingState(false);
    }
}


// --- Initial Data Loading ---

/** Loads the initial data required for the Chat tab. */
export async function loadInitialChatData() {
    // loadSavedChats is called by initializeApp before switchTab
    // await loadSavedChats(); // Load chat list first

    let chatToLoadId = state.currentChatId; // Use persisted ID if available

    if (chatToLoadId !== null) {
        console.log(`[DEBUG] loadInitialChatData: currentChatId is ${chatToLoadId}, attempting to load it.`);
        try {
            await loadChat(chatToLoadId); // Attempt to load the persisted chat
        } catch (error) {
            console.warn(`[DEBUG] loadInitialChatData: loadChat(${chatToLoadId}) failed: ${error}. Falling back.`);
            state.setCurrentChatId(null); // Clear the failed ID
            localStorage.removeItem('currentChatId');
            chatToLoadId = null; // Ensure fallback logic triggers
        }
    }

    // If no persisted chat or loading failed, load most recent or start new
    if (chatToLoadId === null) {
        console.log("[DEBUG] loadInitialChatData: No valid currentChatId, loading most recent or creating new.");
        const firstChatElement = elements.savedChatsList?.querySelector('.list-item');
        if (firstChatElement) {
            const mostRecentChatId = parseInt(firstChatElement.dataset.chatId);
            console.log(`[DEBUG] Loading most recent chat: ${mostRecentChatId}`);
            await loadChat(mostRecentChatId);
        } else {
            console.log("[DEBUG] No saved chats found, starting new chat.");
            await startNewChat();
        }
    }
    console.log(`[DEBUG] loadInitialChatData finished. Final currentChatId: ${state.currentChatId}`);
}

/** Loads the initial data required for the Notes tab. */
export async function loadInitialNotesData() {
    // loadSavedNotes is called by initializeApp before switchTab
    // await loadSavedNotes(); // Load notes list first

    let noteToLoadId = state.currentNoteId; // Use persisted ID

    if (noteToLoadId !== null) {
        console.log(`[DEBUG] loadInitialNotesData: currentNoteId is ${noteToLoadId}, attempting to load it.`);
        try {
            await loadNote(noteToLoadId); // Attempt to load persisted note
        } catch (error) {
            console.warn(`[DEBUG] loadInitialNotesData: loadNote(${noteToLoadId}) failed: ${error}. Starting new note.`);
            await startNewNote(); // If load fails, start new
            noteToLoadId = state.currentNoteId; // Update ID to the newly created one
        }
    } else {
        console.log("[DEBUG] loadInitialNotesData: No currentNoteId, loading most recent or creating new.");
        const firstNoteElement = elements.savedNotesList?.querySelector('.list-item');
        if (firstNoteElement) {
            const mostRecentNoteId = parseInt(firstNoteElement.dataset.noteId);
            console.log(`[DEBUG] Loading most recent note: ${mostRecentNoteId}`);
            await loadNote(mostRecentNoteId);
        } else {
            console.log("[DEBUG] No saved notes found, starting new note.");
            await startNewNote();
        }
    }

    // Ensure the correct note mode is applied after loading
    if (state.currentNoteId === null) {
         ui.switchNoteMode('edit'); // Default to edit if no note could be loaded/created
    } else {
         ui.switchNoteMode(state.currentNoteMode); // Apply persisted/default mode
    }

    console.log(`[DEBUG] loadInitialNotesData finished. Final currentNoteId: ${state.currentNoteId}`);
}
