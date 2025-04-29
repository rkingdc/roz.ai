// js/dom.js

// This module will hold references to DOM elements.
// It will be populated by app.js after the DOM is loaded.
// Export an object that will be filled later.

export const elements = {
    // Chat Elements
    chatbox: null,
    messageInput: null,
    micButton: null, // Added mic button reference
    cleanupTranscriptButton: null, // Add cleanup button reference
    sendButton: null,
    modelSelector: null,
    modelSelectorContainer: null,
    webSearchToggle: null,
    webSearchToggleLabel: null,
    calendarToggle: null,
    calendarToggleInputArea: null, // This element doesn't exist in HTML, remove or fix
    fileUploadSessionLabel: null,
    fileUploadSessionInput: null,
    selectedFilesContainer: null,
    inputArea: null, // Container for input elements

    // Sidebar Elements
    sidebar: null,
    sidebarToggleTab: null, // Renamed from sidebarToggleButton
    savedChatsList: null,
    newChatButton: null,
    currentChatNameInput: null,
    // Corrected: Use a specific name for the chat save button reference
    saveChatNameButton: null, // Reference for the chat name save button
    currentChatIdDisplay: null,
    chatSidebarContent: null, // Container for chat-specific sidebar items
    notesSidebarContent: null, // Container for note-specific sidebar items
    savedNotesList: null,
    newNoteButton: null,
    currentNoteNameInput: null,
    saveNoteNameButton: null, // Reference for the note name save button (matches HTML ID)
    currentNoteIdDisplay: null,

    // Plugins Sidebar Elements
    pluginsSidebar: null,
    pluginsToggleTab: null, // Renamed from pluginsToggleButton
    filePluginSection: null,
    filePluginHeader: null,
    filePluginContent: null,
    uploadedFilesList: null,
    manageFilesButton: null,
    attachFullButton: null,
    attachSummaryButton: null,
    calendarPluginSection: null,
    calendarPluginHeader: null,
    calendarPluginContent: null,
    loadCalendarButton: null,
    calendarStatus: null,
    viewCalendarButton: null,
    // Removed Web Search Plugin Section elements
    // webSearchPluginSection: null,
    // webSearchPluginHeader: null,
    // webSearchPluginContent: null,
    historyPluginSection: null, // Added history plugin elements
    historyPluginHeader: null,
    historyPluginContent: null,
    noteHistoryList: null,


    // Main Content Area Elements
    chatSection: null,
    notesSection: null,
    notesTextarea: null,
    notesPreview: null,
    notesModeButtons: null,
    editNoteButton: null,
    viewNoteButton: null,
    markdownTipsButton: null,
    notesModeElements: null, // Container for notes mode buttons and markdown tips button
    notesMicButtonGroup: null,
    micButtonNotes: null,
    cleanupTranscriptButtonNotes: null,
    longRecButtonNotes: null, // *** ADDED: Long Record Button ***
    notesTocDrawer: null, // TOC Drawer elements
    notesTocHeader: null,
    notesTocToggle: null,
    notesTocList: null,

    // Modal Elements
    summaryModal: null,
    closeSummaryModal: null, // Corrected ID to match HTML
    summaryModalFilename: null,
    summaryTextarea: null,
    saveSummaryButton: null,
    summaryStatus: null,
    calendarModal: null,
    closeCalendarModal: null, // Corrected ID to match HTML
    calendarModalContent: null,
    urlModal: null,
    closeUrlModal: null, // Corrected ID to match HTML
    urlInput: null,
    fetchUrlButton: null,
    urlStatus: null,
    manageFilesModal: null,
    closeManageFilesModal: null, // Corrected ID to match HTML
    manageFilesList: null,
    fileUploadModalInput: null,
    fileUploadModalLabel: null,
    addUrlModalButton: null,
    settingsModal: null,
    settingsButton: null,
    closeSettingsModal: null, // Corrected ID to match HTML
    streamingToggle: null,
    filesPluginToggle: null,
    calendarPluginToggle: null,
    webSearchPluginToggle: null,
    markdownTipsModal: null,
    closeMarkdownTipsModal: null, // Corrected ID to match HTML

    // Other Elements
    statusBar: null,
    bodyElement: null,
    chatNavButton: null,
    notesNavButton: null,
    toastContainer: null, // *** ADDED: Toast Container ***
};

/**
 * Populates the elements object with references from the DOM.
 * MUST be called after DOMContentLoaded.
 */
export function populateElements() {
    elements.chatbox = document.getElementById('chatbox');
    elements.messageInput = document.getElementById('message-input');
    elements.micButton = document.getElementById('mic-button');
    // --- Add more detailed logging for cleanupTranscriptButton ---
    const cleanupBtnElement = document.getElementById('cleanup-transcript-btn');
    elements.cleanupTranscriptButton = cleanupBtnElement; // Assign the found element (or null)
    // ---------------------------------------------------------
    elements.sendButton = document.getElementById('send-button');
    elements.sidebar = document.getElementById('sidebar');
    elements.savedChatsList = document.getElementById('saved-chats-list');
    elements.newChatButton = document.getElementById('new-chat-btn');
    elements.currentChatNameInput = document.getElementById('current-chat-name');
    // Corrected: Assign the correct element to the chat save button reference
    elements.saveChatNameButton = document.getElementById('save-chat-name-btn'); // Corrected ID to match HTML
    elements.currentChatIdDisplay = document.getElementById('current-chat-id-display');
    elements.statusBar = document.getElementById('status-bar');
    elements.sidebarToggleTab = document.getElementById('sidebar-toggle-tab'); // Use new ID
    elements.pluginsSidebar = document.getElementById('plugins-sidebar');
    elements.pluginsToggleTab = document.getElementById('plugins-toggle-tab'); // Use new ID
    elements.uploadedFilesList = document.getElementById('uploaded-files-list');
    elements.selectedFilesContainer = document.getElementById('selected-files-container');
    elements.bodyElement = document.body;
    elements.filePluginHeader = document.getElementById('file-plugin-header');
    elements.filePluginContent = document.getElementById('file-plugin-content');
    elements.attachFullButton = document.getElementById('attach-full-btn');
    elements.attachSummaryButton = document.getElementById('attach-summary-btn');
    elements.summaryModal = document.getElementById('summary-modal');
    elements.closeSummaryModal = document.getElementById('close-summary-modal'); // Corrected ID
    elements.summaryModalFilename = document.getElementById('summary-modal-filename');
    elements.summaryTextarea = document.getElementById('summary-textarea');
    elements.saveSummaryButton = document.getElementById('save-summary-btn');
    elements.summaryStatus = document.getElementById('summary-status');
    elements.modelSelector = document.getElementById('model-selector');
    elements.calendarPluginHeader = document.getElementById('calendar-plugin-header');
    elements.calendarPluginContent = document.getElementById('calendar-plugin-content');
    elements.loadCalendarButton = document.getElementById('load-calendar-btn');
    elements.calendarToggle = document.getElementById('calendar-toggle');
    elements.calendarStatus = document.getElementById('calendar-status');
    elements.viewCalendarButton = document.getElementById('view-calendar-btn');
    elements.calendarModal = document.getElementById('calendar-modal');
    elements.closeCalendarModal = document.getElementById('close-calendar-modal'); // Corrected ID
    elements.calendarModalContent = document.getElementById('calendar-modal-content');
    elements.webSearchToggle = document.getElementById('web-search-toggle');
    elements.webSearchToggleLabel = document.getElementById('web-search-toggle-label');
    elements.urlModal = document.getElementById('url-modal');
    elements.closeUrlModal = document.getElementById('close-url-modal'); // Corrected ID
    elements.urlInput = document.getElementById('url-input');
    elements.fetchUrlButton = document.getElementById('fetch-url-btn');
    elements.urlStatus = document.getElementById('url-status');
    elements.manageFilesButton = document.getElementById('manage-files-btn');
    elements.manageFilesModal = document.getElementById('manage-files-modal');
    elements.closeManageFilesModal = document.getElementById('close-manage-files-modal'); // Corrected ID
    elements.manageFilesList = document.getElementById('manage-files-list');
    elements.fileUploadModalInput = document.getElementById('file-upload-modal-input');
    elements.fileUploadModalLabel = document.getElementById('file-upload-modal-label');
    elements.addUrlModalButton = document.getElementById('add-url-modal-btn');
    elements.settingsButton = document.getElementById('settings-btn');
    elements.settingsModal = document.getElementById('settings-modal');
    elements.closeSettingsModal = document.getElementById('close-settings-modal'); // Corrected ID
    elements.streamingToggle = document.getElementById('streaming-toggle');
    elements.filesPluginToggle = document.getElementById('files-plugin-toggle');
    elements.calendarPluginToggle = document.getElementById('calendar-plugin-toggle');
    elements.webSearchPluginToggle = document.getElementById('web-search-plugin-toggle');
    elements.filePluginSection = document.getElementById('file-plugin-section');
    elements.calendarPluginSection = document.getElementById('calendar-plugin-section');
    elements.fileUploadSessionLabel = document.getElementById('file-upload-session-label');
    // elements.calendarToggleInputArea = elements.calendarToggle?.closest('label'); // This element doesn't exist in HTML, remove or fix
    elements.fileUploadSessionInput = document.getElementById('file-upload-session-input');
    elements.chatNavButton = document.getElementById('chat-nav-btn');
    elements.notesNavButton = document.getElementById('notes-nav-btn');
    elements.chatSection = document.getElementById('chat-section');
    elements.notesSection = document.getElementById('notes-section');
    elements.notesTextarea = document.getElementById('notes-textarea');
    elements.notesPreview = document.getElementById('notes-preview');
    elements.chatSidebarContent = document.getElementById('chat-sidebar-content');
    elements.notesSidebarContent = document.getElementById('notes-sidebar-content');
    elements.newNoteButton = document.getElementById('new-note-btn');
    elements.currentNoteNameInput = document.getElementById('current-note-name');
    elements.saveNoteNameButton = document.getElementById('save-note-name-btn'); // Corrected ID to match HTML
    elements.currentNoteIdDisplay = document.getElementById('current-note-id-display');
    elements.savedNotesList = document.getElementById('saved-notes-list');
    elements.modelSelectorContainer = document.getElementById('model-selector-container');
    elements.notesModeButtons = document.getElementById('notes-mode-buttons');
    elements.editNoteButton = document.getElementById('edit-note-btn');
    elements.viewNoteButton = document.getElementById('view-note-btn');
    elements.markdownTipsButton = document.getElementById('markdown-tips-btn');
    elements.notesModeElements = document.getElementById('notes-mode-elements');
    elements.markdownTipsModal = document.getElementById('markdown-tips-modal');
    elements.closeMarkdownTipsModal = document.getElementById('close-markdown-tips-modal'); // Corrected ID
    elements.inputArea = document.getElementById('input-area');
    elements.historyPluginSection = document.getElementById('history-plugin-section'); // Added history plugin elements
    elements.historyPluginHeader = document.getElementById('history-plugin-header');
    elements.historyPluginContent = document.getElementById('history-plugin-content');
    elements.noteHistoryList = document.getElementById('note-history-list');
    elements.notesMicButtonGroup = document.getElementById('notes-mic-button-group');
    elements.micButtonNotes = document.getElementById('mic-button-notes');
    elements.cleanupTranscriptButtonNotes = document.getElementById('cleanup-transcript-btn-notes');
    elements.longRecButtonNotes = document.getElementById('long-rec-button-notes'); // *** ADDED ***
    elements.notesTocDrawer = document.getElementById('notes-toc-drawer'); // TOC Drawer elements
    elements.notesTocHeader = document.getElementById('notes-toc-header');
    elements.notesTocToggle = document.getElementById('notes-toc-toggle');
    elements.notesTocList = document.getElementById('notes-toc-list');
    elements.toastContainer = document.getElementById('toast-container'); // *** ADDED ***


    // Basic check
    if (!elements.bodyElement || !elements.statusBar || !elements.chatbox) {
        console.error("Core DOM elements not found! Application might not work correctly.");
    }
    // *** ADDED: Check for toast container after attempting to populate ***
    if (!elements.toastContainer) {
        console.warn("Toast container element (#toast-container) not found during populateElements.");
    }
    // --------------------------------------------------------------------
}
