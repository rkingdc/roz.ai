// js/state.js

import { elements } from './dom.js'; // Import elements object

// Application State Variables
// Use 'export let' to allow them to be reassigned by other modules
export let currentChatId = null;
export let currentNoteId = null;
export let isLoading = false; // Global loading state
export let statusMessage = "Idle"; // Global status message
export let isErrorStatus = false; // Indicates if the status message is an error

// Files temporarily selected in the sidebar for attachment (before clicking Attach button)
export let sidebarSelectedFiles = [];
// Files permanently attached to the current chat session (sent with every message until removed)
export let attachedFiles = []; // Array of { id, filename, type ('full' or 'summary') }
// File attached via paperclip for the current message only
export let sessionFile = null; // File object { filename, mimetype, content }
export let currentEditingFileId = null; // For summary modal
export let summaryContent = ""; // Content of the summary being edited

export let calendarContext = null; // Loaded calendar events object { events: [], timestamp: ... }
export let isCalendarContextActive = false; // Toggle state for including calendar context

// Plugin enabled states (from settings)
// export let isStreamingEnabled = true; // REMOVED - Always stream
export let isFilePluginEnabled = true;
export let isCalendarPluginEnabled = true;
export let isWebSearchPluginEnabled = true;
export let isWebSearchEnabled = false; // Toggle state for including web search in current message
export let isDeepResearchEnabled = false; // Toggle state for deep research mode
export let isImprovePromptEnabled = false; // <<< ADDED: Toggle state for improving the prompt before sending

// Tab and Note Mode states
export let currentTab = 'chat';
export let currentNoteMode = 'edit';

// Lists of saved items
export let savedChats = []; // Array of { id, name, last_updated_at }
export let savedNotes = []; // Array of { id, name, last_saved_at }
export let uploadedFiles = []; // Array of { id, filename, mimetype, filesize, has_summary, uploaded_at }

// Chat specific state
export let currentChatName = '';
export let currentChatModel = '';
export let chatHistory = []; // Array of { role, content, isError }
export let processingChatId = null; // ID of the chat currently waiting for backend response, or null
// --- NEW: Chat Mode State ---
export let currentChatMode = 'chat'; // 'chat' or 'deep_research'
// ----------------------------

// Note specific state
export let currentNoteName = ''; // Already exists, but adding for clarity
export let noteContent = '';

// Sidebar collapsed states
export let isSidebarCollapsed = false;
export let isPluginsCollapsed = false;
export let isNotesSidebarCollapsed = false; // Assuming a separate notes sidebar state
export let isNotesTocCollapsed = true; // TOC drawer state, default collapsed

// Note History State
export let noteHistory = []; // History entries for the currently selected note

// Voice Recording State
export let isRecording = false; // Whether audio is currently being recorded
export let recordingContext = null; // Context associated with the current recording (e.g., 'chat', 'note')
export let isSocketConnected = false; // WebSocket connection status for transcription
// --- REPLACED streamingTranscript & finalTranscriptSegment ---
export let finalizedTranscript = ""; // Holds the concatenated FINAL results for the current session
export let currentInterimTranscript = ""; // Holds the LATEST interim result
// -----------------------------------------------------------

// --- NEW: Long Recording State ---
export let isLongRecordingActive = false; // Tracks the non-streaming recording state
export let longRecordingToastId = null; // To manage the persistent recording toast
export let lastLongTranscript = ''; // Store the last successful long transcript
// ---------------------------------


// --- Observer Pattern ---
// Map to store listeners for different state change events
const listeners = new Map();
let notificationsEnabled = true; // Flag to control notifications

/**
 * Subscribes a listener function to a specific state change event.
 * @param {string} eventType - The type of state change (e.g., 'isLoading', 'chatHistory').
 * @param {function} listener - The function to call when the state changes.
 */
export function subscribe(eventType, listener) {
    if (!listeners.has(eventType)) {
        listeners.set(eventType, []);
    }
    listeners.get(eventType).push(listener);
}

/**
 * Notifies all listeners subscribed to a specific state change event.
 * @param {string} eventType - The type of state change.
 * @param {*} [data] - Optional data to pass to the listeners.
 */
function notify(eventType, data) {
    if (!notificationsEnabled) {
        return;
    }
    if (listeners.has(eventType)) {
        const eventListeners = listeners.get(eventType);
        eventListeners.forEach((listener, index) => {
            try {
                listener(data); // Pass data if provided
            } catch (error) {
                console.error(`Error in listener for event "${eventType}" (Listener ${index + 1}):`, error);
            }
        });
    }
}

export function setProcessingChatId(id) {
    if (processingChatId !== id) {
        processingChatId = id;
        notify('processingChatId', processingChatId);
    }
}
/**
 * Temporarily disables state change notifications.
 */
export function disableNotifications() {
    notificationsEnabled = false;
}

/**
 * Re-enables state change notifications.
 */
export function enableNotifications() {
    notificationsEnabled = true;
}

/**
 * Notifies all listeners for all current state values.
 * Useful for initial render after loading state.
 */
export function notifyAll() {
    // Explicitly notify for each state property that UI might depend on
    notify('currentChatId', currentChatId);
    notify('currentNoteId', currentNoteId);
    notify('isLoading', isLoading);
    notify('statusMessage', { message: statusMessage, isError: isErrorStatus });
    notify('sidebarSelectedFiles', sidebarSelectedFiles);
    notify('attachedFiles', attachedFiles);
    notify('sessionFile', sessionFile);
    notify('currentEditingFileId', currentEditingFileId);
    notify('summaryContent', summaryContent);
    notify('calendarContext', calendarContext);
    notify('isCalendarContextActive', isCalendarContextActive);
    // notify('isStreamingEnabled', isStreamingEnabled); // REMOVED
    notify('isFilePluginEnabled', isFilePluginEnabled);
    notify('isCalendarPluginEnabled', isCalendarPluginEnabled);
    notify('isWebSearchPluginEnabled', isWebSearchPluginEnabled);
    notify('isWebSearchEnabled', isWebSearchEnabled);
    notify('isDeepResearchEnabled', isDeepResearchEnabled); // Notify deep research state
    notify('isImprovePromptEnabled', isImprovePromptEnabled); // Notify improve prompt state
    notify('currentTab', currentTab);
    notify('currentNoteMode', currentNoteMode);
    notify('savedChats', savedChats);
    notify('savedNotes', savedNotes);
    notify('uploadedFiles', uploadedFiles);
    notify('currentChatName', currentChatName);
    notify('currentChatModel', currentChatModel);
    notify('chatHistory', chatHistory);
    notify('processingChatId', processingChatId); // Notify processing chat ID
    // --- NEW: Notify Chat Mode State ---
    notify('currentChatMode', currentChatMode);
    // ----------------------------------
    notify('noteContent', noteContent);
    notify('currentNoteName', currentNoteName);
    notify('isSidebarCollapsed', isSidebarCollapsed);
    notify('isPluginsCollapsed', isPluginsCollapsed);
    notify('isNotesSidebarCollapsed', isNotesSidebarCollapsed);
    notify('isNotesTocCollapsed', isNotesTocCollapsed); // Notify TOC drawer state
    notify('noteHistory', noteHistory);
    notify('isRecording', isRecording);
    notify('recordingContext', recordingContext);
    notify('isSocketConnected', isSocketConnected); // Notify socket status
    // --- Notify NEW transcript states ---
    notify('finalizedTranscript', finalizedTranscript);
    notify('currentInterimTranscript', currentInterimTranscript);
    // ----------------------------------
    // --- NEW: Notify long recording state ---
    notify('isLongRecordingActive', isLongRecordingActive);
    notify('longRecordingToastId', longRecordingToastId); // If UI needs to react to toast ID changes
    notify('lastLongTranscript', lastLongTranscript); // If UI needs to react to transcript changes
    // ---------------------------------------


    // Also notify combined states if listeners are subscribed to them
    notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode }); // Include mode in combined state
    notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    notify('pluginEnabled', 'all'); // Generic notification for any plugin state change

    // Notify combined states including deep research
    notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
}


// Functions to update state
// These functions modify the state variables *within* this module and notify listeners.

export function setCurrentChatId(id) {
    if (currentChatId !== id) {
        currentChatId = id;
        notify('currentChatId', currentChatId);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled }); // Notify combined chat state
    }
}

export function setCurrentNoteId(id) {
    if (currentNoteId !== id) {
        currentNoteId = id;
        notify('currentNoteId', currentNoteId);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent }); // Notify combined note state
    }
}

export function setIsLoading(loading) {
    if (isLoading !== loading) {
        isLoading = loading;
        // When loading starts, clear previous status unless it was an error
        if (loading && !isErrorStatus) {
            setStatusMessage("Busy..."); // This will notify 'statusMessage'
        } else if (!loading && !isErrorStatus && statusMessage === "Busy...") {
            // If loading finished without an explicit error status being set, revert to Idle
             setStatusMessage("Idle"); // This will notify 'statusMessage'
        }
        notify('isLoading', isLoading);
    }
}

export function setStatusMessage(message, isError = false) {
    if (statusMessage !== message || isErrorStatus !== isError) {
        statusMessage = message;
        isErrorStatus = isError;
        notify('statusMessage', { message: statusMessage, isError: isErrorStatus });
    }
}


// --- Functions for sidebarSelectedFiles ---
export function setSidebarSelectedFiles(files) {
    sidebarSelectedFiles = files;
    notify('sidebarSelectedFiles', sidebarSelectedFiles);
}

export function clearSidebarSelectedFiles() {
    if (sidebarSelectedFiles.length > 0) {
        sidebarSelectedFiles.length = 0;
        notify('sidebarSelectedFiles', sidebarSelectedFiles);
    }
}

export function addSidebarSelectedFile(file) {
    // Add the file if it's not already selected (check by id)
    if (!sidebarSelectedFiles.some(f => f.id === file.id)) {
        sidebarSelectedFiles.push(file);
        notify('sidebarSelectedFiles', sidebarSelectedFiles);
    }
}

export function removeSidebarSelectedFileById(fileId) {
     const initialLength = sidebarSelectedFiles.length;
     sidebarSelectedFiles = sidebarSelectedFiles.filter(f => f.id !== fileId);
     if (sidebarSelectedFiles.length !== initialLength) {
        notify('sidebarSelectedFiles', sidebarSelectedFiles);
     }
}

// --- Functions for attachedFiles (files attached to the chat session) ---
export function setAttachedFiles(files) {
    attachedFiles = files;
    notify('attachedFiles', attachedFiles);
}

export function clearAttachedFiles() {
    if (attachedFiles.length > 0) {
        attachedFiles.length = 0;
        notify('attachedFiles', attachedFiles);
    }
}

export function addAttachedFile(file) {
    // Add the file if it's not already attached (check by id and type)
    // Type is important here ('full' or 'summary')
    if (!attachedFiles.some(f => f.id === file.id && f.type === file.type)) {
        attachedFiles.push(file);
        notify('attachedFiles', attachedFiles);
    }
}

// Function to remove by ID and Type, to match the UI's remove button logic
export function removeAttachedFileByIdAndType(fileIdToRemove, fileTypeToRemove) {
    const initialLength = attachedFiles.length;
    attachedFiles = attachedFiles.filter(f => !(f.id === fileIdToRemove && f.type === fileTypeToRemove));
    if (attachedFiles.length !== initialLength) {
        notify('attachedFiles', attachedFiles);
    }
}

// Function to remove by ID (removes all types for that ID)
export function removeAttachedFileById(fileIdToRemove) {
     const initialLength = attachedFiles.length;
     attachedFiles = attachedFiles.filter(f => f.id !== fileIdToRemove);
     if (attachedFiles.length !== initialLength) {
        notify('attachedFiles', attachedFiles);
     }
}


// --- Function for sessionFile (file attached for the current message) ---
export function setSessionFile(file) {
    if (sessionFile !== file) { // Simple reference check
        sessionFile = file;
        notify('sessionFile', sessionFile);
    }
}


export function setCurrentEditingFileId(id) {
    if (currentEditingFileId !== id) {
        currentEditingFileId = id;
        notify('currentEditingFileId', currentEditingFileId);
    }
}

export function setSummaryContent(content) {
    if (summaryContent !== content) {
        summaryContent = content;
        notify('summaryContent', summaryContent);
    }
}


export function setCalendarContext(context) {
    if (calendarContext !== context) { // Simple reference check
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

// REMOVED setStreamingEnabled function

export function setFilePluginEnabled(enabled) {
    if (isFilePluginEnabled !== enabled) {
        isFilePluginEnabled = enabled;
        notify('isFilePluginEnabled', isFilePluginEnabled);
        notify('pluginEnabled', 'files'); // Notify generic plugin change
    }
}

export function setCalendarPluginEnabled(enabled) {
    if (isCalendarPluginEnabled !== enabled) {
        isCalendarPluginEnabled = enabled;
        notify('isCalendarPluginEnabled', isCalendarPluginEnabled);
        notify('pluginEnabled', 'calendar'); // Notify generic plugin change
    }
}

export function setWebSearchEnabled(enabled) {
    if (isWebSearchEnabled !== enabled) {
        isWebSearchEnabled = enabled;
        notify('isWebSearchEnabled', isWebSearchEnabled);
    }
}

export function setDeepResearchEnabled(enabled) {
    if (isDeepResearchEnabled !== enabled) {
        isDeepResearchEnabled = enabled;
        notify('isDeepResearchEnabled', isDeepResearchEnabled);
        // Also notify combined chat state
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    }
}


export function setWebSearchPluginEnabled(enabled) {
    if (isWebSearchPluginEnabled !== enabled) {
        isWebSearchPluginEnabled = enabled;
        notify('isWebSearchPluginEnabled', isWebSearchPluginEnabled);
        notify('pluginEnabled', 'websearch'); // Notify generic plugin change
    }
}


export function setCurrentTab(tab) {
    if (currentTab !== tab) {
        currentTab = tab;
        notify('currentTab', currentTab);
    }
}

export function setCurrentNoteMode(mode) {
    if (currentNoteMode !== mode) {
        currentNoteMode = mode;
        notify('currentNoteMode', currentNoteMode);
    }
}

// Add setter functions for saved lists
export function setSavedChats(chats) {
    savedChats = chats; // Assume chats array is new or represents a change
    notify('savedChats', savedChats);
}

export function setSavedNotes(notes) {
    savedNotes = notes; // Assume notes array is new or represents a change
    notify('savedNotes', savedNotes);
}

export function setUploadedFiles(files) {
    uploadedFiles = files; // Assume files array is new or represents a change
    notify('uploadedFiles', uploadedFiles);
}

// --- Chat History Functions ---
export function setChatHistory(history) {
    chatHistory = history; // Assume history array is new or represents a change
    notify('chatHistory', chatHistory);
}

export function addMessageToHistory(message) {
    chatHistory.push(message);
    // Notify that history has changed. Pass a copy or the new message if needed by listeners.
    // For simplicity, just notify that the array content changed.
    notify('chatHistory', chatHistory);
}

export function appendContentToLastMessage(content) {
    if (chatHistory.length > 0) {
        const lastMessage = chatHistory[chatHistory.length - 1];
        // Ensure it's an assistant message and not an error
        if (lastMessage.role === 'assistant' && !lastMessage.isError) {
             lastMessage.content += content;
             // Notify that history has changed.
             notify('chatHistory', chatHistory);
        }
    }
}

// --- Chat Details Functions ---
export function setCurrentChatName(name) {
    if (currentChatName !== name) {
        currentChatName = name;
        notify('currentChatName', currentChatName);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled }); // Notify combined chat state
    }
}

export function setCurrentChatModel(modelName) {
    if (currentChatModel !== modelName) {
        currentChatModel = modelName;
        notify('currentChatModel', currentChatModel);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled }); // Notify combined chat state
    }
}

// --- NEW: Improve Prompt Setter ---
export function setImprovePromptEnabled(enabled) {
    if (isImprovePromptEnabled !== enabled) {
        isImprovePromptEnabled = enabled;
        notify('isImprovePromptEnabled', isImprovePromptEnabled);
    }
}
// -----------------------------

// --- NEW: Chat Mode Setter ---
export function setCurrentChatMode(mode) {
    if (currentChatMode !== mode) {
        currentChatMode = mode;
        notify('currentChatMode', currentChatMode);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled }); // Notify combined chat state
    }
}
// -----------------------------

// --- Note Content Functions ---
export function setNoteContent(content) {
    if (noteContent !== content) {
        noteContent = content;
        notify('noteContent', noteContent);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent }); // Notify combined note state
    }
}

export function setCurrentNoteName(name) {
    if (currentNoteName !== name) {
        currentNoteName = name;
        notify('currentNoteName', currentNoteName);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent }); // Notify combined note state
    }
}

// --- Sidebar Collapsed State Functions ---
export function setIsSidebarCollapsed(isCollapsed) {
    if (isSidebarCollapsed !== isCollapsed) {
        isSidebarCollapsed = isCollapsed;
        notify('isSidebarCollapsed', isSidebarCollapsed);
    }
}

export function setIsPluginsCollapsed(isCollapsed) {
    if (isPluginsCollapsed !== isCollapsed) {
        isPluginsCollapsed = isCollapsed;
        notify('isPluginsCollapsed', isPluginsCollapsed);
    }
}

export function setIsNotesSidebarCollapsed(isCollapsed) {
    if (isNotesSidebarCollapsed !== isCollapsed) {
        isNotesSidebarCollapsed = isCollapsed;
        notify('isNotesSidebarCollapsed', isNotesSidebarCollapsed);
    }
}

// --- Notes TOC Drawer State ---
export function setIsNotesTocCollapsed(isCollapsed) {
    if (isNotesTocCollapsed !== isCollapsed) {
        isNotesTocCollapsed = isCollapsed;
        notify('isNotesTocCollapsed', isNotesTocCollapsed);
    }
}

// --- Note History State ---
export function setNoteHistory(history) {
    noteHistory = history; // Assume history array is new or represents a change
    notify('noteHistory', noteHistory);
}

// --- Recording State Functions ---
export function setIsRecording(recording, context = null) {
    if (isRecording !== recording) {
        isRecording = recording;
        recordingContext = recording ? context : null; // Set context only when starting
        notify('isRecording', isRecording);
        notify('recordingContext', recordingContext); // Notify context change as well
    }
}

export function setIsSocketConnected(connected) {
    if (isSocketConnected !== connected) {
        isSocketConnected = connected;
        notify('isSocketConnected', isSocketConnected);
    }
}

// --- REMOVED Old Transcript Setters ---
// export function setStreamingTranscript(transcript) { ... }
// export function appendStreamingTranscript(text) { ... }
// export function setFinalTranscriptSegment(text) { ... }
// ------------------------------------

// --- NEW: Setters for New Transcript State ---
export function setFinalizedTranscript(transcript) {
    if (finalizedTranscript !== transcript) {
        finalizedTranscript = transcript;
        notify('finalizedTranscript', finalizedTranscript);
    }
}

export function appendFinalizedTranscript(segment) {
    // Append with a space if the current finalized transcript isn't empty
    const separator = finalizedTranscript ? " " : "";
    finalizedTranscript += separator + segment;
    notify('finalizedTranscript', finalizedTranscript);
}

export function setCurrentInterimTranscript(transcript) {
     if (currentInterimTranscript !== transcript) {
        currentInterimTranscript = transcript;
        notify('currentInterimTranscript', currentInterimTranscript);
    }
}
// -----------------------------------------


// --- NEW: Function to get the appropriate input element based on context ---
export function getInputElementForContext(context) { // Add export keyword
    if (context === 'chat') {
        return elements.messageInput;
    } else if (context === 'notes') {
        return elements.notesTextarea;
    }
    return null;
}


// --- NEW: Long Recording State Functions ---
export function setIsLongRecordingActive(isActive) {
    if (isLongRecordingActive !== isActive) {
        isLongRecordingActive = isActive;
        notify('isLongRecordingActive', isLongRecordingActive);
    }
}

export function setLongRecordingToastId(toastId) {
    // No need to check for change, just set it and notify if needed
    longRecordingToastId = toastId;
    // notify('longRecordingToastId', longRecordingToastId); // Usually not needed to notify for this
}

export function setLastLongTranscript(transcript) {
    lastLongTranscript = transcript;
    notify('lastLongTranscript', lastLongTranscript); // Notify if UI needs to display this elsewhere
}
// -----------------------------------------
