// js/app.js - Main Application Entry Point
// This module initializes the application, sets up event listeners,
// loads initial data, and triggers the initial UI render.

import { elements, populateElements } from './dom.js';
import * as state from './state.js';
import * as ui from './ui.js';
import * as api from './api.js';
import * as config from './config.js';
import { setupEventListeners } from './eventListeners.js';

/**
 * Initializes the application on page load.
 */
async function initializeApp() {
    console.log("[DEBUG] initializeApp called.");
    // Initial status update handled by ui.updateStatus which reads state.statusMessage
    // ui.updateStatus("Initializing application..."); // Removed direct call

    try {
        // --- Load and Set Initial States from localStorage ---
        // Temporarily disable notifications during initial state load
        state.disableNotifications();
        loadPersistedStates(); // Updates state
        state.enableNotifications(); // Re-enable notifications
        console.log("[DEBUG] Persisted states loaded.");

        // --- Configure Marked.js ---
        if (typeof marked !== 'undefined') {
             marked.setOptions(config.markedOptions);
             console.log("[DEBUG] Marked.js options set globally.");
        } else {
             console.error("Marked.js library not found!");
             state.setStatusMessage("Error: Markdown library not loaded.", true); // Update state
             // UI will react to statusMessage state change
        }

        // --- Load Core Data (Chat & Note Lists, then specific Chat/Note) ---
        // These API calls update the state.
        await api.loadSavedChats(); // Updates state.savedChats, isLoading, statusMessage
        // UI will react to state.savedChats change (renderSavedChats)
        await api.loadSavedNotes(); // Updates state.savedNotes, isLoading, statusMessage
        // UI will react to state.savedNotes change (renderSavedNotes)

        // Load data for the initial tab based on persisted ID or default
        if (state.currentTab === 'chat') {
             await api.loadInitialChatData(); // Updates state (currentChatId, chatHistory, attachedFiles, uploadedFiles, etc.)
             // UI will react to these state changes (handleStateChange_currentChat, handleStateChange_uploadedFiles, etc.)
        } else { // state.currentTab === 'notes'
             await api.loadInitialNotesData(); // Updates state (currentNoteId, noteContent, uploadedFiles, etc.)
             // UI will react to these state changes (handleStateChange_currentNote, handleStateChange_uploadedFiles, etc.)
        }

        // --- Final Initial UI Render ---
        // After all initial data is loaded into state, trigger the full UI render for the active tab.
        // This will render the UI based on the state populated by loadPersistedStates and initial data loads.
        // We notify all state changes that happened while notifications were disabled.
        state.notifyAll(); // Trigger UI updates for all state that changed during loading

        console.log("[DEBUG] initializeApp finished successfully.");
        // Final status is set by the last API call or loadInitialData
        // ui.updateStatus("Idle"); // Removed direct call
    } catch (error) {
        console.error('FATAL Error during application initialization:', error);
        state.setStatusMessage(`Fatal Error during initialization: ${error.message}. Please check console.`, true); // Update state
        // UI will react to statusMessage state change
        // ui.addMessage('system', `[Fatal Error during initialization: ${error.message}. Please check console.]`, true); // Removed direct call
        // ui.updateStatus("Initialization failed.", true); // Removed direct call
    }
    // No finally block needed here as sub-functions handle their own loading state
}

/** Loads persisted state values from localStorage into the state module */
function loadPersistedStates() {
    // Load simple boolean/string states
    state.setCalendarContextActive(localStorage.getItem('calendarContextActive') === 'true');
    state.setStreamingEnabled(localStorage.getItem(config.STREAMING_ENABLED_KEY) === null ? true : localStorage.getItem(config.STREAMING_ENABLED_KEY) === 'true');
    state.setFilePluginEnabled(localStorage.getItem(config.FILES_PLUGIN_ENABLED_KEY) === null ? true : localStorage.getItem(config.FILES_PLUGIN_ENABLED_KEY) === 'true');
    state.setCalendarPluginEnabled(localStorage.getItem(config.CALENDAR_PLUGIN_ENABLED_KEY) === null ? true : localStorage.getItem(config.CALENDAR_PLUGIN_ENABLED_KEY) === 'true');
    state.setWebSearchPluginEnabled(localStorage.getItem(config.WEB_SEARCH_PLUGIN_ENABLED_KEY) === null ? true : localStorage.getItem(config.WEB_SEARCH_PLUGIN_ENABLED_KEY) === 'true');

    // Load initial tab
    const storedTab = localStorage.getItem(config.ACTIVE_TAB_KEY);
    state.setCurrentTab((storedTab === 'chat' || storedTab === 'notes') ? storedTab : 'chat');

    // Load current IDs (will be used by loadInitialData)
    const persistedChatId = localStorage.getItem('currentChatId');
    state.setCurrentChatId(persistedChatId ? parseInt(persistedChatId) : null);
    const persistedNoteId = localStorage.getItem(config.CURRENT_NOTE_ID_KEY);
    state.setCurrentNoteId(persistedNoteId ? parseInt(persistedNoteId) : null);

    // Load note mode
    const persistedNoteMode = localStorage.getItem(config.CURRENT_NOTE_MODE_KEY);
    state.setCurrentNoteMode((persistedNoteMode === 'edit' || persistedNoteMode === 'view') ? persistedNoteMode : 'edit');

    // Load web search toggle state
    state.setWebSearchEnabled(localStorage.getItem('webSearchEnabled') === 'true'); // Assuming you persist this
}


// --- Wait for the DOM to be fully loaded ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // 1. Get references to all DOM elements and store them
    populateElements();
    console.log("DOM elements populated.");

    // 2. Set up all event listeners (which includes subscribing UI to state changes)
    setupEventListeners();

    // 3. Initialize the application state and load initial data
    initializeApp();
});
