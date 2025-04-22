// Global variables/constants (can be defined outside DOMContentLoaded)
let currentChatId = null;
let currentNoteId = null; // New: Track the currently active note ID
let isLoading = false;
let selectedFiles = []; // Files selected for attachment (from the modal list)
let currentEditingFileId = null;
let calendarContext = null; // Store loaded calendar events text
let isCalendarContextActive = false; // Track calendar toggle state (next to message input)
let isStreamingEnabled = true; // Track streaming toggle state (default to true)
let isFilePluginEnabled = true; // Track Files plugin enabled state (default to true)
let isCalendarPluginEnabled = true; // Track Calendar plugin enabled state (default to true)
let isWebSearchPluginEnabled = true; // New: Track Web Search plugin enabled state (default to true)
let currentTab = 'chat'; // New: Track the currently active tab ('chat' or 'notes')
let currentNoteMode = 'edit'; // New: Track the current mode for notes ('edit' or 'view')


const SIDEBAR_COLLAPSED_KEY = 'sidebarCollapsed';
const PLUGINS_COLLAPSED_KEY = 'pluginsCollapsed';
const FILE_PLUGIN_COLLAPSED_KEY = 'filePluginCollapsed';
const CALENDAR_PLUGIN_COLLAPSED_KEY = 'calendarPluginCollapsed';
const STREAMING_ENABLED_KEY = 'streamingEnabled'; // New localStorage key for streaming
const FILES_PLUGIN_ENABLED_KEY = 'filesPluginEnabled'; // New localStorage key for Files plugin
const CALENDAR_PLUGIN_ENABLED_KEY = 'calendarPluginEnabled'; // New localStorage key for Calendar plugin
const WEB_SEARCH_PLUGIN_ENABLED_KEY = 'webSearchPluginEnabled'; // New: localStorage key for Web Search plugin
const ACTIVE_TAB_KEY = 'activeTab'; // New: localStorage key for active tab
const CURRENT_NOTE_ID_KEY = 'currentNoteId'; // New: localStorage key for current note ID
const CURRENT_NOTE_MODE_KEY = 'currentNoteMode'; // New: localStorage key for current note mode


const MAX_FILE_SIZE_MB = 10;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

// Text Decoder for streaming (can be defined globally)
const textDecoder = new TextDecoder();

// Assume 'marked' is available globally or imported
// Make sure you have
// and Font Awesome if using the UI markers.

// Create a custom renderer to apply your specific classes
// to code blocks and inline code, matching the original function's output.
const renderer = new marked.Renderer();

// Helper function for basic HTML escaping within code
function escapeHtml(html) {
    // Ensure input is a string
    const strHtml = String(html);
    return strHtml
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

renderer.code = function(code, language) {
    // Attempt to get the string content if 'code' is an object
    let codeString = typeof code === 'object' && code !== null && typeof code.text === 'string' ? code.text : String(code);

    // Ensure the input 'code' is treated as a string and escape its content
    const escapedCode = escapeHtml(codeString);
    return `<pre class="bg-gray-800 text-white p-2 rounded mt-1 overflow-x-auto text-sm font-mono"><code>${escapedCode}</code></pre>`;
};

renderer.codespan = function(text) {
    // Attempt to get the string content if 'text' is an object
    let textString = typeof text === 'object' && text !== null && typeof text.text === 'string' ? text.text : String(text);

    // Ensure the input 'text' is treated as a string and escape its content
    const escapedText = escapeHtml(textString);

    // Return the HTML string with your desired classes
    return `<code class="bg-gray-200 px-1 rounded text-sm font-mono">${escapedText}</code>`;
};

// Define options for marked.parse
// Use the custom renderer
// Note: marked's default behavior for newlines is different from your original
// const markedOptions = { // REMOVED: Will set globally
//     renderer: renderer,
//     breaks: true
// };


// --- Utility Functions ---
// These functions don't access DOM elements directly on definition,
// so they can be outside DOMContentLoaded, but they might be called
// by code inside it.
function updateStatus(message, isError = false) {
    // Access statusBar inside the function, assuming it's defined in the DOMContentLoaded scope
    const statusBar = document.getElementById('status-bar');
    if (!statusBar) {
        console.error("Status bar element not found.");
        return;
    }
    statusBar.textContent = `Status: ${message}`;
    statusBar.className = `text-xs px-4 py-1 flex-shrink-0 ${isError ? 'text-red-600 bg-red-50 border-t border-red-200' : 'text-rz-status-bar-text bg-rz-status-bar-bg border-t border-rz-frame'}`;
    // console.log(`Status Update: ${message}`); // Reduced verbosity
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// setLoadingState needs to access many DOM elements, so it should be defined
// within or called from the DOMContentLoaded scope where those elements are referenced.
// Let's move its definition inside the listener.

// setSidebarCollapsed, toggleLeftSidebar, toggleRightSidebar,
// setPluginSectionCollapsed, toggleFilePlugin, toggleCalendarPlugin
// These access DOM elements and should be defined within DOMContentLoaded.

// addMessage, applyMarkdownToMessage
// These access chatbox and should be defined within DOMContentLoaded.

// All modal functions (show/close/handle) access modal elements and should be
// defined within DOMContentLoaded.

// loadUploadedFiles, handleFileUpload, addFileFromUrl, attachSelectedFiles,
// renderSelectedFiles, removeSelectedFile
// These access file/modal elements and should be defined within DOMContentLoaded.

// loadCalendarEvents, updateCalendarStatus, handleCalendarToggle, showCalendarModal
// These access calendar elements and should be defined within DOMContentLoaded.

// clearChatbox, loadSavedChats, startNewChat, loadChat, sendMessage,
// handleSaveChatName, handleDeleteChat, updateActiveChatListItem, handleModelChange
// These access chat/sidebar/input elements and should be defined within DOMContentLoaded.

// showSettingsModal, closeSettingsModal, handleStreamingToggle,
// handleFilesPluginToggle, handleCalendarPluginToggle, updatePluginUI
// These access settings/plugin elements and should be defined within DOMContentLoaded.

// initializeApp needs to access many elements and call many functions that do,
// so it should be defined within DOMContentLoaded.


// --- Wait for the DOM to be fully loaded ---
document.addEventListener('DOMContentLoaded', () => {

    // --- DOM Element References (MUST be inside DOMContentLoaded) ---
    const chatbox = document.getElementById('chatbox');
    const messageInput = document.getElementById('message-input');
    const sendButton = document.getElementById('send-button');
    const sidebar = document.getElementById('sidebar');
    const savedChatsList = document.getElementById('saved-chats-list');
    const newChatButton = document.getElementById('new-chat-btn');
    const currentChatNameInput = document.getElementById('current-chat-name');
    const saveChatNameButton = document.getElementById('save-chat-name-btn');
    const currentChatIdDisplay = document.getElementById('current-chat-id-display');
    const statusBar = document.getElementById('status-bar'); // Re-get here for scope
    const sidebarToggleButton = document.getElementById('sidebar-toggle-btn');
    const pluginsSidebar = document.getElementById('plugins-sidebar');
    const pluginsToggleButton = document.getElementById('plugins-toggle-btn');
    const uploadedFilesList = document.getElementById('uploaded-files-list');
    const selectedFilesContainer = document.getElementById('selected-files-container');
    const bodyElement = document.body; // Re-get here for scope
    const filePluginHeader = document.getElementById('file-plugin-header');
    const filePluginContent = document.getElementById('file-plugin-content');
    const attachFullButton = document.getElementById('attach-full-btn');
    const attachSummaryButton = document.getElementById('attach-summary-btn');
    const summaryModal = document.getElementById('summary-modal');
    const closeSummaryModalButton = document.getElementById('close-summary-modal');
    const summaryModalFilename = document.getElementById('summary-modal-filename');
    const summaryTextarea = document.getElementById('summary-textarea');
    const saveSummaryButton = document.getElementById('save-summary-btn');
    const summaryStatus = document.getElementById('summary-status');
    const modelSelector = document.getElementById('model-selector');
    const calendarPluginHeader = document.getElementById('calendar-plugin-header');
    const calendarPluginContent = document.getElementById('calendar-plugin-content');
    const loadCalendarButton = document.getElementById('load-calendar-btn');
    const calendarToggle = document.getElementById('calendar-toggle');
    const calendarStatus = document.getElementById('calendar-status');
    const viewCalendarButton = document.getElementById('view-calendar-btn');
    const calendarModal = document.getElementById('calendar-modal');
    const closeCalendarModalButton = document.getElementById('close-calendar-modal');
    const calendarModalContent = document.getElementById('calendar-modal-content');
    const webSearchToggle = document.getElementById('web-search-toggle');
    const webSearchToggleLabel = document.getElementById('web-search-toggle-label'); // New: Reference to the label wrapping the web search toggle

    // URL Feature References
    const urlModal = document.getElementById('url-modal');
    const closeUrlModalButton = document.getElementById('close-url-modal');
    const urlInput = document.getElementById('url-input');
    const fetchUrlButton = document.getElementById('fetch-url-btn');
    const urlStatus = document.getElementById('url-status');

    // Manage Files Modal References
    const manageFilesButton = document.getElementById('manage-files-btn');
    const manageFilesModal = document.getElementById('manage-files-modal');
    const closeManageFilesModalButton = document.getElementById('close-manage-files-modal');
    const manageFilesList = document.getElementById('manage-files-list');
    const fileUploadModalInput = document.getElementById('file-upload-modal-input');
    const fileUploadModalLabel = document.getElementById('file-upload-modal-label');
    const addUrlModalButton = document.getElementById('add-url-modal-btn');

    // Settings Modal References
    const settingsButton = document.getElementById('settings-btn');
    const settingsModal = document.getElementById('settings-modal');
    const closeSettingsModalButton = document.getElementById('close-settings-modal');
    const streamingToggle = document.getElementById('streaming-toggle');

    // Plugin Toggles in Settings Modal References
    const filesPluginToggle = document.getElementById('files-plugin-toggle');
    const calendarPluginToggle = document.getElementById('calendar-plugin-toggle');
    const webSearchPluginToggle = document.getElementById('web-search-plugin-toggle'); // New: Reference to the web search plugin toggle in settings


    // DOM Elements to hide/show based on plugin settings References
    const filePluginSection = document.getElementById('file-plugin-section');
    const calendarPluginSection = document.getElementById('calendar-plugin-section');
    const fileUploadSessionLabel = document.getElementById('file-upload-session-label');
    const calendarToggleInputArea = calendarToggle.closest('label'); // This is the label next to the input


    // Session File Input Reference (This was the one causing the error)
    const fileUploadSessionInput = document.getElementById('file-upload-session-input');

    // New Notes Feature References
    const chatNavButton = document.getElementById('chat-nav-btn');
    const notesNavButton = document.getElementById('notes-nav-btn');
    const chatSection = document.getElementById('chat-section');
    const notesSection = document.getElementById('notes-section');
    const notesTextarea = document.getElementById('notes-textarea');
    const notesPreview = document.getElementById('notes-preview');
    // const saveNoteButton = document.getElementById('save-note-button'); // This button is now in the sidebar
    const chatSidebarContent = document.getElementById('chat-sidebar-content'); // New: Container for chat sidebar elements
    const notesSidebarContent = document.getElementById('notes-sidebar-content'); // New: Container for notes sidebar elements
    const newNoteButton = document.getElementById('new-note-btn'); // New: New Note button
    const currentNoteNameInput = document.getElementById('current-note-name'); // New: Current Note name input
    const saveNoteNameButton = document.getElementById('save-note-name-btn'); // New: Save Note Name button (also saves content)
    const currentNoteIdDisplay = document.getElementById('current-note-id-display'); // New: Current Note ID display
    const savedNotesList = document.getElementById('saved-notes-list'); // New: Saved Notes list container
    const modelSelectorContainer = document.getElementById('model-selector-container'); // New: Container for model selector

    // New Notes Mode Button References
    const notesModeButtons = document.getElementById('notes-mode-buttons'); // Container for mode buttons
    const editNoteButton = document.getElementById('edit-note-btn');
    const viewNoteButton = document.getElementById('view-note-btn');
    const markdownTipsButton = document.getElementById('markdown-tips-btn'); // New: Markdown Tips button
    const notesModeElements = document.getElementById('notes-mode-elements'); // New: Container for notes mode buttons and markdown tips button


    // New Markdown Tips Modal References
    const markdownTipsModal = document.getElementById('markdown-tips-modal');
    const closeMarkdownTipsModalButton = document.getElementById('close-markdown-tips-modal');


    // Application State (Re-declare or ensure access to global state if needed)
    // These are already declared globally, so no need to re-declare with `let` or `const`
    // let currentChatId = null; // Already global
    // let currentNoteId = null; // Already global
    // let isLoading = false; // Already global
    // let selectedFiles = []; // Already global
    // let currentEditingFileId = null; // Already global
    // let calendarContext = null; // Already global
    // let isCalendarContextActive = false; // Already global
    // let isStreamingEnabled = true; // Already global
    // let isFilePluginEnabled = true; // Already global
    // let isCalendarPluginEnabled = true; // Already global
    // let isWebSearchPluginEnabled = true; // Already global
    // let currentTab = 'chat'; // Already global
    // let currentNoteMode = 'edit'; // Already global
    let sessionFile = null; // Variable to store selected session file (can be local or global, let's keep global)


    // Default model value needs the selector to be available
    const defaultModel = modelSelector.value;

    // --- Configure Marked.js globally ---
    marked.setOptions({
        renderer: renderer,
        breaks: true,
        // Add other options if needed, e.g., gfm: true (default), pedantic: false, sanitize: false
        gfm: true // Ensure GitHub Flavored Markdown is enabled (usually default)
    });
    console.log("[DEBUG] Marked.js options set globally."); // Added log


    // --- Utility Functions ---
    // These functions don't access DOM elements directly on definition,
    // so they can be outside DOMContentLoaded, but they might be called
    // by code inside it.
    function updateStatus(message, isError = false) {
        // Access statusBarElement here, it's defined in the DOMContentLoaded scope
        const statusBarElement = statusBar; // Use the variable from the outer scope

        if (!statusBarElement) {
            console.error("Status bar element not found.");
            return;
        }
        statusBarElement.textContent = `Status: ${message}`;
        statusBarElement.className = `text-xs px-4 py-1 flex-shrink-0 ${isError ? 'text-red-600 bg-red-50 border-t border-red-200' : 'text-rz-status-bar-text bg-rz-status-bar-bg border-t border-rz-frame'}`;
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // setLoadingState needs to access many DOM elements, so it should be defined
    // within or called from the DOMContentLoaded scope where those elements are referenced.
    // Let's move its definition inside the listener.

    // setSidebarCollapsed, toggleLeftSidebar, toggleRightSidebar,
    // setPluginSectionCollapsed, toggleFilePlugin, toggleCalendarPlugin
    // These access DOM elements and should be defined within DOMContentLoaded.

    // addMessage, applyMarkdownToMessage
    // These access chatbox and should be defined within DOMContentLoaded.

    // All modal functions (show/close/handle) access modal elements and should be
    // defined within DOMContentLoaded.

    // loadUploadedFiles, handleFileUpload, addFileFromUrl, attachSelectedFiles,
    // renderSelectedFiles, removeSelectedFile
    // These access file/modal elements and should be defined within DOMContentLoaded.

    // loadCalendarEvents, updateCalendarStatus, handleCalendarToggle, showCalendarModal
    // These access calendar elements and should be defined within DOMContentLoaded.

    // clearChatbox, loadSavedChats, startNewChat, loadChat, sendMessage,
    // handleSaveChatName, handleDeleteChat, updateActiveChatListItem, handleModelChange
    // These access chat/sidebar/input elements and should be defined within DOMContentLoaded.

    // showSettingsModal, closeSettingsModal, handleStreamingToggle,
    // handleFilesPluginToggle, handleCalendarPluginToggle, updatePluginUI
    // These access settings/plugin elements and should be defined within DOMContentLoaded.

    // initializeApp needs to access many elements and call many functions that do,
    // so it should be defined within DOMContentLoaded.


    /** Deletes a file from the backend and updates the UI lists. */
    async function deleteFile(fileId) {
        if (isLoading) return;
        if (!confirm("Are you sure you want to delete this file? This action cannot be undone.")) {
            return;
        }

        setLoadingState(true, "Deleting File");
        updateStatus(`Deleting file ${fileId}...`);

        try {
            const response = await fetch(`/api/files/${fileId}`, {
                method: 'DELETE'
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`${errorData.error || `HTTP error! status: ${response.status}`}`);
            }

            updateStatus(`File ${fileId} deleted.`);
            await loadUploadedFiles(); // Reload *both* file lists

            // Remove from selected files if it's selected
            selectedFiles = selectedFiles.filter(f => f.id !== fileId);
            renderSelectedFiles(); // Update the attached files display

        } catch (error) {
            console.error('Error deleting file:', error);
            updateStatus(`Error deleting file: ${error.message}`, true);
        } finally {
            setLoadingState(false);
        }
    }


    function setLoadingState(loading, operation = "Processing") {
        console.log(`[DEBUG] setLoadingState called with loading=${loading}, operation=${operation}, currentTab=${currentTab}, currentNoteMode=${currentNoteMode}`); // Added log
        isLoading = loading;
        // Chat elements
        messageInput.disabled = loading;
        sendButton.disabled = loading;
        // newChatButton.disabled = loading; // Disabled below based on tab
        saveChatNameButton.disabled = loading;
        modelSelector.disabled = loading;
        attachFullButton.disabled = loading;
        attachSummaryButton.disabled = loading;
        loadCalendarButton.disabled = loading;
        calendarToggle.disabled = loading;
        viewCalendarButton.disabled = loading || !calendarContext;
        webSearchToggle.disabled = loading; // Disable the web search toggle next to input

        // Notes elements
        // Disable/Enable the *currently visible* notes element
        if (currentTab === 'notes') {
             if (currentNoteMode === 'edit') {
                 notesTextarea.disabled = loading;
                 notesPreview.disabled = true; // Preview is never editable
             } else { // view mode
                 notesTextarea.disabled = true; // Textarea is hidden/disabled
                 notesPreview.disabled = true; // Preview is never editable
             }
        } else {
             // If not on notes tab, disable both notes elements
             notesTextarea.disabled = true;
             notesPreview.disabled = true;
        }

        // saveNoteButton.disabled = loading; // Disabled below based on tab
        newNoteButton.disabled = loading; // New: Disable New Note button
        currentNoteNameInput.disabled = loading; // New: Disable Current Note name input
        saveNoteNameButton.disabled = loading; // New: Disable Save Note Name button
        editNoteButton.disabled = loading; // Disable notes mode buttons
        viewNoteButton.disabled = loading; // Disable notes mode buttons
        markdownTipsButton.disabled = loading; // New: Disable markdown tips button
        console.log(`[DEBUG] setLoadingState (Notes Tab): newNoteButton disabled=${newNoteButton.disabled}, saveNoteNameButton disabled=${saveNoteNameButton.disabled}, editNoteButton disabled=${editNoteButton.disabled}, viewNoteButton disabled=${viewNoteButton.disabled}, markdownTipsButton disabled=${markdownTipsButton.disabled}`); // Added log


        // Sidebar/Modal/Settings elements
        sidebarToggleButton.disabled = loading;
        pluginsToggleButton.disabled = loading;
        saveSummaryButton.disabled = loading;
        settingsButton.disabled = loading; // Disable settings button when loading
        streamingToggle.disabled = loading; // Disable streaming toggle when loading
        filesPluginToggle.disabled = loading; // Disable files plugin toggle when loading
        calendarPluginToggle.disabled = loading; // Disable calendar plugin toggle when loading
        webSearchPluginToggle.disabled = loading; // New: Disable web search plugin toggle when loading

        // Navigation buttons (in sidebar)
        chatNavButton.disabled = loading;
        notesNavButton.disabled = loading;


        // Disable/Enable elements in the Manage Files Modal
        manageFilesButton.disabled = loading; // Disable the button that opens the modal
        // Check if elements exist before accessing properties like .disabled
        if (fileUploadModalInput) fileUploadModalInput.disabled = loading;
        if (fileUploadModalLabel) fileUploadModalLabel.disabled = loading; // Disable the label too
        if (addUrlModalButton) addUrlModalButton.disabled = loading;

        // Disable/Enable elements in the URL Modal if it's open
        if (urlModal && urlModal.style.display === 'block') {
             if (urlInput) urlInput.disabled = loading;
             if (fetchUrlButton) fetchUrlButton.disabled = loading;
        }

        // Disable/Enable buttons within the file list in the modal (no checkboxes here anymore)
        manageFilesList.querySelectorAll('button').forEach(el => el.disabled = loading);
         // Disable/Enable checkboxes in the sidebar file list
        uploadedFilesList.querySelectorAll('input[type="checkbox"]').forEach(el => el.disabled = loading);

        selectedFilesContainer.querySelectorAll('button').forEach(el => el.disabled = loading);

        // Disable/Enable buttons within the saved chats/notes lists
        savedChatsList.querySelectorAll('button').forEach(el => el.disabled = loading);
        savedNotesList.querySelectorAll('button').forEach(el => el.disabled = loading); // New: Disable delete buttons in notes list


        // Update button text/icons based on current tab and loading state
        if (currentTab === 'chat') {
             sendButton.innerHTML = loading ? `<i class="fas fa-spinner fa-spin mr-2"></i> ${operation}...` : '<i class="fas fa-paper-plane"></i> Send';
             newChatButton.disabled = loading; // Enable/Disable New Chat button
             newNoteButton.disabled = true; // Disable New Note button when on chat tab
             saveNoteNameButton.disabled = true; // Disable Save Note Name button
             editNoteButton.disabled = true; // Disable notes mode buttons when on chat tab
             viewNoteButton.disabled = true; // Disable notes mode buttons when on chat tab
             markdownTipsButton.disabled = true; // New: Disable markdown tips button when on chat tab
             console.log(`[DEBUG] setLoadingState (Chat Tab): newNoteButton disabled=${newNoteButton.disabled}, saveNoteNameButton disabled=${saveNoteNameButton.disabled}, editNoteButton disabled=${editNoteButton.disabled}, viewNoteButton disabled=${viewNoteButton.disabled}, markdownTipsButton disabled=${markdownTipsButton.disabled}`); // Added log
        } else if (currentTab === 'notes') {
             // saveNoteButton.innerHTML = loading ? `<i class="fas fa-spinner fa-spin mr-1"></i> ${operation}...` : '<i class="fas fa-save mr-1"></i> Save Note'; // Button moved
             sendButton.innerHTML = '<i class="fas fa-paper-plane"></i> Send'; // Reset chat button if on notes tab
             newChatButton.disabled = true; // Disable New Chat button when on notes tab
             newNoteButton.disabled = loading; // Enable/Disable New Note button
             saveNoteNameButton.disabled = loading; // Enable/Disable Save Note Name button
             editNoteButton.disabled = loading; // Enable/Disable notes mode buttons
             viewNoteButton.disabled = loading; // Enable/Disable notes mode buttons
             markdownTipsButton.disabled = loading; // New: Enable/Disable markdown tips button
             console.log(`[DEBUG] setLoadingState (Notes Tab): newNoteButton disabled=${newNoteButton.disabled}, saveNoteNameButton disabled=${saveNoteNameButton.disabled}, editNoteButton disabled=${editNoteButton.disabled}, viewNoteButton disabled=${viewNoteButton.disabled}, markdownTipsButton disabled=${markdownTipsButton.disabled}`); // Added log
        }


        if (loading) {
            updateStatus(`${operation}...`);
        } else {
            updateStatus("Idle");
            // Only focus if no modals are open and sidebars are not collapsed AND on the correct tab
            if (manageFilesModal.style.display !== 'block' && urlModal.style.display !== 'block' && summaryModal.style.display !== 'block' && settingsModal.style.display !== 'block' && markdownTipsModal.style.display !== 'block' && !bodyElement.classList.contains('sidebar-collapsed') && !bodyElement.classList.contains('plugins-collapsed')) {
                 if (currentTab === 'chat') {
                     messageInput.focus();
                 } else if (currentTab === 'notes') {
                     // Focus the visible notes element
                     if (currentNoteMode === 'edit') {
                         notesTextarea.focus();
                     } else {
                         // Cannot focus preview
                     }
                 }
            }
        }
    }

    // --- Sidebar & Plugin Toggle Functions ---
    function setSidebarCollapsed(sidebarElement, toggleButton, collapsed, storageKey, positionClass) {
        const icon = toggleButton.querySelector('i');
        const bodyClass = `${positionClass}-collapsed`;
        const isLeft = positionClass === 'sidebar';
        const expandIcon = isLeft ? 'fa-chevron-left' : 'fa-chevron-right';
        const collapseIcon = isLeft ? 'fa-chevron-right' : 'fa-chevron-left';
        if (collapsed) {
            bodyElement.classList.add(bodyClass);
            icon.classList.remove(expandIcon);
            icon.classList.add(collapseIcon);
            toggleButton.title = `Expand ${isLeft ? 'Chat List' : 'Plugins'}`;
            localStorage.setItem(storageKey, 'true');
        } else {
            bodyElement.classList.remove(bodyClass);
            icon.classList.remove(collapseIcon);
            icon.classList.add(expandIcon);
            toggleButton.title = `Collapse ${isLeft ? 'Chat List' : 'Plugins'}`;
            localStorage.setItem(storageKey, 'false');
        }
        // Only focus if no modals are open and sidebars are not collapsed AND on the correct tab
        if (!collapsed && !isLoading && manageFilesModal.style.display !== 'block' && urlModal.style.display !== 'block' && summaryModal.style.display !== 'block' && settingsModal.style.display !== 'block' && markdownTipsModal.style.display !== 'block' && !bodyElement.classList.contains('sidebar-collapsed') && !bodyElement.classList.contains('plugins-collapsed')) {
            setTimeout(() => {
                if (currentTab === 'chat') {
                    messageInput.focus();
                } else if (currentTab === 'notes') {
                     if (currentNoteMode === 'edit') {
                         notesTextarea.focus();
                     } else {
                         // Cannot focus preview
                     }
                }
            }, 350); // Small delay to allow transition
        }
    }

    function toggleLeftSidebar() {
        setSidebarCollapsed(sidebar, sidebarToggleButton, !bodyElement.classList.contains('sidebar-collapsed'), SIDEBAR_COLLAPSED_KEY, 'sidebar');
    }

    function toggleRightSidebar() {
        setSidebarCollapsed(pluginsSidebar, pluginsToggleButton, !bodyElement.classList.contains('plugins-collapsed'), PLUGINS_COLLAPSED_KEY, 'plugins');
    }

    function setPluginSectionCollapsed(headerElement, contentElement, collapsed, storageKey) {
        const icon = headerElement.querySelector('.toggle-icon');
        if (collapsed) {
            headerElement.classList.add('collapsed');
            contentElement.classList.add('hidden');
            if (icon) {
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-up');
            }
            localStorage.setItem(storageKey, 'true');
        } else {
            headerElement.classList.remove('collapsed');
            contentElement.classList.remove('hidden');
            if (icon) {
                icon.classList.remove('fa-chevron-up');
                icon.classList.add('fa-chevron-down');
            }
            localStorage.setItem(storageKey, 'false');
        }
    }

    function toggleFilePlugin() {
        const isCollapsed = filePluginContent.classList.contains('hidden');
        setPluginSectionCollapsed(filePluginHeader, filePluginContent, !isCollapsed, FILE_PLUGIN_COLLAPSED_KEY);
    }

    function toggleCalendarPlugin() {
        const isCollapsed = calendarPluginContent.classList.contains('hidden');
        setPluginSectionCollapsed(calendarPluginHeader, calendarPluginContent, !isCollapsed, CALENDAR_PLUGIN_COLLAPSED_KEY);
    }


    /// uploads in the main chat location

    // Event Listener for Session File Input Label (Paperclip button)
    fileUploadSessionLabel.addEventListener('click', () => {
        // Only trigger if the Files plugin is enabled AND we are on the chat tab
        if (isFilePluginEnabled && currentTab === 'chat') {
            fileUploadSessionInput.click(); // Simulate click to open file dialog.
        } else if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
        }
        // No status update needed if not on chat tab, the button is hidden
    });

    // Event Listener for Session File Input
    fileUploadSessionInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        // Clear any existing session file tag first
        const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
        if (existingSessionTag) {
            existingSessionTag.remove();
        }

        if (!file) {
            sessionFile = null; // Ensure sessionFile is null if no file is chosen
            renderSelectedFiles(); // Re-render to ensure container visibility is correct
            return;
        }

        if (file.size > MAX_FILE_SIZE_BYTES) {
             alert(`Skipping "${file.name}": File is too large (${formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
             sessionFile = null;
             fileUploadSessionInput.value = ''; // Reset file input
             renderSelectedFiles();
             return;
        }


        // Reset sessionFile before reading the new one
        sessionFile = null;
        // Show loading state within the shared container
        selectedFilesContainer.classList.remove('hidden');
        const loadingTag = document.createElement('span');
        loadingTag.classList.add('selected-file-tag', 'session-file-tag', 'opacity-75'); // Add session-file-tag class
        loadingTag.innerHTML = `<span class="text-xs">Loading ${file.name}...</span>`;
        selectedFilesContainer.appendChild(loadingTag);


        const reader = new FileReader();
    reader.onload = function(event) {
        // Remove loading tag
        loadingTag.remove();
        // Store file details AND content
        sessionFile = {
            filename: file.name,
            mimetype: file.type,
            content: event.target.result // Store the Base64 content
        };

        // Update display in the shared container
        selectedFilesContainer.classList.remove('hidden'); // Ensure container is visible
        const tag = document.createElement('span');
        tag.classList.add('selected-file-tag', 'session-file-tag'); // Add session-file-tag class
        tag.innerHTML = `
        <i class="fas fa-paperclip mr-1 text-xs"></i> <!-- Icon for session file -->
        <span class="filename truncate" title="${file.name}">${file.name}</span>
        <span class="file-type">SESSION</span> <!-- Differentiate session file -->
        <button title="Remove Attachment" class="ml-2">&times;</button>
    `;
        tag.querySelector('button').onclick = () => {
            sessionFile = null; // Clear the selected file state.
            tag.remove(); // Remove the tag itself.
            renderSelectedFiles(); // Re-render to potentially hide container if empty
            fileUploadSessionInput.value = ''; // Reset file input
        };
        // Prepend session file tag for visual distinction or append, user preference? Let's prepend.
        selectedFilesContainer.prepend(tag);
    }
        reader.onerror = function(error) {
            // Remove loading tag if it exists
            loadingTag.remove();
            console.error("Error reading file:", error);
            // Optionally show error in the container or just log it
            // Example: add a temporary error tag
            const errorTag = document.createElement('span');
            errorTag.classList.add('selected-file-tag', 'session-file-tag', 'bg-red-100', 'text-red-700', 'border-red-300');
            errorTag.textContent = `Error loading ${file.name}`;
            selectedFilesContainer.prepend(errorTag);
            setTimeout(() => errorTag.remove(), 3000); // Remove error after 3s

            sessionFile = null;
            fileUploadSessionInput.value = ''; // Reset file input
            renderSelectedFiles(); // Re-render to potentially hide container
        }
        reader.readAsDataURL(file); // Read file as data URL (Base64)
    });


    /**
     * Adds a message to the chatbox.
     * @param {string} role - 'user', 'assistant', or 'system'.
     * @param {string} content - The message content (can include UI markers).
     * @param {boolean} [isError=false] - Whether the message represents an error.
     * @param {HTMLElement} [targetElement=null] - Optional: An existing element to append content to (for streaming).
     * @returns {HTMLElement|null} The created or updated message element, or null if chatbox not found.
     */
    function addMessage(role, content, isError = false, targetElement = null) {
        // Access chatboxElement here, it's defined in the DOMContentLoaded scope
        const chatboxElement = chatbox;

        if (!chatboxElement) {
            console.error("Chatbox element with ID 'chatbox' not found. Cannot add message.");
            return null; // Return null if chatbox is not found
        }

        let messageDiv;
        // Ensure content is a string before processing
        const stringContent = String(content); // Explicitly convert to string

        if (targetElement) {
            // If targetElement is provided, append content to it
            messageDiv = targetElement;
            // Append content directly for streaming, markdown will be applied later
            // Escape HTML content before appending to prevent script injection or unwanted HTML rendering during streaming
            // Ensure targetElement has a .message-content span to append to
            const contentSpan = messageDiv.querySelector('.message-content');
            if (contentSpan) {
                 contentSpan.innerHTML += escapeHtml(stringContent); // Append escaped string content to content span
            } else {
                 // Fallback if structure is unexpected
                 messageDiv.innerHTML += escapeHtml(stringContent);
            }

        } else {
            // Create a new message element
            messageDiv = document.createElement('div');
            if (role === 'system') {
                messageDiv.classList.add('system-msg');
            } else {
                messageDiv.classList.add('message');
                if (isError) messageDiv.classList.add('error-msg');
                else messageDiv.classList.add(role === 'user' ? 'user-msg' : 'assistant-msg');
            }

            const roleSpan = document.createElement('span');
            roleSpan.classList.add('message-role');
            roleSpan.textContent = role === 'user' ? 'You: ' : 'Assistant: ';
            messageDiv.appendChild(roleSpan);

            const contentSpan = document.createElement('span');
            contentSpan.classList.add('message-content');
            messageDiv.appendChild(contentSpan);


            // Process UI markers only when creating the initial message or final content
            let processedContent = stringContent; // Use the stringContent here
            processedContent = processedContent.replace(/\[UI-MARKER:file:(.*?):(.*?)\]/g, (match, filename, type) => `<span class="attachment-icon" title="Attached ${filename} (${type})"><i class="fas fa-paperclip"></i> ${filename}</span>`).replace(/\[UI-MARKER:calendar\]/g, `<span class="attachment-icon" title="Calendar Context Active"><i class="fas fa-calendar-check"></i> Calendar</span>`).replace(/\[UI-MARKER:error:(.*?)\]/g, (match, filename) => `<span class="attachment-icon error-marker" title="Error attaching ${filename}"><i class="fas fa-exclamation-circle"></i> ${filename}</span>`).replace(/\[UI-MARKER:websearch\]/g, `<span class="attachment-icon" title="Web Search Enabled"><i class="fas fa-globe"></i> Web Search</span>`); // Added web search marker


            // Apply markdown parsing only when creating a new message (non-streaming initial content)
            // For streaming, content is appended chunk by chunk, markdown applied at the end
            // This branch is for non-streaming or initial message creation
            // REMOVED escapeHtml here - let marked handle escaping within code blocks/spans
            contentSpan.innerHTML = marked.parse(processedContent); // Use globally set options


            // Append the new message element to the chatbox
            chatboxElement.appendChild(messageDiv);
        }

        // Always scroll to the bottom after adding/updating content, but only if chatbox exists
        chatboxElement.scrollTop = chatboxElement.scrollHeight;

        return messageDiv; // Return the element for potential future updates (streaming)
    }

    /**
     * Applies markdown parsing to the content of a given message element.
     * This is typically used after streaming is complete.
     * @param {HTMLElement} messageElement - The message element to parse.
     */
    function applyMarkdownToMessage(messageElement) {
        if (!messageElement) return;
        const contentElement = messageElement.querySelector('.message-content');
        if (!contentElement) return;

        const rawContent = contentElement.innerHTML; // Get the accumulated raw text (which was escaped)

        // Unescape HTML entities before parsing markdown
        const unescapedContent = rawContent
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>');

        // Re-process UI markers before final markdown parse
        let processedContent = unescapedContent;
        processedContent = processedContent.replace(/\[UI-MARKER:file:(.*?):(.*?)\]/g, (match, filename, type) => `<span class="attachment-icon" title="Attached ${filename} (${type})"><i class="fas fa-paperclip"></i> ${filename}</span>`).replace(/\[UI-MARKER:calendar\]/g, `<span class="attachment-icon" title="Calendar Context Active"><i class="fas fa-calendar-check"></i> Calendar</span>`).replace(/\[UI-MARKER:error:(.*?)\]/g, (match, filename) => `<span class="attachment-icon error-marker" title="Error attaching ${filename}"><i class="fas fa-exclamation-circle"></i> ${filename}</span>`).replace(/\[UI-MARKER:websearch\]/g, `<span class="attachment-icon" title="Web Search Enabled"><i class="fas fa-globe"></i> Web Search</span>`); // Added web search marker


        // Apply markdown parsing to the unescaped content
        const parsedContent = marked.parse(processedContent); // Use globally set options

        // Ensure the result is a string before setting innerHTML
        contentElement.innerHTML = String(parsedContent);
    }


    // --- Manage Files Modal Functions ---

    /** Shows the Manage Files modal and loads the file list. */
    async function showManageFilesModal() {
        if (isLoading) return;
        // Only show if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Manage Files is only available in the Chat section.", true);
             return;
         }
        manageFilesModal.style.display = "block";
        // Load files when the modal is shown
        await loadUploadedFiles(); // This will now load into both lists
    }

    /** Closes the Manage Files modal. */
    function closeManageFilesModal() {
        closeModal(manageFilesModal); // Use generic close modal function
    }

    /** Loads uploaded files and populates the lists in both the sidebar and the modal. */
    async function loadUploadedFiles() {
        // Only load if Files plugin is enabled
        if (!isFilePluginEnabled) {
            uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
            manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
            updateStatus("Files plugin disabled. File list not loaded.");
            return; // Exit early if plugin is disabled
        }

        updateStatus("Loading uploaded files...");
        // Clear both lists and show loading state
        uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;
        manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Loading...</p>`;

        try {
            const response = await fetch('/api/files');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const files = await response.json();

            // Clear lists again before populating
            uploadedFilesList.innerHTML = '';
            manageFilesList.innerHTML = '';

            if (files.length === 0) {
                uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No files uploaded yet.</p>`;
                manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">No files uploaded yet.</p>`;
            } else {
                files.forEach(file => {
                    const isSelected = selectedFiles.some(f => f.id === file.id);

                    // --- Create Sidebar List Item ---
                    const sidebarItemDiv = document.createElement('div');
                    sidebarItemDiv.classList.add('file-list-item', 'flex', 'items-center', 'p-1', 'border-b', 'border-rz-sidebar-border', 'last:border-b-0');
                    sidebarItemDiv.dataset.fileId = file.id;
                    sidebarItemDiv.dataset.filename = file.filename;
                    if (isSelected) sidebarItemDiv.classList.add('active-selection');

                    const sidebarCheckbox = document.createElement('input');
                    sidebarCheckbox.type = 'checkbox';
                    sidebarCheckbox.value = file.id;
                    sidebarCheckbox.classList.add('file-checkbox', 'mr-2');
                    sidebarCheckbox.title = "Select file for attachment";
                    sidebarCheckbox.checked = isSelected;

                    const sidebarNameSpan = document.createElement('span');
                    sidebarNameSpan.textContent = file.filename;
                    sidebarNameSpan.classList.add('filename', 'truncate', 'flex-grow', 'text-sm', 'text-rz-sidebar-text');
                    sidebarNameSpan.title = file.filename;

                    sidebarItemDiv.appendChild(sidebarCheckbox);
                    sidebarItemDiv.appendChild(sidebarNameSpan);
                    uploadedFilesList.appendChild(sidebarItemDiv);

                    // Add event listener to sidebar checkbox
                    sidebarCheckbox.addEventListener('change', (e) => {
                        const fileId = parseInt(e.target.value);
                        const listItem = e.target.closest('.file-list-item');
                        const filename = listItem.dataset.filename;
                        // Find the corresponding item in the modal list (no checkbox there)
                        const modalItem = manageFilesList.querySelector(`.file-list-item[data-file-id="${fileId}"]`);

                        if (e.target.checked) {
                            // Add to selectedFiles if not already there (handles both full/summary)
                            // We don't know *how* it will be attached yet (full/summary), just that it's selected
                            // The actual type is determined when attachFull/attachSummary is clicked.
                            // For now, just mark it as selected. We'll refine `attachSelectedFiles`.
                            if (!selectedFiles.some(f => f.id === fileId)) {
                                 // Add a placeholder entry, type will be determined later
                                 selectedFiles.push({ id: fileId, filename: filename, type: 'pending' });
                            }
                            listItem.classList.add('active-selection');
                            if (modalItem) modalItem.classList.add('active-selection'); // Sync modal styling
                        } else {
                            // Remove ALL entries for this file ID from selectedFiles
                            selectedFiles = selectedFiles.filter(f => f.id !== fileId);
                            listItem.classList.remove('active-selection');
                            if (modalItem) modalItem.classList.remove('active-selection'); // Sync modal styling
                        }
                        renderSelectedFiles(); // Update the display below the message input
                    });


                    // --- Create Modal List Item ---
                    const modalItemDiv = document.createElement('div');
                    // Use grid for layout: filename/type | date/summary | actions
                    modalItemDiv.classList.add('file-list-item', 'grid', 'grid-cols-12', 'gap-2', 'items-center', 'p-2', 'border-b', 'border-gray-200', 'last:border-b-0', 'text-sm'); // Added grid classes and text-sm
                    modalItemDiv.dataset.fileId = file.id;
                    modalItemDiv.dataset.filename = file.filename;
                    modalItemDiv.dataset.hasSummary = file.has_summary;
                     if (isSelected) modalItemDiv.classList.add('active-selection'); // Keep styling sync


                    // Column 1: Filename and Type
                    const fileInfoDiv = document.createElement('div');
                    fileInfoDiv.classList.add('col-span-5', 'flex', 'flex-col', 'min-w-0'); // Span 5 columns, flex column layout

                    const modalNameSpan = document.createElement('span');
                    modalNameSpan.textContent = file.filename;
                    modalNameSpan.classList.add('filename', 'truncate', 'font-medium'); // Added font-medium, text-gray-800
                    modalNameSpan.title = file.filename;

                    const modalTypeSpan = document.createElement('span');
                    modalTypeSpan.textContent = `Type: ${file.mimetype ? file.mimetype.split('/')[1] || file.mimetype : 'unknown'}`; // Display simplified type
                    modalTypeSpan.classList.add('file-type-display', 'text-xs', 'text-gray-500'); // Added styling

                    fileInfoDiv.appendChild(modalNameSpan);
                    fileInfoDiv.appendChild(modalTypeSpan);


                    // Column 2: Upload Date and Summary Status
                    const detailsDiv = document.createElement('div');
                    detailsDiv.classList.add('col-span-4', 'flex', 'flex-col', 'min-w-0'); // Span 4 columns, flex column layout

                    const uploadDateSpan = document.createElement('span');
                    let dateString = file.uploaded_at; // *** FIX: Use uploaded_at ***

                    let formattedDate = 'Date N/A'; // Default if date is missing or invalid

                    if (dateString && typeof dateString === 'string') {
                         // Attempt to make the date string more reliably parseable by replacing space with 'T'
                         // This assumes a format like 'YYYY-MM-DD HH:MM:SS' or similar
                         if (dateString.includes(' ')) {
                             dateString = dateString.replace(' ', 'T');
                         }
                         const date = new Date(dateString);
                         if (!isNaN(date.getTime())) { // Check if the date is valid using getTime()
                             formattedDate = date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
                         }
                    }


                    uploadDateSpan.textContent = `Uploaded: ${formattedDate}`;
                    uploadDateSpan.classList.add('text-xs', 'text-gray-500');

                    const summaryStatusSpan = document.createElement('span');
                    summaryStatusSpan.textContent = file.has_summary ? 'Summary: Yes' : 'Summary: No';
                    summaryStatusSpan.classList.add('text-xs', file.has_summary ? 'text-green-600' : 'text-gray-500'); // Color based on summary existence

                    detailsDiv.appendChild(uploadDateSpan);
                    detailsDiv.appendChild(summaryStatusSpan);


                    // Column 3: Actions (Summary and Delete buttons)
                    const modalActionsDiv = document.createElement('div');
                    modalActionsDiv.classList.add('col-span-3', 'flex', 'items-center', 'justify-end', 'gap-1'); // Span 3 columns, flex, justify-end

                    const summaryBtn = document.createElement('button');
                    summaryBtn.classList.add('btn', 'btn-outline', 'btn-xs', 'p-1');
                    summaryBtn.innerHTML = '<i class="fas fa-file-alt"></i>';
                    summaryBtn.title = file.has_summary ? "View/Edit Summary" : "Generate Summary";
                    summaryBtn.disabled = false;
                    summaryBtn.onclick = (e) => {
                        e.stopPropagation();
                        showSummaryModal(file.id, file.filename);
                    };
                    modalActionsDiv.appendChild(summaryBtn);

                    const deleteBtn = document.createElement('button');
                    deleteBtn.classList.add('btn', 'btn-outline', 'btn-xs', 'delete-btn', 'p-1');
                    deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
                    deleteBtn.title = "Delete File";
                    deleteBtn.onclick = (e) => {
                        e.stopPropagation();
                        deleteFile(file.id); // This is the call that was failing
                    };
                    modalActionsDiv.appendChild(deleteBtn);

                    modalItemDiv.appendChild(fileInfoDiv);
                    modalItemDiv.appendChild(detailsDiv);
                    modalItemDiv.appendChild(modalActionsDiv);
                    manageFilesList.appendChild(modalItemDiv); // Append to the modal list

                     // No event listener needed for modal item click itself, actions are on buttons
                });
            }
            updateStatus("Uploaded files loaded.");
        } catch (error) {
            console.error('Error loading uploaded files:', error);
            uploadedFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
            manageFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
            updateStatus("Error loading files.", true);
            throw error; // Re-throw the error
        }
    }


    /** Handles file upload triggered from the modal. */
    function handleFileUpload(event) {
        // Only allow if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
            fileUploadModalInput.value = ''; // Reset input
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("File uploads are only available in the Chat section.", true);
             fileUploadModalInput.value = ''; // Reset input
             return;
         }


        const files = event.target.files;
        if (!files || files.length === 0) return;
        setLoadingState(true, "Uploading");
        // updateStatus("Uploading files..."); // Status bar already updated by setLoadingState

        const formData = new FormData();
        let fileCount = 0;
        for (const file of files) {
            if (file.size > MAX_FILE_SIZE_BYTES) {
                alert(`Skipping "${file.name}": File is too large (${formatFileSize(file.size)}). Max size is ${MAX_FILE_SIZE_MB} MB.`);
                continue;
            }
            formData.append('file', file);
            fileCount++;
        }
        if (fileCount === 0) {
            setLoadingState(false);
            fileUploadModalInput.value = ''; // Reset modal file input
            updateStatus("No valid files selected for upload.", true);
            return;
        }
        fetch('/api/files', {
            method: 'POST',
            body: formData
        }).then(async response => {
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }
            const successfulUploads = data.uploaded_files?.length || 0;
            const errors = data.errors || [];
            let statusMsg = `Uploaded ${successfulUploads} file(s).`;
            if (errors.length > 0) {
                statusMsg += ` ${errors.length} failed: ${errors.join('; ')}`;
                console.warn("Upload errors:", errors);
            }
            updateStatus(statusMsg, errors.length > 0);
        }).catch(error => {
            console.error('Error uploading files:', error);
            updateStatus(`Error uploading files: ${error.message}`, true);
        }).finally(async () => {
            await loadUploadedFiles(); // Reload *both* lists
            setLoadingState(false);
            fileUploadModalInput.value = ''; // Reset modal file input
        });
    }

    // New function to handle adding file from URL (triggered from Manage Files Modal)
    async function addFileFromUrl(url) {
        if (isLoading) return;
        // Only allow if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            urlStatus.textContent = "Files plugin is disabled in settings.";
            urlStatus.classList.add('text-red-500');
            updateStatus("Files plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Adding files from URL is only available in the Chat section.", true);
             urlStatus.textContent = "Adding files from URL is only available in the Chat section.";
             urlStatus.classList.add('text-red-500');
             return;
         }


        if (!url || !url.startsWith('http')) {
            urlStatus.textContent = "Please enter a valid URL (must start with http or https).";
            urlStatus.classList.add('text-red-500');
            return;
        }

        setLoadingState(true, "Fetching URL");
        urlStatus.textContent = "Fetching content...";
        urlStatus.classList.remove('text-red-500');

        try {
            const response = await fetch('/api/files/from_url', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP error! status: ${response.status}`);
            }

            updateStatus(`Successfully added file from URL: ${data.filename}`);
            urlStatus.textContent = `Successfully added file: ${data.filename}`;
            urlStatus.classList.remove('text-red-500'); // Clear error styling
            urlInput.value = ''; // Clear input on success
            await loadUploadedFiles(); // Reload *both* file lists
            closeUrlModal(); // Close the URL modal

        } catch (error) {
            console.error('Error adding file from URL:', error);
            updateStatus(`Error adding file from URL: ${error.message}`, true);
            urlStatus.textContent = `Error: ${error.message}`;
            urlStatus.classList.add('text-red-500');
        } finally {
            setLoadingState(false);
        }
    }

    /** Attaches selected files from the sidebar list to the current chat. */
    function attachSelectedFiles(type) {
        // Only allow if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Attaching files is only available in the Chat section.", true);
             return;
         }


        // Get checkboxes from the list *inside the sidebar*
        const checkboxes = uploadedFilesList.querySelectorAll('.file-checkbox:checked');
        if (checkboxes.length === 0) {
            updateStatus("No files selected to attach.", true);
            return;
        }
        let addedCount = 0;
        checkboxes.forEach(checkbox => {
            const fileId = parseInt(checkbox.value);
            const listItem = checkbox.closest('.file-list-item');
            const filename = listItem.dataset.filename;

            // Remove any existing attachment for this file ID before adding the new one (either full or summary)
            selectedFiles = selectedFiles.filter(f => f.id !== fileId);

            // Add the file with the specified type
            selectedFiles.push({
                id: fileId,
                filename: filename,
                type: type
            });
            addedCount++;
            // Keep checkboxes checked in the sidebar for visual feedback until they are manually unchecked
        });
        renderSelectedFiles(); // Update the display below the message input
        if (addedCount > 0) {
            updateStatus(`${addedCount} file(s) added as ${type} for the next message.`);
        } else {
            // This case should ideally not happen if checkboxes.length > 0, but good for safety
            updateStatus(`Selected file(s) already attached as ${type}.`);
        }
        // Checkboxes remain checked in the sidebar until manually unchecked or chat changes
    }

    /** Renders the list of files currently selected for attachment below the message input. */
    function renderSelectedFiles() {
        // Clear only non-session file tags
        selectedFilesContainer.querySelectorAll('.selected-file-tag:not(.session-file-tag)').forEach(tag => tag.remove());

        // Render plugin-selected files
        // Only render if Files plugin is enabled, otherwise clear any pending selections
        if (isFilePluginEnabled) {
            selectedFiles.forEach(file => {
                // Only render tags for files that have a type assigned (i.e., attached via full/summary buttons)
                // Files with type 'pending' are just selected in the list but not yet attached for the *next* message
                if (file.type !== 'pending') {
                    const tag = document.createElement('span');
                    tag.classList.add('selected-file-tag'); // No session-file-tag class here
                    tag.innerHTML = `
                        <span class="filename truncate" title="${file.filename}">${file.filename}</span>
                        <span class="file-type">${file.type.toUpperCase()}</span>
                        <button title="Remove Attachment">&times;</button>
                    `;
                    // When removing, remove ALL entries for this file ID (both full/summary if somehow duplicated)
                    tag.querySelector('button').onclick = () => removeSelectedFile(file.id);
                    selectedFilesContainer.appendChild(tag); // Append plugin files
                }
            });
        } else {
            // If Files plugin is disabled, clear all permanent file selections
            selectedFiles = [];
            // The session file tag (if any) remains because session files are handled separately
        }


        // Update container visibility based on whether *any* tags exist (session or plugin with type != 'pending')
        const visibleTags = selectedFilesContainer.querySelectorAll('.selected-file-tag');
        if (visibleTags.length === 0) {
            selectedFilesContainer.classList.add('hidden');
        } else {
            selectedFilesContainer.classList.remove('hidden');
        }
    }

    /** Removes a file from the list of files selected for attachment. */
    function removeSelectedFile(fileId) {
        // Remove ALL entries for this file ID (both full/summary if somehow duplicated)
        selectedFiles = selectedFiles.filter(f => f.id !== fileId);
        renderSelectedFiles();
        updateStatus(`File attachment removed.`);

        // Uncheck the corresponding checkbox in the sidebar list
        const sidebarCheckbox = uploadedFilesList.querySelector(`.file-list-item[data-file-id="${fileId}"] .file-checkbox`);
        if (sidebarCheckbox) {
            sidebarCheckbox.checked = false;
            sidebarCheckbox.closest('.file-list-item').classList.remove('active-selection');
        }
        // If the manage files modal is open, remove the active-selection class (no checkboxes there)
        if (manageFilesModal.style.display === 'block') {
            const modalItem = manageFilesList.querySelector(`.file-list-item[data-file-id="${fileId}"]`);
            if (modalItem) {
                modalItem.classList.remove('active-selection');
            }
        }
    }


    // --- Summary Modal Functions ---
    async function showSummaryModal(fileId, filename) {
        if (isLoading) return;
        // Only show if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("File summaries are only available in the Chat section.", true);
             return;
         }

        currentEditingFileId = fileId;
        summaryModalFilename.textContent = filename;
        summaryTextarea.value = "";
        summaryTextarea.placeholder = "Loading or generating summary...";
        summaryStatus.textContent = "";
        summaryStatus.classList.remove('text-red-500');
        summaryModal.style.display = "block";
        saveSummaryButton.disabled = true;
        updateStatus(`Fetching summary for ${filename}...`);
        try {
            const response = await fetch(`/api/files/${fileId}/summary`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            const data = await response.json();
            summaryTextarea.value = data.summary;
            summaryTextarea.placeholder = "Enter or edit summary here.";
            saveSummaryButton.disabled = false;
            updateStatus(`Summary loaded for ${filename}.`);
            if (data.summary.startsWith("[Error") || data.summary.startsWith("[Summary not applicable")) {
                summaryStatus.textContent = data.summary;
                summaryStatus.classList.add('text-red-500');
                saveSummaryButton.disabled = data.summary.startsWith("[Summary not applicable");
            } else {
                summaryStatus.textContent = "Summary loaded. You can edit and save changes.";
            }
        } catch (error) {
            console.error("Error fetching summary:", error);
            summaryTextarea.value = `[Error loading summary: ${error.message}]`;
            summaryTextarea.placeholder = "Could not load summary.";
            updateStatus(`Error fetching summary for ${filename}.`, true);
            summaryStatus.textContent = `Error: ${error.message}`;
            summaryStatus.classList.add('text-red-500');
            // No re-throw needed here as this is not part of the critical init path
        } finally {
            setLoadingState(false);
        }
    }
    async function saveSummary() {
        if (!currentEditingFileId || isLoading) return;
        // Only allow if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Saving summaries is only available in the Chat section.", true);
             return;
         }

        const updatedSummary = summaryTextarea.value;
        setLoadingState(true, "Saving Summary");
        summaryStatus.textContent = "Saving...";
        summaryStatus.classList.remove('text-red-500');
        try {
            const response = await fetch(`/api/files/${currentEditingFileId}/summary`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    summary: updatedSummary
                })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            updateStatus("Summary saved successfully.");
            summaryStatus.textContent = "Summary saved!";
            await loadUploadedFiles(); // Reload *both* file lists to update summary status
            closeModal(summaryModal); // Close the summary modal
        } catch (error) {
            console.error("Error saving summary:", error);
            updateStatus("Error saving summary.", true);
            summaryStatus.textContent = `Error saving: ${error.message}`;
            summaryStatus.classList.add('text-red-500');
            // No re-throw needed here
        } finally {
            setLoadingState(false);
        }
    }

    /** Generic function to close a modal. */
    function closeModal(modalElement) {
        modalElement.style.display = "none";
        // If the closed modal was the summary modal, clear the editing state
        if (modalElement === summaryModal) {
            currentEditingFileId = null;
        }
         // If the closed modal was the URL modal, ensure focus returns to the Manage Files modal if it's open
         if (modalElement === urlModal && manageFilesModal.style.display === 'block') {
             // No specific element to focus in the manage files modal, maybe just ensure it's interactive
         } else if (modalElement === manageFilesModal) {
             // If the manage files modal was closed, ensure focus returns to message input (if on chat tab)
             if (!isLoading && urlModal.style.display !== 'block' && summaryModal.style.display !== 'block' && settingsModal.style.display !== 'block' && markdownTipsModal.style.display !== 'block' && !bodyElement.classList.contains('sidebar-collapsed') && !bodyElement.classList.contains('plugins-collapsed')) {
                 if (currentTab === 'chat') messageInput.focus();
             }
         } else if (modalElement === settingsModal) {
             // If the settings modal was closed, ensure focus returns to message input/notes textarea
             if (!isLoading && manageFilesModal.style.display !== 'block' && urlModal.style.display !== 'block' && summaryModal.style.display !== 'block' && markdownTipsModal.style.display !== 'block' && !bodyElement.classList.contains('sidebar-collapsed') && !bodyElement.classList.contains('plugins-collapsed')) {
                 if (currentTab === 'chat') messageInput.focus();
                 else if (currentTab === 'notes' && currentNoteMode === 'edit') notesTextarea.focus(); // Only focus textarea if in edit mode
             }
         } else if (modalElement === markdownTipsModal) { // New: Handle closing markdown tips modal
             // If the markdown tips modal was closed, ensure focus returns to the notes textarea (if on notes tab and in edit mode)
             if (!isLoading && manageFilesModal.style.display !== 'block' && urlModal.style.display !== 'block' && summaryModal.style.display !== 'block' && settingsModal.style.display !== 'block' && !bodyElement.classList.contains('sidebar-collapsed') && !bodyElement.classList.contains('plugins-collapsed')) {
                 if (currentTab === 'notes' && currentNoteMode === 'edit') notesTextarea.focus();
             }
         }
         else {
             // Default case, focus message input/notes textarea if no modals are open
             if (!isLoading && manageFilesModal.style.display !== 'block' && urlModal.style.display !== 'block' && summaryModal.style.display !== 'block' && settingsModal.style.display !== 'block' && markdownTipsModal.style.display !== 'block' && !bodyElement.classList.contains('sidebar-collapsed') && !bodyElement.classList.contains('plugins-collapsed')) {
                 if (currentTab === 'chat') messageInput.focus();
                 else if (currentTab === 'notes' && currentNoteMode === 'edit') notesTextarea.focus(); // Only focus textarea if in edit mode
             }
         }
    }


    // New URL Modal Functions (Triggered from Manage Files Modal)
    function showUrlModal() {
        if (isLoading) return;
        // Only show if Files plugin is enabled AND we are on the chat tab
        if (!isFilePluginEnabled) {
            updateStatus("Files plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Adding files from URL is only available in the Chat section.", true);
             return;
         }

        urlInput.value = ''; // Clear previous input
        urlStatus.textContent = ''; // Clear previous status
        urlStatus.classList.remove('text-red-500');
        urlModal.style.display = "block"; // Show the URL modal on top of Manage Files modal
        setTimeout(() => urlInput.focus(), 100); // Focus input after modal is displayed
    }

    function closeUrlModal() {
        closeModal(urlModal); // Use generic close modal function
    }


    // --- Calendar Plugin Functions (MODIFIED) ---
    /** Fetches calendar events and updates state/UI. */
    async function loadCalendarEvents() {
        if (isLoading) return;
        // Only load if Calendar plugin is enabled AND we are on the chat tab
        if (!isCalendarPluginEnabled) {
            updateStatus("Calendar plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Calendar events can only be loaded in the Chat section.", true);
             return;
         }

        setLoadingState(true, "Loading Events");
        updateStatus("Loading calendar events...");

        try {
            const response = await fetch('/api/calendar/events');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP error ${response.status}`);
            }

            calendarContext = data.events || "[No event data received]"; // Store formatted events
            updateCalendarStatus(); // Update status display based on loaded context and toggle state
            viewCalendarButton.classList.remove('hidden'); // Show view button
            viewCalendarButton.disabled = false;
            updateStatus("Calendar events loaded.");

        } catch (error) {
            console.error('Error loading calendar events:', error);
            calendarContext = null; // Clear context on error
            updateCalendarStatus(); // Update status display
            viewCalendarButton.classList.add('hidden'); // Hide view button
            viewCalendarButton.disabled = true;
            addMessage('system', `[Error loading calendar events: ${error.message}]`, true); // Show error in chat
            updateStatus(`Error loading calendar events: ${error.message}`, true);
            // No re-throw needed here as this is not part of the critical init path
        } finally {
            setLoadingState(false);
        }
    }

    /** Updates the calendar status text based on loaded context and toggle state. */
    function updateCalendarStatus() {
        // Only update status if Calendar plugin is enabled
        if (isCalendarPluginEnabled) {
            if (calendarContext) {
                calendarStatus.textContent = `Status: Events loaded. Context: ${isCalendarContextActive ? 'Active' : 'Inactive'}`;
                calendarStatus.classList.remove('text-red-500');
            } else {
                calendarStatus.textContent = "Status: Not loaded";
                calendarStatus.classList.remove('text-red-500');
            }
        } else {
            calendarStatus.textContent = "Status: Plugin disabled";
            calendarStatus.classList.remove('text-red-500'); // Remove error color if it was there
        }
    }

    /** Handles changes to the calendar context toggle switch (next to message input). */
    function handleCalendarToggle() {
        // Only allow toggle if Calendar plugin is enabled AND we are on the chat tab
        if (!isCalendarPluginEnabled) {
            calendarToggle.checked = false; // Force off if plugin disabled
            updateStatus("Calendar plugin is disabled in settings.", true);
            return;
        }
         if (currentTab !== 'chat') {
             calendarToggle.checked = false; // Force off if not on chat tab
             updateStatus("Calendar context is only available in the Chat section.", true);
             return;
         }

        isCalendarContextActive = calendarToggle.checked;
        localStorage.setItem('calendarContextActive', isCalendarContextActive); // Persist toggle state
        updateCalendarStatus(); // Update display text
    }

    /** Shows the modal with the loaded calendar events. */
    function showCalendarModal() {
        // Only show if Calendar plugin is enabled and context exists AND we are on the chat tab
        if (!isCalendarPluginEnabled) {
             updateStatus("Calendar plugin is disabled in settings.", true);
             return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Viewing calendar events is only available in the Chat section.", true);
             return;
         }

        if (calendarContext) {
            calendarModalContent.textContent = calendarContext; // Display raw text in <pre>
            calendarModal.style.display = 'block';
        } else {
            updateStatus("No calendar events loaded to view.", true);
        }
    }

    function clearChatbox() {
        // Ensure chatbox element exists before clearing
        const chatboxElement = chatbox;
        if (chatboxElement) {
            chatboxElement.innerHTML = '';
        } else {
            console.error("Chatbox element with ID 'chatbox' not found. Cannot clear chatbox.");
        }
    }


    async function loadSavedChats() {
        updateStatus("Loading saved chats...");
        // console.log("[DEBUG] loadSavedChats called."); // Reduced verbosity
        try {
            const response = await fetch('/api/chats');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const chats = await response.json();
            savedChatsList.innerHTML = '';
            if (chats.length === 0) {
                savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved chats yet.</p>`;
            } else {
                chats.forEach(chat => {
                    const listItem = document.createElement('div');
                    listItem.classList.add('list-item', 'chat-list-item');
                    listItem.dataset.chatId = chat.id;

                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = chat.name || `Chat ${chat.id}`;
                    nameSpan.classList.add('filename');
                    nameSpan.title = chat.name || `Chat ${chat.id}`;

                    const timestampElement = document.createElement('div');
                    const date = new Date(chat.last_updated_at);
                    // Format the date (example)
                    const formattedDate = date.toLocaleString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit'
                    });

                    timestampElement.textContent = `Last updated: ${formattedDate}`;
                    timestampElement.classList.add('text-xs', 'text-rz-tab-background-text', 'mt-0.5'); // Styling for the timestamp


                    const deleteButton = document.createElement('button');
                    deleteButton.classList.add('delete-btn');
                    deleteButton.innerHTML = '<i class="fas fa-trash-alt fa-xs"></i>';
                    deleteButton.title = "Delete Chat";
                    deleteButton.onclick = (e) => {
                        e.stopPropagation();
                        handleDeleteChat(chat.id, listItem);
                    };


                    const nameContainer = document.createElement('div'); // Create a container
                    nameContainer.classList.add('name-container'); // for name and delete button

                    nameContainer.appendChild(nameSpan); // Add name to the container
                    nameContainer.appendChild(deleteButton); // Add button to container

                    listItem.appendChild(nameContainer); // Add the container to the list item
                    listItem.appendChild(timestampElement);

                    listItem.onclick = () => {
                        if (chat.id != currentChatId) {
                            loadChat(chat.id);
                        }
                    };
                    savedChatsList.appendChild(listItem);
                });
            }
            // updateActiveChatListItem(); // REMOVED: Highlighting is now handled by loadChat
            updateStatus("Saved chats loaded.");
            // console.log("[DEBUG] loadSavedChats finished successfully."); // Reduced verbosity
        } catch (error) {
            console.error('Error loading saved chats:', error);
            savedChatsList.innerHTML = '<p class="text-red-500 text-sm p-1">Error loading chats.</p>';
            updateStatus("Error loading saved chats.", true);
            // console.log("[DEBUG] loadSavedChats caught an error."); // Reduced verbosity
            throw error; // Re-throw the error
        } finally {
            // console.log(`[DEBUG] loadSavedChats finally block entered.`); // Added log
            setLoadingState(false); // <-- UNCOMMENTED THIS LINE
            // console.log("[DEBUG] setLoadingState(false) called in loadSavedChats finally block."); // Added log
        }
    }




    async function startNewChat() {
        // REMOVED: if (isLoading) return;
        setLoadingState(true, "Creating Chat");
        updateStatus("Creating new chat...");
        try {
            const response = await fetch('/api/chat', {
                method: 'POST'
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const newChat = await response.json();
            await loadChat(newChat.id); // loadChat sets currentChatId and calls updateActiveChatListItem
            await loadSavedChats(); // loadSavedChats populates the list, but doesn't highlight anymore
            updateStatus(`New chat created (ID: ${newChat.id}).`);
            setSidebarCollapsed(sidebar, sidebarToggleButton, false, SIDEBAR_COLLAPSED_KEY, 'sidebar');

            // Reset chat-specific context, but NOT plugin enabled states
            selectedFiles = []; // Clear permanent file selections
            sessionFile = null; // Clear session file state
            // Clear session file tag from container
            const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
            if (existingSessionTag) existingSessionTag.remove();
            renderSelectedFiles(); // Render (clears plugin files and updates visibility)
            fileUploadSessionInput.value = ''; // Reset file input

            calendarContext = null;
            isCalendarContextActive = false;
            calendarToggle.checked = false;
            updateCalendarStatus(); // Update status based on cleared context

            viewCalendarButton.classList.add('hidden');
            modelSelector.value = defaultModel;
            webSearchToggle.checked = false; // Reset web search toggle state for the new chat

            // Ensure plugin UI reflects the *current* enabled state (which wasn't reset)
            updatePluginUI();

            // loadUploadedFiles() is now called by loadChat, which is called here
        } catch (error) {
            console.error('Error starting new chat:', error);
            addMessage('system', `[Error creating new chat: ${error.message}]`, true);
            updateStatus("Error creating new chat.", true);
            // No re-throw needed here, initializeApp's catch will handle it if this was the first chat
        } finally {
            setLoadingState(false); // This one is NOT commented out.
        }
    }
    async function loadChat(chatId) {
        // console.log(`[DEBUG] loadChat(${chatId}) called.`); // Reduced verbosity
        // REMOVED: if (isLoading) { console.log(`[DEBUG] loadChat(${chatId}) skipped, isLoading is true.`); return; }
        setLoadingState(true, "Loading Chat");
        updateStatus(`Loading chat ${chatId}...`);
        clearChatbox();
        addMessage('system', `Loading chat (ID: ${chatId})...`);
        // console.log(`[DEBUG] Chatbox cleared and loading message added for chat ${chatId}.`); // Reduced verbosity

        try {
            // console.log(`[DEBUG] Fetching chat data for chat ${chatId}...`); // Reduced verbosity
            const response = await fetch(`/api/chat/${chatId}`);
            if (!response.ok) {
                const errorText = await response.text(); // Get text for more info
                throw new Error(`HTTP error! status: ${response.status} ${response.statusText} - ${errorText}`);
            }
            const data = await response.json();
            // console.log(`[DEBUG] Chat data fetched successfully for chat ${chatId}.`); // Reduced verbosity

            currentChatId = chatId;
            // console.log(`[DEBUG] currentChatId set to ${currentChatId}.`); // Reduced verbosity

            clearChatbox(); // Clear the loading message
            currentChatNameInput.value = data.details.name || '';
            currentChatIdDisplay.textContent = `ID: ${currentChatId}`;
            modelSelector.value = data.details.model_name || defaultModel;

            // console.log(`[DEBUG] Populating chat history for chat ${chatId}. History length: ${data.history.length}`); // Reduced verbosity
            if (data.history.length === 0) {
                addMessage('system', 'This chat is empty. Start typing!');
            } else {
                data.history.forEach(msg => {
                    addMessage(msg.role, msg.content);
                });
            }
            // console.log(`[DEBUG] Chat history populated for chat ${chatId}.`); // Reduced verbosity


            // Reset chat-specific context, but NOT plugin enabled states
            selectedFiles = []; // Clear permanent file selections
            sessionFile = null; // Clear session file state
            // Clear session file tag from container
            const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
            if (existingSessionTag) existingSessionTag.remove();
            renderSelectedFiles(); // Render (clears plugin files and updates visibility)
            fileUploadSessionInput.value = ''; // Reset file input
            // console.log(`[DEBUG] Chat context (files, session file) reset for chat ${chatId}.`); // Reduced verbosity


            calendarContext = null;
            isCalendarContextActive = false;
            calendarToggle.checked = isCalendarContextActive; // Ensure UI matches state
            updateCalendarStatus(); // Update status based on cleared context
            viewCalendarButton.classList.add('hidden');
            // console.log(`[DEBUG] Calendar context reset for chat ${chatId}.`); // Reduced verbosity

            webSearchToggle.checked = false; // Reset web search toggle state for the loaded chat
            // console.log(`[DEBUG] Web search toggle reset for chat ${chatId}.`); // Reduced verbosity


            // Ensure plugin UI reflects the *current* enabled state (which wasn't reset)
            updatePluginUI();
            // console.log(`[DEBUG] Plugin UI updated based on settings for chat ${chatId}.`); // Reduced verbosity


            // Load files for the new chat context (files are global, but list needs refreshing)
            // Only load files if the plugin is enabled
            if (isFilePluginEnabled) {
                 // console.log(`[DEBUG] Files plugin enabled, loading uploaded files for chat ${chatId}.`); // Reduced verbosity
                 await loadUploadedFiles(); // This might re-throw, which is caught by the catch block below
                 // console.log(`[DEBUG] loadUploadedFiles completed for chat ${chatId}.`); // Reduced verbosity
            } else {
                 // console.log(`[DEBUG] Files plugin disabled, skipping loadUploadedFiles for chat ${chatId}.`); // Reduced verbosity
                 // If plugin is disabled, clear the lists and show disabled message
                 uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
                 manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
            }

            // Update chat list highlighting AFTER everything else is loaded/rendered
            updateActiveChatListItem(); // <-- Keep this call here
            // console.log(`[DEBUG] updateActiveChatListItem called for chat ${chatId}.`); // Reduced verbosity


            updateStatus(`Chat ${chatId} loaded.`);
            // console.log(`[DEBUG] loadChat(${chatId}) finished successfully.`); // Reduced verbosity


        } catch (error) { // <-- This will now catch errors from fetch('/api/chat') AND re-thrown errors from loadUploadedFiles
            console.error('Error loading chat:', error);
            clearChatbox(); // Clear any partial history or loading message
            addMessage('system', `[Error loading chat ${chatId}: ${error.message}]`, true);
            // console.log(`[DEBUG] Error message added to chatbox for chat ${chatId}.`); // Reduced verbosity

            currentChatId = null; // Clear current chat state on error
            currentChatNameInput.value = '';
            currentChatIdDisplay.textContent = 'ID: -';
            modelSelector.value = defaultModel;
            // console.log(`[DEBUG] Chat state reset on error for chat ${chatId}.`); // Reduced verbosity

            updateStatus(`Error loading chat ${chatId}.`, true);
            // console.log(`[DEBUG] Status updated for error loading chat ${chatId}.`); // Reduced verbosity

            updateActiveChatListItem(); // Update highlighting (should remove highlight)
            // console.log(`[DEBUG] updateActiveChatListItem called after error for chat ${chatId}.`); // Reduced verbosity

            // Reset chat-specific context again on error to be safe
            selectedFiles = [];
            sessionFile = null;
            const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
            if (existingSessionTag) existingSessionTag.remove();
            renderSelectedFiles();
            fileUploadSessionInput.value = '';
            calendarContext = null;
            isCalendarContextActive = false;
            calendarToggle.checked = isCalendarContextActive;
            updateCalendarStatus();
            viewCalendarButton.classList.add('hidden');
            webSearchToggle.checked = false; // Reset web search toggle state on error
            // console.log(`[DEBUG] Chat context reset again on error for chat ${chatId}.`); // Reduced verbosity


            // Ensure plugin UI reflects the *current* enabled state even on error
            updatePluginUI();
            // console.log(`[DEBUG] Plugin UI updated after error for chat ${chatId}.`); // Reduced verbosity

            // Clear file lists if plugin enabled (as they might be stale)
            if (isFilePluginEnabled) {
                 uploadedFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
                 manageFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
                 // console.log(`[DEBUG] File lists cleared/error state set after error loading chat ${chatId}.`); // Reduced verbosity
            }


            throw error; // Re-throw the error so initializeApp's catch block can handle it if this was the initial load
        } finally {
            // console.log(`[DEBUG] loadChat(${chatId}) finally block entered.`); // Added log
            setLoadingState(false); // <-- UNCOMMENTED THIS LINE
            // console.log("[DEBUG] setLoadingState(false) called in loadChat finally block."); // Added log
        }
    }

    /** Sends message, attached files, and optionally calendar context to backend. */
    async function sendMessage() {
        if (isLoading || !currentChatId) {
            updateStatus("Cannot send message: No active chat or busy.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Messages can only be sent in the Chat section.", true);
             return;
         }

        const message = messageInput.value.trim();

        // Filter selectedFiles to only include those marked for attachment (type !== 'pending')
        // Only include permanent files if the Files plugin is enabled
        const filesToAttach = isFilePluginEnabled ? selectedFiles.filter(f => f.type !== 'pending') : [];

        // Only include session file if the Files plugin is enabled
        const sessionFileToSend = isFilePluginEnabled ? sessionFile : null;

        // Only include calendar context if the Calendar plugin is enabled AND the toggle is active AND context exists
        const calendarContextToSend = (isCalendarPluginEnabled && isCalendarContextActive && calendarContext) ? calendarContext : null;

        // Web search is only enabled if the plugin is enabled AND the user's toggle is checked
        const webSearchEnabledToSend = isWebSearchPluginEnabled && webSearchToggle.checked;


        if (!message && filesToAttach.length === 0 && !sessionFileToSend && !calendarContextToSend && !webSearchEnabledToSend) {
            updateStatus("Cannot send: Type a message or attach file(s)/active context/enable web search.", true);
            return;
        }

        // Clear the input field immediately
        messageInput.value = '';

        // --- Display user message + UI markers immediately ---
        let displayMessage = message || ((filesToAttach.length > 0 || sessionFileToSend || calendarContextToSend || webSearchEnabledToSend) ? "(Context attached)" : "");
        let uiMarkers = "";
        if (filesToAttach.length > 0) {
            // Use non-HTML placeholder for files
            uiMarkers += filesToAttach.map(f => `\[UI-MARKER:file:${f.filename}:${f.type}\]`).join(''); // Escaped brackets
        }
         if (sessionFileToSend) { // Add marker for session file
            uiMarkers += `\[UI-MARKER:file:${sessionFileToSend.filename}:session\]`; // Escaped brackets
        }
        if (calendarContextToSend) {
            // Use non-HTML placeholder for calendar
            uiMarkers += `\[UI-MARKER:calendar\]`; // Escaped brackets
        }
        if (webSearchEnabledToSend) { // Add marker for web search
            uiMarkers += `\[UI-MARKER:websearch\]`; // Escaped brackets
        }

        // Prepend placeholders to the actual message text
        displayMessage = uiMarkers + (uiMarkers ? "\n" : "") + displayMessage; // Add newline if markers exist
        addMessage('user', displayMessage); // addMessage will handle replacing placeholders


        setLoadingState(true, "Sending");
        updateStatus("Sending message...");

        // --- Prepare payload for backend ---
        const payload = {
            chat_id: currentChatId, // Ensure chat_id is included in the payload
            message: message,
            attached_files: filesToAttach, // Send only files marked for attachment (and if plugin enabled)
            calendar_context: calendarContextToSend, // Send context only if plugin enabled and toggle active
            // Use the stored sessionFile object which now includes content (only if plugin enabled)
            session_files: sessionFileToSend ? [{
                filename: sessionFileToSend.filename,
                content: sessionFileToSend.content,
                mimetype: sessionFileToSend.mimetype
            }] : [],
            enable_web_search: webSearchEnabledToSend, // Add the web search flag (controlled by plugin setting AND user toggle)
            enable_streaming: isStreamingEnabled, // Add the streaming flag
            // Add plugin enabled states to the payload
            enable_files_plugin: isFilePluginEnabled,
            enable_calendar_plugin: isCalendarPluginEnabled,
            enable_web_search_plugin: isWebSearchPluginEnabled // New: Add web search plugin state
        };

        // Store session file temporarily to clear it in finally block
        const sentSessionFile = sessionFile;

        let assistantMessageElement = null; // Element to append streamed content to

        try {
            const response = await fetch(`/api/chat/${currentChatId}/message`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                // Handle non-streaming errors (e.e., 400, 500)
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            if (isStreamingEnabled && response.headers.get('Content-Type')?.includes('text/plain')) {
                 // --- Handle Streaming Response ---
                 assistantMessageElement = addMessage('assistant', ''); // Add an empty message element to start
                 if (!assistantMessageElement) { // Check if addMessage failed
                     throw new Error("Failed to create assistant message element for streaming.");
                 }
                 const reader = response.body.getReader();
                 const decoder = new TextDecoder();
                 let receivedText = '';

                 while (true) {
                     const { done, value } = await reader.read();
                     if (done) {
                         break;
                     }
                     const chunk = decoder.decode(value, { stream: true });
                     receivedText += chunk;
                     // Append chunk to the message element
                     addMessage('assistant', chunk, false, assistantMessageElement);
                 }

                 // After streaming is done, apply markdown to the full accumulated text
                 // Note: The backend saves the full message, so we don't need to save here.
                 // We just need to render the final markdown.
                 // The addMessage function with targetElement appends escaped text.
                 // We need to get the full text from the element and re-render with markdown.
                 applyMarkdownToMessage(assistantMessageElement);

                 updateStatus("Assistant replied (streaming finished).");

            } else {
                // --- Handle Non-Streaming Response ---
                const data = await response.json();
                addMessage('assistant', data.reply);
                updateStatus("Assistant replied.");
            }

            await loadSavedChats(); // Reload chats to update timestamp

            // Clear ALL selected files (both 'pending' and attached types) after sending
            // This only clears the frontend state; the backend received the files it needed.
            selectedFiles = [];
            renderSelectedFiles(); // Update the display below the message input
            // Uncheck all checkboxes in the sidebar list
            uploadedFilesList.querySelectorAll('.file-checkbox').forEach(checkbox => {
                checkbox.checked = false;
                checkbox.closest('.file-list-item').classList.remove('active-selection');
            });
             // Remove active-selection class from modal items (no checkboxes there)
             if (manageFilesModal.style.display === 'block') {
                 manageFilesList.querySelectorAll('.file-list-item').forEach(item => {
                     item.classList.remove('active-selection');
                 });
             }


        } catch (error) {
            console.error('Error sending message:', error);
            const errorMessage = `[Error: ${error.message}]`;
            // If streaming started, append error to the existing element
            if (assistantMessageElement) {
                 addMessage('assistant', errorMessage, true, assistantMessageElement);
                 applyMarkdownToMessage(assistantMessageElement); // Apply markdown to the final state
            } else {
                 // If streaming didn't start or it was non-streaming, add a new error message
                 addMessage('assistant', errorMessage, true);
            }
            updateStatus("Error sending message.", true);
        } finally {
            // Clear the session file state and its tag if it was the one sent
            if (sentSessionFile && sessionFile === sentSessionFile) {
                sessionFile = null;
                const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
                if (existingSessionTag) existingSessionTag.remove();
                renderSelectedFiles(); // Update container visibility if needed
                fileUploadSessionInput.value = ''; // Reset file input
            }
            setLoadingState(false);
        }
    }
    async function handleSaveChatName() {
        if (isLoading) return; // Keep this check for user-initiated saves
        if (!currentChatId) {
            updateStatus("Cannot save name: No active chat.", true);
            return;
        }
         if (currentTab !== 'chat') {
             updateStatus("Chat name can only be saved in the Chat section.", true);
             return;
         }

        const newName = currentChatNameInput.value.trim();
        setLoadingState(true, "Saving Name");
        updateStatus(`Saving name for chat ${currentChatId}...`);
        try {
            const response = await fetch(`/api/chat/${currentChatId}/name`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: newName || 'New Chat'
                }),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            updateStatus(`Chat ${currentChatId} name saved as "${newName || 'New Chat'}".`);
            await loadSavedChats();
        } catch (error) {
            console.error('Error saving chat name:', error);
            updateStatus(`Error saving name: ${error.message}`, true);
        } finally {
            setLoadingState(false);
        }
    }
    async function handleDeleteChat(chatId, listItemElement) {
        if (isLoading) return; // Keep this check for user-initiated deletes
         if (currentTab !== 'chat') {
             updateStatus("Chats can only be deleted from the Chat section.", true);
             return;
         }

        const chatName = listItemElement.querySelector('span.filename').textContent || `Chat ${chatId}`;
        if (!confirm(`Are you sure you want to delete "${chatName}"? This cannot be undone.`)) {
            return;
        }
        setLoadingState(true, "Deleting Chat");
        updateStatus(`Deleting chat ${chatId}...`);
        try {
            // AWAIT the fetch call to ensure the backend deletion completes before proceeding
            const response = await fetch(`/api/chat/${chatId}`, {
                method: 'DELETE'
            });
            if (!response.ok) {
                 const errorData = await response.json(); // Get error details from backend
                 throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            updateStatus(`Chat ${chatId} deleted.`);
            listItemElement.remove(); // Remove from UI list *after* successful backend delete
            if (!savedChatsList.querySelector('.list-item')) {
                savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved chats yet.</p>`;
            }
            if (chatId == currentChatId) {
                await startNewChat(); // Start a new chat if the current one was deleted
            } else {
                 // If a different chat was deleted, just reload the list to be safe
                 await loadSavedChats();
            }
        } catch (error) {
            console.error(`Error deleting chat ${chatId}:`, error);
            updateStatus(`Error deleting chat: ${error.message}`, true);
            addMessage('system', `[Error deleting chat ${chatId}: ${error.message}]`, true);
            // If the delete failed, the item was removed from the UI prematurely.
            // loadSavedChats() is called in the success path or if the current chat was deleted.
            // If a non-current chat delete failed, loadSavedChats() isn't called here.
            // We should probably reload the list on *any* delete attempt failure to resync the UI.
            // However, loadSavedChats() is already called in the finally block of initializeApp
            // and loadChat. Let's rely on those for now, or add a specific reload here if needed.
            // For now, the fix is just adding await. If the backend returns an error,
            // the catch block runs, and the item won't be removed from the UI list *before* the error.
            // The list will only be reloaded on success or if the current chat is deleted.
            // This seems correct.
        } finally {
            setLoadingState(false);
        }
    }

    function updateActiveChatListItem() {
        // console.log(`[DEBUG] updateActiveChatListItem called. currentChatId: ${currentChatId}`); // Reduced verbosity
        const chatListItems = document.querySelectorAll('.chat-list-item');
        // console.log(`[DEBUG] Found ${chatListItems.length} chat list items.`); // Reduced verbosity

        chatListItems.forEach(item => {
            const chatId = parseInt(item.dataset.chatId);
            const timestampElement = item.querySelector('.text-xs'); // select the timestamp element

            if (chatId === currentChatId) {
                // console.log(`[DEBUG] Highlighting chat item ${chatId}`); // Reduced verbosity
                item.classList.add('active');
                timestampElement.classList.remove('text-rz-tab-background-text'); // Remove inactive color
                timestampElement.classList.add('text-rz-sidebar-text'); // Add active color
            } else {
                // console.log(`[DEBUG] Deactivating chat item ${chatId}`); // Reduced verbosity
                item.classList.remove('active');
                timestampElement.classList.remove('text-rz-sidebar-text'); // Remove active color
                timestampElement.classList.add('text-rz-tab-background-text'); // Add inactive color
            }
        });
         // console.log(`[DEBUG] updateActiveChatListItem finished.`); // Reduced verbosity
    }


    async function handleModelChange() {
        if (!currentChatId || isLoading) return; // Keep this check for user-initiated changes
         if (currentTab !== 'chat') {
             updateStatus("Model can only be changed in the Chat section.", true);
             // Reset selector to current chat model if not on chat tab
             if (currentChatId) {
                 // Need to fetch chat details to get the current model
                 fetch(`/api/chat/${currentChatId}`)
                     .then(response => response.json())
                     .then(data => {
                         modelSelector.value = data.details.model_name || defaultModel;
                     })
                     .catch(error => {
                         console.error("Error fetching chat details for model reset:", error);
                         modelSelector.value = defaultModel; // Fallback
                     });
             } else {
                 modelSelector.value = defaultModel; // Fallback if no current chat
             }
             return;
         }

        const newModel = modelSelector.value;
        updateStatus(`Updating model to ${newModel}...`);
        setLoadingState(true, "Updating Model");
        try {
            const response = await fetch(`/api/chat/${currentChatId}/model`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    model_name: newModel
                })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            updateStatus(`Model updated to ${newModel} for this chat.`);
        } catch (error) {
            console.error("Error updating model:", error);
            updateStatus(`Error updating model: ${error.message}`, true);
            // Revert model selector on error
            if (currentChatId) {
                 // Need to fetch chat details to get the current model
                 fetch(`/api/chat/${currentChatId}`)
                     .then(response => response.json())
                     .then(data => {
                         modelSelector.value = data.details.model_name || defaultModel;
                     })
                     .catch(error => {
                         console.error("Error fetching chat details for model revert:", error);
                         modelSelector.value = defaultModel; // Fallback
                     });
             } else {
                 modelSelector.value = defaultModel; // Fallback if no current chat
             }
        } finally {
            setLoadingState(false);
        }
    }

    // --- Settings Modal Functions ---

    /** Shows the Settings modal. */
    function showSettingsModal() {
        if (isLoading) return; // Keep this check for user-initiated modal open
        settingsModal.style.display = "block";
        // Ensure toggle states match current states when opening
        streamingToggle.checked = isStreamingEnabled;
        filesPluginToggle.checked = isFilePluginEnabled;
        calendarPluginToggle.checked = isCalendarPluginEnabled;
        webSearchPluginToggle.checked = isWebSearchPluginEnabled; // New: Update web search plugin toggle state
    }

    /** Closes the Settings modal. */
    function closeSettingsModal() {
        closeModal(settingsModal); // Use generic close modal function
    }

    /** Handles changes to the streaming toggle switch. */
    function handleStreamingToggle() {
        isStreamingEnabled = streamingToggle.checked;
        localStorage.setItem(STREAMING_ENABLED_KEY, isStreamingEnabled); // Persist toggle state
        updateStatus(`Streaming responses ${isStreamingEnabled ? 'enabled' : 'disabled'}.`);
    }

    /** Handles changes to the Files plugin toggle switch. */
    function handleFilesPluginToggle() {
        isFilePluginEnabled = filesPluginToggle.checked;
        localStorage.setItem(FILES_PLUGIN_ENABLED_KEY, isFilePluginEnabled); // Persist toggle state
        updatePluginUI(); // Update UI visibility
        updateStatus(`Files plugin ${isFilePluginEnabled ? 'enabled' : 'disabled'}.`);
        // If disabling, clear any selected files that aren't session files
        if (!isFilePluginEnabled) {
            selectedFiles = []; // Clear permanent file selections
            renderSelectedFiles(); // Update display
            // Also uncheck checkboxes in the sidebar list
            uploadedFilesList.querySelectorAll('.file-checkbox').forEach(checkbox => {
                checkbox.checked = false;
                checkbox.closest('.file-list-item').classList.remove('active-selection');
            });
             // Remove active-selection class from modal items
             if (manageFilesModal.style.display === 'block') {
                 manageFilesList.querySelectorAll('.file-list-item').forEach(item => {
                     item.classList.remove('active-selection');
                 });
             }
             // Clear file lists in sidebar/modal if open
             uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">Files plugin disabled.</p>`;
             manageFilesList.innerHTML = `<p class="text-gray-500 text-xs p-1">Files plugin disabled.</p>`;
        } else {
            // If enabling, reload the file lists
            loadUploadedFiles();
        }
    }

    /** Handles changes to the Calendar plugin toggle switch. */
    function handleCalendarPluginToggle() {
        isCalendarPluginEnabled = calendarPluginToggle.checked;
        localStorage.setItem(CALENDAR_PLUGIN_ENABLED_KEY, isCalendarPluginEnabled); // Persist toggle state
        updatePluginUI(); // Update UI visibility
        updateStatus(`Calendar plugin ${isCalendarPluginEnabled ? 'enabled' : 'disabled'}.`);
        // If disabling, clear calendar context and toggle state
        if (!isCalendarPluginEnabled) {
            calendarContext = null;
            isCalendarContextActive = false;
            calendarToggle.checked = false; // Force the input area toggle off
            updateCalendarStatus(); // Update status display
        }
    }

    /** New: Handles changes to the Web Search plugin toggle switch. */
    function handleWebSearchPluginToggle() {
        isWebSearchPluginEnabled = webSearchPluginToggle.checked;
        localStorage.setItem(WEB_SEARCH_PLUGIN_ENABLED_KEY, isWebSearchPluginEnabled); // Persist toggle state
        updatePluginUI(); // Update UI visibility
        updateStatus(`Web Search plugin ${isWebSearchPluginEnabled ? 'enabled' : 'disabled'}.`);
        // If disabling, explicitly turn off the web search toggle next to the input
        if (!isWebSearchPluginEnabled) {
            webSearchToggle.checked = false;
            // Trigger a change event on the webSearchToggle to ensure any listeners (if added later) are fired
            // Although currently, the state is just read in sendMessage, this is good practice.
            webSearchToggle.dispatchEvent(new Event('change'));
        }
    }


    /** Updates the visibility of plugin-related UI elements based on enabled state. */
    function updatePluginUI() {
        // Files Plugin UI
        // Hide/Show the entire file plugin section in the sidebar
        if (isFilePluginEnabled) {
            filePluginSection.classList.remove('hidden');
        } else {
            filePluginSection.classList.add('hidden');
        }
        // Hide/Show the paperclip button next to the message input (only visible on chat tab)
        // Visibility is also controlled by the tab switching logic
        if (isFilePluginEnabled && currentTab === 'chat') {
             fileUploadSessionLabel.classList.remove('hidden');
        } else {
             fileUploadSessionLabel.classList.add('hidden');
        }


        // Calendar Plugin UI
        // Hide/Show the entire calendar plugin section in the sidebar
        if (isCalendarPluginEnabled) {
            calendarPluginSection.classList.remove('hidden');
        } else {
            calendarPluginSection.classList.add('hidden');
        }
        // Hide/Show the calendar toggle next to the message input (only visible on chat tab)
        // Visibility is also controlled by the tab switching logic
        if (isCalendarPluginEnabled && currentTab === 'chat') {
             calendarToggleInputArea.classList.remove('hidden');
        } else {
             calendarToggleInputArea.classList.add('hidden');
        }


        // New: Web Search Plugin UI
        // Hide/Show the label element that wraps the web search toggle input (only visible on chat tab)
        // Visibility is also controlled by the tab switching logic
        if (isWebSearchPluginEnabled && currentTab === 'chat') {
            webSearchToggleLabel.classList.remove('hidden');
        } else {
            webSearchToggleLabel.classList.add('hidden');
        }


        // Note: The plugins sidebar itself (#plugins-sidebar) is controlled by pluginsToggleButton.
        // We don't hide the entire sidebar just because one plugin is off.
        // We hide the individual plugin sections within the sidebar.
    }

    // --- Tab Navigation Functions ---

    /** Switches between the Chat and Notes sections. */
    async function switchTab(tabName) {
        console.log(`[DEBUG] switchTab called for tab: ${tabName}. Current tab: ${currentTab}, isLoading: ${isLoading}`); // Added log
        if (isLoading || currentTab === tabName) return;

        currentTab = tabName;
        localStorage.setItem(ACTIVE_TAB_KEY, tabName); // Persist active tab
        console.log(`[DEBUG] currentTab set to: ${currentTab}`); // Added log

        // Update button styles
        chatNavButton.classList.remove('active');
        notesNavButton.classList.remove('active');

        // Set loading state for the entire tab switch operation
        setLoadingState(true, `Switching to ${tabName === 'chat' ? 'Chat' : 'Notes'}`);

        try {
            // Hide/Show main content sections and header elements
            if (tabName === 'chat') {
                chatNavButton.classList.add('active');
                chatSection.classList.remove('hidden');
                notesSection.classList.add('hidden');
                document.getElementById('input-area').classList.remove('hidden'); // Show chat input area
                modelSelectorContainer.classList.remove('hidden'); // Show model selector
                notesModeElements.classList.add('hidden'); // Hide notes mode elements container

                // Show chat sidebar content, hide notes sidebar content
                chatSidebarContent.classList.remove('hidden');
                notesSidebarContent.classList.add('hidden');

                // Ensure chat sidebar is visible if not collapsed
                sidebar.classList.remove('hidden');

                // Load chat data if not already loaded or if switching back
                if (currentChatId === null) {
                     console.log("[DEBUG] switchTab (chat): No currentChatId, loading initial chat."); // Added log
                     // This case should ideally be handled by initializeApp, but as a fallback
                     try {
                         await loadSavedChats();
                         const firstChatElement = savedChatsList.querySelector('.list-item');
                         if (firstChatElement) {
                             await loadChat(parseInt(firstChatElement.dataset.chatId));
                         } else {
                             await startNewChat();
                         }
                     } catch (error) {
                         console.error("[DEBUG] switchTab (chat): Error during initial chat load:", error);
                         // Error handling is done within loadChat/startNewChat, just log here
                     }
                } else {
                     console.log(`[DEBUG] switchTab (chat): currentChatId is ${currentChatId}, ensuring highlight.`); // Added log
                     // If chat is already loaded, just ensure highlighting is correct
                     updateActiveChatListItem();
                }


                // Focus message input
                messageInput.focus();

            } else if (tabName === 'notes') {
                notesNavButton.classList.add('active');
                chatSection.classList.add('hidden');
                notesSection.classList.remove('hidden');
                document.getElementById('input-area').classList.add('hidden'); // Hide chat input area
                modelSelectorContainer.classList.add('hidden'); // Hide model selector
                notesModeElements.classList.remove('hidden'); // Show notes mode elements container

                // Hide chat sidebar content, show notes sidebar content
                chatSidebarContent.classList.add('hidden');
                notesSidebarContent.classList.remove('hidden');

                // Ensure chat sidebar is visible if not collapsed (it contains the notes content now)
                sidebar.classList.remove('hidden');


                // Load notes data
                console.log("[DEBUG] switchTab (notes): Loading notes data..."); // Added log
                try {
                     await loadSavedNotes(); // Load the list of notes
                     console.log("[DEBUG] loadSavedNotes completed.");

                     if (currentNoteId !== null) {
                         console.log(`[DEBUG] switchTab (notes): currentNoteId is ${currentNoteId}, attempting to load it.`); // Added log
                         try {
                             await loadNote(currentNoteId); // Load the persisted note
                             console.log(`[DEBUG] loadNote(${currentNoteId}) completed.`);
                         } catch (error) {
                             console.warn(`[DEBUG] switchTab (notes): loadNote(${currentNoteId}) failed: ${error}. Starting new note.`);
                             // If loading the persisted note fails (e.g., deleted), start a new one
                             await startNewNote(); // Create and load a new note
                             console.log("[DEBUG] switchTab (notes): startNewNote completed after load failure.");
                         }
                     } else {
                         console.log("[DEBUG] No currentNoteId, loading most recent or creating new.");
                         const firstNoteElement = savedNotesList.querySelector('.list-item');
                         if (firstNoteElement) {
                             const mostRecentNoteId = parseInt(firstNoteElement.dataset.noteId);
                             console.log(`[DEBUG] Loading most recent note: ${mostRecentNoteId}`);
                             await loadNote(mostRecentNoteId);
                             console.log(`[DEBUG] loadNote(${mostRecentNoteId}) completed.`);
                         } else {
                             console.log("[DEBUG] No saved notes found, starting new note.");
                             await startNewNote(); // Create and load a new note
                             console.log("[DEBUG] startNewNote completed.");
                         }
                     }
                     // After loadNote/startNewNote completes, currentNoteId should be set
                     console.log(`[DEBUG] switchTab (notes): Finished loading note. Final currentNoteId: ${currentNoteId}`);

                     // Ensure the correct note mode is applied after loading content
                     // The mode is loaded in initializeApp, but we need to apply it here
                     // if switching tabs. loadNote also calls switchNoteMode.
                     // Let's ensure switchNoteMode is called *after* content is loaded.
                     // loadNote already calls updateNotesPreview and switchNoteMode.
                     // So, if loadNote succeeds, the mode is set. If it fails and startNewNote is called,
                     // startNewNote calls loadNote, which sets the mode.
                     // The only case is if loadSavedNotes fails entirely, then currentNoteId remains null.
                     // In that case, we should default to edit mode.
                     if (currentNoteId === null) {
                         switchNoteMode('edit'); // Default to edit if no note could be loaded/created
                     }


                } catch (error) {
                     console.error("[DEBUG] switchTab (notes): Error during initial notes load:", error);
                     // Error handling is done within loadSavedNotes/loadNote/startNewNote, just log here
                     // Ensure UI is in a safe state (e.g., edit mode, disabled)
                     switchNoteMode('edit'); // Default to edit mode on error
                     notesTextarea.value = `[Error loading notes: ${error.message}]`;
                     notesPreview.innerHTML = `<p class="text-red-500">Error loading note: ${escapeHtml(error.message)}</p>`;
                     notesTextarea.disabled = true; // Disable input on fatal error
                     currentNoteId = null; // Ensure state is null
                     currentNoteNameInput.value = '';
                     currentNoteIdDisplay.textContent = 'ID: -';
                     updateActiveNoteListItem(); // Remove highlight
                     localStorage.removeItem(CURRENT_NOTE_ID_KEY); // Clear persisted ID
                }


                // Focus notes textarea (if in edit mode) or notes section (if in view mode)
                if (currentNoteMode === 'edit') {
                     notesTextarea.focus();
                } else {
                     // Cannot focus preview, maybe focus the section?
                     notesSection.focus(); // Or just do nothing
                }
            }

            // Update plugin UI visibility based on enabled state (some elements are chat-only)
            updatePluginUI();

            // Ensure sidebars are positioned correctly after tab switch
            setSidebarCollapsed(sidebar, sidebarToggleButton, bodyElement.classList.contains('sidebar-collapsed'), SIDEBAR_COLLAPSED_KEY, 'sidebar');
            setSidebarCollapsed(pluginsSidebar, pluginsToggleButton, bodyElement.classList.contains('plugins-collapsed'), PLUGINS_COLLAPSED_KEY, 'plugins');

            updateStatus(`Switched to ${tabName} section.`);
            console.log(`[DEBUG] switchTab finished for tab: ${tabName}. isLoading: ${isLoading}`); // Added log

        } finally {
            // Ensure loading state is false after the entire tab switch process
            setLoadingState(false);
            console.log(`[DEBUG] switchTab finally block. isLoading: ${isLoading}`); // Added log
        }
    }

    // --- Notes Feature Functions (MODIFIED for multiple notes and mode toggle) ---

    /** Switches the display mode for the notes section ('edit' or 'view'). */
    function switchNoteMode(mode) {
        console.log(`[DEBUG] switchNoteMode called for mode: ${mode}. Current mode: ${currentNoteMode}, isLoading: ${isLoading}`); // Added log
        if (isLoading || currentNoteMode === mode) return;

        currentNoteMode = mode;
        localStorage.setItem(CURRENT_NOTE_MODE_KEY, mode); // Persist note mode
        console.log(`[DEBUG] currentNoteMode set to: ${currentNoteMode}`); // Added log

        // Update button styles
        editNoteButton.classList.remove('active');
        viewNoteButton.classList.remove('active');

        // Show/Hide elements based on mode
        if (mode === 'edit') {
            editNoteButton.classList.add('active');
            notesTextarea.classList.remove('hidden');
            notesPreview.classList.add('hidden');
            // Ensure textarea is enabled if not in a global loading state
            if (!isLoading) {
                 notesTextarea.disabled = false;
                 notesTextarea.focus(); // Focus the textarea when switching to edit mode
            }
            notesPreview.disabled = true; // Preview is never editable

        } else if (mode === 'view') {
            viewNoteButton.classList.add('active');
            notesTextarea.classList.add('hidden');
            notesPreview.classList.remove('hidden');
            // Disable textarea when hidden
            notesTextarea.disabled = true;
            notesPreview.disabled = true; // Preview is never editable

            // Update the preview content
            updateNotesPreview();
        }
        console.log(`[DEBUG] switchNoteMode finished for mode: ${mode}.`); // Added log
    }


    /** Creates a new note entry and loads it. */
    async function startNewNote() {
        console.log(`[DEBUG] startNewNote called. isLoading: ${isLoading}`); // Added log
        if (isLoading) return;
        setLoadingState(true, "Creating Note");
        updateStatus("Creating new note...");
        notesTextarea.value = ""; // Clear textarea while creating
        notesPreview.innerHTML = ""; // Clear preview while creating
        currentNoteNameInput.value = "New Note"; // Set default name
        currentNoteIdDisplay.textContent = "ID: -"; // Clear ID display
        notesTextarea.placeholder = "Creating new note...";
        switchNoteMode('edit'); // Always switch to edit mode when creating a new note

        try {
            const response = await fetch('/api/notes', { // POST to /api/notes
                method: 'POST'
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const newNote = await response.json(); // Expect the new note details back
            console.log(`[DEBUG] startNewNote: Received new note ID ${newNote.id}. Loading it...`); // Added log
            await loadNote(newNote.id); // Load the newly created note
            await loadSavedNotes(); // Reload the list in the sidebar
            updateStatus(`New note created (ID: ${newNote.id}).`);
            console.log(`[DEBUG] startNewNote: Successfully created and loaded note ${newNote.id}. currentNoteId is now ${currentNoteId}`); // Added log
            // No need to toggle sidebar collapse here, it's handled by switchTab
        } catch (error) {
            console.error('Error starting new note:', error);
            notesTextarea.value = `[Error creating new note: ${error.message}]`;
            notesPreview.innerHTML = `<p class="text-red-500">Error creating new note: ${escapeHtml(error.message)}</p>`;
            notesTextarea.placeholder = "Could not create note.";
            updateStatus("Error creating new note.", true);
            currentNoteId = null; // Ensure currentNoteId is null on error
            localStorage.removeItem(CURRENT_NOTE_ID_KEY); // Clear persisted ID on error
            console.error(`[DEBUG] startNewNote: Error occurred, currentNoteId set to null.`); // Added log
        } finally {
            setLoadingState(false);
            console.log(`[DEBUG] startNewNote finally block. isLoading: ${isLoading}`); // Added log
        }
    }


    /** Loads the note content from the backend and displays it. */
    async function loadNote(noteId) {
        console.log(`[DEBUG] loadNote(${noteId}) called. Current note: ${currentNoteId}, isLoading: ${isLoading}`); // Added log
        if (isLoading) return;
        // REMOVED: Early exit check - we want this to run fully when called
        // if (noteId === currentNoteId) {
        //      console.log(`[DEBUG] loadNote(${noteId}) skipped, isLoading is true.`); // Added log
        //      return; // Avoid reloading if already on this note
        // }
        setLoadingState(true, "Loading Note");
        updateStatus(`Loading note ${noteId}...`);
        notesTextarea.value = ""; // Clear textarea while loading
        notesPreview.innerHTML = ""; // Clear preview while loading
        currentNoteNameInput.value = ""; // Clear name while loading
        currentNoteIdDisplay.textContent = `ID: ${noteId}`; // Show ID while loading
        notesTextarea.placeholder = "Loading note...";
        // Do NOT switch mode here. The mode should be preserved or loaded from localStorage.
        // switchNoteMode('edit'); // <-- REMOVED: Mode should not be forced to edit on load

        try {
            const response = await fetch(`/api/note/${noteId}`); // GET /api/note/<id>
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }
            const data = await response.json(); // Expect note details {id, name, content, last_saved_at}
            currentNoteId = data.id; // Set current note ID
            console.log(`[DEBUG] loadNote(${noteId}): Successfully fetched. Set currentNoteId to ${currentNoteId}`); // Added log
            currentNoteNameInput.value = data.name || ''; // Populate name input
            notesTextarea.value = data.content || ''; // Populate content textarea
            notesTextarea.placeholder = "Start typing your markdown notes here...";

            // Apply the current mode after loading content
            switchNoteMode(currentNoteMode); // Apply the mode that was active before loading

            updateStatus(`Note ${noteId} loaded.`);
            updateActiveNoteListItem(); // Highlight the loaded note in the list
            localStorage.setItem(CURRENT_NOTE_ID_KEY, noteId); // Persist current note ID

        } catch (error) {
            console.error(`Error loading note ${noteId}:`, error);
            notesTextarea.value = `[Error loading note ${noteId}: ${error.message}]`;
            notesPreview.innerHTML = `<p class="text-red-500">Error loading note: ${escapeHtml(error.message)}</p>`;
            notesTextarea.placeholder = "Could not load note.";
            updateStatus(`Error loading note ${noteId}.`, true);
            currentNoteId = null; // Clear current note state on error
            localStorage.removeItem(CURRENT_NOTE_ID_KEY); // Clear persisted ID
            console.error(`[DEBUG] loadNote(${noteId}): Error occurred, currentNoteId set to null.`); // Added log
            currentNoteNameInput.value = '';
            currentNoteIdDisplay.textContent = 'ID: -';
            updateActiveNoteListItem(); // Remove highlight
            // Ensure UI is in edit mode and disabled on error
            switchNoteMode('edit');
            notesTextarea.disabled = true; // Disable input on fatal error
        } finally {
            // console.log(`[DEBUG] loadNote(${noteId}) finally block. isLoading: ${isLoading}`); // Added log
            setLoadingState(false); // <-- UNCOMMENTED THIS LINE
            // console.log("[DEBUG] setLoadingState(false) called in loadNote finally block."); // Added log
        }
    }

    /** Saves the current note content and name to the backend. */
    async function saveNote() {
        console.log(`[DEBUG] saveNote called. isLoading: ${isLoading}, currentNoteId: ${currentNoteId}`); // Added log
        if (isLoading || !currentNoteId) {
             updateStatus("Cannot save note: No active note selected or busy.", true);
             console.warn(`[DEBUG] saveNote aborted. isLoading=${isLoading}, currentNoteId=${currentNoteId}`); // Added log
             return;
        }
        setLoadingState(true, "Saving Note");
        updateStatus(`Saving note ${currentNoteId}...`);

        const noteName = currentNoteNameInput.value.trim();
        const noteContent = notesTextarea.value;

        try {
            const response = await fetch(`/api/note/${currentNoteId}`, { // PUT /api/note/<id>
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name: noteName, content: noteContent })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            updateStatus(`Note ${currentNoteId} saved successfully.`);
            await loadSavedNotes(); // Reload the list to update timestamp/name
            updateActiveNoteListItem(); // Ensure highlighting remains correct

        } catch (error) {
            console.error(`Error saving note ${currentNoteId}:`, error);
            updateStatus(`Error saving note: ${error.message}`, true);
        } finally {
            setLoadingState(false);
            console.log(`[DEBUG] saveNote finally block. isLoading: ${isLoading}`); // Added log
        }
    }

    /** Loads all saved notes and populates the list in the sidebar. */
    async function loadSavedNotes() {
        updateStatus("Loading saved notes...");
        // console.log("[DEBUG] loadSavedNotes called."); // Reduced verbosity
        try {
            const response = await fetch('/api/notes'); // GET /api/notes
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const notes = await response.json();
            savedNotesList.innerHTML = ''; // Clear current list

            if (notes.length === 0) {
                savedNotesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved notes yet.</p>`;
            } else {
                notes.forEach(note => {
                    const listItem = document.createElement('div');
                    listItem.classList.add('list-item', 'note-list-item'); // Add note-list-item class
                    listItem.dataset.noteId = note.id;

                    const nameSpan = document.createElement('span');
                    nameSpan.textContent = note.name || `Note ${note.id}`;
                    nameSpan.classList.add('filename');
                    nameSpan.title = note.name || `Note ${note.id}`;

                    const timestampElement = document.createElement('div');
                    const date = new Date(note.last_saved_at);
                    const formattedDate = date.toLocaleString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit'
                    });
                    timestampElement.textContent = `Last saved: ${formattedDate}`;
                    timestampElement.classList.add('text-xs', 'text-rz-tab-background-text', 'mt-0.5');

                    const deleteButton = document.createElement('button');
                    deleteButton.classList.add('delete-btn');
                    deleteButton.innerHTML = '<i class="fas fa-trash-alt fa-xs"></i>';
                    deleteButton.title = "Delete Note";
                    deleteButton.onclick = (e) => {
                        e.stopPropagation();
                        handleDeleteNote(note.id, listItem);
                    };

                    const nameContainer = document.createElement('div');
                    nameContainer.classList.add('name-container');
                    nameContainer.appendChild(nameSpan);
                    nameContainer.appendChild(deleteButton);

                    listItem.appendChild(nameContainer);
                    listItem.appendChild(timestampElement);

                    listItem.onclick = () => {
                        if (note.id != currentNoteId) {
                            loadNote(note.id); // Load this note when clicked
                        }
                    };
                    savedNotesList.appendChild(listItem);
                });
            }
            updateActiveNoteListItem(); // Highlight the currently loaded note
            updateStatus("Saved notes loaded.");
            // console.log("[DEBUG] loadSavedNotes finished successfully."); // Reduced verbosity
        } catch (error) {
            console.error('Error loading saved notes:', error);
            savedNotesList.innerHTML = '<p class="text-red-500 text-sm p-1">Error loading notes.</p>';
            updateStatus("Error loading saved notes.", true);
            // console.log("[DEBUG] loadSavedNotes caught an error."); // Reduced verbosity
            throw error;
        } finally {
            // console.log(`[DEBUG] loadSavedNotes finally block entered.`); // Added log
            setLoadingState(false); // <-- UNCOMMENTED THIS LINE
            // console.log("[DEBUG] setLoadingState(false) called in loadSavedNotes finally block."); // Added log
        }
    }

    /** Deletes a specific note. */
    async function handleDeleteNote(noteId, listItemElement) {
        if (isLoading) return;
        const noteName = listItemElement.querySelector('span.filename').textContent || `Note ${noteId}`;
        if (!confirm(`Are you sure you want to delete "${noteName}"? This cannot be undone.`)) {
            return;
        }
        setLoadingState(true, "Deleting Note");
        updateStatus(`Deleting note ${noteId}...`);
        try {
            const response = await fetch(`/api/note/${noteId}`, { // DELETE /api/note/<id>
                method: 'DELETE'
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            updateStatus(`Note ${noteId} deleted.`);
            listItemElement.remove(); // Remove from UI list

            // If the deleted note was the currently active one, start a new note
            if (noteId == currentNoteId) {
                currentNoteId = null; // Clear current note state
                localStorage.removeItem(CURRENT_NOTE_ID_KEY); // Clear persisted ID
                // Check if there are any notes left. If so, load the most recent. If not, create a new one.
                await loadSavedNotes(); // Reload the list first
                const firstNoteElement = savedNotesList.querySelector('.list-item');
                 if (firstNoteElement) {
                     await loadNote(parseInt(firstNoteElement.dataset.noteId));
                 } else {
                     await startNewNote(); // Create and load a new note
                 }
            } else {
                 // If a different note was deleted, just reload the list to be safe
                 await loadSavedNotes();
            }

        } catch (error) {
            console.error(`Error deleting note ${noteId}:`, error);
            updateStatus(`Error deleting note: ${error.message}`, true);
            // Optionally display error in the notes area if it was the current note
            if (noteId == currentNoteId) {
                 notesTextarea.value = `[Error deleting note ${noteId}: ${error.message}]`;
                 notesPreview.innerHTML = `<p class="text-red-500">Error deleting note: ${escapeHtml(error.message)}</p>`;
                 // Ensure UI is in edit mode and disabled on error
                 switchNoteMode('edit');
                 notesTextarea.disabled = true;
            }
        } finally {
            setLoadingState(false);
        }
    }

    /** Updates the highlighting of the active note in the sidebar list. */
    function updateActiveNoteListItem() {
        // console.log(`[DEBUG] updateActiveNoteListItem called. currentNoteId: ${currentNoteId}`); // Reduced verbosity
        const noteListItems = document.querySelectorAll('.note-list-item');
        // console.log(`[DEBUG] Found ${noteListItems.length} note list items.`); // Reduced verbosity

        noteListItems.forEach(item => {
            const noteId = parseInt(item.dataset.noteId);
            const timestampElement = item.querySelector('.text-xs');

            if (noteId === currentNoteId) {
                // console.log(`[DEBUG] Highlighting note item ${noteId}`); // Reduced verbosity
                item.classList.add('active');
                timestampElement.classList.remove('text-rz-tab-background-text');
                timestampElement.classList.add('text-rz-sidebar-text');
            } else {
                // console.log(`[DEBUG] Deactivating note item ${noteId}`); // Reduced verbosity
                item.classList.remove('active');
                timestampElement.classList.remove('text-rz-sidebar-text');
                timestampElement.classList.add('text-rz-tab-background-text');
            }
        });
        // console.log(`[DEBUG] updateActiveNoteListItem finished.`); // Reduced verbosity
    }


    /** Updates the markdown preview area based on the textarea content. */
    function updateNotesPreview() {
        const markdownText = notesTextarea.value;
        // Use marked.parse with the globally set options
        const renderedHtml = marked.parse(markdownText); // Pass only the text
        // Ensure the result is a string before setting innerHTML
        notesPreview.innerHTML = String(renderedHtml);
    }

    // --- New Markdown Tips Modal Functions ---

    /** Shows the Markdown Tips modal. */
    function showMarkdownTipsModal() {
        if (isLoading) return;
        // Only show if we are on the notes tab
        if (currentTab !== 'notes') {
             updateStatus("Markdown tips are only available in the Notes section.", true);
             return;
         }
        markdownTipsModal.style.display = "block";
    }

    /** Closes the Markdown Tips modal. */
    function closeMarkdownTipsModal() {
        closeModal(markdownTipsModal); // Use generic close modal function
    }


    // --- Event Listeners Setup (MUST be inside DOMContentLoaded) ---
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    newChatButton.addEventListener('click', startNewChat);
    saveChatNameButton.addEventListener('click', handleSaveChatName);
    currentChatNameInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleSaveChatName();
            currentChatNameInput.blur();
        }
    });
    sidebarToggleButton.addEventListener('click', toggleLeftSidebar);
    pluginsToggleButton.addEventListener('click', toggleRightSidebar);

    // File Plugin Listeners
    filePluginHeader.addEventListener('click', toggleFilePlugin);
    manageFilesButton.addEventListener('click', showManageFilesModal); // New listener for the Manage Files button
    attachFullButton.addEventListener('click', () => attachSelectedFiles('full'));
    attachSummaryButton.addEventListener('click', () => attachSelectedFiles('summary'));

    // Manage Files Modal Listeners
    closeManageFilesModalButton.addEventListener('click', () => closeModal(manageFilesModal)); // Use generic close
    manageFilesModal.addEventListener('click', (event) => {
        if (event.target === manageFilesModal) {
            closeModal(manageFilesModal); // Use generic close
        }
    });
    fileUploadModalInput.addEventListener('change', handleFileUpload); // Listener for file input inside modal
    addUrlModalButton.addEventListener('click', showUrlModal); // Listener for Add URL button inside modal

    // Existing URL Feature Listeners (Triggered from Add URL button inside Manage Files Modal)
    closeUrlModalButton.addEventListener('click', closeUrlModal); // Use generic close
    fetchUrlButton.addEventListener('click', () => addFileFromUrl(urlInput.value));
    urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addFileFromUrl(urlInput.value);
        }
    });
    urlModal.addEventListener('click', (event) => {
        if (event.target === urlModal) {
            closeUrlModal(); // Use generic close
        }
    });

    // Calendar Plugin Listeners
    calendarPluginHeader.addEventListener('click', toggleCalendarPlugin);
    loadCalendarButton.addEventListener('click', loadCalendarEvents);
    calendarToggle.addEventListener('change', handleCalendarToggle); // Listen to toggle change (next to message input)
    viewCalendarButton.addEventListener('click', showCalendarModal); // Listen to view button
    closeCalendarModalButton.addEventListener('click', () => closeModal(calendarModal)); // Use generic close

    // Summary Modal Listeners
    closeSummaryModalButton.addEventListener('click', () => closeModal(summaryModal)); // Use generic close
    saveSummaryButton.addEventListener('click', saveSummary);
    summaryModal.addEventListener('click', (event) => {
        if (event.target === summaryModal) {
            closeModal(summaryModal); // Use generic close
        }
    });

    // Settings Modal Listeners
    settingsButton.addEventListener('click', showSettingsModal);
    closeSettingsModalButton.addEventListener('click', () => closeModal(settingsModal));
    settingsModal.addEventListener('click', (event) => {
        if (event.target === settingsModal) {
            closeModal(settingsModal);
        }
    });
    streamingToggle.addEventListener('change', handleStreamingToggle); // Listen to streaming toggle change

    // New Plugin Toggle Listeners in Settings Modal
    filesPluginToggle.addEventListener('change', handleFilesPluginToggle);
    calendarPluginToggle.addEventListener('change', handleCalendarPluginToggle);
    webSearchPluginToggle.addEventListener('change', handleWebSearchPluginToggle); // New: Listen to web search plugin toggle change


    // Model Selector Listener
    modelSelector.addEventListener('change', handleModelChange);

    // New Notes Feature Listeners
    chatNavButton.addEventListener('click', () => switchTab('chat'));
    notesNavButton.addEventListener('click', () => switchTab('notes'));
    notesTextarea.addEventListener('input', updateNotesPreview); // Real-time markdown preview (only visible in edit mode)
    // saveNoteButton.addEventListener('click', saveNote); // Button moved
    newNoteButton.addEventListener('click', startNewNote); // New: Listener for New Note button
    saveNoteNameButton.addEventListener('click', saveNote); // New: Save button in notes sidebar now saves the current note

    // New Notes Mode Button Listeners
    editNoteButton.addEventListener('click', () => switchNoteMode('edit'));
    viewNoteButton.addEventListener('click', () => switchNoteMode('view'));
    markdownTipsButton.addEventListener('click', showMarkdownTipsModal); // New: Listener for Markdown Tips button

    // New Markdown Tips Modal Listeners
    closeMarkdownTipsModalButton.addEventListener('click', closeMarkdownTipsModal);
    markdownTipsModal.addEventListener('click', (event) => {
        if (event.target === markdownTipsModal) {
            closeMarkdownTipsModal();
        }
    });


    // --- Initial Application Load (MUST be inside DOMContentLoaded) ---
    /** Initializes the application on page load. */
    async function initializeApp() {
        console.log("[DEBUG] initializeApp called."); // Added log
        // Set initial status
        updateStatus("Initializing application...");
        // REMOVED: setLoadingState(true, "Initializing"); // Set loading state at the very beginning
        console.log("[DEBUG] Initializing state set."); // Added log

        try {
            // Load and set initial toggle states from localStorage
            const chatSidebarCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
            const pluginSidebarCollapsed = localStorage.getItem(PLUGINS_COLLAPSED_KEY) === 'true';
            const filePluginCollapsed = localStorage.getItem(FILE_PLUGIN_COLLAPSED_KEY) === 'true';
            const calendarPluginCollapsed = localStorage.getItem(CALENDAR_PLUGIN_COLLAPSED_KEY) === 'true';
            setSidebarCollapsed(sidebar, sidebarToggleButton, chatSidebarCollapsed, SIDEBAR_COLLAPSED_KEY, 'sidebar');
            setSidebarCollapsed(pluginsSidebar, pluginsToggleButton, pluginSidebarCollapsed, PLUGINS_COLLAPSED_KEY, 'plugins');
            setPluginSectionCollapsed(filePluginHeader, filePluginContent, filePluginCollapsed, FILE_PLUGIN_COLLAPSED_KEY);
            setPluginSectionCollapsed(calendarPluginHeader, calendarPluginContent, calendarPluginCollapsed, CALENDAR_PLUGIN_COLLAPSED_KEY);
            // console.log("[DEBUG] Sidebar/Plugin collapse states loaded and applied."); // Reduced verbosity


            // Load Calendar Context Active state (toggle next to input)
            isCalendarContextActive = localStorage.getItem('calendarContextActive') === 'true';
            calendarToggle.checked = isCalendarContextActive;
            // console.log(`[DEBUG] Calendar context active state loaded: ${isCalendarContextActive}.`); // Reduced verbosity
            // updateCalendarStatus() is called after loading plugin enabled state

            // Load Streaming toggle state (default to true if not found)
            const storedStreamingState = localStorage.getItem(STREAMING_ENABLED_KEY);
            // localStorage stores strings, convert 'true'/'false' to boolean
            isStreamingEnabled = storedStreamingState === null ? true : storedStreamingState === 'true';
            streamingToggle.checked = isStreamingEnabled;
            // console.log(`[DEBUG] Streaming enabled state loaded: ${isStreamingEnabled}.`); // Reduced verbosity


            // Load Plugin Enabled states (default to true if not found)
            const storedFilesPluginState = localStorage.getItem(FILES_PLUGIN_ENABLED_KEY);
            isFilePluginEnabled = storedFilesPluginState === null ? true : storedFilesPluginState === 'true';
            filesPluginToggle.checked = isFilePluginEnabled; // Update settings modal toggle
            // console.log(`[DEBUG] Files plugin enabled state loaded: ${isFilePluginEnabled}.`); // Reduced verbosity


            const storedCalendarPluginState = localStorage.getItem(CALENDAR_PLUGIN_ENABLED_KEY);
            isCalendarPluginEnabled = storedCalendarPluginState === null ? true : storedCalendarPluginState === 'true';
            calendarPluginToggle.checked = isCalendarPluginEnabled; // Update settings modal toggle
            // console.log(`[DEBUG] Calendar plugin enabled state loaded: ${isCalendarPluginEnabled}.`); // Reduced verbosity

            // New: Load Web Search Plugin Enabled state (default to true if not found)
            const storedWebSearchPluginState = localStorage.getItem(WEB_SEARCH_PLUGIN_ENABLED_KEY);
            isWebSearchPluginEnabled = storedWebSearchPluginState === null ? true : storedWebSearchPluginState === 'true';
            webSearchPluginToggle.checked = isWebSearchPluginEnabled; // Update settings modal toggle
            // console.log(`[DEBUG] Web Search plugin enabled state loaded: ${isWebSearchPluginEnabled}.`); // Reduced verbosity


            // Update UI visibility based on loaded plugin states
            updatePluginUI();
            // console.log("[DEBUG] Plugin UI visibility updated."); // Reduced verbosity
            // Now update calendar status based on loaded context and plugin state
            updateCalendarStatus();
            // console.log("[DEBUG] Calendar status updated.");


            // Load and set initial tab state from localStorage (default to 'chat')
            const storedTab = localStorage.getItem(ACTIVE_TAB_KEY);
            currentTab = (storedTab === 'chat' || storedTab === 'notes') ? storedTab : 'chat';
            console.log(`[DEBUG] Active tab loaded: ${currentTab}.`); // Added log

            // Load persisted current note ID (default to null)
            const persistedNoteId = localStorage.getItem(CURRENT_NOTE_ID_KEY);
            currentNoteId = persistedNoteId ? parseInt(persistedNoteId) : null;
            console.log(`[DEBUG] Persisted currentNoteId loaded: ${currentNoteId}.`);

            // New: Load persisted note mode (default to 'edit')
            const persistedNoteMode = localStorage.getItem(CURRENT_NOTE_MODE_KEY);
            currentNoteMode = (persistedNoteMode === 'edit' || persistedNoteMode === 'view') ? persistedNoteMode : 'edit';
            console.log(`[DEBUG] Persisted note mode loaded: ${currentNoteMode}.`);


            // Load data based on the initial tab
            // Use switchTab to handle the initial load based on the persisted tab
            await switchTab(currentTab); // This will now manage the loading state internally

            // Final status update on successful initialization (handled by switchTab now)
            // updateStatus("Application initialized.");
            console.log("[DEBUG] initializeApp finished successfully.");


        } catch (error) {
            console.error('Error during application initialization:', error);
            // Display a prominent error message in the chatbox (if chatbox exists)
            if (chatbox) {
                 addMessage('system', `[Fatal Error during initialization: ${error.message}. Please check console for details.]`, true);
            } else {
                 console.error("Chatbox not found, cannot display fatal error message.");
            }
            // Update status bar with error
            updateStatus("Initialization failed.", true);
            console.log("[DEBUG] initializeApp caught an error.");
            // The finally block will now run because the error is caught here
        } finally {
            console.log("[DEBUG] initializeApp finally block entered."); // Added log
            // setLoadingState(false) is now handled by switchTab's finally block
            console.log("[DEBUG] setLoadingState(false) is handled by switchTab finally block."); // Added log
        }
    }

    // Start the application initialization process
    initializeApp();

}); // End DOMContentLoaded listener
