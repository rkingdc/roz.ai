// DOM Element References (Unchanged)
const chatbox = document.getElementById('chatbox');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const sidebar = document.getElementById('sidebar');
const savedChatsList = document.getElementById('saved-chats-list');
const newChatButton = document.getElementById('new-chat-btn');
const currentChatNameInput = document.getElementById('current-chat-name');
const saveChatNameButton = document.getElementById('save-chat-name-btn');
const currentChatIdDisplay = document.getElementById('current-chat-id-display');
const statusBar = document.getElementById('status-bar');
const sidebarToggleButton = document.getElementById('sidebar-toggle-btn');
const pluginsSidebar = document.getElementById('plugins-sidebar');
const pluginsToggleButton = document.getElementById('plugins-toggle-btn');
const fileUploadInput = document.getElementById('file-upload-input');
const uploadedFilesList = document.getElementById('uploaded-files-list');
const selectedFilesContainer = document.getElementById('selected-files-container');
const bodyElement = document.body;
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
const webSearchToggle = document.getElementById('web-search-toggle'); // Added web search toggle

// New DOM Element References for URL feature
const addUrlButton = document.getElementById('add-url-btn');
const urlModal = document.getElementById('url-modal');
const closeUrlModalButton = document.getElementById('close-url-modal');
const urlInput = document.getElementById('url-input');
const fetchUrlButton = document.getElementById('fetch-url-btn');
const urlStatus = document.getElementById('url-status');


// Application State (Added Calendar state)
let currentChatId = null;
let isLoading = false;
let selectedFiles = [];
let currentEditingFileId = null;
let calendarContext = null; // Store loaded calendar events text
let isCalendarContextActive = false; // Track toggle state
const defaultModel = modelSelector.value;
const SIDEBAR_COLLAPSED_KEY = 'sidebarCollapsed';
const PLUGINS_COLLAPSED_KEY = 'pluginsCollapsed';
const FILE_PLUGIN_COLLAPSED_KEY = 'filePluginCollapsed';
const CALENDAR_PLUGIN_COLLAPSED_KEY = 'calendarPluginCollapsed';
const MAX_FILE_SIZE_MB = 10;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

// --- Utility Functions (Unchanged) ---
function updateStatus(message, isError = false) {
    statusBar.textContent = `Status: ${message}`;
    statusBar.className = `text-xs px-4 py-1 flex-shrink-0 ${isError ? 'text-red-600 bg-red-50 border-t border-red-200' : 'text-rz-status-bar-text bg-rz-status-bar-bg border-t border-rz-frame'}`;
    console.log(`Status Update: ${message}`);
}
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
        await loadUploadedFiles(); // Reload the file list

        // Remove from selected files if it's selected
        selectedFiles = selectedFiles.filter(f => f.id !== fileId);
        renderSelectedFiles();

    } catch (error) {
        console.error('Error deleting file:', error);
        updateStatus(`Error deleting file: ${error.message}`, true);
    } finally {
        setLoadingState(false);
    }
}

function setLoadingState(loading, operation = "Processing") {
    isLoading = loading;
    messageInput.disabled = loading;
    sendButton.disabled = loading;
    newChatButton.disabled = loading;
    saveChatNameButton.disabled = loading;
    sidebarToggleButton.disabled = loading;
    pluginsToggleButton.disabled = loading;
    fileUploadInput.disabled = loading;
    attachFullButton.disabled = loading;
    attachSummaryButton.disabled = loading;
    saveSummaryButton.disabled = loading;
    modelSelector.disabled = loading;
    loadCalendarButton.disabled = loading;
    calendarToggle.disabled = loading;
    viewCalendarButton.disabled = loading || !calendarContext;
    webSearchToggle.disabled = loading; // Disable web search toggle
    addUrlButton.disabled = loading; // Disable new Add URL button
    fetchUrlButton.disabled = loading; // Disable Fetch URL button in modal
    urlInput.disabled = loading; // Disable URL input in modal

    uploadedFilesList.querySelectorAll('input[type="checkbox"], button').forEach(el => el.disabled = loading);
    selectedFilesContainer.querySelectorAll('button').forEach(el => el.disabled = loading);
    sendButton.innerHTML = loading ? `<i class="fas fa-spinner fa-spin mr-2"></i> ${operation}...` : '<i class="fas fa-paper-plane mr-2"></i> Send';
    if (loading) {
        updateStatus(`${operation}...`);
    } else {
        updateStatus("Idle");
        if (!bodyElement.classList.contains('sidebar-collapsed')) {
            messageInput.focus();
        }
    }
}

// --- Sidebar & Plugin Toggle Functions (Unchanged) ---
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
    if (!collapsed && !isLoading) {
        setTimeout(() => messageInput.focus(), 350);
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

const fileUploadSessionInput = document.getElementById('file-upload-session-input');
const fileUploadSessionLabel = document.getElementById('file-upload-session-label');
// const sessionFileDisplayArea = document.getElementById('session-file-display-area'); // Removed
let sessionFile = null; // Variable to store selected session file

// Show the file upload container
fileUploadSessionLabel.addEventListener('click', () => {
    // fileUploadSessionContainer.classList.remove('hidden'); // This container is now always visible but input is hidden
    fileUploadSessionInput.click(); // Simulate click to open file dialog.
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




// Assume 'marked' is available globally or imported
// Make sure you have
// and Font Awesome if using the UI markers.

// Create a custom renderer to apply your specific classes
// to code blocks and inline code, matching the original function's output.
const renderer = new marked.Renderer();

// Helper function for basic HTML escaping within code
function escapeHtml(html) {
    return html
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

renderer.code = function(code, language) {
    // Ensure the input 'code' is treated as a string and escape its content
    const escapedCode = escapeHtml(String(code.text));
    console.log(escapedCode)
    return `<pre class="bg-gray-800 text-white p-2 rounded mt-1 overflow-x-auto text-sm font-mono"><code>${escapedCode}</code></pre>`;
};

renderer.codespan = function(text) {
    // Ensure the input 'text' is treated as a string and escape its content
    const escapedText = escapeHtml(String(text.text));

    // Return the HTML string with your desired classes
    return `<code class="bg-gray-200 px-1 rounded text-sm font-mono">${escapedText}</code>`;
};

// Define options for marked.parse
// Use the custom renderer
// Note: marked's default behavior for newlines is different from your original
const markedOptions = {
    renderer: renderer,
    breaks: true
};


function addMessage(role, content, isError = false) {
    const messageDiv = document.createElement('div');
    if (role === 'system') {
        messageDiv.classList.add('system-msg');
    } else {
        messageDiv.classList.add('message');
        if (isError) messageDiv.classList.add('error-msg');
        else messageDiv.classList.add(role === 'user' ? 'user-msg' : 'assistant-msg');
    }
    console.log("content")
    console.log(content)
    let processedContent = content;
    processedContent = processedContent.replace(/\[UI-MARKER:file:(.*?):(.*?)\]/g, (match, filename, type) => `<span class="attachment-icon" title="Attached ${filename} (${type})"><i class="fas fa-paperclip"></i> ${filename}</span>`).replace(/\[UI-MARKER:calendar\]/g, `<span class="attachment-icon" title="Calendar Context Active"><i class="fas fa-calendar-check"></i> Calendar</span>`).replace(/\[UI-MARKER:error:(.*?)\]/g, (match, filename) => `<span class="attachment-icon error-marker" title="Error attaching ${filename}"><i class="fas fa-exclamation-circle"></i> ${filename}</span>`);
    console.log("processed Content")
    console.log(processedContent)
    const htmlContent = marked.parse(processedContent, markedOptions);

    messageDiv.innerHTML = htmlContent;

    // Assuming 'chatbox' is a pre-existing element in your DOM
    const chatbox = document.getElementById('chatbox');

    if (chatbox) {
        chatbox.appendChild(messageDiv);
        chatbox.scrollTop = chatbox.scrollHeight;
    } else {
        console.error("Chatbox element with ID 'chatbox' not found.");
    }
}

// Example usage (assuming chatbox element exists in your HTML):
// addMessage('user', 'Hello **world**!');
// addMessage('assistant', 'Here is some `inline code` and a ```javascript\nconsole.log("block");\n```');
// addMessage('assistant', 'Attached file: [UI-MARKER:file:report.pdf:application/pdf]');
// addMessage('system', 'System message here.');
// addMessage('assistant', 'Error during attach: [UI-MARKER:error:image.jpg]', true);




async function loadUploadedFiles() {
    updateStatus("Loading uploaded files...");
    uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">Loading...</p>`;
    try {
        const response = await fetch('/api/files');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const files = await response.json();
        uploadedFilesList.innerHTML = '';
        if (files.length === 0) {
            uploadedFilesList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-xs p-1">No files uploaded yet.</p>`;
        } else {
            files.forEach(file => {
                const itemDiv = document.createElement('div');
                itemDiv.classList.add('file-list-item');
                itemDiv.dataset.fileId = file.id;
                itemDiv.dataset.filename = file.filename;
                itemDiv.dataset.hasSummary = file.has_summary;
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.value = file.id;
                checkbox.classList.add('file-checkbox');
                checkbox.title = "Select file";
                checkbox.addEventListener('change', (e) => {
                    if (e.target.checked) itemDiv.classList.add('active-selection');
                    else itemDiv.classList.remove('active-selection');
                });
                const nameSpan = document.createElement('span');
                nameSpan.textContent = file.filename;
                nameSpan.classList.add('filename');
                nameSpan.title = file.filename;
                const actionsDiv = document.createElement('div');
                actionsDiv.classList.add('file-actions');
                const summaryBtn = document.createElement('button');
                summaryBtn.classList.add('btn', 'btn-outline', 'btn-xs');
                summaryBtn.innerHTML = '<i class="fas fa-file-alt"></i>';
                summaryBtn.title = "View/Edit Summary";
                summaryBtn.disabled = false;
                summaryBtn.onclick = (e) => {
                    e.stopPropagation();
                    showSummaryModal(file.id, file.filename);
                };
                actionsDiv.appendChild(summaryBtn);

                // --- Add Delete Button Here ---
                const deleteBtn = document.createElement('button');
                deleteBtn.classList.add('btn', 'btn-outline', 'btn-xs', 'delete-btn'); // Added 'delete-btn' class
                deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
                deleteBtn.title = "Delete File";
                deleteBtn.onclick = (e) => {
                    e.stopPropagation(); // Stop itemDiv onclick from triggering
                    deleteFile(file.id); // Call the deleteFile function
                };
                actionsDiv.appendChild(deleteBtn);
                // --- End Delete Button ---

                itemDiv.appendChild(checkbox);
                itemDiv.appendChild(nameSpan);
                itemDiv.appendChild(actionsDiv);
                uploadedFilesList.appendChild(itemDiv);
            });
        }
        updateStatus("Uploaded files loaded.");
    } catch (error) {
        console.error('Error loading uploaded files:', error);
        uploadedFilesList.innerHTML = '<p class="text-red-500 text-xs p-1">Error loading files.</p>';
        updateStatus("Error loading files.", true);
    }
}


function handleFileUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    setLoadingState(true, "Uploading");
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
        fileUploadInput.value = '';
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
        await loadUploadedFiles();
        setLoadingState(false);
        fileUploadInput.value = '';
    });
}

// New function to handle adding file from URL
async function addFileFromUrl(url) {
    if (isLoading) return;
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
        await loadUploadedFiles(); // Reload the file list
        closeUrlModal(); // Close the modal on success

    } catch (error) {
        console.error('Error adding file from URL:', error);
        updateStatus(`Error adding file from URL: ${error.message}`, true);
        urlStatus.textContent = `Error: ${error.message}`;
        urlStatus.classList.add('text-red-500');
    } finally {
        setLoadingState(false);
    }
}


function attachSelectedFiles(type) {
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
        const alreadySelected = selectedFiles.some(f => f.id === fileId && f.type === type);
        if (!alreadySelected) {
            selectedFiles = selectedFiles.filter(f => !(f.id === fileId));
            selectedFiles.push({
                id: fileId,
                filename: filename,
                type: type
            });
            addedCount++;
        }
        checkbox.checked = false;
        listItem.classList.remove('active-selection');
    });
    renderSelectedFiles();
    if (addedCount > 0) {
        updateStatus(`${addedCount} file(s) added as ${type}.`);
    } else {
        updateStatus(`Selected file(s) already attached as ${type}.`);
    }
}

function removeSelectedFile(fileId, type) {
    selectedFiles = selectedFiles.filter(f => !(f.id === fileId && f.type === type));
    renderSelectedFiles();
    updateStatus(`File attachment removed.`);
}

function renderSelectedFiles() {
    // Clear only non-session file tags
    selectedFilesContainer.querySelectorAll('.selected-file-tag:not(.session-file-tag)').forEach(tag => tag.remove());

    // Render plugin-selected files
    selectedFiles.forEach(file => {
        const tag = document.createElement('span');
        tag.classList.add('selected-file-tag'); // No session-file-tag class here
        tag.innerHTML = `
            <span class="filename truncate" title="${file.filename}">${file.filename}</span>
            <span class="file-type">${file.type.toUpperCase()}</span>
            <button title="Remove Attachment">&times;</button>
        `;
        tag.querySelector('button').onclick = () => removeSelectedFile(file.id, file.type);
        selectedFilesContainer.appendChild(tag); // Append plugin files
    });

    // Update container visibility based on whether *any* tags exist (session or plugin)
    if (selectedFilesContainer.children.length === 0) {
        selectedFilesContainer.classList.add('hidden');
    } else {
        selectedFilesContainer.classList.remove('hidden');
    }
}

// --- Summary Modal Functions (Unchanged) ---
async function showSummaryModal(fileId, filename) {
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
    }
}
async function saveSummary() {
    if (!currentEditingFileId || isLoading) return;
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
        await loadUploadedFiles();
        closeModal();
    } catch (error) {
        console.error("Error saving summary:", error);
        updateStatus("Error saving summary.", true);
        summaryStatus.textContent = `Error saving: ${error.message}`;
        summaryStatus.classList.add('text-red-500');
    } finally {
        setLoadingState(false);
    }
}

function closeModal() {
    summaryModal.style.display = "none";
    currentEditingFileId = null;
}

function closeCalendarModal() {
    calendarModal.style.display = "none";
}

// New URL Modal Functions
function showUrlModal() {
    if (isLoading) return;
    urlInput.value = ''; // Clear previous input
    urlStatus.textContent = ''; // Clear previous status
    urlStatus.classList.remove('text-red-500');
    urlModal.style.display = "block";
    setTimeout(() => urlInput.focus(), 100); // Focus input after modal is displayed
}

function closeUrlModal() {
    urlModal.style.display = "none";
    urlInput.value = ''; // Clear input on close
    urlStatus.textContent = ''; // Clear status on close
    urlStatus.classList.remove('text-red-500');
}


// --- Calendar Plugin Functions (MODIFIED) ---
/** Fetches calendar events and updates state/UI. */
async function loadCalendarEvents() {
    if (isLoading) return;
    setLoadingState(true, "Loading Events");
    updateStatus("Loading calendar events...");
    // addMessage('system', 'Fetching Google Calendar events...'); // No longer add system message

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
    } finally {
        setLoadingState(false);
    }
}

/** Updates the calendar status text based on loaded context and toggle state. */
function updateCalendarStatus() {
    if (calendarContext) {
        calendarStatus.textContent = `Status: Events loaded. Context: ${isCalendarContextActive ? 'Active' : 'Inactive'}`;
        calendarStatus.classList.remove('text-red-500');
    } else {
        calendarStatus.textContent = "Status: Not loaded";
        calendarStatus.classList.remove('text-red-500');
    }
}

/** Handles changes to the calendar context toggle switch. */
function handleCalendarToggle() {
    isCalendarContextActive = calendarToggle.checked;
    localStorage.setItem('calendarContextActive', isCalendarContextActive); // Persist toggle state
    updateCalendarStatus(); // Update display text
}

/** Shows the modal with the loaded calendar events. */
function showCalendarModal() {
    if (calendarContext) {
        calendarModalContent.textContent = calendarContext; // Display raw text in <pre>
        calendarModal.style.display = 'block';
    } else {
        updateStatus("No calendar events loaded to view.", true);
    }
}

function clearChatbox() {
    chatbox.innerHTML = '';
}


async function loadSavedChats() {
    updateStatus("Loading saved chats...");
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
        updateActiveChatListItem();
        updateStatus("Saved chats loaded.");
    } catch (error) {
        console.error('Error loading saved chats:', error);
        savedChatsList.innerHTML = '<p class="text-red-500 text-sm p-1">Error loading chats.</p>';
        updateStatus("Error loading saved chats.", true);
    }
}




async function startNewChat() {
    if (isLoading) return;
    setLoadingState(true, "Creating Chat");
    updateStatus("Creating new chat...");
    try {
        const response = await fetch('/api/chat', {
            method: 'POST'
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newChat = await response.json();
        await loadChat(newChat.id);
        await loadSavedChats();
        updateStatus(`New chat created (ID: ${newChat.id}).`);
        setSidebarCollapsed(sidebar, sidebarToggleButton, false, SIDEBAR_COLLAPSED_KEY, 'sidebar');
        selectedFiles = []; // Clear permanent file selections
        sessionFile = null; // Clear session file state
        // Clear session file tag from container
        const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
        if (existingSessionTag) existingSessionTag.remove();
        renderSelectedFiles(); // Render (clears plugin files and updates visibility)
        fileUploadSessionInput.value = ''; // Reset session file input
        calendarContext = null;
        isCalendarContextActive = false;
        calendarToggle.checked = false;
        updateCalendarStatus();
        viewCalendarButton.classList.add('hidden');
        modelSelector.value = defaultModel;
        webSearchToggle.checked = false; // Reset web search toggle
    } catch (error) {
        console.error('Error starting new chat:', error);
        addMessage('system', `[Error creating new chat: ${error.message}]`, true);
        updateStatus("Error creating new chat.", true);
    } finally {
        setLoadingState(false);
    }
}
async function loadChat(chatId) {
    if (isLoading) return;
    setLoadingState(true, "Loading Chat");
    updateStatus(`Loading chat ${chatId}...`);
    clearChatbox();
    addMessage('system', `Loading chat (ID: ${chatId})...`);
    try {
        const response = await fetch(`/api/chat/${chatId}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status} ${response.statusText}`);
        const data = await response.json();
        currentChatId = chatId;
        clearChatbox();
        currentChatNameInput.value = data.details.name || '';
        currentChatIdDisplay.textContent = `ID: ${currentChatId}`;
        modelSelector.value = data.details.model_name || defaultModel;
        if (data.history.length === 0) {
            addMessage('system', 'This chat is empty. Start typing!');
        } else {
            data.history.forEach(msg => addMessage(msg.role, msg.content));
        }
        updateActiveChatListItem();
        updateStatus(`Chat ${chatId} loaded.`);
        setSidebarCollapsed(sidebar, sidebarToggleButton, false, SIDEBAR_COLLAPSED_KEY, 'sidebar');
        selectedFiles = []; // Clear permanent file selections
        sessionFile = null; // Clear session file state
        // Clear session file tag from container
        const existingSessionTag = selectedFilesContainer.querySelector('.session-file-tag');
        if (existingSessionTag) existingSessionTag.remove();
        renderSelectedFiles(); // Render (clears plugin files and updates visibility)
        fileUploadSessionInput.value = ''; // Reset session file input
        calendarContext = null;
        isCalendarContextActive = false;
        calendarToggle.checked = false;
        updateCalendarStatus();
        viewCalendarButton.classList.add('hidden');
        webSearchToggle.checked = false; // Reset web search toggle
    } catch (error) {
        console.error('Error loading chat:', error);
        clearChatbox();
        addMessage('system', `[Error loading chat ${chatId}: ${error.message}]`, true);
        currentChatId = null;
        currentChatNameInput.value = '';
        currentChatIdDisplay.textContent = 'ID: -';
        modelSelector.value = defaultModel;
        updateStatus(`Error loading chat ${chatId}.`, true);
        updateActiveChatListItem();
    } finally {
        setLoadingState(false);
    }
}

/** Sends message, attached files, and optionally calendar context to backend. */
async function sendMessage() {
    if (isLoading || !currentChatId) {
        updateStatus("Cannot send message: No active chat or busy.", true);
        return;
    }
    const message = messageInput.value.trim();
    if (!message && selectedFiles.length === 0 && (!isCalendarContextActive || !calendarContext) && !sessionFile) { // Added sessionFile check
        updateStatus("Cannot send: Type a message or attach file(s)/active context.", true);
        return;
    }

    // --- Display user message + UI markers immediately ---
    let displayMessage = message || ((selectedFiles.length > 0 || (isCalendarContextActive && calendarContext) || sessionFile) ? "(Context attached)" : ""); // Added sessionFile check
    let uiMarkers = "";
    if (selectedFiles.length > 0) {
        // Use non-HTML placeholder for files
        uiMarkers = selectedFiles.map(f => `[UI-MARKER:file:${f.filename}:${f.type}]`).join('');
    }
     if (sessionFile) { // Add marker for session file
        uiMarkers += `[UI-MARKER:file:${sessionFile.filename}:session]`;
    }
    if (isCalendarContextActive && calendarContext) {
        // Use non-HTML placeholder for calendar
        uiMarkers += `[UI-MARKER:calendar]`;
    }
    // Prepend placeholders to the actual message text
    displayMessage = uiMarkers + (uiMarkers ? "\n" : "") + displayMessage; // Add newline if markers exist
    addMessage('user', displayMessage); // addMessage will handle replacing placeholders

    messageInput.value = '';
    setLoadingState(true, "Sending");
    updateStatus("Sending message...");

    // --- Prepare payload for backend ---
    const payload = {
        message: message,
        attached_files: selectedFiles,
        calendar_context: (isCalendarContextActive && calendarContext) ? calendarContext : null,
        // Use the stored sessionFile object which now includes content
        session_files: sessionFile ? [{
            filename: sessionFile.filename,
            content: sessionFile.content,
            mimetype: sessionFile.mimetype
        }] : [],
        enable_web_search: webSearchToggle.checked // Add the web search flag
    };

    // Store session file temporarily to clear it in finally block
    const sentSessionFile = sessionFile;

    try {
        const response = await fetch(`/api/chat/${currentChatId}/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        addMessage('assistant', data.reply);
        updateStatus("Assistant replied.");
        await loadSavedChats();
        // Clear selected files, but keep calendar context loaded and active/inactive state
        selectedFiles = [];
        renderSelectedFiles();
    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('assistant', `[Error: ${error.message}]`, true);
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
    if (isLoading || !currentChatId) {
        updateStatus("Cannot save name: No active chat or busy.", true);
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
    if (isLoading) return;
    const chatName = listItemElement.querySelector('span.filename').textContent || `Chat ${chatId}`;
    if (!confirm(`Are you sure you want to delete "${chatName}"? This cannot be undone.`)) {
        return;
    }
    setLoadingState(true, "Deleting Chat");
    updateStatus(`Deleting chat ${chatId}...`);
    try {
        const response = await fetch(`/api/chat/${chatId}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        updateStatus(`Chat ${chatId} deleted.`);
        listItemElement.remove();
        if (!savedChatsList.querySelector('.list-item')) {
            savedChatsList.innerHTML = `<p class="text-rz-sidebar-text opacity-75 text-sm p-1">No saved chats yet.</p>`;
        }
        if (chatId == currentChatId) {
            await startNewChat();
        }
    } catch (error) {
        console.error(`Error deleting chat ${chatId}:`, error);
        updateStatus(`Error deleting chat: ${error.message}`, true);
        addMessage('system', `[Error deleting chat ${chatId}: ${error.message}]`, true);
    } finally {
        setLoadingState(false);
    }
}

function updateActiveChatListItem() {
    const chatListItems = document.querySelectorAll('.chat-list-item');

    chatListItems.forEach(item => {
        const chatId = parseInt(item.dataset.chatId);
        const timestampElement = item.querySelector('.text-xs'); // select the timestamp element

        if (chatId === currentChatId) {
            item.classList.add('active');
            timestampElement.classList.remove('text-rz-tab-background-text'); // Remove inactive color
            timestampElement.classList.add('text-rz-sidebar-text'); // Add active color
        } else {
            item.classList.remove('active');
            timestampElement.classList.remove('text-rz-sidebar-text'); // Remove active color
            timestampElement.classList.add('text-rz-tab-background-text'); // Add inactive color
        }
    });
}


async function handleModelChange() {
    if (!currentChatId || isLoading) return;
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
    } finally {
        setLoadingState(false);
    }
}


// --- Event Listeners Setup ---
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
fileUploadInput.addEventListener('change', handleFileUpload);
attachFullButton.addEventListener('click', () => attachSelectedFiles('full'));
attachSummaryButton.addEventListener('click', () => attachSelectedFiles('summary'));
// New URL Feature Listeners
addUrlButton.addEventListener('click', showUrlModal);
closeUrlModalButton.addEventListener('click', closeUrlModal);
fetchUrlButton.addEventListener('click', () => addFileFromUrl(urlInput.value));
urlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        addFileFromUrl(urlInput.value);
    }
});
urlModal.addEventListener('click', (event) => {
    if (event.target === urlModal) {
        closeUrlModal();
    }
});

// Calendar Plugin Listeners
calendarPluginHeader.addEventListener('click', toggleCalendarPlugin);
loadCalendarButton.addEventListener('click', loadCalendarEvents);
calendarToggle.addEventListener('change', handleCalendarToggle); // Listen to toggle change
viewCalendarButton.addEventListener('click', showCalendarModal); // Listen to view button
closeCalendarModalButton.addEventListener('click', closeCalendarModal); // Calendar modal close
// Summary Modal Listeners
closeSummaryModalButton.addEventListener('click', closeModal);
saveSummaryButton.addEventListener('click', saveSummary);
summaryModal.addEventListener('click', (event) => {
    if (event.target === summaryModal) {
        closeModal();
    }
});
// Calendar Modal Background Close
calendarModal.addEventListener('click', (event) => {
    if (event.target === calendarModal) {
        closeCalendarModal();
    }
});
// Model Selector Listener
modelSelector.addEventListener('change', handleModelChange);


// --- Initial Application Load ---
/** Initializes the application on page load. */
async function initializeApp() {
    const chatSidebarCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true';
    const pluginSidebarCollapsed = localStorage.getItem(PLUGINS_COLLAPSED_KEY) === 'true';
    const filePluginCollapsed = localStorage.getItem(FILE_PLUGIN_COLLAPSED_KEY) === 'true';
    const calendarPluginCollapsed = localStorage.getItem(CALENDAR_PLUGIN_COLLAPSED_KEY) === 'true';
    setSidebarCollapsed(sidebar, sidebarToggleButton, chatSidebarCollapsed, SIDEBAR_COLLAPSED_KEY, 'sidebar');
    setSidebarCollapsed(pluginsSidebar, pluginsToggleButton, pluginSidebarCollapsed, PLUGINS_COLLAPSED_KEY, 'plugins');
    setPluginSectionCollapsed(filePluginHeader, filePluginContent, filePluginCollapsed, FILE_PLUGIN_COLLAPSED_KEY);
    setPluginSectionCollapsed(calendarPluginHeader, calendarPluginContent, calendarPluginCollapsed, CALENDAR_PLUGIN_COLLAPSED_KEY);
    // Set initial toggle state from localStorage
    isCalendarContextActive = localStorage.getItem('calendarContextActive') === 'true';
    calendarToggle.checked = isCalendarContextActive;
    updateCalendarStatus(); // Initial status update
    await loadSavedChats();
    await loadUploadedFiles();
    const firstChatElement = savedChatsList.querySelector('.list-item');
    if (firstChatElement) {
        const mostRecentChatId = parseInt(firstChatElement.dataset.chatId);
        await loadChat(mostRecentChatId);
    } else {
        await startNewChat();
    }
    renderSelectedFiles();
}

// Start the application initialization process
initializeApp();
