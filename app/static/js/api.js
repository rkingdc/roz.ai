// js/api.js
// This module handles all interactions with the backend API.
// It updates the application state based on API responses.
// It does NOT directly manipulate the DOM or call UI rendering functions.

import { elements } from './dom.js'; // Still need elements to read input values sometimes
import * as state from './state.js'; // API updates the state
import * as ui from './ui.js'; // Import ui module to access autoResizeTextarea
import { escapeHtml, formatFileSize } from './utils.js';
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from './config.js';
// --- NEW: Import Toast and MIME_TYPE ---
import { showToast, removeToast, updateToast } from './toastNotifications.js'; // Adjust path if needed
import { MIME_TYPE } from './voice.js'; // Import MIME_TYPE constant
// ---------------------------------------
// Import Socket.IO client library (assuming it's loaded via script tag or bundler)
// If using a script tag, it attaches to `window.io`
// const io = window.io; // Uncomment if using script tag

// --- Socket.IO Instance ---
let socket = null; // Holds the socket connection
let permanentListenersAttached = false; // Flag to ensure permanent listeners are added only once


// --- SocketIO Initialization and Connection ---

/**
 * Initializes the WebSocket connection if it doesn't exist or is disconnected.
 * Attaches permanent listeners exactly once per connection lifecycle.
 * Safe to call multiple times.
 */
export function initializeWebSocketConnection() {
    // Only proceed if socket doesn't exist or is disconnected
    if (socket && socket.connected) {
        console.log("[DEBUG] WebSocket connection already active.");
        return; // Already connected
    }
    if (socket && socket.connecting) {
        console.log("[DEBUG] WebSocket connection attempt already in progress.");
        return; // Connection attempt in progress
    }

    if (typeof io === 'undefined') {
        console.error("Socket.IO client library not found. Make sure it's included.");
        setStatus("Error: Missing Socket.IO library.", true);
        return; // Cannot proceed
    }

    console.log("[DEBUG] Initializing WebSocket connection...");
    setStatus("Connecting to server...");
    state.setIsSocketConnected(false); // Assume disconnected until 'connect' event
    permanentListenersAttached = false; // Reset listener flag for new connection attempt

    // Create the single socket instance (or recreate if disconnected)
    socket = io({
        // Optional: Add reconnection options if needed
        // reconnectionAttempts: 5,
        // reconnectionDelay: 1000,
    });

    // Attach permanent listeners (will only run if not already attached)
    initializeSocketListeners();
}


// --- Helper to update loading and status state ---
function setLoading(isLoading, message = "Busy...") {
    state.setIsLoading(isLoading);
    if (isLoading) {
        state.setStatusMessage(message);
    } else {
        // Status message will be set by the specific API function on success/failure
        // or reset to "Idle" by setIsLoading if no error occurred.
    }
}

function setStatus(message, isError = false) {
    state.setStatusMessage(message, isError);
}

// --- SocketIO Initialization and Listeners ---

/**
 * Attaches permanent SocketIO event listeners.
 */
function initializeSocketListeners() {
    if (!socket || permanentListenersAttached) {
        return; // Don't attach if no socket or already attached
    }

    console.log("[DEBUG] Initializing permanent SocketIO listeners.");

    // --- Connection Handling ---
    socket.on('connect', () => {
        console.log("Socket connected:", socket.id);
        setStatus("Connected to server."); // General status
        state.setIsSocketConnected(true);
    });

    socket.on('connect_error', (error) => {
        console.error("WebSocket connection error:", error);
        setStatus(`Server connection failed: ${error.message}`, true);
        state.setIsSocketConnected(false);
        socket = null; // Nullify on connection error
        permanentListenersAttached = false; // Reset flag
    });

    socket.on('disconnect', (reason) => {
        console.log("WebSocket disconnected:", reason);
        if (!state.isErrorStatus) { // Don't overwrite specific errors
            setStatus("Disconnected from server.");
        }
        state.setIsSocketConnected(false);
        state.setIsRecording(false); // Stop recording state if disconnected
        socket = null; // Nullify on disconnect
        permanentListenersAttached = false; // Reset flag
    });

    // --- Transcription Listeners (Permanent) ---
    socket.on('transcript_update', (data) => {
        if (data && data.transcript !== undefined) {
            const newSegment = data.transcript.trim();
            if (data.is_final && newSegment) {
                state.appendFinalizedTranscript(newSegment);
                state.setCurrentInterimTranscript("");
            } else if (!data.is_final) {
                state.setCurrentInterimTranscript(newSegment);
            }
        }
    });

    // --- Chat/Task Listeners (Permanent) ---
    socket.on('prompt_improved', handlePromptImproved);
    socket.on('task_started', (data) => {
        console.log("Backend task started:", data.message);
        if (data.message) {
            setStatus(data.message);
        }
    });

    socket.on('status_update', (data) => {
        console.log("Backend status update:", data.message);
        if (data.message) {
            setStatus(data.message);
        }
    });

    socket.on('chat_response', (data) => {
        console.log("Received non-streaming chat response:", data.reply);
        if (data.reply !== undefined) {
            // Assuming backend might send attachments with non-streaming responses too
            state.addMessageToHistory({
                role: 'assistant',
                content: data.reply,
                attachments: data.attachments || [] // Expect attachments from backend
            });
            setStatus("Assistant replied.");
            loadSavedChats();
        } else {
            console.warn("Received 'chat_response' event with missing 'reply'.", data);
            state.addMessageToHistory({ role: 'assistant', content: "[Error: Received empty response from server]", isError: true, attachments: [] });
            setStatus("Received empty response.", true);
        }
        if (state.processingChatId !== null) {
             console.log(`[DEBUG] chat_response received. Clearing processingChatId: ${state.processingChatId}`);
             state.setProcessingChatId(null);
        }
    });

    socket.on('stream_chunk', (data) => {
        if (data.chunk !== undefined) {
            const lastMessage = state.chatHistory.length > 0 ? state.chatHistory[state.chatHistory.length - 1] : null;
            if (!lastMessage || lastMessage.role === 'user' || (lastMessage.role === 'assistant' && lastMessage.isError)) { // Also add new if last was error
                console.log("[DEBUG] stream_chunk: Adding initial assistant message placeholder.");
                // If backend sends attachments with the first chunk (unlikely but possible)
                state.addMessageToHistory({ role: 'assistant', content: data.chunk, attachments: data.attachments || [] });
            } else {
                state.appendContentToLastMessage(data.chunk);
            }
        }
    });

    socket.on('stream_end', (data) => {
        console.log("Received stream end signal:", data.message);
        setStatus("Assistant finished streaming.");
        if (state.processingChatId !== null) {
             console.log(`[DEBUG] stream_end received. Clearing processingChatId: ${state.processingChatId}`);
             state.setProcessingChatId(null);
        }
        loadSavedChats();
    });

    socket.on('deep_research_result', (data) => {
        console.log("Received deep research result.");
        if (data.report !== undefined) {
            const reportContent = `# Deep Research Report\n\n${data.report}`;
            state.addMessageToHistory({ role: 'assistant', content: reportContent, attachments: [] });
            setStatus("Deep Research complete.");
            loadSavedChats();
        } else {
            console.warn("Received 'deep_research_result' event with missing 'report'.", data);
            state.addMessageToHistory({ role: 'assistant', content: "[Error: Received empty report from server]", isError: true, attachments: [] });
            setStatus("Received empty report.", true);
        }
        if (state.processingChatId !== null) {
             console.log(`[DEBUG] deep_research_result received. Clearing processingChatId: ${state.processingChatId}`);
             state.setProcessingChatId(null);
        }
    });

    socket.on('task_error', (data) => {
        console.error("Received task error from backend:", data.error);
        const errorMessage = `[Error: ${data.error || 'Unknown error from server'}]`;
        state.addMessageToHistory({ role: 'assistant', content: errorMessage, isError: true, attachments: [] });
        setStatus("Error processing request.", true);
        if (state.processingChatId !== null) {
             console.log(`[DEBUG] task_error received. Clearing processingChatId: ${state.processingChatId}`);
             state.setProcessingChatId(null);
        }
    });

    socket.on('generation_cancelled', (data) => {
        console.log("Backend confirmed generation cancelled:", data.message);
        if (data.chat_id && data.chat_id === state.processingChatId) {
            setStatus("Generation cancelled by user.");
            state.setProcessingChatId(null);
            loadSavedChats();
        } else {
            console.warn(`Received 'generation_cancelled' for chat ${data.chat_id}, but current processing chat is ${state.processingChatId}.`);
        }
    });

    socket.on('cancel_request_received', (data) => {
        console.log("Backend acknowledged cancellation request:", data.message);
        setStatus("Cancellation requested...");
    });

    socket.on('transcription_started', (data) => {
        console.log("Backend confirmed transcription started (permanent listener).");
    });

    socket.on('transcription_error', (data) => {
        console.error("Transcription error from backend (permanent listener):", data.error);
        setStatus(`Transcription Error: ${data.error}`, true);
    });

    socket.on('transcription_complete', (data) => {
        console.log("Backend confirmed transcription complete (permanent listener).");
    });

    socket.on('transcription_stop_acknowledged', (data) => {
        console.log("Backend acknowledged stop signal (permanent listener).");
    });

    permanentListenersAttached = true;
}

function handlePromptImproved({ original, improved }) {
    console.log(`[DEBUG] Received prompt_improved. Original: "${original.substring(0, 50)}...", Improved: "${improved.substring(0, 50)}..."`);
    const currentHistory = state.chatHistory;
    let lastUserMessageIndex = -1;
    for (let i = currentHistory.length - 1; i >= 0; i--) {
        if (currentHistory[i].role === 'user') {
            lastUserMessageIndex = i;
            break;
        }
    }

    if (lastUserMessageIndex !== -1) {
        if (currentHistory[lastUserMessageIndex].content === original) {
            console.log(`[DEBUG] Found matching user message at index ${lastUserMessageIndex}. Updating content.`);
            const newHistory = currentHistory.map((message, index) => {
                if (index === lastUserMessageIndex) {
                    return { ...message, content: improved, rawContent: improved }; // Update rawContent too
                }
                return message;
            });
            state.setChatHistory(newHistory);
        } else {
            console.warn(`[DEBUG] Found last user message at index ${lastUserMessageIndex}, but content did not match original prompt. Original in state: "${currentHistory[lastUserMessageIndex].content.substring(0, 50)}..."`);
        }
    } else {
        console.warn("[DEBUG] Could not find the last user message in history to update for 'prompt_improved'.");
    }
}

export function connectTranscriptionSocket(languageCode = 'en-US', audioFormat = 'WEBM_OPUS') {
    return new Promise((resolve, reject) => {
        let promiseResolved = false;
        let promiseRejected = false;

        const resolveOnce = () => {
            if (!promiseResolved && !promiseRejected) {
                promiseResolved = true;
                if (socket) {
                    socket.off('transcription_started', handleStarted);
                    socket.off('transcription_error', handleError);
                    socket.off('disconnect', handleDisconnectError);
                }
                resolve();
            }
        };
        const rejectOnce = (error) => {
             if (!promiseResolved && !promiseRejected) {
                promiseRejected = true;
                if (socket) {
                    socket.off('transcription_started', handleStarted);
                    socket.off('transcription_error', handleError);
                    socket.off('disconnect', handleDisconnectError);
                }
                reject(error);
            }
        };

        const handleStarted = (data) => {
            setStatus("Recording... Speak now.");
            resolveOnce();
        };
        const handleError = (data) => {
            console.error("Transcription error during start attempt:", data.error);
            setStatus(`Transcription Error: ${data.error}`, true);
            rejectOnce(new Error(data.error));
        };
        const handleDisconnectError = (reason) => {
            console.warn(`WebSocket disconnected while waiting for transcription start: ${reason}`);
            setStatus("Transcription service disconnected before starting.", true);
            rejectOnce(new Error(`WebSocket disconnected: ${reason}`));
        };

        initializeWebSocketConnection();

        if (socket && socket.connected) {
            console.log("[DEBUG] connectTranscriptionSocket: Socket already connected. Proceeding.");
            setStatus("Initializing transcription stream...");
            socket.once('transcription_started', handleStarted);
            socket.once('transcription_error', handleError);
            socket.once('disconnect', handleDisconnectError);
            console.log("[DEBUG] Emitting start_transcription on existing socket.");
            socket.emit('start_transcription', { languageCode, audioFormat });
        } else {
            const errorMsg = socket ? "WebSocket is still connecting, please try again shortly." : "WebSocket connection failed to initialize.";
            console.warn(`connectTranscriptionSocket: Cannot start transcription - ${errorMsg}`);
            setStatus(errorMsg, true);
            rejectOnce(new Error(errorMsg));
        }
    });
}

export function sendAudioChunk(chunk) {
    if (socket && socket.connected) {
        socket.emit('audio_chunk', chunk);
    } else {
        console.warn("Cannot send audio chunk: WebSocket not connected.");
        setStatus("Error: Transcription service disconnected. Cannot send audio.", true);
    }
}

export function stopAudioStream() {
    return new Promise((resolve, reject) => {
        if (!socket || !socket.connected) {
            console.warn("Cannot signal stop: WebSocket not connected.");
            return reject(new Error("WebSocket not connected."));
        }

        let promiseResolved = false;
        let promiseRejected = false;
        let timeoutId = null;

        const removeListeners = () => {
            if (socket) {
                socket.off('transcription_complete', handleComplete);
                socket.off('transcription_error', handleError);
                socket.off('disconnect', handleDisconnect);
            }
        };

        const resolveOnce = (message = "Transcription complete.") => {
            if (!promiseResolved && !promiseRejected) {
                clearTimeout(timeoutId);
                promiseResolved = true;
                removeListeners();
                resolve();
            }
        };
        const rejectOnce = (error) => {
             if (!promiseResolved && !promiseRejected) {
                clearTimeout(timeoutId);
                promiseRejected = true;
                removeListeners();
                reject(error);
            }
        };

        const handleComplete = (data) => resolveOnce(data.message);
        const handleError = (data) => rejectOnce(new Error(data.error));
        const handleDisconnect = (reason) => rejectOnce(new Error(`WebSocket disconnected: ${reason}`));

        socket.on('transcription_complete', handleComplete);
        socket.on('transcription_error', handleError);
        socket.on('disconnect', handleDisconnect);
        socket.emit('stop_transcription');
        const timeoutDuration = 10000;
        timeoutId = setTimeout(() => rejectOnce(new Error(`Timeout waiting for transcription completion after ${timeoutDuration}ms`)), timeoutDuration);
    });
}

export function disconnectTranscriptionSocket() {
    if (socket) {
        socket.disconnect();
        socket = null;
        state.setIsSocketConnected(false);
    }
}

export async function transcribeLongAudio(audioBlob, languageCode = 'en-US') {
    const transcribingToastId = showToast("Transcribing recorded audio...", { autoClose: false, type: 'info' });
    console.log(`[DEBUG] transcribeLongAudio: Showing transcribing toast ID: ${transcribingToastId}`);

    const formData = new FormData();
    formData.append('audio_blob', audioBlob, `long_recording.${MIME_TYPE.split('/')[1].split(';')[0]}`);
    formData.append('languageCode', languageCode);
    formData.append('mimeType', MIME_TYPE);

    try {
        const response = await fetch('/api/voice/transcribe_long', {
            method: 'POST',
            body: formData,
        });
        console.log(`[DEBUG] transcribeLongAudio: Removing transcribing toast ID: ${transcribingToastId}`);
        removeToast(transcribingToastId);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
            console.error('Long transcription API error:', response.status, errorData);
            showToast(`Transcription Error: ${errorData.error || response.statusText}`, { type: 'error' });
            state.setLastLongTranscript('');
            return null;
        }

        const data = await response.json();
        state.setLastLongTranscript(data.transcript);
        const snippet = data.transcript.substring(0, 70) + (data.transcript.length > 70 ? '...' : '');
        const toastContent = `
            <div class="flex flex-col space-y-1 relative pr-4">
                <button class="toast-close-button absolute top-0 right-0 px-1 py-0 text-white hover:text-gray-300 text-lg leading-none" title="Close">&times;</button>
                <span class="font-medium">Transcription Complete:</span>
                <span class="text-xs italic">"${escapeHtml(snippet)}"</span>
                <button class="toast-copy-button self-end mt-1 px-2 py-0.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-300" data-transcript-target="long">Copy</button>
            </div>
        `;
        showToast(toastContent, { type: 'success', autoClose: false });
        return data.transcript;
    } catch (error) {
        console.error('Network or other error during long transcription:', error);
        if (transcribingToastId) {
             console.log(`[DEBUG] transcribeLongAudio (catch): Removing transcribing toast ID: ${transcribingToastId}`);
             removeToast(transcribingToastId);
        }
        showToast(`Transcription Error: ${error.message}`, { type: 'error' });
        state.setLastLongTranscript('');
        return null;
    }
}

export async function deleteFile(fileId) {
    if (state.isLoading) return;
    if (!confirm("Are you sure you want to delete this file? This action cannot be undone.")) {
        return;
    }
    setLoading(true, "Deleting File");
    try {
        const response = await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`File ${fileId} deleted.`);
        state.removeSidebarSelectedFileById(fileId);
        state.removeAttachedFileById(fileId);
        if (state.sessionFile && state.sessionFile.id === fileId) {
             state.setSessionFile(null);
        }
        await loadUploadedFiles();
    } catch (error) {
        console.error('Error deleting file:', error);
        setStatus(`Error deleting file: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

export async function loadUploadedFiles() {
    const wasLoading = state.isLoading;
    if (!wasLoading) setLoading(true, "Loading Files");
    state.setUploadedFiles([]);
    try {
        const response = await fetch('/api/files');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const files = await response.json();
        state.setUploadedFiles(files);
        setStatus("Uploaded files loaded.");
    } catch (error) {
        console.error('Error loading uploaded files:', error);
        setStatus("Error loading files.", true);
        throw error;
    } finally {
        if (!wasLoading) setLoading(false);
    }
}

export async function handleFileUpload(event) {
    if (state.currentTab !== 'chat') {
        setStatus("File uploads only allowed on Chat tab.", true);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }
    const files = event.target.files;
    if (!files || files.length === 0) {
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }
    if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
    if (elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = true;
    if (elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.add('disabled');

    setLoading(true, "Uploading");
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
        setLoading(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = false;
        if(elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.remove('disabled');
        setStatus("No valid files selected for upload.", true);
        return;
    }

    try {
        const response = await fetch('/api/files', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        const successfulUploads = data.uploaded_files?.length || 0;
        const errors = data.errors || [];
        let statusMsg = `Uploaded ${successfulUploads} file(s).`;
        if (errors.length > 0) {
            statusMsg += ` ${errors.length} failed: ${errors.join('; ')}`;
        }
        setStatus(statusMsg, errors.length > 0);
        await loadUploadedFiles();
    } catch (error) {
        console.error('Error uploading files:', error);
        setStatus(`Error uploading files: ${error.message}`, true);
    } finally {
        setLoading(false);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = false;
        if(elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.remove('disabled');
    }
}

export async function addFileFromUrl(url) {
     if (state.isLoading) return;
     if (state.currentTab !== 'chat') return;
     if (!url || !url.startsWith('http')) return;
     setLoading(true, "Fetching URL");
     try {
         const response = await fetch('/api/files/from_url', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ url: url })
         });
         const data = await response.json();
         if (!response.ok) {
             throw new Error(data.error || `HTTP error! status: ${response.status}`);
         }
         setStatus(`Successfully added file from URL: ${data.filename}`);
         if(elements.urlInput) elements.urlInput.value = '';
         await loadUploadedFiles();
     } catch (error) {
         console.error('Error adding file from URL:', error);
         setStatus(`Error adding file from URL: ${error.message}`, true);
     } finally {
         setLoading(false);
     }
}

export async function fetchSummary(fileId) {
    if (state.isLoading) return;
    if (state.currentTab !== 'chat') {
         setStatus("Fetching summaries only allowed on Chat tab.", true);
         return;
    }
    setLoading(true, "Fetching Summary");
    try {
        const response = await fetch(`/api/files/${fileId}/summary`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        const data = await response.json();
        state.setCurrentEditingFileId(fileId);
        state.setSummaryContent(data.summary);
        setStatus(`Summary loaded/generated for file ${fileId}.`);
        await loadUploadedFiles();
    } catch (error) {
        console.error("Error fetching summary:", error);
        state.setSummaryContent(`[Error loading summary: ${error.message}]`);
        setStatus(`Error fetching summary for file ${fileId}.`, true);
    } finally {
        setLoading(false);
    }
}

export async function saveSummary() {
    if (!state.currentEditingFileId || state.isLoading) return;
    if (state.currentTab !== 'chat') {
         setStatus("Saving summaries only allowed on Chat tab.", true);
         return;
    }
    const updatedSummary = state.summaryContent;
    setLoading(true, "Saving Summary");
    try {
        const response = await fetch(`/api/files/${state.currentEditingFileId}/summary`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ summary: updatedSummary })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        setStatus("Summary saved successfully.");
        await loadUploadedFiles();
    } catch (error) {
        console.error("Error saving summary:", error);
        setStatus("Error saving summary.", true);
    } finally {
        setLoading(false);
    }
}

export function attachSelectedFilesFull() {
    if (state.currentTab !== 'chat' || state.isLoading) {
        setStatus("Cannot attach files: Not on Chat tab or busy.", true);
        return;
    }
    if (state.sidebarSelectedFiles.length === 0) {
        setStatus("No files selected in the sidebar to attach.", true);
        return;
    }
    state.sidebarSelectedFiles.forEach(file => {
        if (!state.attachedFiles.some(f => f.id === file.id && f.type === 'full')) {
             state.addAttachedFile({ id: file.id, filename: file.filename, type: 'full', mimetype: file.mimetype }); // Add mimetype
        }
    });
    state.clearSidebarSelectedFiles();
    setStatus(`Attached ${state.attachedFiles.length} file(s) (full content).`);
}

export async function attachSelectedFilesSummary() {
    if (state.currentTab !== 'chat' || state.isLoading) {
        setStatus("Cannot attach files: Not on Chat tab or busy.", true);
        return;
    }
    const selectedFiles = [...state.sidebarSelectedFiles];
    if (selectedFiles.length === 0) {
        setStatus("No files selected in the sidebar to attach.", true);
        return;
    }
    setLoading(true, "Attaching Summaries (generating if needed)...");
    const filesToAttach = [];
    const errors = [];

    for (const file of selectedFiles) {
        setStatus(`Processing ${file.filename}...`);
        let summaryAvailable = file.has_summary;
        let fileId = file.id;

        if (!summaryAvailable) {
            setStatus(`Generating summary for ${file.filename}...`);
            try {
                await fetchSummary(fileId);
                const updatedFile = state.uploadedFiles.find(f => f.id === fileId);
                const summaryLooksValid = !state.summaryContent.startsWith('[Error');
                if ((updatedFile && updatedFile.has_summary) || summaryLooksValid) {
                    summaryAvailable = true;
                    setStatus(`Summary generated and attached for ${file.filename}.`);
                } else {
                    const errorMsg = state.summaryContent.startsWith('[Error') ? state.summaryContent : `[Error: Failed to generate or verify summary for ${file.filename}]`;
                    console.error(`Summary generation failed for ${file.filename}: ${errorMsg}`);
                    errors.push(`${file.filename}: ${errorMsg}`); // Use errorMsg
                    summaryAvailable = false;
                }
            } catch (error) {
                console.error(`Error during summary attachment logic for ${file.filename}:`, error);
                const specificError = error.message || (state.summaryContent.startsWith('[Error') ? state.summaryContent : `[Error: Unknown issue processing summary for ${file.filename}]`);
                errors.push(`${file.filename}: ${specificError}`);
                summaryAvailable = false;
            }
        }
        if (summaryAvailable) {
            if (!state.attachedFiles.some(f => f.id === fileId && f.type === 'summary')) {
                 filesToAttach.push({ id: fileId, filename: file.filename, type: 'summary', mimetype: file.mimetype }); // Add mimetype
            } else {
                 console.log(`[DEBUG] File ${fileId} (summary) already attached, skipping duplicate.`);
            }
        }
    }
    filesToAttach.forEach(file => state.addAttachedFile(file));
    state.clearSidebarSelectedFiles();
    let finalStatus = `Attached ${filesToAttach.length} file(s) (summary).`;
    if (errors.length > 0) finalStatus += ` Errors: ${errors.join('; ')}`;
    setStatus(finalStatus, errors.length > 0);
    setLoading(false);
}

export async function loadCalendarEvents() {
    if (state.isLoading) return;
    if (state.currentTab !== 'chat') {
        setStatus("Loading calendar events only allowed on Chat tab.", true);
        return;
    }
    setLoading(true, "Loading Events");
    try {
        const response = await fetch('/api/calendar/events');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error ${response.status}`);
        }
        state.setCalendarContext(data.events || "[No event data received]");
        setStatus("Calendar events loaded.");
    } catch (error) {
        console.error('Error loading calendar events:', error);
        state.setCalendarContext(null);
        setStatus(`Error loading calendar events: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

export async function loadSavedChats() {
    if (!elements.savedChatsList) return;
    const wasLoading = state.isLoading;
    if (!wasLoading) setLoading(true, "Loading Chats");
    state.setSavedChats([]);
    try {
        const response = await fetch('/api/chats');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const chats = await response.json();
        state.setSavedChats(chats);
        setStatus("Saved chats loaded.");
    } catch (error) {
        console.error('Error loading saved chats:', error);
        setStatus("Error loading saved chats.", true);
        throw error;
    } finally {
        if (!wasLoading) setLoading(false);
    }
}

export async function startNewChat() {
    if (state.isLoading) return;
    setLoading(true, "Creating Chat");
    state.setCurrentChatId(null);
    state.setCurrentChatName('');
    state.setCurrentChatModel('');
    state.setChatHistory([]);
    resetChatContext();
    state.setCurrentChatMode('chat');
    try {
        const response = await fetch('/api/chat', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newChat = await response.json();
        await loadChat(newChat.id);
        await loadSavedChats();
        setStatus(`New chat created (ID: ${newChat.id}).`);
    } catch (error) {
        console.error('Error starting new chat:', error);
        setStatus("Error creating new chat.", true);
    } finally {
        setLoading(false);
    }
}

export async function loadChat(chatId) {
    setLoading(true, "Loading Chat");
    state.setChatHistory([]);
    try {
        const response = await fetch(`/api/chat/${chatId}`);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status} ${response.statusText} - ${errorText}`);
        }
        const data = await response.json();
        const fetchedHistory = data.history || [];
        const currentHistory = state.chatHistory;
        let historyNeedsUpdate = true;
        if (currentHistory.length > 0 && fetchedHistory.length > 0) {
            const lastCurrentMsg = currentHistory[currentHistory.length - 1];
            const lastFetchedMsg = fetchedHistory[fetchedHistory.length - 1];
            if (lastCurrentMsg.role === 'assistant' && lastFetchedMsg.role === 'assistant' && lastCurrentMsg.content === lastFetchedMsg.content) {
                console.log(`[DEBUG] loadChat(${chatId}): Last message matches current state. Skipping history update to prevent duplication.`);
                historyNeedsUpdate = false;
            }
        }
        state.setCurrentChatId(data.details.id);
        localStorage.setItem('currentChatId', data.details.id);
        state.setCurrentChatName(data.details.name || '');
        state.setCurrentChatModel(data.details.model_name || '');
        if (historyNeedsUpdate) {
            console.log(`[DEBUG] loadChat(${chatId}): Updating chat history state.`);
            state.setChatHistory(fetchedHistory);
        }
        state.setCurrentChatMode('chat');
        resetChatContext();
        state.setAttachedFiles(data.details.attached_files || []);
        setStatus(`Chat ${state.currentChatId} loaded.`);
    } catch (error) {
        console.error(`Error loading chat ${chatId}:`, error);
        setStatus(`Error loading chat ${chatId}.`, true);
        state.setCurrentChatId(null);
        localStorage.removeItem('currentChatId');
        state.setCurrentChatName('');
        state.setCurrentChatModel('');
        state.setChatHistory([]);
        resetChatContext();
        state.setCurrentChatMode('chat');
        throw error;
    } finally {
        setLoading(false);
    }
}

function resetChatContext() {
    state.clearSidebarSelectedFiles();
    state.clearAttachedFiles();
    state.setSessionFile(null);
    state.setCalendarContext(null);
    state.setCalendarContextActive(false);
    state.setWebSearchEnabled(false);
}

export function sendMessage() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        setStatus("Cannot send: No active chat, busy, or not on Chat tab.", true);
        return;
    }
    if (!socket || !socket.connected) {
        setStatus("Cannot send: Not connected to the server.", true);
        return;
    }

    const message = elements.messageInput?.value.trim() || '';
    const stagedAttachedFiles = state.attachedFiles; // Files from sidebar (full/summary)
    const stagedSessionFile = state.sessionFile;     // File from paperclip
    const calendarContextToSend = (state.isCalendarContextActive && state.calendarContext) ? state.calendarContext : null;
    const webSearchEnabledToSend = state.isWebSearchEnabled;
    const deepResearchEnabled = state.isDeepResearchEnabled;
    const mode = deepResearchEnabled ? 'deep_research' : 'chat';

    // --- Prepare attachments list for chat history and backend payload ---
    const attachmentsForHistory = [];
    const backendAttachedFilesPayload = []; // For files like full/summary from sidebar
    const backendSessionFilesPayload = [];  // For the main session file

    if (stagedSessionFile) {
        attachmentsForHistory.push({
            filename: stagedSessionFile.filename,
            type: 'session', // UI hint
            mimetype: stagedSessionFile.mimetype
        });
        backendSessionFilesPayload.push({
            filename: stagedSessionFile.filename,
            content: stagedSessionFile.content, // Base64 content
            mimetype: stagedSessionFile.mimetype
        });
    }

    stagedAttachedFiles.forEach(file => {
        attachmentsForHistory.push({
            id: file.id, // Keep ID if available
            filename: file.filename,
            type: file.type, // 'full' or 'summary'
            mimetype: file.mimetype
        });
        // For backend, send only id and type for these, as content is already on server
        backendAttachedFilesPayload.push({ id: file.id, type: file.type });
    });
    // --- End Attachment Preparation ---


    if (mode === 'deep_research') {
        if (!message) {
            setStatus("Deep Research mode requires a text query.", true);
            return;
        }
    } else {
        if (!message && attachmentsForHistory.length === 0 && !calendarContextToSend && !webSearchEnabledToSend) {
            setStatus("Cannot send: Empty message and no context/files attached.", true);
            return;
        }
    }

    if (elements.messageInput) {
        elements.messageInput.value = '';
        ui.autoResizeTextarea(elements.messageInput);
    }

    // Add user message to state, now including the prepared attachmentsForHistory
    const userMessageContent = message || (attachmentsForHistory.length > 0 ? '[Context/Files Sent]' : '');
    if (userMessageContent) { // Only add if there's actual text or attachments
        state.addMessageToHistory({
            role: 'user',
            content: userMessageContent,
            attachments: attachmentsForHistory, // Pass the prepared attachments
            rawContent: message // Store original message for copy
        });
    }
 
    state.setProcessingChatId(state.currentChatId);
    setStatus(mode === 'deep_research' ? "Performing Deep Research..." : "Waiting for response...");

    const payload = {
        chat_id: state.currentChatId,
        message: message,
        attached_files: backendAttachedFilesPayload, // Use prepared payload
        session_files: backendSessionFilesPayload,   // Use prepared payload
        calendar_context: calendarContextToSend,
        enable_web_search: webSearchEnabledToSend,
        mode: mode,
        enable_streaming: (mode === 'chat'),
        improve_prompt: state.isImprovePromptEnabled,
    };

    console.log(`[DEBUG] >>>>> Preparing to emit 'send_chat_message'. Socket state: connected=${socket?.connected}, id=${socket?.id}`);
    console.log(`[DEBUG] Emitting 'send_chat_message' with payload:`, payload);
    socket.emit('send_chat_message', payload);
    console.log(`[DEBUG] <<<<< Finished emitting 'send_chat_message'.`);

    // Clear all staged attachments from the input area state
    state.clearAllCurrentMessageAttachments();
    // Sidebar selections are typically cleared when they are "attached" to the message draft (state.attachedFiles)
    // If they persist in state.sidebarSelectedFiles and should be cleared on send, do it here:
    // state.clearSidebarSelectedFiles(); 
}

export function cancelChatGeneration() {
    const processingId = state.processingChatId;
    if (!processingId) {
        console.warn("Cancel button clicked, but no chat is currently processing.");
        return;
    }
    if (!socket || !socket.connected) {
        setStatus("Cannot cancel: Not connected to the server.", true);
        return;
    }
    console.log(`[DEBUG] Emitting 'cancel_generation' for Chat ID: ${processingId}`);
    socket.emit('cancel_generation', { chat_id: processingId });
    setStatus("Requesting cancellation...");
}

export async function handleSaveChatName() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        if (state.currentTab !== 'chat') setStatus("Cannot save chat name: Not on Chat tab.", true);
        else if (!state.currentChatId) setStatus("Cannot save chat name: No active chat.", true);
        else if (state.isLoading) setStatus("Cannot save chat name: Application is busy.", true);
        return;
    }
    const newName = elements.currentChatNameInput?.value.trim() || 'New Chat';
    setLoading(true, "Saving Name");
    try {
        const response = await fetch(`/api/chat/${state.currentChatId}/name`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName }),
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`Chat ${state.currentChatId} name saved.`);
        state.setCurrentChatName(newName);
        await loadSavedChats();
    } catch (error) {
        console.error('Error saving chat name:', error);
        setStatus(`Error saving name: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

export async function handleDeleteChat(chatId) {
    if (state.isLoading || state.currentTab !== 'chat') return;
    const chatToDelete = state.savedChats.find(chat => chat.id === chatId);
    const chatName = chatToDelete ? (chatToDelete.name || `Chat ${chatId}`) : `Chat ${chatId}`;
    if (!confirm(`Are you sure you want to delete "${chatName}"? This cannot be undone.`)) return;
    setLoading(true, "Deleting Chat");
    try {
        const response = await fetch(`/api/chat/${chatId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`Chat ${chatId} deleted.`);
        state.setSavedChats(state.savedChats.filter(chat => chat.id !== chatId));
        if (chatId == state.currentChatId) {
            state.setCurrentChatId(null);
            localStorage.removeItem('currentChatId');
            const firstChat = state.savedChats.length > 0 ? state.savedChats[0] : null;
            if (firstChat) await loadChat(firstChat.id);
            else await startNewChat();
        }
    } catch (error) {
        console.error(`Error deleting chat ${chatId}:`, error);
        setStatus(`Error deleting chat: ${error.message}`, true);
        await loadSavedChats();
    } finally {
        setLoading(false);
    }
}

export async function handleModelChange() {
    if (!state.currentChatId || state.isLoading || state.currentTab !== 'chat') return;
    const newModel = elements.modelSelector?.value;
    if (!newModel) return;
    const originalModel = state.currentChatModel;
    setLoading(true, "Updating Model");
    try {
        const response = await fetch(`/api/chat/${state.currentChatId}/model`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_name: newModel })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        setStatus(`Model updated to ${newModel} for this chat.`);
        state.setCurrentChatModel(newModel);
    } catch (error) {
        console.error("Error updating model:", error);
        setStatus(`Error updating model: ${error.message}`, true);
        state.setCurrentChatModel(originalModel);
    } finally {
        setLoading(false);
    }
}

export async function loadSavedNotes() {
     if (!elements.savedNotesList) return;
     const wasLoading = state.isLoading;
     if (!wasLoading) setLoading(true, "Loading Notes");
     state.setSavedNotes([]);
     try {
         const response = await fetch('/api/notes');
         if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
         const notes = await response.json();
         state.setSavedNotes(notes);
         setStatus("Saved notes loaded.");
     } catch (error) {
         console.error('Error loading saved notes:', error);
         setStatus("Error loading saved notes.", true);
         throw error;
     } finally {
         if (!wasLoading) setLoading(false);
     }
}

export async function startNewNote() {
    console.log(`[DEBUG] startNewNote called.`);
    if (state.isLoading) return;
    setLoading(true, "Creating Note");
    state.setCurrentNoteId(null);
    state.setCurrentNoteName('');
    state.setNoteContent('');
    state.setNoteHistory([]);
    try {
        const response = await fetch('/api/notes', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newNote = await response.json();
        console.log(`[DEBUG] startNewNote: Received new note ID ${newNote.id}. Loading it...`);
        await loadNote(newNote.id);
        await loadSavedNotes();
        setStatus(`New note created (ID: ${newNote.id}).`);
        console.log(`[DEBUG] startNewNote: Successfully created and loaded note ${newNote.id}.`);
    } catch (error) {
        console.error('Error starting new note:', error);
        setStatus("Error creating new note.", true);
    } finally {
        setLoading(false);
    }
}

export async function loadNote(noteId) {
    console.log(`[DEBUG] loadNote(${noteId}) called.`);
    if (state.isLoading) return;
    setLoading(true, "Loading Note");
    state.setNoteContent('');
    state.setNoteHistory([]);
    try {
        const response = await fetch(`/api/note/${noteId}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        state.setCurrentNoteId(data.id);
        localStorage.setItem('currentNoteId', data.id);
        state.setCurrentNoteName(data.name || '');
        state.setNoteContent(data.content || '');
        await loadNoteHistory(noteId);
        setStatus(`Note ${state.currentNoteId} loaded.`);
    } catch (error) {
        console.error(`Error loading note ${noteId}:`, error);
        setStatus(`Error loading note ${noteId}.`, true);
        state.setCurrentNoteId(null);
        localStorage.removeItem('currentNoteId');
        state.setCurrentNoteName('');
        state.setNoteContent(`[Error loading note ${noteId}: ${error.message}]`);
        state.setNoteHistory([]);
        throw error;
    } finally {
        setLoading(false);
    }
}

export async function saveNote() {
    if (state.isLoading || !state.currentNoteId || state.currentTab !== 'notes') {
        if (state.currentTab !== 'notes') setStatus("Cannot save note: Not on Notes tab.", true);
        else if (!state.currentNoteId) setStatus("Cannot save note: No active note.", true);
        else if (state.isLoading) setStatus("Cannot save note: Application is busy.", true);
        return;
    }
    setLoading(true, "Saving Note");
    const noteName = state.currentNoteName || 'New Note';
    const noteContent = state.noteContent || '';
    try {
        const response = await fetch(`/api/note/${state.currentNoteId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: noteName, content: noteContent })
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`Note ${state.currentNoteId} saved successfully.`);
        await loadSavedNotes();
        await loadNoteHistory(state.currentNoteId);
    } catch (error) {
        console.error(`Error saving note ${state.currentNoteId}:`, error);
        setStatus(`Error saving note: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

export async function handleDeleteNote(noteId) {
    if (state.isLoading || state.currentTab !== 'notes') return;
    const noteToDelete = state.savedNotes.find(note => note.id === noteId);
    const noteName = noteToDelete ? (noteToDelete.name || `Note ${noteId}`) : `Note ${noteId}`;
    if (!confirm(`Are you sure you want to delete "${noteName}"? This cannot be undone.`)) return;
    setLoading(true, "Deleting Note");
    try {
        const response = await fetch(`/api/note/${noteId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        setStatus(`Note ${noteId} deleted.`);
        state.setSavedNotes(state.savedNotes.filter(note => note.id !== noteId));
        if (noteId == state.currentNoteId) {
            state.setCurrentNoteId(null);
            localStorage.removeItem('currentNoteId');
            state.setNoteContent('');
            state.setNoteHistory([]);
            const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null;
            if (firstNote) await loadNote(firstNote.id);
            else await startNewNote();
        }
    } catch (error) {
        console.error(`Error deleting note ${noteId}:`, error);
        setStatus(`Error deleting note: ${error.message}`, true);
        await loadSavedNotes();
    } finally {
        setLoading(false);
    }
}

export async function loadNoteHistory(noteId) {
    try {
        const response = await fetch(`/api/notes/${noteId}/history`);
        if (!response.ok) {
             const errorData = await response.json();
             throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const history = await response.json();
        state.setNoteHistory(history);
    } catch (error) {
        state.setNoteHistory([]);
        throw error;
    }
}

export async function generateNoteDiffSummaryForHistoryItem(noteId, historyId) {
    if (state.isLoading) {
        setStatus("Cannot generate summary: Application is busy.", true);
        return false;
    }
    setLoading(true, `Generating summary for version ${historyId}...`);
    try {
        const response = await fetch(`/api/notes/${noteId}/history/${historyId}/generate_summary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        if (data.error && data.error.includes("Failed to save")) {
             setStatus(`Summary generated for version ${historyId}, but failed to save.`, true);
             await loadNoteHistory(noteId);
             return false;
        } else if (data.message && data.message.includes("already existed")) {
             setStatus(`Summary for version ${historyId} already existed.`);
             return true;
        } else {
             setStatus(`Summary generated for version ${historyId}.`);
             await loadNoteHistory(noteId);
             return true;
        }
    } catch (error) {
        console.error(`Error generating/saveSummary for history ${historyId}:`, error);
        setStatus(`Error generating summary: ${error.message}`, true);
        try { await loadNoteHistory(noteId); }
        catch (reloadError) { console.error(`Error reloading note history after summary generation failure:`, reloadError); }
        return false;
    } finally {
        setLoading(false);
    }
}

export async function cleanupTranscript(rawTranscript) {
    if (state.isLoading) {
        throw new Error("Application is busy.");
    }
    setLoading(true, "Cleaning Transcript");
    try {
        const response = await fetch('/api/voice/cleanup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript: rawTranscript })
        });
        const responseText = await response.text();
        let data;
        try { data = JSON.parse(responseText); }
        catch (parseError) { throw new Error(`Failed to parse API response. Status: ${response.status}`); }
        if (!response.ok) { throw new Error(data.error || `HTTP error! status: ${response.status}`); }
        const cleanedTranscript = data.cleaned_transcript;
        setStatus("Transcript cleaned.");
        return cleanedTranscript;
    } catch (error) {
        console.error('Error during cleanupTranscript fetch/processing:', error);
        setStatus(`Cleanup failed: ${error.message}`, true);
        throw error;
    } finally {
        setLoading(false);
    }
}

export async function loadInitialChatData() {
    let chatToLoadId = state.currentChatId;
    let chatFoundInList = false;
    if (chatToLoadId !== null && state.savedChats.length > 0) {
        chatFoundInList = state.savedChats.some(chat => chat.id === chatToLoadId);
        if (!chatFoundInList) {
            state.setCurrentChatId(null);
            localStorage.removeItem('currentChatId');
            chatToLoadId = null;
        }
    } else if (chatToLoadId !== null && state.savedChats.length === 0) {
         state.setCurrentChatId(null);
         localStorage.removeItem('currentChatId');
         chatToLoadId = null;
    }
    if (state.currentChatId === null) {
        const firstChat = state.savedChats.length > 0 ? state.savedChats[0] : null;
        if (firstChat) await loadChat(firstChat.id);
        else await startNewChat();
    }
}

export async function loadInitialNotesData() {
    let noteToLoadId = state.currentNoteId;
    let noteFoundInList = false;
    if (noteToLoadId !== null && state.savedNotes.length > 0) {
        noteFoundInList = state.savedNotes.some(note => note.id === noteToLoadId);
        if (!noteFoundInList) {
            state.setCurrentNoteId(null);
            localStorage.removeItem('currentNoteId');
            noteToLoadId = null;
        }
    } else if (noteToLoadId !== null && state.savedNotes.length === 0) {
         state.setCurrentNoteId(null);
         localStorage.removeItem('currentNoteId');
         noteToLoadId = null;
    }
    if (state.currentNoteId === null) {
        const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null;
        if (firstNote) await loadNote(firstNote.id);
        else await startNewNote();
    }
}
