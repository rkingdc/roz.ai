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

// Functions to update state (optional, alternative is direct modification via export let)
// It's often cleaner to manage state changes via functions if logic is complex.
// For simple assignments, direct modification might be okay for smaller projects.

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
    selectedFiles = files;
}
export function clearSelectedFiles() {
    selectedFiles = [];
}
export function addSelectedFile(file) {
    // Remove existing first to avoid duplicates if re-attaching
    selectedFiles = selectedFiles.filter(f => f.id !== file.id);
    selectedFiles.push(file);
}
export function removeSelectedFileById(fileId) {
     selectedFiles = selectedFiles.filter(f => f.id !== fileId);
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
