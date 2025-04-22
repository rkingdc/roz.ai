// js/state.js

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
export let attachedFiles = [];
// File attached via paperclip for the current message only
export let sessionFile = null; // File object { filename, mimetype, content }
export let currentEditingFileId = null; // For summary modal

export let calendarContext = null; // Loaded calendar events
export let isCalendarContextActive = false; // Toggle state for including calendar context

// Plugin enabled states (from settings)
export let isStreamingEnabled = true;
export let isFilePluginEnabled = true;
export let isCalendarPluginEnabled = true;
export let isWebSearchPluginEnabled = true;

// Tab and Note Mode states
export let currentTab = 'chat';
export let currentNoteMode = 'edit';

// Lists of saved items
export let savedChats = [];
export let savedNotes = [];
export let uploadedFiles = []; // List of files from the backend


// Functions to update state
// These functions modify the state variables *within* this module.

export function setCurrentChatId(id) {
    currentChatId = id;
}

export function setCurrentNoteId(id) {
    currentNoteId = id;
}

export function setIsLoading(loading) {
    isLoading = loading;
    // When loading starts, clear previous status unless it was an error
    if (loading && !isErrorStatus) {
        setStatusMessage("Busy...");
    } else if (!loading && !isErrorStatus) {
        // If loading finished without an explicit error status being set, revert to Idle
         setStatusMessage("Idle");
    }
    // Note: updateStatus UI function will read these state variables
}

export function setStatusMessage(message, isError = false) {
    statusMessage = message;
    isErrorStatus = isError;
    // Note: updateStatus UI function will read these state variables
}


// --- Functions for sidebarSelectedFiles ---
export function setSidebarSelectedFiles(files) {
    // This function is intended to replace the entire array
    sidebarSelectedFiles = files;
}

export function clearSidebarSelectedFiles() {
    // Mutate the array in place
    sidebarSelectedFiles.length = 0;
}

export function addSidebarSelectedFile(file) {
    // Add the file if it's not already selected (check by id)
    if (!sidebarSelectedFiles.some(f => f.id === file.id)) {
        sidebarSelectedFiles.push(file);
    }
}

export function removeSidebarSelectedFileById(fileId) {
     // Reassign the array after filtering
     sidebarSelectedFiles = sidebarSelectedFiles.filter(f => f.id !== fileId);
}

// --- Functions for attachedFiles (files attached to the chat session) ---
export function setAttachedFiles(files) {
    // This function is intended to replace the entire array
    attachedFiles = files;
}

export function clearAttachedFiles() {
    // Mutate the array in place
    attachedFiles.length = 0;
}

export function addAttachedFile(file) {
    // Add the file if it's not already attached (check by id and type)
    // Type is important here ('full' or 'summary')
    if (!attachedFiles.some(f => f.id === file.id && f.type === file.type)) {
        attachedFiles.push(file);
    }
}

// Function to remove by ID and Type, to match the UI's remove button logic
export function removeAttachedFileByIdAndType(fileIdToRemove, fileTypeToRemove) {
    attachedFiles = attachedFiles.filter(f => !(f.id === fileIdToRemove && f.type === fileTypeToRemove));
}


// --- Function for sessionFile (file attached for the current message) ---
export function setSessionFile(file) {
    sessionFile = file;
}


export function setCurrentEditingFileId(id) {
    currentEditingFileId = id;
}

export function setCalendarContext(context) {
    calendarContext = context;
}

export function setCalendarContextActive(active) {
    isCalendarContextActive = active;
}

export function setStreamingEnabled(enabled) {
    isStreamingEnabled = enabled;
}

export function setFilePluginEnabled(enabled) {
    isFilePluginEnabled = enabled;
}

export function setCalendarPluginEnabled(enabled) {
    isCalendarPluginEnabled = enabled;
}

export function setWebSearchPluginEnabled(enabled) {
    isWebSearchPluginEnabled = enabled;
}

export function setCurrentTab(tab) {
    currentTab = tab;
}

export function setCurrentNoteMode(mode) {
    currentNoteMode = mode;
}

// Add setter functions for saved lists
export function setSavedChats(chats) {
    savedChats = chats;
}

export function setSavedNotes(notes) {
    savedNotes = notes;
}

export function setUploadedFiles(files) {
    uploadedFiles = files;
}
