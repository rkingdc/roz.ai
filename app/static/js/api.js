// js/api.js
import { elements } from './dom.js';
import * as state from './state.js';
// REMOVED: import * as ui from './ui.js'; // Import all functions from ui.js
import { escapeHtml, formatFileSize } from './utils.js'; // Import utility functions
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js';

// --- File API ---

/** Deletes a file from the backend and updates the UI lists. */
export async function deleteFile(fileId) {
    const ui = await import('./ui.js'); // Dynamic import
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

        // Remove from state lists
        state.removeSidebarSelectedFileById(fileId); // Remove from sidebar selection state
        // Corrected: Use the function that removes by ID from attachedFiles
        state.removeAttachedFileById(fileId); // Remove from attached state
        if (state.sessionFile && state.sessionFile.id === fileId) { // Check if it's the session file
             state.setSessionFile(null);
        }

        await loadUploadedFiles(); // Reload file lists (this calls renderUploadedFiles)
        // renderAttachedAndSessionFiles is called by renderUploadedFiles
        // updateSelectedFileListItemStyling is called by renderUploadedFiles
        // updateAttachButtonState is called by renderUploadedFiles

    } catch (error) {
        console.error('Error deleting file:', error);
        ui.updateStatus(`Error deleting file: ${error.message}`, true);
    } finally {
        ui.setLoadingState(false);
    }
}

/** Loads uploaded files and populates the lists in both the sidebar and the modal. */
export async function loadUploadedFiles() {
    const ui = await import('./ui.js'); // Dynamic import
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

        // Call UI function to render the lists
        ui.renderUploadedFiles(files); // This function now handles sidebar selection highlighting and attached/session file display

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


/** Handles file upload triggered from the modal. */
export async function handleFileUpload(event) {
    const ui = await import('./ui.js'); // Dynamic import
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
            alert(`Skipping "${file.name}": File is too large (${formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
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
        await loadUploadedFiles(); // Reload lists (this calls renderUploadedFiles)
        ui.setLoadingState(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = ''; // Reset input
    }
}

/** Adds a file by fetching content from a URL. */
export async function addFileFromUrl(url) {
     const ui = await import('./ui.js'); // Dynamic import
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
         await loadUploadedFiles(); // Reload lists (this calls renderUploadedFiles)
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
    const ui = await import('./ui.js'); // Dynamic import
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
    const ui = await import('./ui.js'); // Dynamic import
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
        await loadUploadedFiles(); // Reload file lists to update summary status display (calls renderUploadedFiles)
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

/**
 * Attaches selected files from the sidebar to the current chat as 'full' files.
 */
export async function attachSelectedFilesFull() {
    const ui = await import('./ui.js'); // Dynamic import
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat' || state.isLoading) {
        ui.updateStatus("Cannot attach files: Files plugin disabled, not on Chat tab, or busy.", true);
        return;
    }
    if (state.sidebarSelectedFiles.length === 0) {
        ui.updateStatus("No files selected in the sidebar to attach.", true);
        return;
    }

    // Add selected files to the attachedFiles state with type 'full'
    state.sidebarSelectedFiles.forEach(file => {
        // Ensure we don't add duplicates (same file ID, same type)
        if (!state.attachedFiles.some(f => f.id === file.id && f.type === 'full')) {
             state.addAttachedFile({ id: file.id, filename: file.filename, type: 'full' });
        }
    });

    // Clear the temporary sidebar selection
    state.clearSidebarSelectedFiles();

    // Update the UI
    ui.updateSelectedFileListItemStyling(); // Remove highlighting from sidebar
    ui.renderAttachedAndSessionFiles(); // Render the newly attached files below input
    ui.updateAttachButtonState(); // Disable attach buttons
    ui.updateStatus(`Attached ${state.attachedFiles.length} file(s) (full content).`); // Status message might need refinement
}

/**
 * Attaches selected files from the sidebar to the current chat as 'summary' files.
 */
export async function attachSelectedFilesSummary() {
     const ui = await import('./ui.js'); // Dynamic import
     if (!state.isFilePluginEnabled || state.currentTab !== 'chat' || state.isLoading) {
        ui.updateStatus("Cannot attach files: Files plugin disabled, not on Chat tab, or busy.", true);
        return;
    }
    if (state.sidebarSelectedFiles.length === 0) {
        ui.updateStatus("No files selected in the sidebar to attach.", true);
        return;
    }
    // Check if any selected file actually has a summary
    const filesWithSummary = state.sidebarSelectedFiles.filter(file => file.has_summary);
    if (filesWithSummary.length === 0) {
         ui.updateStatus("None of the selected files have a summary to attach.", true);
         return;
    }

    // Add selected files with summaries to the attachedFiles state with type 'summary'
    filesWithSummary.forEach(file => {
        // Ensure we don't add duplicates (same file ID, same type)
        if (!state.attachedFiles.some(f => f.id === file.id && f.type === 'summary')) {
            state.addAttachedFile({ id: file.id, filename: file.filename, type: 'summary' });
        }
    });

    // Clear the temporary sidebar selection
    state.clearSidebarSelectedFiles();

    // Update the UI
    ui.updateSelectedFileListItemStyling(); // Remove highlighting from sidebar
    ui.renderAttachedAndSessionFiles(); // Render the newly attached files below input
    ui.updateAttachButtonState(); // Disable attach buttons
    ui.updateStatus(`Attached ${filesWithSummary.length} file(s) (summary).`); // Status message might need refinement
}


// --- Calendar API ---

/** Fetches calendar events and updates state/UI. */
export async function loadCalendarEvents() {
    const ui = await import('./ui.js'); // Dynamic import
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
    const ui = await import('./ui.js'); // Dynamic import
    if (!elements.savedChatsList) return;

    // Set loading only if not already loading (e.g., during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) ui.setLoadingState(true, "Loading Chats");

    elements.savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;

    try {
        const response = await fetch('/api/chats');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const chats = await response.json();
        state.setSavedChats(chats); // Store chats in state
        ui.renderSavedChats(state.savedChats); // Use UI function to render

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


/** Starts a new chat session. */
export async function startNewChat() {
    const ui = await import('./ui.js'); // Dynamic import
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
    const ui = await import('./ui.js'); // Dynamic import
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
        localStorage.setItem('currentChatId', data.details.id); // Persist
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

        // Reset chat-specific context states (files, calendar, web search toggle)
        await resetChatContext(); // Helper function below - Make it awaitable

        // Assuming the backend returns attached files with chat details
        if (data.details.attached_files) {
             state.setAttachedFiles(data.details.attached_files);
        } else {
             state.clearAttachedFiles();
        }

        // Ensure plugin UI reflects current enabled state
        ui.updatePluginUI();

        // Load files list if plugin is enabled
        if (state.isFilePluginEnabled) {
            await loadUploadedFiles(); // Load files for the new chat context (calls renderUploadedFiles)
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
        localStorage.removeItem('currentChatId');
        if(elements.currentChatNameInput) elements.currentChatNameInput.value = '';
        if(elements.currentChatIdDisplay) elements.currentChatIdDisplay.textContent = 'ID: -';
        if(elements.modelSelector) elements.modelSelector.value = elements.modelSelector.options[0]?.value || '';
        await resetChatContext(); // Clear files, calendar, etc. - Make it awaitable
        ui.updatePluginUI(); // Update UI based on cleared state
        ui.updateActiveChatListItem(); // Remove highlight

        // Clear file lists if plugin enabled
        if (state.isFilePluginEnabled) {
            if(elements.uploadedFilesList) elements.uploadedFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
            if(elements.manageFilesList) elements.manageFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
        }
        ui.updateStatus(`Error loading chat ${chatId}.`, true);
        throw error; // Re-throw for initializeApp or switchTab to handle
    } finally {
        ui.setLoadingState(false);
    }
}

// Helper to reset context when switching chats or starting new
// Made async to allow dynamic import of ui
async function resetChatContext() {
    const ui = await import('./ui.js'); // Dynamic import
    state.clearSidebarSelectedFiles(); // Clear temporary sidebar selections
    state.clearAttachedFiles(); // Clear permanent file selections
    state.setSessionFile(null); // Clear session file state

    ui.renderAttachedAndSessionFiles(); // Update attached files display

    ui.updateSelectedFileListItemStyling(); // Update sidebar highlighting
    ui.updateAttachButtonState(); // Update attach button state

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
    const ui = await import('./ui.js'); // Dynamic import
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        ui.updateStatus("Cannot send: No active chat, busy, or not on Chat tab.", true);
        return;
    }

    const message = elements.messageInput?.value.trim() || '';

    // Files to send are the permanently attached files PLUS the session file
    const filesToAttach = state.isFilePluginEnabled ? state.attachedFiles : []; // Corrected: Use state.attachedFiles
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
    // Add markers for attached files
    if (filesToAttach.length > 0) {
        uiMarkers += filesToAttach.map(f => `\\[UI-MARKER:file:${f.filename}:${f.type}\\]`).join('');
    }
    // Add marker for session file
    if (sessionFileToSend) {
        uiMarkers += `\\[UI-MARKER:file:${sessionFileToSend.filename}:session\\]`;
    }
    if (calendarContextToSend) uiMarkers += `\\[UI-MARKER:calendar\\]`;
    if (webSearchEnabledToSend) uiMarkers += `\\[UI-MARKER:websearch\\]`;
    displayMessage = uiMarkers + (uiMarkers ? "\n" : "") + displayMessage;
    ui.addMessage('user', displayMessage);

    ui.setLoadingState(true, "Sending");

    const payload = {
        chat_id: state.currentChatId,
        message: message,
        // Send attached files (full/summary)
        attached_files: filesToAttach.map(f => ({ id: f.id, type: f.type })), // Send only id and type for attached files
        // Send session file (content included)
        session_files: sessionFileToSend ? [{ filename: sessionFileToSend.filename, content: sessionFileToSend.content, mimetype: sessionFileToSend.mimetype }] : [],
        calendar_context: calendarContextToSend,
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

        // Clear temporary sidebar selection after successful send
        state.clearSidebarSelectedFiles();
        ui.updateSelectedFileListItemStyling(); // Remove highlighting from sidebar
        ui.updateAttachButtonState(); // Update button state

        // Do NOT clear attachedFiles here. They persist per chat.
        // Only clear the session file.

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
             ui.renderAttachedAndSessionFiles(); // Update display to remove session file tag
             if(elements.fileUploadSessionInput) elements.fileUploadSessionInput.value = ''; // Reset input
        }
        ui.setLoadingState(false);
    }
}


/** Saves the current chat's name. */
export async function handleSaveChatName() {
    const ui = await import('./ui.js'); // Dynamic import
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
    const ui = await import('./ui.js'); // Dynamic import
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
        // Remove from state first
        state.setSavedChats(state.savedChats.filter(chat => chat.id !== chatId));
        ui.renderSavedChats(state.savedChats); // Re-render list

        if (chatId == state.currentChatId) {
            await startNewChat(); // Start a new chat if the current one was deleted
        } else {
            // If a different chat was deleted, just ensure the list is updated (done by renderSavedChats)
            ui.updateActiveChatListItem(); // Re-highlight the current one
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
    const ui = await import('./ui.js'); // Dynamic import
    if (!state.currentChatId || state.isLoading || state.currentTab !== 'chat') return;

    const newModel = elements.modelSelector?.value;
    if (!newModel) return;

    // Fetch current model before attempting update in case of error
    let originalModel = elements.modelSelector?.value; // Assume current UI value is correct initially
    if (state.currentChatId) {
        try {
            const chatDetails = await fetch(`/api/chat/${state.currentChatId}`).then(res => res.json()).catch(() => ({ details: {} }));
            originalModel = chatDetails.details.model_name || originalModel;
        } catch (e) {
            console.warn("Could not fetch current model name before update attempt:", e);
        }
    }


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
     const ui = await import('./ui.js'); // Dynamic import
     if (!elements.savedNotesList) return;

     const wasLoading = state.isLoading;
     if (!wasLoading) ui.setLoadingState(true, "Loading Notes");
     elements.savedNotesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;

     try {
         const response = await fetch('/api/notes');
         if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
         const notes = await response.json();
         state.setSavedNotes(notes); // Store notes in state
         ui.renderSavedNotes(state.savedNotes); // Use UI function to render

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


/** Creates a new note entry and loads it. */
export async function startNewNote() {
    const ui = await import('./ui.js'); // Dynamic import
    console.log(`[DEBUG] startNewNote called.`);
    if (state.isLoading) return;
    ui.setLoadingState(true, "Creating Note");
    if(elements.notesTextarea) {
        elements.notesTextarea.value = "";
        elements.notesTextarea.placeholder = "Creating new note...";
        elements.notesTextarea.disabled = false; // Ensure enabled for new note
    }
    if(elements.notesPreview) elements.notesPreview.innerHTML = "";
    if(elements.currentNoteNameInput) elements.currentNoteNameInput.value = "New Note";
    if(elements.currentNoteIdDisplay) elements.currentNoteIdDisplay.textContent = "ID: -";
    ui.setNoteMode('edit'); // Always start in edit mode

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
            elements.notesTextarea.disabled = true; // Disable on error
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
    const ui = await import('./ui.js'); // Dynamic import
    console.log(`[DEBUG] loadNote(${noteId}) called.`);
    if (state.isLoading) return;
    ui.setLoadingState(true, "Loading Note");
    if(elements.notesTextarea) {
        elements.notesTextarea.value = "";
        elements.notesTextarea.placeholder = "Loading note...";
        elements.notesTextarea.disabled = false; // Enable while loading
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
        ui.setNoteMode(state.currentNoteMode); // Applies persisted/default mode

        ui.updateStatus(`Note ${state.currentNoteId} loaded.`);
        ui.updateActiveNoteListItem(); // Highlight

    } catch (error) {
        console.error(`Error loading note ${noteId}:`, error);
        if(elements.notesTextarea) {
            elements.notesTextarea.value = `[Error loading note ${noteId}: ${error.message}]`;
            elements.notesTextarea.placeholder = "Could not load note.";
            elements.notesTextarea.disabled = true; // Disable on error
        }
        if(elements.notesPreview) elements.notesPreview.innerHTML = `<p class="text-red-500">Error loading note: ${escapeHtml(error.message)}</p>`;
        ui.updateStatus(`Error loading note ${noteId}.`, true);
        state.setCurrentNoteId(null); // Reset state
        localStorage.removeItem('currentNoteId'); // Clear persisted ID
        if(elements.currentNoteNameInput) elements.currentNoteNameInput.value = '';
        if(elements.currentNoteIdDisplay) elements.currentNoteIdDisplay.textContent = 'ID: -';
        ui.updateActiveNoteListItem(); // Remove highlight
        ui.setNoteMode('edit'); // Default to edit mode on error
        // Textarea is already disabled above
        throw error; // Re-throw for switchTab to handle
    } finally {
        ui.setLoadingState(false);
    }
}

/** Saves the current note content and name. */
export async function saveNote() {
    const ui = await import('./ui.js'); // Dynamic import
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
    const ui = await import('./ui.js'); // Dynamic import
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
        // Remove from state first
        state.setSavedNotes(state.savedNotes.filter(note => note.id !== noteId));
        ui.renderSavedNotes(state.savedNotes); // Re-render list

        // If the deleted note was the currently active one, load another or start new
        if (noteId == state.currentNoteId) {
            state.setCurrentNoteId(null); // Clear current note state
            localStorage.removeItem('currentNoteId');
            // loadSavedNotes already re-rendered the list
            const firstNoteElement = elements.savedNotesList?.querySelector('.list-item');
            if (firstNoteElement) {
                await loadNote(parseInt(firstNoteElement.dataset.noteId));
            } else {
                await startNewNote(); // Create and load a new note
            }
        } else {
            // If a different note was deleted, just ensure the list is updated (done by renderSavedNotes)
            ui.updateActiveNoteListItem(); // Re-highlight the current one
        }
    } catch (error) {
        console.error(`Error deleting note ${noteId}:`, error);
        ui.updateStatus(`Error deleting note: ${error.message}`, true);
        if (noteId == state.currentNoteId) {
             if(elements.notesTextarea) {
                 elements.notesTextarea.value = `[Error deleting note ${noteId}: ${error.message}]`;
                 elements.notesTextarea.disabled = true;
             }
             if(elements.notesPreview) elements.notesPreview.innerHTML = `<p class="text-red-500">Error deleting note: ${escapeHtml(error.message)}</p>`;
             ui.setNoteMode('edit'); // Default to edit mode on error
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
        const firstChat = state.savedChats.length > 0 ? state.savedChats[0] : null; // Get from state
        if (firstChat) {
            const mostRecentChatId = firstChat.id;
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
        const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null; // Get from state
        if (firstNote) {
            const mostRecentNoteId = firstNote.id;
            console.log(`[DEBUG] Loading most recent note: ${mostRecentNoteId}`);
            await loadNote(mostRecentNoteId);
        } else {
            console.log("[DEBUG] No saved notes found, starting new note.");
            await startNewNote();
        }
    }

    // Ensure the correct note mode is applied after loading
    if (state.currentNoteId === null) {
         ui.setNoteMode('edit'); // Default to edit if no note could be loaded/created
    } else {
         ui.setNoteMode(state.currentNoteMode); // Apply persisted/default mode
    }

    console.log(`[DEBUG] loadInitialNotesData finished. Final currentNoteId: ${state.currentNoteId}`);
}
