// js/state.js

// Application State Variables
// Use 'export let' to allow them to be reassigned by other modules
export let currentChatId = null;
export let currentNoteId = null;
export let isLoading = false;
// Renamed selectedFiles to sidebarSelectedFiles for temporary selection in sidebar
export let sidebarSelectedFiles = []; // Files temporarily selected in the sidebar for attachment
export let attachedFiles = []; // Files permanently attached to the current chat session
export let sessionFile = null; // File attached via paperclip for the current message only
export let currentEditingFileId = null; // For summary modal
export let calendarContext = null;
export let isCalendarContextActive = false;
export let isStreamingEnabled = true;
export let isFilePluginEnabled = true;
export let isCalendarPluginEnabled = true;
export let isWebSearchPluginEnabled = true;
export let currentTab = 'chat';
export let currentNoteMode = 'edit';
export let savedChats = []; // Add state variable for saved chats list
export let savedNotes = []; // Add state variable for saved notes list


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
    // Add the file if it's not already selected
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
    if (!attachedFiles.some(f => f.id === file.id && f.type === file.type)) {
        attachedFiles.push(file);
    }
}

export function removeAttachedFileById(fileId) {
     // Reassign the array after filtering
     attachedFiles = attachedFiles.filter(f => f.id !== fileId);
}


// --- Function for sessionFile ---
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
