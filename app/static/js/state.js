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
// These are files intended to be sent WITH the NEXT message.
export let attachedFiles = []; // Array of { id, filename, type ('full' or 'summary'), mimetype }
// File attached via paperclip for the current message only
export let sessionFile = null; // File object { filename, mimetype, content, name (same as filename) }
export let currentEditingFileId = null; // For summary modal
export let summaryContent = ""; // Content of the summary being edited

// State for the File Content Modal
export let isFileContentModalOpen = false;
export let currentViewingFileId = null;
export let currentViewingFilename = "";
export let currentViewingFileContent = ""; // Decoded text or base64 string
export let currentViewingFileMimetype = "";
export let currentViewingFileIsBase64 = false; // Flag if content is base64

export let calendarContext = null; // Loaded calendar events object { events: [], timestamp: ... }
export let isCalendarContextActive = false; // Toggle state for including calendar context

// Plugin enabled states (from settings)
export let isWebSearchEnabled = false; // Toggle state for including web search in current message
export let isDeepResearchEnabled = false; // Toggle state for deep research mode
export let isImprovePromptEnabled = false; // Toggle state for improving the prompt before sending

// Tab and Note Mode states
export let currentTab = 'chat';
export let currentNoteMode = 'edit';
export let currentNoteActiveH1SectionIndex = 0; // Index of the active H1 tab for the current note

// Lists of saved items
export let savedChats = []; // Array of { id, name, last_updated_at }
export let savedNotes = []; // Array of { id, name, last_saved_at }
export let uploadedFiles = []; // Array of { id, filename, mimetype, filesize, has_summary, uploaded_at }

// Chat specific state
export let currentChatName = '';
export let currentChatModel = '';
// chatHistory stores message objects. Each message object should now include an 'attachments' array
// if files were sent with that message.
// Example message object: { role, content, isError, attachments: [{filename, type, mimetype}, ...] }
export let chatHistory = [];
export let processingChatId = null; // ID of the chat currently waiting for backend response, or null
export let currentChatMode = 'chat'; // 'chat' or 'deep_research'

// Note specific state
export let currentNoteName = '';
export let noteContent = '';

// Sidebar collapsed states
export let isSidebarCollapsed = false;
export let isPluginsCollapsed = false;
export let isNotesSidebarCollapsed = false;
export let isNotesTocCollapsed = true;

// Note History State
export let noteHistory = [];

// Voice Recording State
export let isRecording = false;
export let recordingContext = null;
export let isSocketConnected = false;
export let finalizedTranscript = "";
export let currentInterimTranscript = "";

// Long Recording State
export let isLongRecordingActive = false;
export let longRecordingToastId = null;
export let lastLongTranscript = '';


// --- Observer Pattern ---
const listeners = new Map();
let notificationsEnabled = true;

export function subscribe(eventType, listener) {
    if (!listeners.has(eventType)) {
        listeners.set(eventType, []);
    }
    listeners.get(eventType).push(listener);
}

function notify(eventType, data) {
    if (!notificationsEnabled) {
        return;
    }
    if (listeners.has(eventType)) {
        const eventListeners = listeners.get(eventType);
        eventListeners.forEach((listener, index) => {
            try {
                listener(data);
            } catch (error) {
                console.error(`Error in listener for event "${eventType}" (Listener ${index + 1}):`, error);
            }
        });
    }
}

export function disableNotifications() {
    notificationsEnabled = false;
}

export function enableNotifications() {
    notificationsEnabled = true;
}

export function notifyAll() {
    notify('currentChatId', currentChatId);
    notify('currentNoteId', currentNoteId);
    notify('isLoading', isLoading);
    notify('statusMessage', { message: statusMessage, isError: isErrorStatus });
    notify('sidebarSelectedFiles', sidebarSelectedFiles);
    notify('attachedFiles', attachedFiles); // For input area display
    notify('sessionFile', sessionFile);     // For input area display
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
    notify('currentNoteMode', currentNoteMode);
    notify('savedChats', savedChats);
    notify('savedNotes', savedNotes);
    notify('uploadedFiles', uploadedFiles);
    notify('currentChatName', currentChatName);
    notify('currentChatModel', currentChatModel);
    notify('chatHistory', chatHistory); // For chat display
    notify('processingChatId', processingChatId);
    notify('currentChatMode', currentChatMode);
    notify('noteContent', noteContent);
    notify('currentNoteName', currentNoteName);
    notify('isSidebarCollapsed', isSidebarCollapsed);
    notify('isPluginsCollapsed', isPluginsCollapsed);
    notify('isNotesSidebarCollapsed', isNotesSidebarCollapsed);
    notify('isNotesTocCollapsed', isNotesTocCollapsed);
    notify('noteHistory', noteHistory);
    notify('isRecording', isRecording);
    notify('recordingContext', recordingContext);
    notify('isSocketConnected', isSocketConnected);
    notify('finalizedTranscript', finalizedTranscript);
    notify('currentInterimTranscript', currentInterimTranscript);
    notify('isLongRecordingActive', isLongRecordingActive);
    notify('longRecordingToastId', longRecordingToastId);
    notify('lastLongTranscript', lastLongTranscript);
    notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    notify('pluginEnabled', 'all');
    notify('currentNoteActiveH1SectionIndex', currentNoteActiveH1SectionIndex);
}


// --- State Update Functions ---

export function setCurrentChatId(id) {
    if (currentChatId !== id) {
        currentChatId = id;
        notify('currentChatId', currentChatId);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    }
}

export function setCurrentNoteId(id) {
    if (currentNoteId !== id) {
        currentNoteId = id;
        setCurrentNoteActiveH1SectionIndex(0);
        notify('currentNoteId', currentNoteId);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    } else if (id === null && currentNoteId !== null) {
        setCurrentNoteActiveH1SectionIndex(0);
    }
}

export function setIsLoading(loading) {
    if (isLoading !== loading) {
        isLoading = loading;
        if (loading && !isErrorStatus) {
            setStatusMessage("Busy...");
        } else if (!loading && !isErrorStatus && statusMessage === "Busy...") {
             setStatusMessage("Idle");
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

export function setProcessingChatId(id) {
    if (processingChatId !== id) {
        processingChatId = id;
        notify('processingChatId', processingChatId);
    }
}

// --- Sidebar Selected Files (for potential attachment) ---
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

// --- Attached Files (staged for the *next* message) ---
export function setAttachedFiles(files) {
    attachedFiles = files;
    notify('attachedFiles', attachedFiles);
}

export function clearAttachedFiles() {
    if (attachedFiles.length > 0) {
        attachedFiles.length = 0; // Modifies in place
        notify('attachedFiles', attachedFiles);
    }
}

export function addAttachedFile(file) {
    if (!attachedFiles.some(f => f.id === file.id && f.type === file.type)) {
        attachedFiles.push(file);
        notify('attachedFiles', attachedFiles);
    }
}

export function removeAttachedFileByIdAndType(fileIdToRemove, fileTypeToRemove) {
    const initialLength = attachedFiles.length;
    attachedFiles = attachedFiles.filter(f => !(f.id === fileIdToRemove && f.type === fileTypeToRemove));
    if (attachedFiles.length !== initialLength) {
        notify('attachedFiles', attachedFiles);
    }
}

export function removeAttachedFileById(fileIdToRemove) {
     const initialLength = attachedFiles.length;
     attachedFiles = attachedFiles.filter(f => f.id !== fileIdToRemove);
     if (attachedFiles.length !== initialLength) {
        notify('attachedFiles', attachedFiles);
     }
}

// --- Session File (single file from paperclip for *next* message) ---
export function setSessionFile(file) {
    if (sessionFile !== file) {
        sessionFile = file;
        notify('sessionFile', sessionFile);
    }
}

// --- NEW: Clear all attachments staged for the next message ---
// This should be called by the message sending logic *after* the message
// (and its attachments) have been processed and added to chatHistory.
export function clearAllCurrentMessageAttachments() { // <<< ADDED export
    setSessionFile(null);    // Notifies 'sessionFile'
    clearAttachedFiles();    // Notifies 'attachedFiles'
}
// --- END NEW ---

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

// --- File Content Modal State Functions ---
export function setIsFileContentModalOpen(isOpen) {
    if (isFileContentModalOpen !== isOpen) {
        isFileContentModalOpen = isOpen;
        notify('isFileContentModalOpen', isFileContentModalOpen);
    }
}

export function setCurrentViewingFile(fileId, filename, content, mimetype, isBase64) {
    if (currentViewingFileId !== fileId || currentViewingFilename !== filename ||
        currentViewingFileContent !== content || currentViewingFileMimetype !== mimetype ||
        currentViewingFileIsBase64 !== isBase64) {
        currentViewingFileId = fileId;
        currentViewingFilename = filename;
        currentViewingFileContent = content;
        currentViewingFileMimetype = mimetype;
        currentViewingFileIsBase64 = isBase64;
        notify('currentViewingFileId', currentViewingFileId); // Notify individually for granular updates
        notify('currentViewingFilename', currentViewingFilename);
        notify('currentViewingFileContent', currentViewingFileContent);
        notify('currentViewingFileMimetype', currentViewingFileMimetype);
        notify('currentViewingFileIsBase64', currentViewingFileIsBase64);
    }
}

export function clearCurrentViewingFile() {
    if (currentViewingFileId !== null) {
        currentViewingFileId = null;
        currentViewingFilename = "";
        currentViewingFileContent = "";
        currentViewingFileMimetype = "";
        currentViewingFileIsBase64 = false;
        notify('currentViewingFileId', currentViewingFileId);
        notify('currentViewingFilename', currentViewingFilename);
        notify('currentViewingFileContent', currentViewingFileContent);
        notify('currentViewingFileMimetype', currentViewingFileMimetype);
        notify('currentViewingFileIsBase64', currentViewingFileIsBase64);
    }
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
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
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

export function setSavedChats(chats) {
    savedChats = chats;
    notify('savedChats', savedChats);
}

export function setSavedNotes(notes) {
    savedNotes = notes;
    notify('savedNotes', savedNotes);
}

export function setUploadedFiles(files) {
    uploadedFiles = files;
    notify('uploadedFiles', uploadedFiles);
}

// --- Chat History Functions ---
// The 'message' object passed to addMessageToHistory should be prepared by the caller.
// It MUST include: { role, content, attachments: [], rawContent (optional), isError (optional) }
// 'attachments' is an array of file objects {filename, type, mimetype} that were sent with THIS message.
export function addMessageToHistory(message) {
    chatHistory.push(message);
    notify('chatHistory', chatHistory);
}

export function setChatHistory(history) {
    chatHistory = history;
    notify('chatHistory', chatHistory);
}

export function appendContentToLastMessage(content) {
    if (chatHistory.length > 0) {
        const lastMessage = chatHistory[chatHistory.length - 1];
        if (lastMessage.role === 'assistant' && !lastMessage.isError) {
             lastMessage.content += content;
             notify('chatHistory', chatHistory);
        }
    }
}

// --- Chat Details Functions ---
export function setCurrentChatName(name) {
    if (currentChatName !== name) {
        currentChatName = name;
        notify('currentChatName', currentChatName);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    }
}

export function setCurrentChatModel(modelName) {
    if (currentChatModel !== modelName) {
        currentChatModel = modelName;
        notify('currentChatModel', currentChatModel);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    }
}

export function setImprovePromptEnabled(enabled) {
    if (isImprovePromptEnabled !== enabled) {
        isImprovePromptEnabled = enabled;
        notify('isImprovePromptEnabled', isImprovePromptEnabled);
    }
}

export function setCurrentChatMode(mode) {
    if (currentChatMode !== mode) {
        currentChatMode = mode;
        notify('currentChatMode', currentChatMode);
        notify('currentChat', { id: currentChatId, name: currentChatName, model: currentChatModel, mode: currentChatMode, deepResearch: isDeepResearchEnabled });
    }
}

export function setCurrentNoteActiveH1SectionIndex(index) {
    if (currentNoteActiveH1SectionIndex !== index) {
        currentNoteActiveH1SectionIndex = index;
        notify('currentNoteActiveH1SectionIndex', currentNoteActiveH1SectionIndex);
    }
}

// --- Note Content Functions ---
export function setNoteContent(content) {
    if (noteContent !== content) {
        noteContent = content;
        notify('noteContent', noteContent);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
    }
}

export function setCurrentNoteName(name) {
    if (currentNoteName !== name) {
        currentNoteName = name;
        notify('currentNoteName', currentNoteName);
        notify('currentNote', { id: currentNoteId, name: currentNoteName, content: noteContent });
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

export function setIsNotesTocCollapsed(isCollapsed) {
    if (isNotesTocCollapsed !== isCollapsed) {
        isNotesTocCollapsed = isCollapsed;
        notify('isNotesTocCollapsed', isNotesTocCollapsed);
    }
}

// --- Note History State ---
export function setNoteHistory(history) {
    noteHistory = history;
    notify('noteHistory', noteHistory);
}

// --- Recording State Functions ---
export function setIsRecording(recording, context = null) {
    if (isRecording !== recording) {
        isRecording = recording;
        recordingContext = recording ? context : null;
        notify('isRecording', isRecording);
        notify('recordingContext', recordingContext);
    }
}

export function setIsSocketConnected(connected) {
    if (isSocketConnected !== connected) {
        isSocketConnected = connected;
        notify('isSocketConnected', isSocketConnected);
    }
}

export function setFinalizedTranscript(transcript) {
    if (finalizedTranscript !== transcript) {
        finalizedTranscript = transcript;
        notify('finalizedTranscript', finalizedTranscript);
    }
}

export function appendFinalizedTranscript(segment) {
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

export function getInputElementForContext(context) {
    if (context === 'chat') {
        return elements.messageInput;
    } else if (context === 'notes') {
        return elements.notesTextarea;
    }
    return null;
}

// --- Long Recording State Functions ---
export function setIsLongRecordingActive(isActive) {
    if (isLongRecordingActive !== isActive) {
        isLongRecordingActive = isActive;
        notify('isLongRecordingActive', isLongRecordingActive);
    }
}

export function setLongRecordingToastId(toastId) {
    longRecordingToastId = toastId;
}

export function setLastLongTranscript(transcript) {
    lastLongTranscript = transcript;
    notify('lastLongTranscript', lastLongTranscript);
}
