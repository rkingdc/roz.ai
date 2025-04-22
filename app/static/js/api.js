// js/api.js
// This module handles all interactions with the backend API.
// It updates the application state based on API responses.
// It does NOT directly manipulate the DOM or call UI rendering functions.

import { elements } from './dom.js'; // Still need elements to read input values sometimes
import * as state from './state.js'; // API updates the state
import { escapeHtml, formatFileSize } from './utils.js'; // Still need utilities
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js'; // Still need config

// --- Helper to update loading and status state ---
// API functions will use these state setters instead of calling ui.updateStatus/setLoadingState directly
function setLoading(isLoading, message = "Busy...") {
    state.setIsLoading(isLoading);
    if (isLoading) {
        state.setStatusMessage(message);
    } else {
        // Status message will be set by the specific API function on success/failure
        // or reset to "Idle" by setIsLoading if no error occurred.
    }
}

function setStatus(message, isError = false) {
    state.setStatusMessage(message, isError);
}


// --- File API ---

/** Deletes a file from the backend and updates the state. */
export async function deleteFile(fileId) {
    if (state.isLoading) return;
    if (!confirm("Are you sure you want to delete this file? This action cannot be undone.")) {
        return;
    }

    setLoading(true, "Deleting File");
    try {
        const response = await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`File ${fileId} deleted.`);

        // Update state lists directly
        state.removeSidebarSelectedFileById(fileId); // Remove from sidebar selection state
        state.removeAttachedFileById(fileId); // Remove from attached state
        if (state.sessionFile && state.sessionFile.id === fileId) { // Check if it's the session file
             state.setSessionFile(null);
        }

        // Reload the full list to ensure UI consistency (this will update state.uploadedFiles)
        await loadUploadedFiles();

    } catch (error) {
        console.error('Error deleting file:', error);
        setStatus(`Error deleting file: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

/** Loads uploaded files from the backend and updates the state. */
export async function loadUploadedFiles() {
    // Only load if Files plugin is enabled
    if (!state.isFilePluginEnabled) {
        state.setUploadedFiles([]); // Clear list if plugin disabled
        // Status will be updated by updatePluginUI based on state.isFilePluginEnabled
        return;
    }

    // Set loading state only if not already loading (might be called during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) setLoading(true, "Loading Files");

    // Clear current list in state immediately to show loading state in UI
    state.setUploadedFiles([]);

    try {
        const response = await fetch('/api/files');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const files = await response.json();

        // Update state with fetched files
        state.setUploadedFiles(files);

        setStatus("Uploaded files loaded.");
    } catch (error) {
        console.error('Error loading uploaded files:', error);
        setStatus("Error loading files.", true);
        // state.uploadedFiles is already [] from above
        throw error; // Re-throw for caller (e.g., initializeApp) to handle if needed
    } finally {
        // Only turn off loading if this function set it
        if (!wasLoading) setLoading(false);
    }
}


/** Handles file upload triggered from the modal. */
export async function handleFileUpload(event) {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
        setStatus("File uploads only allowed when Files plugin is enabled and on Chat tab.", true);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }

    const files = event.target.files;
    if (!files || files.length === 0) {
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }

    setLoading(true, "Uploading");
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
        setLoading(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        setStatus("No valid files selected for upload.", true);
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
        setStatus(statusMsg, errors.length > 0);

        // Reload the file list state after upload
        await loadUploadedFiles();

    } catch (error) {
        console.error('Error uploading files:', error);
        setStatus(`Error uploading files: ${error.message}`, true);
    } finally {
        setLoading(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = ''; // Reset input
        // Closing modal should be handled by event listener or UI logic reacting to state
    }
}

/** Adds a file by fetching content from a URL. */
export async function addFileFromUrl(url) {
     if (state.isLoading) return;
     if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         // Status update for URL modal handled by event listener
         return;
     }
     if (!url || !url.startsWith('http')) {
         // Status update for URL modal handled by event listener
         return;
     }

     setLoading(true, "Fetching URL");
     // Status update for URL modal handled by event listener

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
         setStatus(`Successfully added file from URL: ${data.filename}`);
         // Status update for URL modal handled by event listener
         if(elements.urlInput) elements.urlInput.value = ''; // Clear input

         // Reload the file list state
         await loadUploadedFiles();

         // Closing modal should be handled by event listener or UI logic reacting to state
     } catch (error) {
         console.error('Error adding file from URL:', error);
         setStatus(`Error adding file from URL: ${error.message}`, true);
         // Status update for URL modal handled by event listener
     } finally {
         setLoading(false);
     }
}

/** Fetches/Generates summary and updates state. */
export async function fetchSummary(fileId) {
    if (state.isLoading) return;
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         setStatus("Fetching summaries requires Files plugin enabled on Chat tab.", true);
         return;
    }

    setLoading(true, "Fetching Summary");
    // Status update for summary modal handled by UI reacting to loading state

    try {
        const response = await fetch(`/api/files/${fileId}/summary`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        const data = await response.json();

        // Update state with the summary content
        // Assuming state has a place to hold the summary for the currently edited file
        // We need a state variable for the summary content itself, tied to currentEditingFileId
        state.setCurrentEditingFileId(fileId); // Ensure state knows which file summary is being edited
        state.setSummaryContent(data.summary); // Assuming you add setSummaryContent to state.js

        setStatus(`Summary loaded/generated for file ${fileId}.`);

        // Reload file list state to update has_summary flag in UI
        await loadUploadedFiles();

    } catch (error) {
        console.error("Error fetching summary:", error);
        state.setSummaryContent(`[Error loading summary: ${error.message}]`); // Update state with error
        setStatus(`Error fetching summary for file ${fileId}.`, true);
    } finally {
        setLoading(false);
    }
}


/** Saves the edited summary. */
export async function saveSummary() {
    if (!state.currentEditingFileId || state.isLoading) return;
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         setStatus("Saving summaries requires Files plugin enabled on Chat tab.", true);
         return;
    }

    // Read the summary content from the state, not the DOM directly
    const updatedSummary = state.summaryContent; // Assuming you add summaryContent to state.js

    setLoading(true, "Saving Summary");
    // Status update handled by UI reacting to loading state

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
        setStatus("Summary saved successfully.");

        // Reload file lists to update summary status display (has_summary flag)
        await loadUploadedFiles();

        // Closing modal should be handled by event listener or UI logic reacting to state
    } catch (error) {
        console.error("Error saving summary:", error);
        setStatus("Error saving summary.", true);
    } finally {
        setLoading(false);
    }
}

/**
 * Attaches selected files from the sidebar to the current chat as 'full' files.
 * Updates state.attachedFiles and clears state.sidebarSelectedFiles.
 */
export function attachSelectedFilesFull() {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat' || state.isLoading) {
        setStatus("Cannot attach files: Files plugin disabled, not on Chat tab, or busy.", true);
        return;
    }
    if (state.sidebarSelectedFiles.length === 0) {
        setStatus("No files selected in the sidebar to attach.", true);
        return;
    }

    // Add selected files to the attachedFiles state with type 'full'
    state.sidebarSelectedFiles.forEach(file => {
        // Ensure we don't add duplicates (same file ID, same type)
        if (!state.attachedFiles.some(f => f.id === file.id && f.type === 'full')) {
             state.addAttachedFile({ id: file.id, filename: file.filename, type: 'full' });
        }
    });

    // Clear the temporary sidebar selection state
    state.clearSidebarSelectedFiles();

    // UI will react to state changes (attachedFiles and sidebarSelectedFiles)
    setStatus(`Attached ${state.attachedFiles.length} file(s) (full content).`); // Status message might need refinement
}

/**
 * Attaches selected files from the sidebar to the current chat as 'summary' files.
 * Updates state.attachedFiles and clears state.sidebarSelectedFiles.
 * Generates summaries if they don't exist.
 */
export async function attachSelectedFilesSummary() {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat' || state.isLoading) {
        setStatus("Cannot attach files: Files plugin disabled, not on Chat tab, or busy.", true);
        return;
    }
    const selectedFiles = [...state.sidebarSelectedFiles]; // Copy selection
    if (selectedFiles.length === 0) {
        setStatus("No files selected in the sidebar to attach.", true);
        return;
    }

    setLoading(true, "Attaching Summaries (generating if needed)...");
    const filesToAttach = []; // Collect files to attach after processing
    const errors = [];

    for (const file of selectedFiles) {
        setStatus(`Processing ${file.filename}...`); // Update status per file
        let summaryAvailable = file.has_summary;
        let fileId = file.id; // Get file ID

        if (!summaryAvailable) {
            setStatus(`Generating summary for ${file.filename}...`);
            try {
                // Call fetchSummary which handles the API call, state update, and file list reload
                await fetchSummary(fileId);

                // Check state for the summary content after fetchSummary completes
                // We need to find the updated file details from the main list now
                const updatedFile = state.uploadedFiles.find(f => f.id === fileId);
                if (updatedFile && updatedFile.has_summary && !state.summaryContent.startsWith('[Error')) {
                    summaryAvailable = true; // Mark as available after successful generation
                    setStatus(`Summary generated for ${file.filename}.`);
                } else {
                    // Use the potentially updated summaryContent from state for the error message
                    const errorMsg = state.summaryContent.startsWith('[Error') ? state.summaryContent : `Failed to generate summary for ${file.filename}`;
                    throw new Error(errorMsg);
                }
            } catch (error) {
                console.error(`Error generating summary for ${file.filename}:`, error);
                errors.push(`${file.filename}: ${error.message}`);
                summaryAvailable = false; // Ensure it's not attached if generation failed
            }
        }

        // If summary was initially available or successfully generated, prepare to attach
        if (summaryAvailable) {
            // Check for duplicates in the main attachedFiles state before adding
            if (!state.attachedFiles.some(f => f.id === fileId && f.type === 'summary')) {
                 filesToAttach.push({ id: fileId, filename: file.filename, type: 'summary' });
            } else {
                 console.log(`[DEBUG] File ${fileId} (summary) already attached, skipping duplicate.`);
            }
        }
    } // End for loop

    // Now add all successfully processed files to the state
    filesToAttach.forEach(file => {
        state.addAttachedFile(file); // Notifies attachedFiles
    });

    // Clear the temporary sidebar selection state
    state.clearSidebarSelectedFiles(); // Notifies sidebarSelectedFiles

    // Final status update
    let finalStatus = `Attached ${filesToAttach.length} file(s) (summary).`;
    if (errors.length > 0) {
        finalStatus += ` Errors: ${errors.join('; ')}`;
    }
    setStatus(finalStatus, errors.length > 0);
    setLoading(false);
}


// --- Calendar API ---

/** Fetches calendar events and updates state. */
export async function loadCalendarEvents() {
    if (state.isLoading) return;
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        setStatus("Loading calendar events requires Calendar plugin enabled on Chat tab.", true);
        return;
    }

    setLoading(true, "Loading Events");
    try {
        const response = await fetch('/api/calendar/events');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error ${response.status}`);
        }
        // Update state with calendar context
        state.setCalendarContext(data.events || "[No event data received]");
        // state.isCalendarContextActive is toggled by the UI element, not here

        setStatus("Calendar events loaded.");
    } catch (error) {
        console.error('Error loading calendar events:', error);
        state.setCalendarContext(null); // Clear context on error
        // Add a system message to chat history via state? Or let UI handle based on status?
        // For now, just update status
        setStatus(`Error loading calendar events: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}


// --- Chat API ---

/** Loads the list of saved chats from the backend and updates the state. */
export async function loadSavedChats() {
    if (!elements.savedChatsList) return; // Cannot update UI placeholder if element missing

    // Set loading only if not already loading (e.g., during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) setLoading(true, "Loading Chats");

    // Clear current list in state immediately to show loading state in UI
    state.setSavedChats([]);

    try {
        const response = await fetch('/api/chats');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const chats = await response.json();
        state.setSavedChats(chats); // Update state

        setStatus("Saved chats loaded.");
    } catch (error) {
        console.error('Error loading saved chats:', error);
        setStatus("Error loading saved chats.", true);
        // state.savedChats is already [] from above
        throw error; // Re-throw for initializeApp to catch
    } finally {
        if (!wasLoading) setLoading(false);
    }
}


/** Starts a new chat session by calling the backend and updates state. */
export async function startNewChat() {
    setLoading(true, "Creating Chat");
    try {
        const response = await fetch('/api/chat', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newChat = await response.json();

        // Load the new chat (this updates state.currentChatId, loads history, resets context)
        await loadChat(newChat.id);

        // Reload the chat list state to include the new chat
        await loadSavedChats();

        setStatus(`New chat created (ID: ${newChat.id}).`);

    } catch (error) {
        console.error('Error starting new chat:', error);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        setStatus("Error creating new chat.", true);
        // Don't re-throw, allow UI to remain usable if possible
    } finally {
        setLoading(false);
    }
}

/** Loads a specific chat's history and details from the backend and updates state. */
export async function loadChat(chatId) {
    console.log(`[DEBUG] loadChat(${chatId}) called.`);
    setLoading(true, "Loading Chat");
    // Clear chat history in state immediately to show loading state in UI
    state.setChatHistory([]); // Assuming you add setChatHistory to state.js

    try {
        const response = await fetch(`/api/chat/${chatId}`);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status} ${response.statusText} - ${errorText}`);
        }
        const data = await response.json();

        // Update state with chat details and history
        state.setCurrentChatId(data.details.id);
        localStorage.setItem('currentChatId', data.details.id); // Persist ID
        state.setCurrentChatName(data.details.name || ''); // Assuming you add setCurrentChatName to state.js
        state.setCurrentChatModel(data.details.model_name || ''); // Assuming you add setCurrentChatModel to state.js
        state.setChatHistory(data.history || []); // Update state with history

        // Reset chat-specific context states (files, calendar, web search toggle)
        resetChatContext(); // This updates state variables

        // Assuming the backend returns attached files with chat details
        state.setAttachedFiles(data.details.attached_files || []);

        // Plugin enabled states are loaded from localStorage in app.js init

        setStatus(`Chat ${state.currentChatId} loaded.`);
        console.log(`[DEBUG] loadChat(${chatId}) finished successfully.`);

    } catch (error) {
        console.error(`Error loading chat ${chatId}:`, error);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        setStatus(`Error loading chat ${chatId}.`, true);

        // Reset state on error
        state.setCurrentChatId(null);
        localStorage.removeItem('currentChatId');
        state.setCurrentChatName('');
        state.setCurrentChatModel('');
        state.setChatHistory([]);
        resetChatContext(); // Clear files, calendar, etc. state

        throw error; // Re-throw for initializeApp or switchTab to handle
    } finally {
        setLoading(false);
    }
}

// Helper to reset context state when switching chats or starting new
function resetChatContext() {
    state.clearSidebarSelectedFiles(); // Clear temporary sidebar selections
    state.clearAttachedFiles(); // Clear permanent file selections
    state.setSessionFile(null); // Clear session file state

    state.setCalendarContext(null);
    state.setCalendarContextActive(false); // Reset toggle state

    state.setWebSearchEnabled(false); // Assuming you add setWebSearchEnabled to state.js
}


/** Sends the user message and context to the backend. */
export async function sendMessage() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        setStatus("Cannot send: No active chat, busy, or not on Chat tab.", true);
        return;
    }

    // Read message from DOM
    const message = elements.messageInput?.value.trim() || '';

    // Files to send are the permanently attached files PLUS the session file
    const filesToAttach = state.isFilePluginEnabled ? state.attachedFiles : [];
    const sessionFileToSend = state.isFilePluginEnabled ? state.sessionFile : null;
    const calendarContextToSend = (state.isCalendarPluginEnabled && state.isCalendarContextActive && state.calendarContext) ? state.calendarContext : null;
    const webSearchEnabledToSend = state.isWebSearchPluginEnabled && state.isWebSearchEnabled; // Read web search state

    if (!message && filesToAttach.length === 0 && !sessionFileToSend && !calendarContextToSend && !webSearchEnabledToSend) {
        setStatus("Cannot send: Empty message and no context/files attached.", true);
        return;
    }

    // Clear input in DOM immediately
    if (elements.messageInput) elements.messageInput.value = '';

    // Add user message to state immediately
    // UI will react to this state change to display the message
    state.addMessageToHistory({ role: 'user', content: message }); // Assuming addMessageToHistory in state.js

    setLoading(true, "Sending");

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
            // Add an empty assistant message to state immediately for streaming
            state.addMessageToHistory({ role: 'assistant', content: '' }); // Assuming addMessageToHistory handles streaming

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                // Append chunk to the last message in state
                state.appendContentToLastMessage(chunk); // Assuming appendContentToLastMessage in state.js
            }
            // Markdown rendering will be handled by the UI when state updates are processed
            setStatus("Assistant replied (streaming finished).");
        } else {
            // Handle Non-Streaming Response
            const data = await response.json();
            // Add the full assistant message to state
            state.addMessageToHistory({ role: 'assistant', content: data.reply });
            setStatus("Assistant replied.");
        }

        // Reload saved chats list state to update timestamp
        await loadSavedChats();

        // Clear temporary sidebar selection state after successful send
        state.clearSidebarSelectedFiles();

        // Do NOT clear attachedFiles state here. They persist per chat.
        // Only clear the session file state.

    } catch (error) {
        console.error('Error sending message:', error);
        const errorMessage = `[Error: ${error.message}]`;
        // Add error message to state
        state.addMessageToHistory({ role: 'assistant', content: errorMessage, isError: true }); // Assuming addMessageToHistory handles errors
        setStatus("Error sending message.", true);
    } finally {
        // Clear the session file state if it was the one sent
        if (sentSessionFile && state.sessionFile === sentSessionFile) {
             state.setSessionFile(null);
        }
        setLoading(false);
    }
}


/** Saves the current chat's name by calling the backend and updates state. */
export async function handleSaveChatName() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') return;

    // Read new name from DOM
    const newName = elements.currentChatNameInput?.value.trim() || 'New Chat';

    setLoading(true, "Saving Name");
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
        setStatus(`Chat ${state.currentChatId} name saved.`);

        // Update the name in the state directly
        state.setCurrentChatName(newName);

        // Reload saved chats list state to update timestamp/name in sidebar
        await loadSavedChats();

    } catch (error) {
        console.error('Error saving chat name:', error);
        setStatus(`Error saving name: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

/** Deletes a chat by calling the backend and updates state. */
export async function handleDeleteChat(chatId) { // Removed listItemElement param
    if (state.isLoading || state.currentTab !== 'chat') return;

    // Find the chat name from state for the confirmation message
    const chatToDelete = state.savedChats.find(chat => chat.id === chatId);
    const chatName = chatToDelete ? (chatToDelete.name || `Chat ${chatId}`) : `Chat ${chatId}`;

    if (!confirm(`Are you sure you want to delete "${chatName}"? This cannot be undone.`)) {
        return;
    }
    setLoading(true, "Deleting Chat");
    try {
        const response = await fetch(`/api/chat/${chatId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`Chat ${chatId} deleted.`);

        // Remove from state first
        state.setSavedChats(state.savedChats.filter(chat => chat.id !== chatId));

        // If the deleted chat was the currently active one, load another or start new
        if (chatId == state.currentChatId) {
            state.setCurrentChatId(null); // Clear current chat state
            localStorage.removeItem('currentChatId');
            // loadSavedChats already re-rendered the list state
            const firstChat = state.savedChats.length > 0 ? state.savedChats[0] : null; // Get from updated state
            if (firstChat) {
                await loadChat(firstChat.id);
            } else {
                await startNewChat(); // Create and load a new chat
            }
        }
        // If a different chat was deleted, loadSavedChats (called above) will trigger UI re-render

    } catch (error) {
        console.error(`Error deleting chat ${chatId}:`, error);
        setStatus(`Error deleting chat: ${error.message}`, true);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        // Reload list state on failure to ensure UI consistency
        await loadSavedChats();
    } finally {
        setLoading(false);
    }
}

/** Handles changing the model for the current chat by calling the backend and updates state. */
export async function handleModelChange() {
    if (!state.currentChatId || state.isLoading || state.currentTab !== 'chat') return;

    // Read new model from DOM
    const newModel = elements.modelSelector?.value;
    if (!newModel) return;

    // Store current model from state before attempting update in case of error
    const originalModel = state.currentChatModel;

    setLoading(true, "Updating Model");
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
        setStatus(`Model updated to ${newModel} for this chat.`);

        // Update state with the new model name
        state.setCurrentChatModel(newModel);

    } catch (error) {
        console.error("Error updating model:", error);
        setStatus(`Error updating model: ${error.message}`, true);
        // Revert state on error
        state.setCurrentChatModel(originalModel);
    } finally {
        setLoading(false);
    }
}


// --- Notes API ---

/** Loads the list of saved notes from the backend and updates the state. */
export async function loadSavedNotes() {
     if (!elements.savedNotesList) return; // Cannot update UI placeholder if element missing

     const wasLoading = state.isLoading;
     if (!wasLoading) setLoading(true, "Loading Notes");

     // Clear current list in state immediately
     state.setSavedNotes([]);

     try {
         const response = await fetch('/api/notes');
         if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
         const notes = await response.json();
         state.setSavedNotes(notes); // Update state

         setStatus("Saved notes loaded.");
     } catch (error) {
         console.error('Error loading saved notes:', error);
         setStatus("Error loading saved notes.", true);
         // state.savedNotes is already [] from above
         throw error; // Re-throw for initializeApp
     } finally {
         if (!wasLoading) setLoading(false);
     }
}


/** Creates a new note entry by calling the backend and updates state. */
export async function startNewNote() {
    console.log(`[DEBUG] startNewNote called.`);
    if (state.isLoading) return;
    setLoading(true, "Creating Note");

    // Clear current note state immediately
    state.setCurrentNoteId(null);
    state.setCurrentNoteName(''); // Assuming setCurrentNoteName in state.js
    state.setNoteContent(''); // Assuming setNoteContent in state.js

    try {
        const response = await fetch('/api/notes', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newNote = await response.json();
        console.log(`[DEBUG] startNewNote: Received new note ID ${newNote.id}. Loading it...`);

        // Load the new note (this updates state.currentNoteId, name, content)
        await loadNote(newNote.id);

        // Reload the notes list state
        await loadSavedNotes();

        setStatus(`New note created (ID: ${newNote.id}).`);
        console.log(`[DEBUG] startNewNote: Successfully created and loaded note ${newNote.id}.`);
    } catch (error) {
        console.error('Error starting new note:', error);
        setStatus("Error creating new note.", true);
        // state is already reset above
    } finally {
        setLoading(false);
    }
}

/** Loads the content of a specific note from the backend and updates state. */
export async function loadNote(noteId) {
    console.log(`[DEBUG] loadNote(${noteId}) called.`);
    if (state.isLoading) return;
    setLoading(true, "Loading Note");

    // Clear current note content state immediately
    state.setNoteContent(''); // Assuming setNoteContent in state.js

    try {
        const response = await fetch(`/api/note/${noteId}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        // Update state with note details and content
        state.setCurrentNoteId(data.id);
        localStorage.setItem('currentNoteId', data.id); // Persist ID
        state.setCurrentNoteName(data.name || '');
        state.setNoteContent(data.content || '');

        setStatus(`Note ${state.currentNoteId} loaded.`);

    } catch (error) {
        console.error(`Error loading note ${noteId}:`, error);
        setStatus(`Error loading note ${noteId}.`, true);

        // Reset state on error
        state.setCurrentNoteId(null);
        localStorage.removeItem('currentNoteId');
        state.setCurrentNoteName('');
        state.setNoteContent(`[Error loading note ${noteId}: ${error.message}]`); // Put error in content state

        throw error; // Re-throw for switchTab to handle
    } finally {
        setLoading(false);
    }
}

/** Saves the current note content and name by calling the backend and updates state. */
export async function saveNote() {
    console.log(`[DEBUG] saveNote called.`);
    if (state.isLoading || !state.currentNoteId || state.currentTab !== 'notes') {
        setStatus("Cannot save: No active note, busy, or not on Notes tab.", true);
        return;
    }
    setLoading(true, "Saving Note");

    // Read name and content from state, not DOM
    const noteName = state.currentNoteName || 'New Note';
    const noteContent = state.noteContent || ''; // Assuming noteContent in state.js

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
        setStatus(`Note ${state.currentNoteId} saved successfully.`);

        // Reload notes list state to update timestamp/name in sidebar
        await loadSavedNotes();

    } catch (error) {
        console.error(`Error saving note ${state.currentNoteId}:`, error);
        setStatus(`Error saving note: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

/** Deletes a specific note by calling the backend and updates state. */
export async function handleDeleteNote(noteId) { // Removed listItemElement param
    if (state.isLoading || state.currentTab !== 'notes') return;

    // Find the note name from state for the confirmation message
    const noteToDelete = state.savedNotes.find(note => note.id === noteId);
    const noteName = noteToDelete ? (noteToDelete.name || `Note ${noteId}`) : `Note ${noteId}`;

    if (!confirm(`Are you sure you want to delete "${noteName}"? This cannot be undone.`)) {
        return;
    }
    setLoading(true, "Deleting Note");
    try {
        const response = await fetch(`/api/note/${noteId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        setStatus(`Note ${noteId} deleted.`);

        // Remove from state first
        state.setSavedNotes(state.savedNotes.filter(note => note.id !== noteId));

        // If the deleted note was the currently active one, load another or start new
        if (noteId == state.currentNoteId) {
            state.setCurrentNoteId(null); // Clear current note state
            localStorage.removeItem('currentNoteId');
            // loadSavedNotes already re-rendered the list state
            const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null; // Get from updated state
            if (firstNote) {
                await loadNote(firstNote.id);
            } else {
                await startNewNote(); // Create and load a new note
            }
        }
        // If a different note was deleted, loadSavedNotes (called above) will trigger UI re-render

    } catch (error) {
        console.error(`Error deleting note ${noteId}:`, error);
        setStatus(`Error deleting note: ${error.message}`, true);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        // Reload list state on failure
        await loadSavedNotes();
    } finally {
        setLoading(false);
    }
}


// --- Initial Data Loading ---

/** Loads the initial data required for the Chat tab. */
export async function loadInitialChatData() {
    // loadSavedChats is called by initializeApp before switchTab
    // await loadSavedChats(); // Load chat list state first

    let chatToLoadId = state.currentChatId; // Use persisted ID if available

    if (chatToLoadId !== null) {
        console.log(`[DEBUG] loadInitialChatData: currentChatId is ${chatToLoadId}, attempting to load it.`);
        try {
            await loadChat(chatToLoadId); // Attempt to load the persisted chat (updates state)
        } catch (error) {
            console.warn(`[DEBUG] loadInitialChatData: loadChat(${chatToLoadId}) failed: ${error}. Falling back.`);
            state.setCurrentChatId(null); // Clear the failed ID state
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
            await loadChat(mostRecentChatId); // Updates state
        } else {
            console.log("[DEBUG] No saved chats found, starting new chat.");
            await startNewChat(); // Updates state
        }
    }
    console.log(`[DEBUG] loadInitialChatData finished. Final currentChatId: ${state.currentChatId}`);
}

/** Loads the initial data required for the Notes tab. */
export async function loadInitialNotesData() {
    // loadSavedNotes is called by initializeApp before switchTab
    // await loadSavedNotes(); // Load notes list state first

    let noteToLoadId = state.currentNoteId; // Use persisted ID

    if (noteToLoadId !== null) {
        console.log(`[DEBUG] loadInitialNotesData: currentNoteId is ${noteToLoadId}, attempting to load it.`);
        try {
            await loadNote(noteToLoadId); // Attempt to load persisted note (updates state)
        } catch (error) {
            console.warn(`[DEBUG] loadInitialNotesData: loadNote(${noteToLoadId}) failed: ${error}. Starting new note.`);
            await startNewNote(); // If load fails, start new (updates state)
            noteToLoadId = state.currentNoteId; // Update ID to the newly created one in state
        }
    } else {
        console.log("[DEBUG] loadInitialNotesData: No currentNoteId, loading most recent or creating new.");
        const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null; // Get from state
        if (firstNote) {
            const mostRecentNoteId = firstNote.id;
            console.log(`[DEBUG] Loading most recent note: ${mostRecentNoteId}`);
            await loadNote(mostRecentNoteId); // Updates state
        } else {
            console.log("[DEBUG] No saved notes found, starting new note.");
            await startNewNote(); // Updates state
        }
    }

    // Note mode is handled by UI reacting to state.currentNoteMode
    console.log(`[DEBUG] loadInitialNotesData finished. Final currentNoteId: ${state.currentNoteId}`);
}
