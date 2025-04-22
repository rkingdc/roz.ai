// js/app.js - Main Application Entry Point
// This module initializes the application, sets up event listeners,
// loads initial data, and triggers the initial UI render.

import { elements, populateElements } from './dom.js';
import * as state from './state.js';
import * as ui from './ui.js';
import * as api from './api.js';
import * as config from './config.js'; // Import config
import { setupEventListeners } from './eventListeners.js';

/**
 * Initializes the application on page load.
 */
async function initializeApp() {
    console.log("[DEBUG] initializeApp called.");
    // Initial status update handled by ui.updateStatus which reads state.statusMessage
    // ui.updateStatus("Initializing application..."); // Removed direct call

    try {
        // 1. Get references to all DOM elements and store them
        populateElements();
        console.log("DOM elements populated.");

        // --- Load and Set Initial States from localStorage ---
        // Temporarily disable notifications during initial state load
        state.disableNotifications();
        loadPersistedStates(); // Updates state (non-UI related)
        // UI-related collapsed states are loaded after elements are populated
        loadCollapsedStates(); // Updates state and UI for collapsed elements
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

        // --- Set up all event listeners (which includes subscribing UI to state changes) ---
        setupEventListeners();
        console.log("Event listeners set up.");


        // --- Load Core Data (Chat & Note Lists, then specific Chat/Note) ---
        // These API calls update the state.
        await api.loadSavedChats(); // Corrected function name based on api.js - Updates state.savedChats, isLoading, statusMessage
        // UI will react to state.savedChats change (renderSavedChats)
        await api.loadSavedNotes(); // Corrected function name based on api.js - Updates state.savedNotes, isLoading, statusMessage
        // UI will react to state.savedNotes change (renderSavedNotes)

        // Load data for the initial tab based on persisted ID or default
        if (state.currentTab === 'chat') { // Use getter
             await api.loadInitialChatData(); // Updates state (currentChatId, chatHistory, attachedFiles, uploadedFiles, etc.)
             // UI updates triggered by state changes within loadInitialChatData (loadChat, startNewChat)
        } else { // state.currentTab === 'notes' // Use getter
             await api.loadInitialNotesData(); // Updates state (currentNoteId, noteContent, uploadedFiles, etc.)
             // UI updates triggered by state changes within loadInitialNotesData (loadNote, startNewNote)
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
    // --- CHANGE DEFAULT FOR CALENDAR PLUGIN FROM FALSE TO TRUE ---
    state.setCalendarPluginEnabled(localStorage.getItem(config.CALENDAR_PLUGIN_ENABLED_KEY) === null ? true : localStorage.getItem(config.CALENDAR_PLUGIN_ENABLED_KEY) === 'true');
    // ------------------------------------------------------------
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

    // Collapsed states are handled by loadCollapsedStates after elements are populated
}

// Helper function to load collapsed states after elements are populated
function loadCollapsedStates() {
    if (!elements.sidebar || !elements.sidebarToggleButton || !elements.pluginsSidebar || !elements.pluginsToggleButton ||
        !elements.filePluginHeader || !elements.filePluginContent || !elements.calendarPluginHeader || !elements.calendarPluginContent ||
        !elements.historyPluginHeader || !elements.historyPluginContent) { // Added history elements
        console.warn("Missing elements for loading collapsed states.");
        return;
    }

    // Load sidebar collapsed state
    const sidebarCollapsed = localStorage.getItem(config.SIDEBAR_COLLAPSED_KEY) === 'collapsed';
    ui.setSidebarCollapsed(elements.sidebar, elements.sidebarToggleButton, sidebarCollapsed, config.SIDEBAR_COLLAPSED_KEY, 'sidebar');
    // state.setIsSidebarCollapsed is now called inside ui.setSidebarCollapsed

    // Load plugins sidebar collapsed state
    const pluginsCollapsed = localStorage.getItem(config.PLUGINS_COLLAPSED_KEY) === 'collapsed';
    ui.setSidebarCollapsed(elements.pluginsSidebar, elements.pluginsToggleButton, pluginsCollapsed, config.PLUGINS_COLLAPSED_KEY, 'plugins');
    // state.setIsPluginsCollapsed is now called inside ui.setSidebarCollapsed

    // Load plugin section collapsed states
    const filePluginCollapsed = localStorage.getItem(config.FILE_PLUGIN_COLLAPSED_KEY) === 'collapsed';
    ui.setPluginSectionCollapsed(elements.filePluginHeader, elements.filePluginContent, filePluginCollapsed, config.FILE_PLUGIN_COLLAPSED_KEY);

    const calendarPluginCollapsed = localStorage.getItem(config.CALENDAR_PLUGIN_COLLAPSED_KEY) === 'collapsed';
    ui.setPluginSectionCollapsed(elements.calendarPluginHeader, elements.calendarPluginContent, calendarPluginCollapsed, config.CALENDAR_PLUGIN_COLLAPSED_KEY);

    // Load history plugin collapsed state
    const historyPluginCollapsed = localStorage.getItem(config.HISTORY_PLUGIN_COLLAPSED_KEY) === 'collapsed';
    ui.setPluginSectionCollapsed(elements.historyPluginHeader, elements.historyPluginContent, historyPluginCollapsed, config.HISTORY_PLUGIN_COLLAPSED_KEY);

    // Note: Web Search plugin section is not collapsible in the current HTML
}


// --- Wait for the DOM to be fully loaded ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // 1. Get references to all DOM elements and store them
    populateElements();
    console.log("DOM elements populated.");

    // 2. Load persisted UI states that depend on elements existing (collapsed states)
    loadCollapsedStates();
    console.log("Collapsed states loaded.");


    // 3. Set up all event listeners (which includes subscribing UI to state changes)
    setupEventListeners();

    // 4. Initialize the application state and load initial data
    initializeApp();
});
