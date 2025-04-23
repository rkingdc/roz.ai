// Handles microphone access, audio recording, and interaction with the transcription API.

import * as state from './state.js';
import * as api from './api.js'; // To call the transcription API
import { elements } from './dom.js';

let mediaRecorder = null;
let audioChunks = [];
let audioStream = null; // Store the stream to stop tracks later

// --- Configuration ---
// Match the sample rate expected by the backend (app/voice_services.py)
const TARGET_SAMPLE_RATE = 16000;
// Define the desired MIME type. 'audio/wav' is widely supported and expected by the backend (LINEAR16).
// Browsers might record in webm/opus by default, requiring backend adjustment or frontend conversion.
// Let's try 'audio/wav' first. If it fails, we might need 'audio/webm;codecs=opus' and backend changes.
const PREFERRED_MIME_TYPE = 'audio/wav';
const FALLBACK_MIME_TYPE = 'audio/webm;codecs=opus'; // If WAV fails

/**
 * Checks if the preferred MIME type is supported for recording.
 * @returns {string} The supported MIME type (preferred or fallback).
 */
function getSupportedMimeType() {
    if (MediaRecorder.isTypeSupported(PREFERRED_MIME_TYPE)) {
        console.log(`[DEBUG] Using preferred MIME type: ${PREFERRED_MIME_TYPE}`);
        return PREFERRED_MIME_TYPE;
    } else if (MediaRecorder.isTypeSupported(FALLBACK_MIME_TYPE)) {
        console.warn(`[WARN] Preferred MIME type ${PREFERRED_MIME_TYPE} not supported. Using fallback: ${FALLBACK_MIME_TYPE}. Backend might need adjustment.`);
        // TODO: If using fallback, update backend encoding in voice_services.py
        return FALLBACK_MIME_TYPE;
    } else {
        console.error("[ERROR] Neither WAV nor WebM/Opus recording is supported by this browser.");
        return null; // Indicate no supported type found
    }
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

    const supportedMimeType = getSupportedMimeType();
    if (!supportedMimeType) {
        state.setStatusMessage("Audio recording format not supported by this browser.", true);
        return;
    }

    try {
        // Request microphone access
        state.setStatusMessage("Requesting microphone access...");
        audioStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                // Attempt to request the target sample rate if the browser supports constraints
                sampleRate: TARGET_SAMPLE_RATE,
                // Other constraints might be useful, e.g., channelCount: 1
            }
        });
        console.log("[DEBUG] Microphone access granted.");

        // Check the actual sample rate of the track
        const audioTracks = audioStream.getAudioTracks();
        if (audioTracks.length > 0) {
            const settings = audioTracks[0].getSettings();
            console.log("[DEBUG] Audio track settings:", settings);
            if (settings.sampleRate && settings.sampleRate !== TARGET_SAMPLE_RATE) {
                console.warn(`[WARN] Actual sample rate ${settings.sampleRate} differs from target ${TARGET_SAMPLE_RATE}. Transcription quality may be affected.`);
                // Backend might handle resampling, but it's good to be aware.
            }
        }

        // --- Initialize MediaRecorder ---
        // Use the determined supported MIME type
        mediaRecorder = new MediaRecorder(audioStream, { mimeType: supportedMimeType });
        audioChunks = []; // Reset chunks

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
                console.log(`[DEBUG] Audio chunk received, size: ${event.data.size}`);
            }
        };

        mediaRecorder.onstop = async () => {
            console.log("[DEBUG] MediaRecorder stopped.");
            state.setStatusMessage("Processing transcription..."); // Update status before API call

            // Combine chunks into a single Blob
            const audioBlob = new Blob(audioChunks, { type: supportedMimeType });
            console.log(`[DEBUG] Audio Blob created, size: ${audioBlob.size}, type: ${audioBlob.type}`);

            // --- Send to Backend ---
            try {
                // Call the API function (to be created in api.js)
                const transcript = await api.transcribeAudioApi(audioBlob); // Pass the blob

                if (transcript !== null && transcript !== undefined) { // Check for null or undefined explicitly
                    console.log(`[DEBUG] Transcription received: "${transcript.substring(0, 50)}..."`);
                    // Insert transcript into the correct input based on context
                    if (state.recordingContext === 'chat' && elements.messageInput) {
                        // Append to existing content, adding a space if needed
                        const currentVal = elements.messageInput.value;
                        elements.messageInput.value = currentVal + (currentVal.length > 0 ? ' ' : '') + transcript;
                        elements.messageInput.focus(); // Keep focus on input
                        state.setStatusMessage("Transcription added to chat input.");
                    } else if (state.recordingContext === 'notes' && elements.notesTextarea) {
                        // Append to existing content, adding a space if needed
                        const currentVal = elements.notesTextarea.value;
                        elements.notesTextarea.value = currentVal + (currentVal.length > 0 ? ' ' : '') + transcript;
                        // Also update the state for notes
                        state.setNoteContent(elements.notesTextarea.value);
                        elements.notesTextarea.focus(); // Keep focus on textarea
                        state.setStatusMessage("Transcription added to note.");
                    } else {
                        console.warn(`[WARN] Recording context "${state.recordingContext}" not handled or element missing.`);
                        state.setStatusMessage("Transcription received but could not be placed.", true);
                    }
                } else if (transcript === "") { // Handle empty string response (no speech detected)
                     console.log("[DEBUG] Transcription returned empty string (no speech detected?).");
                     state.setStatusMessage("No speech detected in the recording.", true);
                }
                else {
                    // Transcription failed (api.transcribeAudioApi should have set status)
                    console.error("[ERROR] Transcription failed (transcript is null/undefined).");
                    // Status message should be set by the API function on error
                }
            } catch (error) {
                // Error during API call handled by api.transcribeAudioApi
                console.error("[ERROR] Error during transcription API call:", error);
                // Status message should be set by the API function
            } finally {
                // Clean up stream tracks regardless of API success/failure
                stopAudioStream();
                // Reset recording state AFTER API call finishes
                state.setIsRecording(false); // This will trigger UI update for button
            }
        };

        mediaRecorder.onerror = (event) => {
            console.error("[ERROR] MediaRecorder error:", event.error);
            state.setStatusMessage(`Recording error: ${event.error.message}`, true);
            stopAudioStream(); // Clean up stream
            state.setIsRecording(false); // Reset state
        };

        // Start recording
        mediaRecorder.start();
        console.log("[DEBUG] MediaRecorder started.");
        state.setIsRecording(true, context); // Update state (notifies isRecording)
        state.setStatusMessage("Recording... Click stop to finish.");

    } catch (error) {
        console.error("[ERROR] Error accessing microphone or starting recorder:", error);
        if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
            state.setStatusMessage("Microphone access denied. Please allow access in browser settings.", true);
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
             state.setStatusMessage("No microphone found. Please ensure one is connected and enabled.", true);
        } else {
            state.setStatusMessage(`Error starting recording: ${error.message}`, true);
        }
        stopAudioStream(); // Clean up if stream was partially acquired
        state.setIsRecording(false); // Ensure state is reset
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
        mediaRecorder.stop(); // This will trigger the 'onstop' event handler
        console.log("[DEBUG] Requesting MediaRecorder stop.");
        // Status message will be updated in onstop handler
        // State isRecording will be set to false in onstop handler AFTER processing
    } else {
        console.warn(`[WARN] MediaRecorder state is not 'recording': ${mediaRecorder.state}`);
        // If somehow stopped but state wasn't updated, force cleanup
        stopAudioStream();
        state.setIsRecording(false);
    }
}

/**
 * Stops the audio stream tracks to release the microphone.
 */
function stopAudioStream() {
    if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
        console.log("[DEBUG] Audio stream tracks stopped.");
        audioStream = null; // Clear the stream reference
    }
    mediaRecorder = null; // Clear recorder reference
}
