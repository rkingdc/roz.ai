// Handles microphone access, audio recording, and interaction with the transcription API.

import * as state from './state.js';
import * as api from './api.js'; // To manage WebSocket connection and send chunks
import { elements } from './dom.js';
// --- NEW: Import Toast ---
import { showToast, removeToast, updateToast } from './toastNotifications.js'; // Adjust path if needed
// -----------------------

let mediaRecorder = null;
// let audioChunks = []; // No longer needed to store chunks locally for blob creation
let audioStream = null; // Store the stream to stop tracks later
export let originalNoteTextBeforeRecording = null; // Store original notes text - EXPORTED

// --- NEW: Array for long recording chunks ---
let audioChunks = [];
// ------------------------------------------

// --- Configuration ---
// Google Speech-to-Text streaming API works well with LINEAR16 or Opus in WebM/Ogg.
// Since we fixed the backend for WEBM_OPUS, let's stick with that.
// Export MIME_TYPE so api.js can use it when sending the blob
export const MIME_TYPE = 'audio/webm;codecs=opus'; // Or 'audio/ogg;codecs=opus' etc.
const TIMESLICE_MS = 500; // Send audio chunks every 500ms

/**
 * Checks if the required MIME type is supported.
 * @returns {boolean} True if supported, false otherwise.
 */
function isMimeTypeSupported() {
    if (!MediaRecorder.isTypeSupported(MIME_TYPE)) {
        console.error(`[ERROR] Required MIME type ${MIME_TYPE} not supported by this browser.`);
        return false;
    }
    return true;
}

/**
 * Starts the audio recording process.
 * @param {'chat' | 'notes'} context - Where the transcription should go.
 */
export async function startRecording(context) {
    // console.log(`[DEBUG] startRecording called with context: ${context}`); // Log context
    if (state.isRecording) {
        console.warn("[WARN] Already recording.");
        return;
    }

    if (!isMimeTypeSupported()) {
        state.setStatusMessage(`Audio format (${MIME_TYPE}) not supported by this browser.`, true);
        return;
    }

    // --- Check element reference and ensure cleanup button is disabled ---
    const cleanupBtnRefAtStart = elements.cleanupTranscriptButton;
    if (cleanupBtnRefAtStart) {
        cleanupBtnRefAtStart.disabled = true; // Ensure disabled at start
        cleanupBtnRefAtStart.removeAttribute('data-raw-transcript'); // Clear old transcript data
    }
    // ---------------------------------------------

    // Clear previous streaming transcript state first
    state.setStreamingTranscript("");
    state.setFinalTranscriptSegment("");

    // Store original text if recording into notes
    if (context === 'notes' && elements.notesTextarea) {
        originalNoteTextBeforeRecording = elements.notesTextarea.value;
    } else {
        originalNoteTextBeforeRecording = null; // Clear if not recording notes
    }

    try {
        // --- Connect WebSocket and wait for backend readiness FIRST ---
        // This ensures the connection exists and the backend stream is initialized.
        state.setStatusMessage("Connecting to transcription service...");
        // connectTranscriptionSocket now handles reusing/creating the connection
        // and returns a promise that resolves when the backend stream is ready.
        // console.log(`[DEBUG] Connecting transcription socket for context: ${context}`);
        await api.connectTranscriptionSocket('en-US', 'WEBM_OPUS'); // Use appropriate lang code and format
        // console.log(`[DEBUG] Transcription socket connected/ready for context: ${context}`);
        // If we reach here, the connection is established and backend confirmed readiness.
        // Status is now "Recording... Speak now." (set by api.js handler)

        // --- Request microphone access AFTER successful connection ---
        state.setStatusMessage("Requesting microphone access...");
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Log actual track settings
        const audioTracks = audioStream.getAudioTracks();
        if (audioTracks.length > 0) {
            const settings = audioTracks[0].getSettings();
            // Backend handles Opus correctly regardless of sample rate specified here
        }

        // --- Initialize MediaRecorder ---
        // Check if recording was stopped while waiting for mic access (unlikely but possible)
        // Note: isRecording state is NOT set yet. We check if mediaRecorder exists.
        if (mediaRecorder) {
             console.warn("[WARN] MediaRecorder already exists? Aborting startRecording.");
             return;
        }

        mediaRecorder = new MediaRecorder(audioStream, { mimeType: MIME_TYPE });

        mediaRecorder.ondataavailable = (event) => {
            // Send chunk only if recorder is running and socket is connected
            if (event.data.size > 0 && state.isSocketConnected && mediaRecorder?.state === 'recording') {
                // console.log(`[DEBUG] Sending audio chunk, size: ${event.data.size}`); // Verbose
                // Send chunk immediately via WebSocket
                api.sendAudioChunk(event.data);
            } else if (!state.isSocketConnected) {
                 console.warn("[WARN] Received audio data but WebSocket is not connected. Stopping recording.");
                 stopRecording(); // Stop recording if socket disconnects unexpectedly
                 state.setStatusMessage("Transcription service disconnected during recording.", true);
            }
        };

        // Make the onstop handler async to await the backend confirmation
        mediaRecorder.onstop = async () => {

            try {
                // Signal end of audio stream and wait for backend confirmation
                await api.stopAudioStream(); // This now returns a promise

            } catch (error) {
                 // Set error status even if waiting failed, but still try to process transcript
                 state.setStatusMessage(`Error finalizing transcription: ${error.message}`, true);
            }

            // --- Now process the final transcript AFTER waiting ---

            // --- Read context BEFORE resetting state ---
            const recordingContextOnStop = state.recordingContext;
            // console.log(`[DEBUG] mediaRecorder.onstop: Context is "${recordingContextOnStop}"`); // Log context in onstop
            // -----------------------------------------

            // Append the final transcript segment (if any) to the input field
            // The streaming transcript state already updates the input field in real-time via ui.js
            // We just need to ensure the final state is reflected.
            const finalTranscript = state.streamingTranscript.trim(); // Get the full assembled transcript

            if (recordingContextOnStop === 'chat' && elements.messageInput) { // Use local variable
                // Explicitly set the final transcript in the input field
                elements.messageInput.value = finalTranscript;
                elements.messageInput.focus();
                state.setStatusMessage("Recording stopped. Transcript added to input.");
            } else if (recordingContextOnStop === 'notes' && elements.notesTextarea) { // Use local variable
                // Combine original text with the final transcript
                const combinedText = originalNoteTextBeforeRecording + (originalNoteTextBeforeRecording ? "\n\n" : "") + finalTranscript;
                elements.notesTextarea.value = combinedText; // Set combined text in textarea
                state.setNoteContent(combinedText); // Update state with combined text
                elements.notesTextarea.focus();
                state.setStatusMessage("Recording stopped. Transcript added to note.");
                originalNoteTextBeforeRecording = null; // Clear the stored original text
            } else {
                 console.warn(`[WARN] Recording context "${recordingContextOnStop}" not handled on stop.`); // Use local variable
                 state.setStatusMessage("Recording stopped.", true);
            }


            // Clean up audio stream tracks
            stopMediaStreamTracks();
            // Disconnect WebSocket - Let api.js handle this if necessary, or keep connection open?
            // For now, let's keep the connection open unless an error occurs.
            // api.disconnectTranscriptionSocket();

            // Reset recording state *after* processing transcript and context
            state.setIsRecording(false); // This will trigger UI update for button

            // Reset mediaRecorder reference
            mediaRecorder = null;

            // --- Enable Chat Cleanup Button (REMOVED) ---
            // Chat cleanup button is now handled by text selection in the input field, not recording completion.
            // The button's state will be managed by ui.updateChatCleanupButtonState based on selection.
            // Ensure it's disabled here if it was previously enabled by recording.
            if (elements.cleanupTranscriptButton) {
                 elements.cleanupTranscriptButton.disabled = true;
                 elements.cleanupTranscriptButton.removeAttribute('data-raw-transcript');
            }
            // -------------------------------------------------
        };

        mediaRecorder.onerror = (event) => {
            console.error("[ERROR] MediaRecorder error:", event.error);
            state.setStatusMessage(`Recording error: ${event.error.message}`, true);
            stopMediaStreamTracks(); // Clean up stream tracks
            api.disconnectTranscriptionSocket(); // Disconnect socket on media recorder error
            state.setIsRecording(false); // Reset state
            mediaRecorder = null; // Clear reference
        };

        // --- Start recording ---
        // Set recording state *just before* starting
        state.setIsRecording(true, context); // Update state (notifies isRecording)
        mediaRecorder.start(TIMESLICE_MS);
        // Status message is already "Recording... Speak now." from api.js

    } catch (error) {
        // Handle errors from connectTranscriptionSocket promise or getUserMedia
        console.error("[ERROR] Error during recording setup:", error);
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            state.setStatusMessage("Microphone access denied. Please allow access in browser settings.", true);
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
             state.setStatusMessage("No microphone found. Please ensure one is connected and enabled.", true);
        } else {
            state.setStatusMessage(`Error starting recording: ${error.message}`, true);
        }
        stopMediaStreamTracks(); // Clean up if stream was partially acquired
        api.disconnectTranscriptionSocket(); // Disconnect socket if start failed
        state.setIsRecording(false); // Ensure state is reset
        mediaRecorder = null; // Ensure recorder reference is cleared
    }
}

/**
 * Stops the current audio recording.
 */
export function stopRecording() {
    if (!state.isRecording || !mediaRecorder) {
        console.warn("[WARN] Not recording or mediaRecorder not initialized.");
        return;
    }

    if (mediaRecorder.state === "recording") {
        // Status message will be updated in onstop handler
        state.setStatusMessage("Stopping recording...");
        mediaRecorder.stop(); // This will trigger the 'onstop' event handler
        // State isRecording will be set to false in onstop handler AFTER processing
        // We no longer disconnect the socket in the onstop handler by default.
    } else {
        console.warn(`[WARN] MediaRecorder state is not 'recording': ${mediaRecorder.state}`);
        // If somehow stopped but state wasn't updated, force cleanup
        stopMediaStreamTracks();
        // Don't disconnect socket here either, keep it open if possible
        // api.disconnectTranscriptionSocket();
        state.setIsRecording(false);
        mediaRecorder = null; // Ensure reference is cleared
    }
}

/**
 * Stops the audio stream tracks (part of MediaStream) to release the microphone.
 */
function stopMediaStreamTracks() {
    if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
        audioStream = null; // Clear the stream reference
    }
    // mediaRecorder reference is cleared in onstop or onerror
}


// --- NEW: Long Recording Functions ---

/** Starts the non-streaming long recording process. */
export async function startLongRecording() {
    console.log("[DEBUG] Entering startLongRecording function.");
    if (state.isLongRecordingActive) {
        console.warn("[WARN] Long recording is already active. Exiting.");
        return;
    }
    // Prevent starting if streaming recording is active
    if (state.isRecording) {
        console.warn("[WARN] Cannot start long recording while streaming mic is active.");
        showToast("Stop streaming recording first.", { type: 'warning' });
        return;
    }

    console.log("[DEBUG] startLongRecording: Checking MIME type support...");
    if (!isMimeTypeSupported()) {
        console.error("[DEBUG] startLongRecording: MIME type not supported. Exiting.");
        showToast(`Audio format (${MIME_TYPE}) not supported by this browser.`, { type: 'error' });
        return;
    }

    console.log("[INFO] Attempting to start long recording...");
    state.setStatusMessage("Initializing microphone for long recording...");

    try {
        console.log("[DEBUG] startLongRecording: Requesting microphone access...");
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log("[INFO] Microphone access granted for long recording.");

        audioChunks = []; // Reset chunks array for new recording
        console.log("[DEBUG] startLongRecording: Initializing MediaRecorder...");
        mediaRecorder = new MediaRecorder(audioStream, { mimeType: MIME_TYPE });

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
                // console.log(`[DEBUG] Collected audio chunk for long recording: ${event.data.size} bytes`);
            }
        };

        mediaRecorder.onstop = async () => {
            // --- This onstop is ONLY for LONG RECORDING ---
            console.log("[INFO] Long recording stopped by user or error. Processing collected audio.");

            // --- Combine chunks and send ---
            if (audioChunks.length > 0) {
                const audioBlob = new Blob(audioChunks, { type: MIME_TYPE });
                console.log(`[INFO] Combined audio blob size: ${audioBlob.size} bytes`);
                const chunksToClear = audioChunks; // Reference before async call
                audioChunks = []; // Clear chunks array immediately

                // Call the API function to upload and transcribe
                state.setStatusMessage("Transcribing recorded audio..."); // Update status before API call
                await api.transcribeLongAudio(audioBlob, 'en-US'); // API call handles its own toasts
                state.setStatusMessage("Idle"); // Reset general status after API call finishes

            } else {
                console.warn("[WARN] No audio data collected during long recording.");
                showToast("No audio data was recorded.", { type: 'warning' }); // Toast for no data
                state.setStatusMessage("Idle");
            }
            // Clear recorder reference after processing
            mediaRecorder = null;
        };

        mediaRecorder.onerror = (event) => {
            // --- This onerror is ONLY for LONG RECORDING ---
            console.error("[ERROR] MediaRecorder error during long recording:", event.error);
            showToast(`Long Recording Error: ${event.error.message}`, { type: 'error' }); // Toast for error
            // Clean up state and resources on error
            if (state.isLongRecordingActive) {
                 stopLongRecording(true); // Call stop with error flag
            }
             state.setStatusMessage(`Error: ${event.error.message}`, true);
        };

        // Start recording
        mediaRecorder.start(TIMESLICE_MS); // Collect chunks periodically
        state.setIsLongRecordingActive(true); // Update long recording state
        console.log("[INFO] Long recording started successfully.");
        state.setStatusMessage("Long recording in progress..."); // More specific status

        // Show persistent toast with a stop button
        console.log("[DEBUG] startLongRecording: Attempting to show persistent recording toast...");
        const toastId = showToast( // *** Show the persistent recording toast ***
            `<div>
                <span>Long recording active...</span>
                <button class="toast-stop-long-rec-button ml-2 px-2 py-1 bg-red-500 text-white rounded text-xs hover:bg-red-600 focus:outline-none focus:ring-1 focus:ring-red-300">Stop</button>
            </div>`,
            { autoClose: false, type: 'info' } // Keep it open
        );
        console.log(`[DEBUG] startLongRecording: Toast ID received: ${toastId}`);
        state.setLongRecordingToastId(toastId); // Store toast ID in state

    } catch (err) {
        console.error("[ERROR] Failed to start long recording:", err);
        let errorMsg = `Error starting long recording: ${err.message}`;
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
            errorMsg = "Microphone access denied. Please allow access in browser settings.";
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
             errorMsg = "No microphone found. Please ensure one is connected and enabled.";
        }
        showToast(errorMsg, { type: 'error' }); // Toast for startup error
        // Ensure cleanup if getUserMedia failed
        stopMediaStreamTracks();
        mediaRecorder = null;
        state.setIsLongRecordingActive(false);
        state.setStatusMessage("Idle");
    }
}

/** Stops the current non-streaming long recording. */
export function stopLongRecording(isErrorCleanup = false) {
    console.log("[DEBUG] Entering stopLongRecording function."); // ADD LOGGING
    if (!state.isLongRecordingActive || !mediaRecorder) {
        console.warn("[WARN] Not in long recording state or mediaRecorder not initialized.");
        if (state.isLongRecordingActive) state.setIsLongRecordingActive(false);
        return;
    }

    console.log(`[INFO] Attempting to stop long recording... (Error cleanup: ${isErrorCleanup})`);
    if (!isErrorCleanup) {
        state.setStatusMessage("Stopping long recording...");
    }

    // Remove the persistent toast immediately
    if (state.longRecordingToastId) {
        console.log(`[DEBUG] stopLongRecording: Removing persistent toast ID: ${state.longRecordingToastId}`);
        removeToast(state.longRecordingToastId);
        state.setLongRecordingToastId(null);
    } else {
        console.warn("[DEBUG] stopLongRecording: No longRecordingToastId found in state to remove."); // ADD LOGGING
    }

    // Stop the microphone tracks *before* stopping the recorder for long recording
    console.log("[DEBUG] stopLongRecording: Calling stopMediaStreamTracks()."); // ADD LOGGING
    stopMediaStreamTracks();

    // Update state *before* stopping recorder (UI reflects stopping state)
    console.log("[DEBUG] stopLongRecording: Setting isLongRecordingActive state to false."); // ADD LOGGING
    state.setIsLongRecordingActive(false);

    console.log(`[DEBUG] stopLongRecording: Checking mediaRecorder state: ${mediaRecorder?.state}`); // ADD LOGGING
    if (mediaRecorder.state === "recording" || mediaRecorder.state === "paused") {
        console.log("[DEBUG] stopLongRecording: Calling mediaRecorder.stop()."); // ADD LOGGING
        mediaRecorder.stop(); // This will trigger the 'onstop' event handler where processing happens
    } else {
        console.warn(`[WARN] MediaRecorder state is already '${mediaRecorder.state}', cannot stop. Forcing cleanup.`);
         mediaRecorder = null;
         audioChunks = []; // Clear any stale chunks
         if (!isErrorCleanup) state.setStatusMessage("Idle");
    }
}
// -----------------------------------------
