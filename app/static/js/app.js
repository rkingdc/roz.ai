// js/app.js - Main Application Entry Point

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
    ui.updateStatus("Initializing application...");
    // Don't set loading state here, let the specific load functions handle it if needed initially
    // ui.setLoadingState(true, "Initializing");

    try {
        // --- Load and Set Initial States from localStorage ---
        loadPersistedStates();
        console.log("[DEBUG] Persisted states loaded.");

        // --- Configure Marked.js ---
        if (typeof marked !== 'undefined') {
             marked.setOptions(config.markedOptions);
             console.log("[DEBUG] Marked.js options set globally.");
        } else {
             console.error("Marked.js library not found!");
             ui.updateStatus("Error: Markdown library not loaded.", true);
             // Potentially disable markdown features or show a more prominent error
        }


        // --- Apply Initial UI States ---
        ui.setSidebarCollapsed(elements.sidebar, elements.sidebarToggleButton, localStorage.getItem(config.SIDEBAR_COLLAPSED_KEY) === 'true', config.SIDEBAR_COLLAPSED_KEY, 'sidebar');
        ui.setSidebarCollapsed(elements.pluginsSidebar, elements.pluginsToggleButton, localStorage.getItem(config.PLUGINS_COLLAPSED_KEY) === 'true', config.PLUGINS_COLLAPSED_KEY, 'plugins');
        ui.setPluginSectionCollapsed(elements.filePluginHeader, elements.filePluginContent, localStorage.getItem(config.FILE_PLUGIN_COLLAPSED_KEY) === 'true', config.FILE_PLUGIN_COLLAPSED_KEY);
        ui.setPluginSectionCollapsed(elements.calendarPluginHeader, elements.calendarPluginContent, localStorage.getItem(config.CALENDAR_PLUGIN_COLLAPSED_KEY) === 'true', config.CALENDAR_PLUGIN_COLLAPSED_KEY);
        ui.updatePluginUI(); // Update visibility based on loaded plugin enabled states
        console.log("[DEBUG] Initial UI states applied.");

        // --- Load Core Data (Chat & Note Lists) ---
        // These are needed regardless of the initial tab
        await api.loadSavedChats();
        console.log("[DEBUG] loadSavedChats completed in initializeApp.");
        await api.loadSavedNotes();
        console.log("[DEBUG] loadSavedNotes completed in initializeApp.");

        // --- Switch to Initial Tab and Load its Data ---
        // switchTab handles loading the specific chat/note data and setting final loading state
        await ui.switchTab(state.currentTab); // Load data based on the persisted tab

        console.log("[DEBUG] initializeApp finished successfully.");
        // Final status is set by switchTab or its sub-functions

    } catch (error) {
        console.error('FATAL Error during application initialization:', error);
        ui.addMessage('system', `[Fatal Error during initialization: ${error.message}. Please check console.]`, true);
        ui.updateStatus("Initialization failed.", true);
        // setLoadingState(false) should be handled by the finally block of the function that threw
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

    // Load current IDs (will be used by switchTab/loadInitialData)
    const persistedChatId = localStorage.getItem('currentChatId'); // Assuming you save this key
    state.setCurrentChatId(persistedChatId ? parseInt(persistedChatId) : null); // You need to save currentChatId somewhere (e.g., in loadChat)
    const persistedNoteId = localStorage.getItem(config.CURRENT_NOTE_ID_KEY);
    state.setCurrentNoteId(persistedNoteId ? parseInt(persistedNoteId) : null);

    // Load note mode
    const persistedNoteMode = localStorage.getItem(config.CURRENT_NOTE_MODE_KEY);
    state.setCurrentNoteMode((persistedNoteMode === 'edit' || persistedNoteMode === 'view') ? persistedNoteMode : 'edit');

    // Update settings modal toggles to reflect loaded state
    if(elements.streamingToggle) elements.streamingToggle.checked = state.isStreamingEnabled;
    if(elements.filesPluginToggle) elements.filesPluginToggle.checked = state.isFilePluginEnabled;
    if(elements.calendarPluginToggle) elements.calendarPluginToggle.checked = state.isCalendarPluginEnabled;
    if(elements.webSearchPluginToggle) elements.webSearchPluginToggle.checked = state.isWebSearchPluginEnabled;
    if(elements.calendarToggle) elements.calendarToggle.checked = state.isCalendarContextActive;
}


// --- Wait for the DOM to be fully loaded ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // 1. Get references to all DOM elements and store them
    populateElements();
    console.log("DOM elements populated.");

    // 2. Set up all event listeners
    setupEventListeners();

    // 3. Initialize the application state and load initial data
    initializeApp();
});
