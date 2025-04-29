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


// --- Voice Transcription API (WebSocket) ---

/**
 * Connects to the WebSocket server for transcription.
 * @param {string} languageCode - e.g., 'en-US'
 * @param {string} audioFormat - e.g., 'WEBM_OPUS' (must match frontend recording)
 * @returns {Promise<void>} A promise that resolves when the backend confirms transcription started, or rejects on error.
 */
export function connectTranscriptionSocket(languageCode = 'en-US', audioFormat = 'WEBM_OPUS') {
    // Return a promise that resolves when the backend confirms the stream is ready
    return new Promise((resolve, reject) => {

        // --- Promise state management ---
        // Use flags to prevent resolving/rejecting multiple times, especially with existing sockets
        let promiseResolved = false;
        let promiseRejected = false;

        const resolveOnce = () => {
            if (!promiseResolved && !promiseRejected) {
                promiseResolved = true;
                // Remove temporary listeners if they were added for this specific call
                if (socket) {
                    socket.off('transcription_started', handleStarted);
                    socket.off('transcription_error', handleError);
                    socket.off('disconnect', handleDisconnectError); // Remove disconnect listener added for this promise
                }
                resolve();
            }
        };
        const rejectOnce = (error) => {
             if (!promiseResolved && !promiseRejected) {
                promiseRejected = true;
                 // Remove temporary listeners if they were added for this specific call
                if (socket) {
                    socket.off('transcription_started', handleStarted);
                    socket.off('transcription_error', handleError);
                    socket.off('disconnect', handleDisconnectError); // Remove disconnect listener added for this promise
                }
                reject(error);
            }
        };

        // --- Temporary event handlers for this specific promise ---
        const handleStarted = (data) => {
            setStatus("Recording... Speak now."); // Update status
            resolveOnce(); // Resolve the promise
        };
        const handleError = (data) => {
            // This handler catches errors specifically related to *this* start attempt
            console.error("Transcription error from backend during start (handler):", data.error);
            setStatus(`Transcription Error: ${data.error}`, true);
            // Don't disconnect here, let the caller decide based on rejection
            rejectOnce(new Error(data.error)); // Reject the promise
        };
         const handleDisconnectError = (reason) => {
            console.warn(`WebSocket disconnected while waiting for transcription start: ${reason}`);
            setStatus("Transcription service disconnected before starting.", true);
            rejectOnce(new Error(`WebSocket disconnected: ${reason}`));
        };
        // ----------------------------------------------------------


        // --- Check existing socket state ---
        if (socket && socket.connected) {
            setStatus("Initializing transcription stream...");

            // Add temporary listeners for this specific request
            socket.on('transcription_started', handleStarted);
            socket.on('transcription_error', handleError);
            socket.on('disconnect', handleDisconnectError); // Handle disconnect while waiting

            // Emit start_transcription on the existing socket
            socket.emit('start_transcription', { languageCode, audioFormat });
            // The promise will resolve/reject based on the temporary handlers above

            return; // Don't create a new socket
        }
        // ------------------------------------

        // --- Create new socket connection if needed ---

        // Ensure Socket.IO client library is loaded
        if (typeof io === 'undefined') {
            console.error("Socket.IO client library not found. Make sure it's included.");
            setStatus("Error: Missing Socket.IO library.", true);
            rejectOnce(new Error("Socket.IO client library not found.")); // Reject the promise
            return;
        }

        setStatus("Connecting to transcription service...");
        state.setIsSocketConnected(false); // Update state

        // Connect to the Socket.IO server - Creates the *single* socket instance
        socket = io({
            // Optional: Add reconnection options if needed
            // reconnectionAttempts: 5,
            // reconnectionDelay: 1000,
        });

        // --- Permanent Event Handlers for the new socket instance ---
        // These handlers stay attached for the lifetime of the socket connection.

        socket.on('connect', () => {
            setStatus("Transcription service connected. Initializing stream..."); // Status on connect
            state.setIsSocketConnected(true); // Update state

            // Add temporary listeners for the *initial* start request after connection
            socket.once('transcription_started', handleStarted);
            socket.once('transcription_error', handleError);
            socket.once('disconnect', handleDisconnectError); // Handle disconnect while waiting for initial start

            // Emit start_transcription automatically after connecting
            socket.emit('start_transcription', { languageCode, audioFormat });
        });

        socket.on('connect_error', (error) => {
            console.error("WebSocket connection error:", error);
            setStatus(`Transcription connection failed: ${error.message}`, true);
            state.setIsSocketConnected(false); // Update state
            socket = null; // Nullify on connection error
            rejectOnce(error); // Reject the promise if connection fails
        });

        socket.on('disconnect', (reason) => {
            console.log("WebSocket disconnected:", reason);
            // Only update status if it wasn't an error that caused the disconnect
            if (!state.isErrorStatus) {
                 setStatus("Transcription service disconnected.");
            }
            state.setIsSocketConnected(false);
            state.setStreamingTranscript(""); // Clear transcript on disconnect
            socket = null; // Nullify on disconnect
            // Note: If disconnect happens *while waiting* for 'transcription_started',
            // the temporary handleDisconnectError listener will reject the promise.
            // If it happens later, it's just a disconnect, no promise rejection needed.
        });

        // Permanent handler for transcript updates
        socket.on('transcript_update', (data) => {
            // --- REVISED Transcript Update Logic using new state ---
            if (data && data.transcript !== undefined) {
                const newSegment = data.transcript.trim();

                if (data.is_final && newSegment) { // Process non-empty final segments
                    // Append the final segment to the finalized transcript state
                    state.appendFinalizedTranscript(newSegment);
                    // Clear the interim transcript state
                    state.setCurrentInterimTranscript("");
                } else if (!data.is_final) { // Process interim results
                    // Update the interim transcript state with the latest interim result
                    state.setCurrentInterimTranscript(newSegment);
                }
                // Ignore empty final segments (no action needed)
            }
        });

        // Permanent handler for backend errors during transcription
        socket.on('transcription_error', (data) => {
            // This handler catches errors *after* the initial 'transcription_started'
            // or errors broadcast without a specific temporary handler.
            console.error("Transcription error from backend (permanent handler):", data.error);
            setStatus(`Transcription Error: ${data.error}`, true);
            // Don't automatically disconnect, maybe the user wants to retry?
            // disconnectTranscriptionSocket();
            // We don't reject the promise here, as it was likely already resolved or
            // is being handled by a temporary error handler.
            // The error status is set, UI should reflect this.
        });

        // --- Handlers below are mostly for logging/confirmation ---

        // This permanent listener is just for logging subsequent starts if needed,
        // the promise resolution is handled by the temporary listener added above.
        socket.on('transcription_started', (data) => {
             // Status is set by the temporary handler or subsequent calls
        });

        // Listener for the final completion signal from the backend
        // This is now handled by the temporary listener within stopAudioStream promise
        // socket.on('transcription_complete', (data) => {
        //     console.log("Backend confirmed transcription complete (permanent listener):", data.message);
        // });

        // Optional: Keep for logging if needed, but completion is handled by the promise
        socket.on('transcription_stop_acknowledged', (data) => {
        });
    }); //End of promise constructor
}

/**
 * Sends an audio chunk over the WebSocket.
 * @param {Blob | ArrayBuffer | Buffer} chunk - The audio data chunk.
 */
export function sendAudioChunk(chunk) {
    if (socket && socket.connected) {
        // console.debug(`Sending audio chunk, size: ${chunk.size || chunk.byteLength}`); // Verbose
        socket.emit('audio_chunk', chunk);
    } else {
        console.warn("Cannot send audio chunk: WebSocket not connected.");
        // Handle error - maybe try reconnecting or notify user
        setStatus("Error: Transcription service disconnected. Cannot send audio.", true);
    }
}

/**
 * Signals the backend that audio streaming is finished and returns a promise
 * that resolves when the backend confirms completion, or rejects on error/disconnect.
 * @returns {Promise<void>}
 */
export function stopAudioStream() {
    return new Promise((resolve, reject) => {
        if (!socket || !socket.connected) {
            console.warn("Cannot signal stop: WebSocket not connected.");
            return reject(new Error("WebSocket not connected."));
        }

        // --- Promise state management ---
        let promiseResolved = false;
        let promiseRejected = false;
        let timeoutId = null; // Declare timeoutId here

        // Define removeListeners helper first
        const removeListeners = () => {
            if (socket) {
                socket.off('transcription_complete', handleComplete);
                socket.off('transcription_error', handleError);
                socket.off('disconnect', handleDisconnect);
            }
        };

        // Define resolveOnce and rejectOnce with clearTimeout built-in
        const resolveOnce = (message = "Transcription complete.") => {
            if (!promiseResolved && !promiseRejected) {
                clearTimeout(timeoutId); // Clear timeout on resolve
                promiseResolved = true;
                removeListeners();
                resolve();
            }
        };
        const rejectOnce = (error) => {
             if (!promiseResolved && !promiseRejected) {
                clearTimeout(timeoutId); // Clear timeout on reject
                promiseRejected = true;
                removeListeners();
                reject(error);
            }
        };

        // --- Temporary listeners for this stop request (using the functions defined above) ---
        const handleComplete = (data) => {
            resolveOnce(data.message);
        };
        const handleError = (data) => {
            console.error("Transcription error received while waiting for completion:", data.error);
            rejectOnce(new Error(data.error));
        };
        const handleDisconnect = (reason) => {
            console.warn(`WebSocket disconnected while waiting for transcription completion: ${reason}`);
            rejectOnce(new Error(`WebSocket disconnected: ${reason}`));
        };
        // -------------------------------------------------

        // Add listeners specifically for this stop request
        socket.on('transcription_complete', handleComplete);
        socket.on('transcription_error', handleError); // Catch errors during finalization
        socket.on('disconnect', handleDisconnect);

        // Emit the stop signal
        socket.emit('stop_transcription');

        // Optional: Add a timeout in case the backend never sends 'transcription_complete'
        const timeoutDuration = 10000; // 10 seconds
        // Assign to the timeoutId declared earlier
        timeoutId = setTimeout(() => {
             rejectOnce(new Error(`Timeout waiting for transcription completion after ${timeoutDuration}ms`));
        }, timeoutDuration);

        // No need to modify resolveOnce/rejectOnce here, clearTimeout is already included

    }); // End of promise constructor
}

/**
 * Disconnects the WebSocket.
 */
export function disconnectTranscriptionSocket() {
    if (socket) {
        socket.disconnect();
        socket = null; // Clear reference
        state.setIsSocketConnected(false); // Update state
        // Clear transcript state as well? Depends on desired behavior.
        // state.setStreamingTranscript("");
    }
}


// --- NEW: Long Audio Transcription API Call ---
export async function transcribeLongAudio(audioBlob, languageCode = 'en-US') {
    // Show a specific "transcribing" toast
    const transcribingToastId = showToast("Transcribing recorded audio...", { autoClose: false, type: 'info' });
    console.log(`[DEBUG] transcribeLongAudio: Showing transcribing toast ID: ${transcribingToastId}`); // Add log

    const formData = new FormData();
    // Use a generic filename, backend doesn't rely on it but it's good practice
    formData.append('audio_blob', audioBlob, `long_recording.${MIME_TYPE.split('/')[1].split(';')[0]}`); // e.g., long_recording.webm
    formData.append('languageCode', languageCode);
    // *** Crucially, send the MIME type used for recording ***
    formData.append('mimeType', MIME_TYPE);

    try {
        const response = await fetch('/api/voice/transcribe_long', {
            method: 'POST',
            body: formData,
            // No 'Content-Type' header needed for FormData, browser sets it with boundary
        });

        console.log(`[DEBUG] transcribeLongAudio: Removing transcribing toast ID: ${transcribingToastId}`); // Add log
        removeToast(transcribingToastId); // Remove "transcribing" toast regardless of outcome

        if (!response.ok) {
            // Try to parse error JSON, provide fallback
            const errorData = await response.json().catch(() => ({ error: `HTTP error ${response.status}` }));
            console.error('Long transcription API error:', response.status, errorData);
            showToast(`Transcription Error: ${errorData.error || response.statusText}`, { type: 'error' }); // Show error toast
            state.setLastLongTranscript(''); // Clear any previous transcript on error
            return null; // Indicate failure
        }

        const data = await response.json();
        state.setLastLongTranscript(data.transcript); // Store transcript in state

        // Show success toast with snippet, copy button, and close button
        const snippet = data.transcript.substring(0, 70) + (data.transcript.length > 70 ? '...' : '');
        // Ensure buttons have data attributes to identify target and action
        const toastContent = `
            <div class="flex flex-col space-y-1 relative pr-4">
                <button class="toast-close-button absolute top-0 right-0 px-1 py-0 text-white hover:text-gray-300 text-lg leading-none" title="Close">&times;</button>
                <span class="font-medium">Transcription Complete:</span>
                <span class="text-xs italic">"${escapeHtml(snippet)}"</span>
                <button class="toast-copy-button self-end mt-1 px-2 py-0.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-300" data-transcript-target="long">Copy</button>
            </div>
        `;
        // Set autoClose to false so it only closes via the 'x' button
        showToast(toastContent, { type: 'success', autoClose: false });

        return data.transcript; // Return the full transcript

    } catch (error) {
        console.error('Network or other error during long transcription:', error);
        // Ensure toast is removed on network error, even if it wasn't explicitly removed above
        if (transcribingToastId) {
             console.log(`[DEBUG] transcribeLongAudio (catch): Removing transcribing toast ID: ${transcribingToastId}`); // Add log
             removeToast(transcribingToastId);
        }
        showToast(`Transcription Error: ${error.message}`, { type: 'error' }); // Show error toast
        state.setLastLongTranscript(''); // Clear any previous transcript on error
        return null; // Indicate failure
    }
}
// -----------------------------------------


// --- File API --- (Keep existing file API functions)

/** Deletes a file from the backend and updates the state. */
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

        // Update state lists directly
        state.removeSidebarSelectedFileById(fileId); // Remove from sidebar selection state
        state.removeAttachedFileById(fileId); // Remove from attached state
        if (state.sessionFile && state.sessionFile.id === fileId) { // Check if it's the session file
             state.setSessionFile(null);
        }

        // Reload the full list to ensure UI consistency (this will update state.uploadedFiles)
        await loadUploadedFiles();

    } catch (error) {
        console.error('Error deleting file:', error);
        setStatus(`Error deleting file: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

/** Loads uploaded files from the backend and updates the state. */
export async function loadUploadedFiles() {
    // Only load if Files plugin is enabled
    if (!state.isFilePluginEnabled) {
        state.setUploadedFiles([]); // Clear list if plugin disabled
        // Status will be updated by updatePluginUI based on state.isFilePluginEnabled
        return;
    }

    // Set loading state only if not already loading (might be called during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) setLoading(true, "Loading Files");

    // Clear current list in state immediately to show loading state in UI
    state.setUploadedFiles([]);

    try {
        const response = await fetch('/api/files');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const files = await response.json();

        // Update state with fetched files
        state.setUploadedFiles(files);

        setStatus("Uploaded files loaded.");
    } catch (error) {
        console.error('Error loading uploaded files:', error);
        setStatus("Error loading files.", true);
        // state.uploadedFiles is already [] from above
        throw error; // Re-throw for caller (e.g., initializeApp) to handle if needed
    } finally {
        // Only turn off loading if this function set it
        if (!wasLoading) setLoading(false);
    }
}


/** Handles file upload triggered from the modal. */
export async function handleFileUpload(event) {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
        setStatus("File uploads only allowed when Files plugin is enabled and on Chat tab.", true);
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }

    const files = event.target.files;
    if (!files || files.length === 0) {
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
        return;
    }

    // --- FIX: Reset the input value immediately after getting files ---
    // This prevents the 'change' event from potentially re-firing when the value is cleared later.
    if(elements.fileUploadModalInput) elements.fileUploadModalInput.value = '';
    // -----------------------------------------------------------------

    // --- FIX: Disable input and label during upload ---
    if (elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = true;
    if (elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.add('disabled');
    // -------------------------------------------------

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
        // --- FIX: Re-enable input and label ---
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = false;
        if(elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.remove('disabled');
        // -------------------------------------
        // Input value is already reset
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

        // Reload the file list state after upload
        await loadUploadedFiles();

    } catch (error) {
        console.error('Error uploading files:', error);
        setStatus(`Error uploading files: ${error.message}`, true);
    } finally {
        setLoading(false);
        // --- FIX: Re-enable input and label ---
        if(elements.fileUploadModalInput) elements.fileUploadModalInput.disabled = false;
        if(elements.fileUploadModalLabel) elements.fileUploadModalLabel.classList.remove('disabled');
        // Input value is already reset
        // -----------------------------------------------------
        // Closing modal should be handled by event listener or UI logic reacting to state
    }
}

/** Adds a file by fetching content from a URL. */
export async function addFileFromUrl(url) {
     if (state.isLoading) return;
     if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         // Status update for URL modal handled by event listener
         return;
     }
     if (!url || !url.startsWith('http')) {
         // Status update for URL modal handled by event listener
         return;
     }

     setLoading(true, "Fetching URL");
     // Status update for URL modal handled by event listener

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
         // Status update for URL modal handled by event listener
         if(elements.urlInput) elements.urlInput.value = ''; // Clear input

         // Reload the file list state
         await loadUploadedFiles();

         // Closing modal should be handled by event listener or UI logic reacting to state
     } catch (error) {
         console.error('Error adding file from URL:', error);
         setStatus(`Error adding file from URL: ${error.message}`, true);
         // Status update for URL modal handled by event listener
     } finally {
         setLoading(false);
     }
}

/** Fetches/Generates summary and updates state. */
export async function fetchSummary(fileId) {
    if (state.isLoading) return;
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         setStatus("Fetching summaries requires Files plugin enabled on Chat tab.", true);
         return;
    }

    setLoading(true, "Fetching Summary");
    // Status update for summary modal handled by UI reacting to loading state

    try {
        const response = await fetch(`/api/files/${fileId}/summary`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        const data = await response.json();

        // Update state with the summary content
        // Assuming state has a place to hold the summary for the currently edited file
        // We need a state variable for the summary content itself, tied to currentEditingFileId
        state.setCurrentEditingFileId(fileId); // Ensure state knows which file summary is being edited
        state.setSummaryContent(data.summary); // Assuming you add setSummaryContent to state.js

        setStatus(`Summary loaded/generated for file ${fileId}.`);

        // Reload file list state to update has_summary flag in UI
        await loadUploadedFiles();

    } catch (error) {
        console.error("Error fetching summary:", error);
        state.setSummaryContent(`[Error loading summary: ${error.message}]`); // Update state with error
        setStatus(`Error fetching summary for file ${fileId}.`, true);
    } finally {
        setLoading(false);
    }
}


/** Saves the edited summary. */
export async function saveSummary() {
    if (!state.currentEditingFileId || state.isLoading) return;
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat') {
         setStatus("Saving summaries requires Files plugin enabled on Chat tab.", true);
         return;
    }

    // Read the summary content from the state, not the DOM directly
    const updatedSummary = state.summaryContent; // Assuming you add summaryContent to state.js

    setLoading(true, "Saving Summary");
    // Status update handled by UI reacting to loading state

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

        // Reload file lists to update summary status display (has_summary flag)
        await loadUploadedFiles();

        // Closing modal should be handled by event listener or UI logic reacting to state
    } catch (error) {
        console.error("Error saving summary:", error);
        setStatus("Error saving summary.", true);
    } finally {
        setLoading(false);
    }
}

/**
 * Attaches selected files from the sidebar to the current chat as 'full' files.
 * Updates state.attachedFiles and clears state.sidebarSelectedFiles.
 */
export function attachSelectedFilesFull() {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat' || state.isLoading) {
        setStatus("Cannot attach files: Files plugin disabled, not on Chat tab, or busy.", true);
        return;
    }
    if (state.sidebarSelectedFiles.length === 0) {
        setStatus("No files selected in the sidebar to attach.", true);
        return;
    }

    // Add selected files to the attachedFiles state with type 'full'
    state.sidebarSelectedFiles.forEach(file => {
        // Ensure we don't add duplicates (same file ID, same type)
        if (!state.attachedFiles.some(f => f.id === file.id && f.type === 'full')) {
             state.addAttachedFile({ id: file.id, filename: file.filename, type: 'full' });
        }
    });

    // Clear the temporary sidebar selection state
    state.clearSidebarSelectedFiles();

    // UI will react to state changes (attachedFiles and sidebarSelectedFiles)
    setStatus(`Attached ${state.attachedFiles.length} file(s) (full content).`); // Status message might need refinement
}

/**
 * Attaches selected files from the sidebar to the current chat as 'summary' files.
 * Updates state.attachedFiles and clears state.sidebarSelectedFiles.
 * Generates summaries if they don't exist.
 */
export async function attachSelectedFilesSummary() {
    if (!state.isFilePluginEnabled || state.currentTab !== 'chat' || state.isLoading) {
        setStatus("Cannot attach files: Files plugin disabled, not on Chat tab, or busy.", true);
        return;
    }
    const selectedFiles = [...state.sidebarSelectedFiles]; // Copy selection
    if (selectedFiles.length === 0) {
        setStatus("No files selected in the sidebar to attach.", true);
        return;
    }

    setLoading(true, "Attaching Summaries (generating if needed)...");
    const filesToAttach = []; // Collect files to attach after processing
    const errors = [];

    for (const file of selectedFiles) {
        setStatus(`Processing ${file.filename}...`); // Update status per file
        let summaryAvailable = file.has_summary;
        let fileId = file.id; // Get file ID

        if (!summaryAvailable) {
            setStatus(`Generating summary for ${file.filename}...`);
            try {
                // Call fetchSummary which handles the API call, state update, and file list reload
                await fetchSummary(fileId);

                // Check state for the summary content after fetchSummary completes
                // fetchSummary calls loadUploadedFiles on success, which updates state.uploadedFiles
                const updatedFile = state.uploadedFiles.find(f => f.id === fileId);

                // Check if summary generation was successful.
                // fetchSummary updates state.summaryContent and reloads state.uploadedFiles.
                // const updatedFile = state.uploadedFiles.find(f => f.id === fileId); // Removed duplicate declaration
                const summaryLooksValid = !state.summaryContent.startsWith('[Error'); // Check if fetchSummary reported success

                // Consider summary available if the reloaded data shows it OR if fetchSummary didn't report an error.
                if ((updatedFile && updatedFile.has_summary) || summaryLooksValid) {
                    summaryAvailable = true; // Mark as available after successful generation
                    setStatus(`Summary generated and attached for ${file.filename}.`);
                } else {
                    // If both checks fail, generation likely failed.
                    const errorMsg = state.summaryContent.startsWith('[Error')
                        ? state.summaryContent // Use the specific error from fetchSummary/state
                        : `[Error: Failed to generate or verify summary for ${file.filename}]`; // Fallback error
                    console.error(`Summary generation failed for ${file.filename}: ${errorMsg}`);
                    errors.push(`${file.filename}: ${specificError}`); // Use specificError
                    summaryAvailable = false; // Ensure it's not attached if generation failed
                }
            } catch (error) { // This catch block handles errors *within the try block above*
                // This catch block handles errors *within the try block above*,
                // like issues finding the updatedFile or accessing properties.
                // Errors from fetchSummary itself are handled by checking state.summaryContent.
                console.error(`Error during summary attachment logic for ${file.filename}:`, error);
                // Use the caught error message if available, otherwise use the state message or a generic one
                const specificError = error.message || (state.summaryContent.startsWith('[Error') ? state.summaryContent : `[Error: Unknown issue processing summary for ${file.filename}]`);
                errors.push(`${file.filename}: ${specificError}`);
                summaryAvailable = false; // Ensure it's not attached if generation failed
            }
        }

        // If summary was initially available or successfully generated, prepare to attach
        if (summaryAvailable) {
            // Check for duplicates in the main attachedFiles state before adding
            if (!state.attachedFiles.some(f => f.id === fileId && f.type === 'summary')) {
                 filesToAttach.push({ id: fileId, filename: file.filename, type: 'summary' });
            } else {
                 console.log(`[DEBUG] File ${fileId} (summary) already attached, skipping duplicate.`);
            }
        }
    } // End for loop

    // Now add all successfully processed files to the state
    filesToAttach.forEach(file => {
        state.addAttachedFile(file); // Notifies attachedFiles
    });

    // Clear the temporary sidebar selection state
    state.clearSidebarSelectedFiles(); // Notifies sidebarSelectedFiles

    // Final status update
    let finalStatus = `Attached ${filesToAttach.length} file(s) (summary).`;
    if (errors.length > 0) {
        finalStatus += ` Errors: ${errors.join('; ')}`;
    }
    setStatus(finalStatus, errors.length > 0);
    setLoading(false);
}


// --- Calendar API ---

/** Fetches calendar events and updates state. */
export async function loadCalendarEvents() {
    if (state.isLoading) return;
    if (!state.isCalendarPluginEnabled || state.currentTab !== 'chat') {
        setStatus("Loading calendar events requires Calendar plugin enabled on Chat tab.", true);
        return;
    }

    setLoading(true, "Loading Events");
    try {
        const response = await fetch('/api/calendar/events');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `HTTP error ${response.status}`);
        }
        // Update state with calendar context
        state.setCalendarContext(data.events || "[No event data received]");
        // state.isCalendarContextActive is toggled by the UI element, not here

        setStatus("Calendar events loaded.");
    } catch (error) {
        console.error('Error loading calendar events:', error);
        state.setCalendarContext(null); // Clear context on error
        // Add a system message to chat history via state? Or let UI handle based on status?
        // For now, just update status
        setStatus(`Error loading calendar events: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}


// --- Chat API ---

/** Loads the list of saved chats from the backend and updates the state. */
export async function loadSavedChats() {
    if (!elements.savedChatsList) return; // Cannot update UI placeholder if element missing

    // Set loading only if not already loading (e.g., during init)
    const wasLoading = state.isLoading;
    if (!wasLoading) setLoading(true, "Loading Chats");

    // Clear current list in state immediately to show loading state in UI
    state.setSavedChats([]);

    try {
        const response = await fetch('/api/chats');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const chats = await response.json();
        state.setSavedChats(chats); // Update state

        setStatus("Saved chats loaded.");
    } catch (error) {
        console.error('Error loading saved chats:', error);
        setStatus("Error loading saved chats.", true);
        // state.savedChats is already [] from above
        throw error; // Re-throw for initializeApp to catch
    } finally {
        if (!wasLoading) setLoading(false);
    }
}


/** Starts a new chat session by calling the backend and updates state. */
export async function startNewChat() {
    if (state.isLoading) return;
    setLoading(true, "Creating Chat");
    // Clear current chat state immediately
    state.setCurrentChatId(null);
    state.setCurrentChatName(''); // Assuming setCurrentChatName in state.js
    state.setCurrentChatModel(''); // Assuming setCurrentChatModel in state.js
    state.setChatHistory([]); // Clear history for the new empty chat
    resetChatContext(); // Clear chat-specific context states
    state.setCurrentChatMode('chat'); // Reset mode to default 'chat' for new chat

    try {
        const response = await fetch('/api/chat', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newChat = await response.json();

        // Load the new chat (this updates state.currentChatId, loads history, resets context)
        await loadChat(newChat.id);

        // Reload the chat list state to include the new chat
        await loadSavedChats();

        setStatus(`New chat created (ID: ${newChat.id}).`);
    } catch (error) {
        console.error('Error starting new chat:', error);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        setStatus("Error creating new chat.", true);
        // state is already reset above
    } finally {
        setLoading(false);
    }
}

/** Loads a specific chat's history and details from the backend and updates state. */
export async function loadChat(chatId) {
    setLoading(true, "Loading Chat");
    // Clear chat history in state immediately to show loading state in UI
    state.setChatHistory([]); // Assuming you add setChatHistory to state.js

    try {
        const response = await fetch(`/api/chat/${chatId}`);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status} ${response.statusText} - ${errorText}`);
        }
        const data = await response.json();

        // Update state with chat details and history
        state.setCurrentChatId(data.details.id);
        localStorage.setItem('currentChatId', data.details.id); // Persist ID
        state.setCurrentChatName(data.details.name || ''); // Assuming you add setCurrentChatName to state.js
        state.setCurrentChatModel(data.details.model_name || ''); // Assuming you add setCurrentChatModel to state.js
        state.setChatHistory(data.history || []); // Update state with history
        state.setCurrentChatMode('chat'); // Always default to 'chat' mode when loading a chat

        // Reset chat-specific context states (files, calendar, web search toggle)
        resetChatContext(); // This updates state variables

        // Assuming the backend returns attached files with chat details
        state.setAttachedFiles(data.details.attached_files || []);

        // Plugin enabled states are loaded from localStorage in app.js init

        setStatus(`Chat ${state.currentChatId} loaded.`);

    } catch (error) {
        console.error(`Error loading chat ${chatId}:`, error);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        setStatus(`Error loading chat ${chatId}.`, true);

        // Reset state on error
        state.setCurrentChatId(null);
        localStorage.removeItem('currentChatId');
        state.setCurrentChatName('');
        state.setCurrentChatModel('');
        state.setChatHistory([]);
        resetChatContext(); // Clear files, calendar, etc. state
        state.setCurrentChatMode('chat'); // Reset mode on error

        throw error; // Re-throw for initializeApp or switchTab to handle
    } finally {
        setLoading(false);
    }
}

// Helper to reset context state when switching chats or starting new
function resetChatContext() {
    state.clearSidebarSelectedFiles(); // Clear temporary sidebar selections
    state.clearAttachedFiles(); // Clear permanent file selections
    state.setSessionFile(null); // Clear session file state

    state.setCalendarContext(null);
    state.setCalendarContextActive(false); // Reset toggle state

    state.setWebSearchEnabled(false); // Assuming you add setWebSearchEnabled to state.js
}


/**
 * Sends the user message and context to the backend.
 * @param {string} mode - The mode for the AI interaction ('chat' or 'deep_research').
 */
export async function sendMessage(mode = 'chat') { // Added mode parameter with default
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        setStatus("Cannot send: No active chat, busy, or not on Chat tab.", true);
        return;
    }

    // Read message from DOM
    const message = elements.messageInput?.value.trim() || '';

    // Files to send are the permanently attached files PLUS the session file
    // Note: Files/context are ignored in 'deep_research' mode on the backend, but we still send them.
    const filesToAttach = state.isFilePluginEnabled ? state.attachedFiles : [];
    const sessionFileToSend = state.isFilePluginEnabled ? state.sessionFile : null;
    const calendarContextToSend = (state.isCalendarPluginEnabled && state.isCalendarContextActive && state.calendarContext) ? state.calendarContext : null;
    const webSearchEnabledToSend = state.isWebSearchPluginEnabled && state.isWebSearchEnabled; // Read web search state

    // --- Validation based on mode ---
    if (mode === 'deep_research') {
        if (!message) {
            setStatus("Deep Research mode requires a text query.", true);
            return;
        }
        // In deep research mode, we don't send files, context, or web search flags
        // as the backend ignores them. This simplifies the payload.
        // However, the backend is written to ignore them if mode is 'deep_research',
        // so sending them is harmless, just slightly less efficient.
        // Let's keep sending them for now as the backend handles the ignore logic.
    } else { // 'chat' mode
        if (!message && filesToAttach.length === 0 && !sessionFileToSend && !calendarContextToSend && !webSearchEnabledToSend) {
            setStatus("Cannot send: Empty message and no context/files attached.", true);
            return;
        }
    }
    // --- End Validation ---


   // Clear input in DOM immediately
   if (elements.messageInput) {
       elements.messageInput.value = '';
       // --- NEW: Resize textarea back to default after clearing ---
       ui.autoResizeTextarea(elements.messageInput);
       // ---------------------------------------------------------
   }

   // Add user message to state immediately
   // UI will react to this state change to display the message
    state.addMessageToHistory({ role: 'user', content: message }); // Assuming addMessageToHistory in state.js

    setLoading(true, mode === 'deep_research' ? "Performing Deep Research..." : "Sending"); // Update loading message based on mode

    const payload = {
        chat_id: state.currentChatId,
        message: message,
        // Send attached files (full/summary)
        attached_files: filesToAttach.map(f => ({ id: f.id, type: f.type })), // Send only id and type for attached files
        // Send session file (content included)
        session_files: sessionFileToSend ? [{ filename: sessionFileToSend.filename, content: sessionFileToSend.content, mimetype: sessionFileToSend.mimetype }] : [],
        calendar_context: calendarContextToSend,
        enable_web_search: webSearchEnabledToSend,
        enable_streaming: state.isStreamingEnabled, // Streaming is only relevant for 'chat' mode
        enable_files_plugin: state.isFilePluginEnabled,
        enable_calendar_plugin: state.isCalendarPluginEnabled,
        enable_web_search_plugin: state.isWebSearchPluginEnabled,
        // --- NEW: Include the selected mode ---
        mode: mode,
        // -------------------------------------
    };

    const sentSessionFile = state.sessionFile; // Store to clear later

    try {
        const response = await fetch(`/api/chat/${state.currentChatId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        // --- Handle Response based on Mode and Content-Type ---
        const contentType = response.headers.get('Content-Type');

        if (!response.ok) {
             // Handle HTTP errors (4xx, 5xx)
             const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
             console.error('API error:', response.status, errorData);
             const errorMessage = `[Error: ${errorData.error || response.statusText}]`;
             state.addMessageToHistory({ role: 'assistant', content: errorMessage, isError: true });
             setStatus("Error sending message.", true);
             // No need to throw here, error is added to history and status is set.
        } else if (mode === 'chat' && state.isStreamingEnabled && contentType?.includes('text/plain')) {
            // Handle Streaming Chat Response
            // Add an empty assistant message to state immediately for streaming
            state.addMessageToHistory({ role: 'assistant', content: '' }); // Assuming addMessageToHistory handles streaming

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                // Append chunk to the last message in state
                state.appendContentToLastMessage(chunk); // Assuming appendContentToLastMessage in state.js
            }
            // Markdown rendering will be handled by the UI when state updates are processed
            setStatus("Assistant replied (streaming finished).");

        } else {
            // Handle Non-Streaming Chat Response OR Deep Research Report (both are JSON)
            const data = await response.json();

            if (data.report !== undefined) { // Check for deep research report
                 console.log("Received Deep Research Report:", data.report);
                 // Add the full report as a single assistant message
                 // Optionally add a title or special formatting here before adding to state
                 const reportContent = `# Deep Research Report\n\n${data.report}`; // Example: Add a title
                 state.addMessageToHistory({ role: 'assistant', content: reportContent });
                 setStatus("Deep Research complete.");

            } else if (data.reply !== undefined) { // Check for non-streaming chat reply
                 console.log("Received Non-Streaming Chat Reply:", data.reply);
                 // Add the full assistant message to state
                 state.addMessageToHistory({ role: 'assistant', content: data.reply });
                 setStatus("Assistant replied.");

            } else if (data.error !== undefined) { // Check for backend error message in JSON
                 console.error("Received backend error in JSON response:", data.error);
                 const errorMessage = `[Error: ${data.error}]`;
                 state.addMessageToHistory({ role: 'assistant', content: errorMessage, isError: true });
                 setStatus("Error from AI service.", true);

            } else {
                 // Unexpected JSON response structure
                 console.error("Received unexpected JSON response structure:", data);
                 const errorMessage = "[Error: Unexpected response from server]";
                 state.addMessageToHistory({ role: 'assistant', content: errorMessage, isError: true });
                 setStatus("Error processing response.", true);
            }
        }

        // Reload saved chats list state to update timestamp (applies to both modes)
        // This should happen after the response is fully received/processed.
        await loadSavedChats();

        // Clear temporary sidebar selection state after successful send
        state.clearSidebarSelectedFiles();

        // Do NOT clear attachedFiles state here. They persist per chat.
        // Only clear the session file state.
        if (sentSessionFile && state.sessionFile === sentSessionFile) {
             state.setSessionFile(null);
        }

    } catch (error) {
        // This catch block handles network errors or errors during stream processing/JSON parsing
        console.error('Network or processing error sending message:', error);
        const errorMessage = `[Error: ${error.message}]`;
        // Add error message to state
        state.addMessageToHistory({ role: 'assistant', content: errorMessage, isError: true }); // Assuming addMessageToHistory handles errors
        setStatus("Error sending message.", true);
    } finally {
        setLoading(false);
    }
}


/** Saves the current chat's name by calling the backend and updates state. */
export async function handleSaveChatName() {
    if (state.isLoading || !state.currentChatId || state.currentTab !== 'chat') {
        // Set status message if called when not appropriate
        if (state.currentTab !== 'chat') {
             setStatus("Cannot save chat name: Not on Chat tab.", true);
        } else if (!state.currentChatId) {
             setStatus("Cannot save chat name: No active chat.", true);
        } else if (state.isLoading) {
             setStatus("Cannot save chat name: Application is busy.", true);
        }
        return;
    }

    // Read new name from DOM
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

        // Update the name in the state directly
        state.setCurrentChatName(newName);

        // Reload saved chats list state to update timestamp/name in sidebar
        await loadSavedChats();

    } catch (error) {
        console.error('Error saving chat name:', error);
        setStatus(`Error saving name: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

/** Deletes a chat by calling the backend and updates state. */
export async function handleDeleteChat(chatId) { // Removed listItemElement param
    if (state.isLoading || state.currentTab !== 'chat') return;

    // Find the chat name from state for the confirmation message
    const chatToDelete = state.savedChats.find(chat => chat.id === chatId);
    const chatName = chatToDelete ? (chatToDelete.name || `Chat ${chatId}`) : `Chat ${chatId}`;

    if (!confirm(`Are you sure you want to delete "${chatName}"? This cannot be undone.`)) {
        return;
    }
    setLoading(true, "Deleting Chat");
    try {
        const response = await fetch(`/api/chat/${chatId}`, { method: 'DELETE' });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        setStatus(`Chat ${chatId} deleted.`);

        // Remove from state first
        state.setSavedChats(state.savedChats.filter(chat => chat.id !== chatId));

        // If the deleted chat was the currently active one, load another or start new
        if (chatId == state.currentChatId) {
            state.setCurrentChatId(null); // Clear current chat state
            localStorage.removeItem('currentChatId');
            // loadSavedChats already re-rendered the list state
            const firstChat = state.savedChats.length > 0 ? state.savedChats[0] : null; // Get from updated state
            if (firstChat) {
                await loadChat(firstChat.id);
            } else {
                await startNewChat(); // Create and load a new chat
            }
        }
        // If a different chat was deleted, loadSavedChats (called above) will trigger UI re-render

    } catch (error) {
        console.error(`Error deleting chat ${chatId}:`, error);
        setStatus(`Error deleting chat: ${error.message}`, true);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        // Reload list state on failure to ensure UI consistency
        await loadSavedChats();
    } finally {
        setLoading(false);
    }
}

/** Handles changing the model for the current chat by calling the backend and updates state. */
export async function handleModelChange() {
    if (!state.currentChatId || state.isLoading || state.currentTab !== 'chat') return;

    // Read new model from DOM
    const newModel = elements.modelSelector?.value;
    if (!newModel) return;

    // Store current model from state before attempting update in case of error
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

        // Update state with the new model name
        state.setCurrentChatModel(newModel);

    } catch (error) {
        console.error("Error updating model:", error);
        setStatus(`Error updating model: ${error.message}`, true);
        // Revert state on error
        state.setCurrentChatModel(originalModel);
    } finally {
        setLoading(false);
    }
}


// --- Notes API ---

/** Loads the list of saved notes from the backend and updates the state. */
export async function loadSavedNotes() {
     if (!elements.savedNotesList) return; // Cannot update UI placeholder if element missing

     const wasLoading = state.isLoading;
     if (!wasLoading) setLoading(true, "Loading Notes");

     // Clear current list in state immediately
     state.setSavedNotes([]);

     try {
         const response = await fetch('/api/notes');
         if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
         const notes = await response.json();
         state.setSavedNotes(notes); // Update state

         setStatus("Saved notes loaded.");
     } catch (error) {
         console.error('Error loading saved notes:', error);
         setStatus("Error loading saved notes.", true);
         // state.savedNotes is already [] from above
         throw error; // Re-throw for initializeApp
     } finally {
         if (!wasLoading) setLoading(false);
     }
}


/** Creates a new note entry by calling the backend and updates state. */
export async function startNewNote() {
    console.log(`[DEBUG] startNewNote called.`);
    if (state.isLoading) return;
    setLoading(true, "Creating Note");

    // Clear current note state immediately
    state.setCurrentNoteId(null);
    state.setCurrentNoteName(''); // Assuming setCurrentNoteName in state.js
    state.setNoteContent(''); // Assuming setNoteContent in state.js
    state.setNoteHistory([]); // Clear history for the new empty note

    try {
        const response = await fetch('/api/notes', { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const newNote = await response.json();
        console.log(`[DEBUG] startNewNote: Received new note ID ${newNote.id}. Loading it...`);

        // Load the new note (this updates state.currentNoteId, name, content)
        await loadNote(newNote.id);

        // Reload the notes list state
        await loadSavedNotes();

        setStatus(`New note created (ID: ${newNote.id}).`);
        console.log(`[DEBUG] startNewNote: Successfully created and loaded note ${newNote.id}.`);
    } catch (error) {
        console.error('Error starting new note:', error);
        setStatus("Error creating new note.", true);
        // state is already reset above
    } finally {
        setLoading(false);
    }
}

/** Loads the content of a specific note from the backend and updates state. */
export async function loadNote(noteId) {
    console.log(`[DEBUG] loadNote(${noteId}) called.`);
    if (state.isLoading) return;
    setLoading(true, "Loading Note");

    // Clear current note content state immediately
    state.setNoteContent(''); // Assuming setNoteContent in state.js
    state.setNoteHistory([]); // Clear history while loading new note

    try {
        const response = await fetch(`/api/note/${noteId}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        // Update state with note details and content
        state.setCurrentNoteId(data.id);
        localStorage.setItem('currentNoteId', data.id); // Persist ID
        state.setCurrentNoteName(data.name || '');
        state.setNoteContent(data.content || '');

        // Load history for this note after loading the note itself
        await loadNoteHistory(noteId); // Assuming loadNoteHistory exists and updates state.noteHistory

        setStatus(`Note ${state.currentNoteId} loaded.`);

    } catch (error) {
        console.error(`Error loading note ${noteId}:`, error);
        setStatus(`Error loading note ${noteId}.`, true);

        // Reset state on error
        state.setCurrentNoteId(null);
        localStorage.removeItem('currentNoteId');
        state.setCurrentNoteName('');
        state.setNoteContent(`[Error loading note ${noteId}: ${error.message}]`); // Put error in content state
        state.setNoteHistory([]); // Clear history on error

        throw error; // Re-throw for switchTab to handle
    } finally {
        setLoading(false);
    }
}

/** Saves the current note content and name by calling the backend and updates state. */
export async function saveNote() {
    if (state.isLoading || !state.currentNoteId || state.currentTab !== 'notes') {
        // Set status message if called when not appropriate
        if (state.currentTab !== 'notes') {
             setStatus("Cannot save note: Not on Notes tab.", true);
        } else if (!state.currentNoteId) {
             setStatus("Cannot save note: No active note.", true);
        } else if (state.isLoading) {
             setStatus("Cannot save note: Application is busy.", true);
        }
        return;
    }
    setLoading(true, "Saving Note");

    // Read name and content from state, not DOM
    const noteName = state.currentNoteName || 'New Note';
    const noteContent = state.noteContent || ''; // Assuming noteContent in state.js

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

        // Reload notes list state to update timestamp/name in sidebar
        await loadSavedNotes();

        // Reload history for this note after saving
        await loadNoteHistory(state.currentNoteId); // Assuming loadNoteHistory exists and updates state.noteHistory

    } catch (error) {
        console.error(`Error saving note ${state.currentNoteId}:`, error);
        setStatus(`Error saving note: ${error.message}`, true);
    } finally {
        setLoading(false);
    }
}

/** Deletes a specific note by calling the backend and updates state. */
export async function handleDeleteNote(noteId) { // Removed listItemElement param
    if (state.isLoading || state.currentTab !== 'notes') return;

    // Find the note name from state for the confirmation message
    const noteToDelete = state.savedNotes.find(note => note.id === noteId);
    const noteName = noteToDelete ? (noteToDelete.name || `Note ${noteId}`) : `Note ${noteId}`;

    if (!confirm(`Are you sure you want to delete "${noteName}"? This cannot be undone.`)) {
        return;
    }
    setLoading(true, "Deleting Note");
    try {
        const response = await fetch(`/api/note/${noteId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        setStatus(`Note ${noteId} deleted.`);

        // Remove from state first
        state.setSavedNotes(state.savedNotes.filter(note => note.id !== noteId));

        // If the deleted note was the currently active one, load another or start new
        if (noteId == state.currentNoteId) {
            state.setCurrentNoteId(null); // Clear current note state
            localStorage.removeItem('currentNoteId');
            state.setNoteContent(''); // Clear content for deleted note
            state.setNoteHistory([]); // Clear history for the deleted note
            // loadSavedNotes already re-rendered the list state
            const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null; // Get from updated state
            if (firstNote) {
                await loadNote(firstNote.id);
            } else {
                await startNewNote(); // Create and load a new note
            }
        }
        // If a different note was deleted, loadSavedNotes (called above) will trigger UI re-render

    } catch (error) {
        console.error(`Error deleting note ${noteId}:`, error);
        setStatus(`Error deleting note: ${error.message}`, true);
        // Add system message via state? Or let UI react to status?
        // For now, just update status
        // Reload list state on failure
        await loadSavedNotes();
    } finally {
        setLoading(false);
    }
}

/** Loads the history of a specific note from the backend and updates state. */
export async function loadNoteHistory(noteId) {
    // Note: Loading state is handled by the caller (loadNote or saveNote)
    // setStatus("Loading note history..."); // Status handled by caller

    try {
        const response = await fetch(`/api/notes/${noteId}/history`);
        if (!response.ok) {
             const errorData = await response.json();
             throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        const history = await response.json();

        // --- Frontend Workaround: Update the name of the most recent history entry ---
        // This assumes the backend returns history sorted by saved_at DESC
        // REMOVED: This workaround is no longer needed as the backend is fixed
        // if (history && history.length > 0) {
        //     const currentNote = state.savedNotes.find(note => note.id === noteId);
        //     const currentNoteName = currentNote ? (currentNote.name || `Note ${noteId}`) : (state.currentNoteName || `Note ${noteId}`);
        //     history[0] = { ...history[0], name: currentNoteName };
        //     console.log('[DEBUG] loadNoteHistory: Applied frontend workaround to update name of most recent history entry:', history[0]);
        // }
        // -----------------------------------------------------------------------------

        state.setNoteHistory(history); // Update state (this notifies 'noteHistory')
        // Status handled by caller
    } catch (error) {
        state.setNoteHistory([]); // Clear history on error
        // Status handled by caller
        throw error; // Re-throw for caller to handle if needed
    } finally {
        // Loading state handled by caller
    }
}


// --- Removed Note Diff Summary Generation API function ---
// Summary generation is now handled during note save.

// --- NEW: On-Demand Note Diff Summary Generation API ---
/**
 * Calls the backend to generate and save an AI diff summary for a specific note history entry.
 * This is typically called when clicking a history item with a pending summary.
 * @param {number} noteId - The ID of the parent note.
 * @param {number} historyId - The ID of the specific history entry.
 * @returns {Promise<boolean>} True if summary was generated/saved successfully or already existed, false otherwise.
 */
export async function generateNoteDiffSummaryForHistoryItem(noteId, historyId) {
    if (state.isLoading) {
        setStatus("Cannot generate summary: Application is busy.", true);
        return false; // Indicate failure
    }
    // Use a more specific loading message
    setLoading(true, `Generating summary for version ${historyId}...`);

    try {
        const response = await fetch(`/api/notes/${noteId}/history/${historyId}/generate_summary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // No body needed for this request
        });

        const data = await response.json(); // Always expect JSON back

        if (!response.ok) {
            // Throw error even if backend returns a summary but failed to save
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        // Check if the backend reported a save error despite 2xx status
        if (data.error && data.error.includes("Failed to save")) {
             setStatus(`Summary generated for version ${historyId}, but failed to save.`, true);
             // Reload history anyway to show the generated (but unsaved) summary if backend sent it
             await loadNoteHistory(noteId);
             return false; // Indicate failure due to save error
        } else if (data.message && data.message.includes("already existed")) {
             setStatus(`Summary for version ${historyId} already existed.`);
             // No need to reload history if it already existed
             return true; // Indicate success (already existed)
        } else {
             setStatus(`Summary generated for version ${historyId}.`);
             // Reload history for this note to show the new summary
             await loadNoteHistory(noteId); // This updates state.noteHistory
             return true; // Indicate success
        }

    } catch (error) {
        console.error(`Error generating/saveSummary for history ${historyId}:`, error);
        setStatus(`Error generating summary: ${error.message}`, true);
        // Attempt to reload history even on error to reset UI state if needed
        try {
            await loadNoteHistory(noteId);
        } catch (reloadError) {
            console.error(`Error reloading note history after summary generation failure:`, reloadError);
        }
        return false; // Indicate failure
    } finally {
        setLoading(false);
    }
}
// -----------------------------------------


// --- Transcript Cleanup API ---
/**
 * Sends raw transcript text to the backend for cleanup.
 * @param {string} rawTranscript - The raw transcript text.
 * @returns {Promise<string>} A promise that resolves with the cleaned transcript or rejects on error.
 */
export async function cleanupTranscript(rawTranscript) {
    // console.log("[DEBUG] cleanupTranscript API called with:", rawTranscript); // Log input
    if (state.isLoading) {
        // console.warn("[WARN] cleanupTranscript called while loading.");
        throw new Error("Application is busy."); // Throw error if already loading
    }
    setLoading(true, "Cleaning Transcript");

    try {
        const response = await fetch('/api/voice/cleanup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript: rawTranscript })
        });

        // console.log("[DEBUG] cleanupTranscript API response status:", response.status);
        const responseText = await response.text(); // Get raw text first for logging
        // console.log("[DEBUG] cleanupTranscript API raw response body:", responseText);

        let data;
        try {
            data = JSON.parse(responseText); // Try parsing JSON
        } catch (parseError) {
            console.error("[ERROR] Failed to parse cleanupTranscript API response as JSON:", parseError);
            throw new Error(`Failed to parse API response. Status: ${response.status}`);
        }


        if (!response.ok) {
            console.error("[ERROR] cleanupTranscript API returned error:", data.error || `HTTP ${response.status}`);
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        const cleanedTranscript = data.cleaned_transcript;
        // console.log("[DEBUG] cleanupTranscript API success. Cleaned text:", cleanedTranscript);

        setStatus("Transcript cleaned."); // Set status on success
        return cleanedTranscript; // Return the cleaned text

    } catch (error) {
        // Error is already logged above if it's an API error
        // This catch block handles network errors or JSON parsing errors primarily
        console.error('Error during cleanupTranscript fetch/processing:', error);
        setStatus(`Cleanup failed: ${error.message}`, true); // Set error status
        throw error; // Re-throw the error for the caller to handle
    } finally {
        setLoading(false);
    }
}


// --- Initial Data Loading ---

/** Loads the initial data required for the Chat tab. */
export async function loadInitialChatData() {
    // loadSavedChats is called by initializeApp before switchTab
    // await loadSavedChats(); // Load chat list state first

    let chatToLoadId = state.currentChatId; // Use persisted ID if available
    let chatFoundInList = false;

    // Check if the persisted ID exists in the already loaded list of chats
    if (chatToLoadId !== null && state.savedChats.length > 0) {
        chatFoundInList = state.savedChats.some(chat => chat.id === chatToLoadId);
        if (!chatFoundInList) {
            state.setCurrentChatId(null); // Clear the stale ID state
            localStorage.removeItem('currentChatId');
            chatToLoadId = null; // Ensure fallback logic triggers
        }
    } else if (chatToLoadId !== null && state.savedChats.length === 0) {
         // If there's a persisted ID but no saved chats at all, it's definitely stale
         state.setCurrentChatId(null); // Clear the stale ID state
         localStorage.removeItem('currentChatId');
         chatToLoadId = null; // Ensure fallback logic triggers
    }


    // If no valid persisted chat or loading failed, load most recent or start new
    if (state.currentChatId === null) { // Check state.currentChatId after attempts
        const firstChat = state.savedChats.length > 0 ? state.savedChats[0] : null; // Get from state (already sorted by loadSavedChats)
        if (firstChat) {
            const mostRecentChatId = firstChat.id;
            await loadChat(mostRecentChatId); // Updates state
        } else {
            await startNewChat(); // Updates state
        }
    }
}

/** Loads the initial data required for the Notes tab. */
export async function loadInitialNotesData() {
    // loadSavedNotes is called by initializeApp before switchTab
    // await loadSavedNotes(); // Load notes list state first

    let noteToLoadId = state.currentNoteId; // Use persisted ID
    let noteFoundInList = false;

    // Check if the persisted ID exists in the already loaded list of notes
    if (noteToLoadId !== null && state.savedNotes.length > 0) {
        noteFoundInList = state.savedNotes.some(note => note.id === noteToLoadId);
        if (!noteFoundInList) {
            state.setCurrentNoteId(null); // Clear the stale ID state
            localStorage.removeItem('currentNoteId');
            noteToLoadId = null; // Ensure fallback logic triggers
        }
    } else if (noteToLoadId !== null && state.savedNotes.length === 0) {
         // If there's a persisted ID but no saved notes at all, it's definitely stale
         state.setCurrentNoteId(null); // Clear the stale ID state
         localStorage.removeItem('currentNoteId');
         noteToLoadId = null; // Ensure fallback logic triggers
    }


    // If no valid persisted note or loading failed, load most recent or start new
    if (state.currentNoteId === null) { // Check state.currentNoteId after attempts
        const firstNote = state.savedNotes.length > 0 ? state.savedNotes[0] : null; // Get from state (already sorted by loadSavedNotes)
        if (firstNote) {
            const mostRecentNoteId = firstNote.id;
            await loadNote(mostRecentNoteId); // Updates state
        } else {
            await startNewNote(); // Creates and loads a new note
        }
    }

    // Note mode is handled by UI reacting to state.currentNoteMode
}
