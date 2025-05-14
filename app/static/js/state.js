// js/state.js

import { elements } from './dom.js'; // Import elements object

// Application State Variables
// Use 'export let' to allow them to be reassigned by other modules
export let currentChatId = null;
export let currentNoteId = null;
export let isLoading = false;
export let statusMessage = "Initializing..."; // Default status
export let isErrorStatus = false;
export let savedChats = [];
export let chatHistory = [];
export let currentChatName = '';
export let currentChatModel = ''; // Default model or from config
export let currentChatMode = 'chat';
export let processingChatId = null; // ID of the chat currently being processed (e.g., for streaming response)
export let isRecording = false;
export let isSocketConnected = false; // Track WebSocket connection status
export let streamingTranscript = ''; // Holds the full streaming transcript (final + interim)
export let finalizedTranscript = ''; // Holds the finalized part of the transcript
export let currentInterimTranscript = ''; // Holds the current interim part
export let recordingContext = null; // 'chat' or 'notes'
export let isLongRecordingActive = false; // For non-streaming long recordings
export let lastLongTranscript = null; // Stores the result of the last long recording
export let recordingTimerInterval = null; // Timer for long recording duration
export let longRecordingStartTime = null; // Start time for long recording

// Notes State
export let savedNotes = [];
export let currentNoteName = '';
export let noteContent = ''; // Markdown content of the current note
export let noteHistory = []; // Array of {id, name, content, saved_at, note_diff}
export let currentNoteMode = 'edit'; // 'edit' or 'view'
export let currentNoteActiveH1SectionIndex = 0; // Index of the active H1 section in view mode

// File Management State
export let uploadedFiles = []; // Array of {id, filename, mimetype, filesize, has_summary, uploaded_at}
export let sidebarSelectedFiles = []; // Array of {id, filename, has_summary} for files selected in the sidebar
export let attachedFiles = []; // Array of {id, filename, type: 'full' | 'summary'} for files attached to current message
export let sessionFile = null; // {filename, mimetype, content (dataURL)} for the single session file
export let currentEditingFileId = null; // ID of the file whose summary is being edited
export let summaryContent = ""; // Content of the summary being edited
export let isFileContentModalOpen = false; // Tracks if the file content modal is open
export let currentViewingFileId = null;
export let currentViewingFilename = null;
export let currentViewingFileContent = null; // Can be text or base64 string
export let currentViewingFileMimetype = null;
export let currentViewingFileIsBase64 = false; // Flag if currentViewingFileContent is raw base64

// Plugin States
export let calendarContext = null; // { events: [], timestamp: Date }
export let isCalendarContextActive = false;
export let isWebSearchEnabled = false;
export let isDeepResearchEnabled = false;
export let isImprovePromptEnabled = false;

// UI State
export let currentTab = 'chat'; // 'chat' or 'notes'
export let isSidebarCollapsed = false;
export let isPluginsCollapsed = false;
export let isNotesTocCollapsed = false;

// --- Notes Search State ---
export let isNoteSearchActive = false;
export let noteSearchQuery = '';
export let noteSearchResults = [];
// --------------------------


// --- Internal State for Notifications ---
const listeners = new Map();
let notificationsEnabled = true; // Start with notifications enabled

// --- Notification Control ---
export function disableNotifications() {
    notificationsEnabled = false;
}
export function enableNotifications() {
    notificationsEnabled = true;
}

/**
 * Notifies listeners of a specific event type.
 * @param {string} eventType - The type of event/state change.
 * @param {any} data - The data associated with the event.
 */
function notify(eventType, data) {
    if (!notificationsEnabled) {
        // console.log(`[STATE DEBUG] Notifications disabled. Skipping notify for ${eventType}.`);
        return;
    }
    // console.log(`[STATE DEBUG] Notifying for ${eventType} with data:`, data);
    if (listeners.has(eventType)) {
        const eventListeners = listeners.get(eventType);
        eventListeners.forEach((listener, index) => {
            try {
                // console.log(`[STATE DEBUG] Calling listener ${index + 1} for ${eventType}.`);
                listener(data);
            } catch (error) {
                console.error(`Error in listener for ${eventType} (listener ${index + 1}):`, error);
                // Optionally, remove the faulty listener to prevent further errors
                // eventListeners.splice(index, 1);
            }
        });
    }
}

/**
 * Subscribes a listener function to a specific event type.
 * @param {string} eventType - The event type to subscribe to.
 * @param {Function} listener - The function to call when the event occurs.
 */
export function subscribe(eventType, listener) {
    if (!listeners.has(eventType)) {
        listeners.set(eventType, []);
    }
    listeners.get(eventType).push(listener);
    // console.log(`[STATE DEBUG] Listener subscribed to ${eventType}. Total listeners for type: ${listeners.get(eventType).length}`);
}

/**
 * Notifies all listeners about the current state of all properties.
 * Useful for initial UI setup or after re-enabling notifications.
 */
export function notifyAll() {
    console.log("[STATE DEBUG] notifyAll called. Re-notifying all current states.");
    // Temporarily enable notifications if they were disabled, to ensure notifyAll works
    const wasEnabled = notificationsEnabled;
    notificationsEnabled = true;

    notify('isLoading', isLoading);
    notify('statusMessage', { message: statusMessage, isError: isErrorStatus });
    notify('savedChats', savedChats);
    notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, history: chatHistory });
    notify('chatHistory', chatHistory);
    notify('currentChatMode', currentChatMode);
    notify('processingChatId', processingChatId);
    notify('isRecording', isRecording);
    notify('isSocketConnected', isSocketConnected);
    notify('streamingTranscript', { finalized: finalizedTranscript, interim: currentInterimTranscript, context: recordingContext });
    notify('isLongRecordingActive', isLongRecordingActive);
    notify('lastLongTranscript', lastLongTranscript);

    notify('savedNotes', savedNotes);
    notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    notify('noteContent', noteContent); // Explicitly notify for noteContent as well
    notify('noteHistory', noteHistory);
    notify('currentNoteMode', currentNoteMode);
    notify('currentNoteActiveH1SectionIndex', currentNoteActiveH1SectionIndex);

    notify('uploadedFiles', uploadedFiles);
    notify('sidebarSelectedFiles', sidebarSelectedFiles);
    notify('attachedFiles', attachedFiles);
    notify('sessionFile', sessionFile);
    notify('currentEditingFileId', currentEditingFileId);
    notify('summaryContent', summaryContent);
    notify('isFileContentModalOpen', isFileContentModalOpen);
    notify('currentViewingFileId', currentViewingFileId);
    notify('currentViewingFilename', currentViewingFilename);
    notify('currentViewingFileContent', currentViewingFileContent);
    notify('currentViewingFileMimetype', currentViewingFileMimetype);
    notify('currentViewingFileIsBase64', currentViewingFileIsBase64);

    notify('calendarContext', calendarContext);
    notify('isCalendarContextActive', isCalendarContextActive);
    notify('isWebSearchEnabled', isWebSearchEnabled);
    notify('isDeepResearchEnabled', isDeepResearchEnabled);
    notify('isImprovePromptEnabled', isImprovePromptEnabled);

    notify('currentTab', currentTab);
    notify('isSidebarCollapsed', isSidebarCollapsed);
    notify('isPluginsCollapsed', isPluginsCollapsed);
    notify('isNotesTocCollapsed', isNotesTocCollapsed);

    // --- Notify for new note search states ---
    notify('isNoteSearchActive', isNoteSearchActive);
    notify('noteSearchQuery', noteSearchQuery);
    notify('noteSearchResults', noteSearchResults);
    // ---------------------------------------

    notificationsEnabled = wasEnabled; // Restore original notification state
}


// --- Setter Functions (Alphabetical Order, with new additions at the end or in logical groups) ---

export function addAttachedFile(file) {
    // Ensure file is not already attached (check by id and type)
    const existingFile = attachedFiles.find(f => f.id === file.id && f.type === file.type);
    if (!existingFile) {
        attachedFiles.push(file);
        notify('attachedFiles', attachedFiles);
    }
}

export function addSavedChat(chat) {
    const index = savedChats.findIndex(c => c.id === chat.id);
    if (index === -1) {
        savedChats.push(chat);
    } else {
        savedChats[index] = chat;
    }
    savedChats.sort((a, b) => new Date(b.last_updated_at) - new Date(a.last_updated_at));
    notify('savedChats', savedChats);
}

export function addSavedNote(note) {
    const index = savedNotes.findIndex(n => n.id === note.id);
    if (index === -1) {
        savedNotes.push(note);
    } else {
        savedNotes[index] = note;
    }
    savedNotes.sort((a, b) => new Date(b.last_saved_at) - new Date(a.last_saved_at));
    notify('savedNotes', savedNotes);
}

export function addMessageToHistory(message) {
    if (!message || typeof message.role === 'undefined' || typeof message.content === 'undefined') {
        console.error("Attempted to add invalid message to history:", message);
        return;
    }
    chatHistory.push(message);
    notify('chatHistory', chatHistory);
}

export function addSidebarSelectedFile(file) {
    if (!sidebarSelectedFiles.some(sf => sf.id === file.id)) {
        sidebarSelectedFiles.push(file);
        notify('sidebarSelectedFiles', sidebarSelectedFiles);
    }
}

export function addUploadedFile(file) {
    const index = uploadedFiles.findIndex(f => f.id === file.id);
    if (index === -1) {
        uploadedFiles.push(file);
    } else {
        uploadedFiles[index] = file;
    }
    uploadedFiles.sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
    notify('uploadedFiles', uploadedFiles);
}

export function appendContentToLastMessage(chunk) { // <<< NEW FUNCTION
    if (chatHistory.length > 0) {
        const lastMessage = chatHistory[chatHistory.length - 1];
        if (lastMessage.role === 'assistant' && !lastMessage.isError) {
            lastMessage.content += chunk;
            notify('chatHistory', chatHistory);
        } else {
            console.warn("appendContentToLastMessage: Last message not suitable for appending or is an error message.", lastMessage);
            // Potentially, one could add a new assistant message here if the last one isn't suitable,
            // but the calling logic in api.js already handles creating a new message if needed.
        }
    }
}

export function appendFinalizedTranscript(segment) { // <<< NEW FUNCTION
    if (segment) {
        finalizedTranscript += (finalizedTranscript ? " " : "") + segment;
        streamingTranscript = finalizedTranscript ? `${finalizedTranscript} ${currentInterimTranscript}`.trim() : currentInterimTranscript;
        notify('streamingTranscript', { finalized: finalizedTranscript, interim: currentInterimTranscript, context: recordingContext });
    }
}

export function clearAllCurrentMessageAttachments() { // <<< NEW FUNCTION
    let notifiedAttached = false;
    let notifiedSession = false;

    if (attachedFiles.length > 0) {
        attachedFiles.length = 0; // Modifies in place
        notify('attachedFiles', attachedFiles);
        notifiedAttached = true;
    }
    if (sessionFile !== null) {
        sessionFile = null;
        notify('sessionFile', sessionFile);
        notifiedSession = true;
    }
    // If neither was changed, no need to log anything specific.
    // Individual notifications are sufficient.
}

export function clearAttachedFiles() {
    if (attachedFiles.length > 0) {
        attachedFiles.length = 0;
        notify('attachedFiles', attachedFiles);
    }
}

export function clearChatHistory() {
    if (chatHistory.length > 0) {
        chatHistory.length = 0;
        notify('chatHistory', chatHistory);
    }
}

export function clearCurrentViewingFile() {
    let changed = false;
    if (currentViewingFileId !== null) { currentViewingFileId = null; changed = true; }
    if (currentViewingFilename !== null) { currentViewingFilename = null; changed = true; }
    if (currentViewingFileContent !== null) { currentViewingFileContent = null; changed = true; }
    if (currentViewingFileMimetype !== null) { currentViewingFileMimetype = null; changed = true; }
    if (currentViewingFileIsBase64 !== false) { currentViewingFileIsBase64 = false; changed = true; }

    if (changed) {
        notify('currentViewingFileId', currentViewingFileId);
        notify('currentViewingFilename', currentViewingFilename);
        notify('currentViewingFileContent', currentViewingFileContent);
        notify('currentViewingFileMimetype', currentViewingFileMimetype);
        notify('currentViewingFileIsBase64', currentViewingFileIsBase64);
    }
}

export function clearSidebarSelectedFiles() {
    if (sidebarSelectedFiles.length > 0) {
        sidebarSelectedFiles.length = 0;
        notify('sidebarSelectedFiles', sidebarSelectedFiles);
    }
}

export function getInputElementForContext(context) {
    if (context === 'chat') return elements.messageInput;
    if (context === 'notes') return elements.notesTextarea;
    return null;
}

export function removeAttachedFileByIdAndType(fileId, fileType) {
    const initialLength = attachedFiles.length;
    attachedFiles = attachedFiles.filter(f => !(f.id === fileId && f.type === fileType));
    if (attachedFiles.length !== initialLength) {
        notify('attachedFiles', attachedFiles);
    }
}

export function removeSavedChat(chatId) {
    const initialLength = savedChats.length;
    savedChats = savedChats.filter(c => c.id !== chatId);
    if (savedChats.length !== initialLength) {
        notify('savedChats', savedChats);
    }
}

export function removeSavedNote(noteId) {
    const initialLength = savedNotes.length;
    savedNotes = savedNotes.filter(n => n.id !== noteId);
    if (savedNotes.length !== initialLength) {
        notify('savedNotes', savedNotes);
    }
}

export function removeSidebarSelectedFileById(fileId) {
    const initialLength = sidebarSelectedFiles.length;
    sidebarSelectedFiles = sidebarSelectedFiles.filter(sf => sf.id !== fileId);
    if (sidebarSelectedFiles.length !== initialLength) {
        notify('sidebarSelectedFiles', sidebarSelectedFiles);
    }
}

export function removeUploadedFile(fileId) {
    const initialLength = uploadedFiles.length;
    uploadedFiles = uploadedFiles.filter(f => f.id !== fileId);
    if (uploadedFiles.length !== initialLength) {
        notify('uploadedFiles', uploadedFiles);
    }
}

export function setAttachedFiles(files) {
    attachedFiles = Array.isArray(files) ? files : [];
    notify('attachedFiles', attachedFiles);
}

export function setCalendarContext(context) {
    if (calendarContext !== context) {
        calendarContext = context;
        notify('calendarContext', calendarContext);
    }
}

export function setCalendarContextActive(active) {
    if (isCalendarContextActive !== active) {
        isCalendarContextActive = active;
        notify('isCalendarContextActive', isCalendarContextActive);
    }
}

export function setChatHistory(history) {
    chatHistory = history;
    notify('chatHistory', chatHistory);
}

export function setCurrentChatId(id) {
    if (currentChatId !== id) {
        currentChatId = id;
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, history: chatHistory });
    }
}

export function setCurrentChatMode(mode) {
    if (currentChatMode !== mode) {
        currentChatMode = mode;
        notify('currentChatMode', currentChatMode);
    }
}

export function setCurrentChatModel(model) {
    if (currentChatModel !== model) {
        currentChatModel = model;
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, history: chatHistory });
    }
}

export function setCurrentChatName(name) {
    if (currentChatName !== name) {
        currentChatName = name;
        notify('currentChatName', currentChatName);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, history: chatHistory });
    }
}

export function setCurrentEditingFileId(id) {
    if (currentEditingFileId !== id) {
        currentEditingFileId = id;
        notify('currentEditingFileId', currentEditingFileId);
    }
}

export function setCurrentInterimTranscript(transcript) {
    if (currentInterimTranscript !== transcript) {
        currentInterimTranscript = transcript;
        streamingTranscript = finalizedTranscript ? `${finalizedTranscript} ${currentInterimTranscript}`.trim() : currentInterimTranscript;
        notify('streamingTranscript', { finalized: finalizedTranscript, interim: currentInterimTranscript, context: recordingContext });
    }
}

export function setCurrentNoteActiveH1SectionIndex(index) {
    if (currentNoteActiveH1SectionIndex !== index) {
        currentNoteActiveH1SectionIndex = index;
        notify('currentNoteActiveH1SectionIndex', currentNoteActiveH1SectionIndex);
    }
}

export function setCurrentNoteId(id) {
    if (currentNoteId !== id) {
        currentNoteId = id;
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    }
}

export function setCurrentNoteMode(mode) {
    if (currentNoteMode !== mode) {
        currentNoteMode = mode;
        notify('currentNoteMode', currentNoteMode);
    }
}

export function setCurrentNoteName(name) {
    if (currentNoteName !== name) {
        currentNoteName = name;
        notify('currentNoteName', currentNoteName);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    }
}

export function setCurrentTab(tab) {
    if (currentTab !== tab) {
        currentTab = tab;
        notify('currentTab', currentTab);
    }
}

export function setCurrentViewingFile(id, filename, content, mimetype, isBase64) {
    let changed = false;
    if (currentViewingFileId !== id) { currentViewingFileId = id; changed = true; }
    if (currentViewingFilename !== filename) { currentViewingFilename = filename; changed = true; }
    if (currentViewingFileContent !== content) { currentViewingFileContent = content; changed = true; }
    if (currentViewingFileMimetype !== mimetype) { currentViewingFileMimetype = mimetype; changed = true; }
    if (currentViewingFileIsBase64 !== isBase64) { currentViewingFileIsBase64 = isBase64; changed = true; }

    if (changed) {
        notify('currentViewingFileId', currentViewingFileId);
        notify('currentViewingFilename', currentViewingFilename);
        notify('currentViewingFileContent', currentViewingFileContent);
        notify('currentViewingFileMimetype', currentViewingFileMimetype);
        notify('currentViewingFileIsBase64', currentViewingFileIsBase64);
    }
}

export function setDeepResearchEnabled(enabled) {
    if (isDeepResearchEnabled !== enabled) {
        isDeepResearchEnabled = enabled;
        notify('isDeepResearchEnabled', isDeepResearchEnabled);
    }
}

export function setFinalizedTranscript(transcript) {
    if (finalizedTranscript !== transcript) {
        finalizedTranscript = transcript;
        streamingTranscript = finalizedTranscript ? `${finalizedTranscript} ${currentInterimTranscript}`.trim() : currentInterimTranscript;
        notify('streamingTranscript', { finalized: finalizedTranscript, interim: currentInterimTranscript, context: recordingContext });
    }
}

export function setIsErrorStatus(isError) {
    if (isErrorStatus !== isError) {
        isErrorStatus = isError;
        notify('statusMessage', { message: statusMessage, isError: isErrorStatus });
    }
}

export function setIsFileContentModalOpen(isOpen) {
    if (isFileContentModalOpen !== isOpen) {
        isFileContentModalOpen = isOpen;
        notify('isFileContentModalOpen', isFileContentModalOpen);
    }
}

export function setIsLoading(loading, message = null) {
    if (isLoading !== loading) {
        isLoading = loading;
        notify('isLoading', isLoading);
    }
    if (message) {
        setStatusMessage(message, isErrorStatus);
    } else if (!loading && statusMessage.startsWith("Loading")) {
        setStatusMessage("Idle");
    }
}

export function setIsLongRecordingActive(isActive) {
    if (isLongRecordingActive !== isActive) {
        isLongRecordingActive = isActive;
        notify('isLongRecordingActive', isLongRecordingActive);
    }
}

export function setIsNotesTocCollapsed(collapsed) {
    if (isNotesTocCollapsed !== collapsed) {
        isNotesTocCollapsed = collapsed;
        notify('isNotesTocCollapsed', isNotesTocCollapsed);
    }
}

export function setIsPluginsCollapsed(collapsed) {
    if (isPluginsCollapsed !== collapsed) {
        isPluginsCollapsed = collapsed;
        notify('isPluginsCollapsed', isPluginsCollapsed);
    }
}

export function setIsRecording(recording) {
    if (isRecording !== recording) {
        isRecording = recording;
        notify('isRecording', isRecording);
    }
}

export function setIsSidebarCollapsed(collapsed) {
    if (isSidebarCollapsed !== collapsed) {
        isSidebarCollapsed = collapsed;
        notify('isSidebarCollapsed', isSidebarCollapsed);
    }
}

export function setIsSocketConnected(connected) {
    if (isSocketConnected !== connected) {
        isSocketConnected = connected;
        notify('isSocketConnected', isSocketConnected);
    }
}

export function setImprovePromptEnabled(enabled) {
    if (isImprovePromptEnabled !== enabled) {
        isImprovePromptEnabled = enabled;
        notify('isImprovePromptEnabled', isImprovePromptEnabled);
    }
}

export function setLastLongTranscript(transcript) {
    if (lastLongTranscript !== transcript) {
        lastLongTranscript = transcript;
        notify('lastLongTranscript', lastLongTranscript);
    }
}

export function setLongRecordingStartTime(time) {
    if (longRecordingStartTime !== time) {
        longRecordingStartTime = time;
    }
}

export function setNoteContent(content) {
    if (noteContent !== content) {
        noteContent = content;
        notify('noteContent', noteContent);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    }
}

export function setNoteHistory(history) {
    noteHistory = history;
    notify('noteHistory', noteHistory);
}

export function setIsNoteSearchActive(isActive) {
    if (isNoteSearchActive !== isActive) {
        isNoteSearchActive = isActive;
        notify('isNoteSearchActive', isNoteSearchActive);
    }
}

export function setNoteSearchQuery(query) {
    if (noteSearchQuery !== query) {
        noteSearchQuery = query;
        notify('noteSearchQuery', noteSearchQuery);
    }
}

export function setNoteSearchResults(results) {
    noteSearchResults = results;
    notify('noteSearchResults', noteSearchResults);
}

export function setProcessingChatId(id) {
    if (processingChatId !== id) {
        processingChatId = id;
        notify('processingChatId', processingChatId);
    }
}

export function setRecordingContext(context) {
    if (recordingContext !== context) {
        recordingContext = context;
    }
}

export function setRecordingTimerInterval(intervalId) {
    if (recordingTimerInterval !== intervalId) {
        recordingTimerInterval = intervalId;
    }
}

export function setSavedChats(chats) {
    savedChats = chats;
    savedChats.sort((a, b) => new Date(b.last_updated_at) - new Date(a.last_updated_at));
    notify('savedChats', savedChats);
}

export function setSavedNotes(notes) {
    savedNotes = notes;
    savedNotes.sort((a, b) => new Date(b.last_saved_at) - new Date(a.last_saved_at));
    notify('savedNotes', savedNotes);
}

export function setSessionFile(file) {
    if (sessionFile !== file) {
        sessionFile = file;
        notify('sessionFile', sessionFile);
    }
}

export function setStatusMessage(message, isError = false) {
    if (statusMessage !== message || isErrorStatus !== isError) {
        statusMessage = message;
        isErrorStatus = isError;
        notify('statusMessage', { message: statusMessage, isError: isErrorStatus });
    }
}

export function setSummaryContent(content) {
    if (summaryContent !== content) {
        summaryContent = content;
        notify('summaryContent', summaryContent);
    }
}

export function setUploadedFiles(files) {
    uploadedFiles = files;
    uploadedFiles.sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
    notify('uploadedFiles', uploadedFiles);
}

export function setWebSearchEnabled(enabled) {
    if (isWebSearchEnabled !== enabled) {
        isWebSearchEnabled = enabled;
        notify('isWebSearchEnabled', isWebSearchEnabled);
    }
}

export function updateChatInSavedChats(chatId, updatedData) {
    const index = savedChats.findIndex(c => c.id === chatId);
    if (index !== -1) {
        savedChats[index] = { ...savedChats[index], ...updatedData };
        if (updatedData.last_updated_at) {
            savedChats.sort((a, b) => new Date(b.last_updated_at) - new Date(a.last_updated_at));
        }
        notify('savedChats', savedChats);
        if (currentChatId === chatId) {
            if (updatedData.name && currentChatName !== updatedData.name) {
                setCurrentChatName(updatedData.name);
            }
            if (updatedData.model && currentChatModel !== updatedData.model) {
                setCurrentChatModel(updatedData.model);
            }
        }
    }
}

export function updateNoteInSavedNotes(noteId, updatedData) {
    const index = savedNotes.findIndex(n => n.id === noteId);
    if (index !== -1) {
        savedNotes[index] = { ...savedNotes[index], ...updatedData };
        if (updatedData.last_saved_at) {
            savedNotes.sort((a, b) => new Date(b.last_saved_at) - new Date(a.last_saved_at));
        }
        notify('savedNotes', savedNotes);
        if (currentNoteId === noteId) {
            if (updatedData.name && currentNoteName !== updatedData.name) {
                setCurrentNoteName(updatedData.name);
            }
        }
    }
}

export function updateUploadedFile(fileId, updatedData) {
    const index = uploadedFiles.findIndex(f => f.id === fileId);
    if (index !== -1) {
        uploadedFiles[index] = { ...uploadedFiles[index], ...updatedData };
        if (updatedData.uploaded_at) {
            uploadedFiles.sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
        }
        notify('uploadedFiles', uploadedFiles);
    }
}

export function updateLastMessageInHistory(updatedContent, newAttachments = null) {
    if (chatHistory.length > 0) {
        const lastMessage = chatHistory[chatHistory.length - 1];
        lastMessage.content = updatedContent;
        if (newAttachments !== null) {
            lastMessage.attachments = newAttachments;
        }
        notify('chatHistory', chatHistory);
    }
}
