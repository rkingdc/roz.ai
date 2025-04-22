// js/state.js

// Application State Variables
// Use 'export let' to allow them to be reassigned by other modules
export let currentChatId = null;
export let currentNoteId = null;
export let isLoading = false;
export let selectedFiles = []; // Files selected for attachment (plugin files)
export let sessionFile = null; // File attached via paperclip for the current session only
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

export function setSelectedFiles(files) {
    // This function is intended to replace the entire array
    selectedFiles = files;
}

export function clearSelectedFiles() {
    // Mutate the array in place
    selectedFiles.length = 0;
}

export function addSelectedFile(file) {
    // Remove existing file with the same ID first (handles updates or re-adding)
    selectedFiles = selectedFiles.filter(f => f.id !== file.id);
    // Add the new file
    selectedFiles.push(file);
}

export function removeSelectedFileById(fileId) {
     // Reassign the array after filtering
     selectedFiles = selectedFiles.filter(f => f.id !== fileId);
}

/** Removes the session file entry from the selectedFiles array. */
export function removeSessionFileFromSelected() {
    // Reassign the array after filtering out the session file
    selectedFiles = selectedFiles.filter(f => f.type !== 'session');
}


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
