// Handles microphone access, audio recording, and interaction with the transcription API.

import * as state from './state.js';
import * as api from './api.js'; // To manage WebSocket connection and send chunks
import { elements } from './dom.js';

let mediaRecorder = null;
// let audioChunks = []; // No longer needed to store chunks locally for blob creation
let audioStream = null; // Store the stream to stop tracks later

// --- Configuration ---
// Google Speech-to-Text streaming API works well with LINEAR16 or Opus in WebM/Ogg.
// Since we fixed the backend for WEBM_OPUS, let's stick with that.
const MIME_TYPE = 'audio/webm;codecs=opus';
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
    console.log(`[DEBUG] Using MIME type: ${MIME_TYPE}`);
    return true;
}

/**
 * Starts the audio recording process.
 * @param {'chat' | 'notes'} context - Where the transcription should go.
 */
export async function startRecording(context) {
    console.log(`[DEBUG] startRecording called with context: ${context}`);
    if (state.isRecording) {
        console.warn("[WARN] Already recording.");
        return;
    }

    if (!isMimeTypeSupported()) {
        state.setStatusMessage(`Audio format (${MIME_TYPE}) not supported by this browser.`, true);
        return;
    }

    // Clear previous streaming transcript state first
    state.setStreamingTranscript("");
    state.setFinalTranscriptSegment("");

    try {
        // --- Connect WebSocket and wait for backend readiness FIRST ---
        // This ensures the connection exists and the backend stream is initialized.
        state.setStatusMessage("Connecting to transcription service...");
        // connectTranscriptionSocket now handles reusing/creating the connection
        // and returns a promise that resolves when the backend stream is ready.
        await api.connectTranscriptionSocket('en-US', 'WEBM_OPUS'); // Use appropriate lang code and format
        // If we reach here, the connection is established and backend confirmed readiness.
        // Status is now "Recording... Speak now." (set by api.js handler)

        // --- Request microphone access AFTER successful connection ---
        state.setStatusMessage("Requesting microphone access...");
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log("[DEBUG] Microphone access granted.");

        // Log actual track settings
        const audioTracks = audioStream.getAudioTracks();
        if (audioTracks.length > 0) {
            const settings = audioTracks[0].getSettings();
            console.log("[DEBUG] Actual audio track settings:", settings);
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

        mediaRecorder.onstop = () => {
            console.log("[DEBUG] MediaRecorder stopped.");
            // Signal end of audio stream to backend via WebSocket
            api.stopAudioStream();

            // The final transcript is assembled via 'transcript_update' events.
            // We might want to perform final actions here, like focusing the input.

            // --- Read context BEFORE resetting state ---
            const recordingContextOnStop = state.recordingContext;
            // -----------------------------------------

            // Append the final transcript segment (if any) to the input field
            // The streaming transcript state already updates the input field in real-time via ui.js
            // We just need to ensure the final state is reflected.
            const finalTranscript = state.streamingTranscript.trim(); // Get the full assembled transcript
            console.log(`[DEBUG] Final assembled transcript on stop: "${finalTranscript}"`);

            if (recordingContextOnStop === 'chat' && elements.messageInput) { // Use local variable
                // Explicitly set the final transcript in the input field
                elements.messageInput.value = finalTranscript;
                elements.messageInput.focus();
                state.setStatusMessage("Recording stopped. Transcript added to input.");
            } else if (recordingContextOnStop === 'notes' && elements.notesTextarea) { // Use local variable
                // Set the final transcript in the notes textarea
                const currentVal = elements.notesTextarea.value;
                // Replace the streaming placeholder with the final transcript
                // This assumes the streaming updates were also directed to the notes textarea
                elements.notesTextarea.value = finalTranscript; // Replace content
                state.setNoteContent(finalTranscript); // Update state
                elements.notesTextarea.focus();
                state.setStatusMessage("Recording stopped. Transcript added to note.");
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
        console.log(`[DEBUG] MediaRecorder started with timeslice ${TIMESLICE_MS}ms.`);
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
    console.log("[DEBUG] stopRecording called.");
    if (!state.isRecording || !mediaRecorder) {
        console.warn("[WARN] Not recording or mediaRecorder not initialized.");
        return;
    }

    if (mediaRecorder.state === "recording") {
        // Status message will be updated in onstop handler
        state.setStatusMessage("Stopping recording...");
        mediaRecorder.stop(); // This will trigger the 'onstop' event handler
        console.log("[DEBUG] Requesting MediaRecorder stop.");
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
        console.log("[DEBUG] MediaStream audio tracks stopped.");
        audioStream = null; // Clear the stream reference
    }
    // mediaRecorder reference is cleared in onstop or onerror
}
