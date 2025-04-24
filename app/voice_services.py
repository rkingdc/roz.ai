import logging
from google.cloud import speech
from google.api_core.exceptions import (
    GoogleAPICallError,
    NotFound,
    InvalidArgument,
    OutOfRange,
)
import os
from flask import current_app, g  # Import g for potential context caching if needed
import threading
import queue  # For passing audio chunks between threads

# Import the new cleanup function
from app.ai_services import clean_up_transcript
# Import the socketio instance directly from the app package
from app import socketio

logger = logging.getLogger(__name__)

# --- Thread-safe storage for audio queues ---
# Key: session ID (sid), Value: queue.Queue
audio_queues = {}
_queue_lock = threading.Lock()

# Ensure credentials are set (the library often picks up the env var automatically)
# You might need to explicitly point to the credentials file if the env var isn't set
# before the app starts, though relying on the standard env var is preferred.
# Example: client = speech.SpeechClient.from_service_account_json(current_app.config['GOOGLE_APPLICATION_CREDENTIALS'])


def transcribe_audio(
    audio_content: bytes, language_code: str = "en-US", sample_rate_hertz: int = 16000
) -> str | None:
    """
    Transcribes the given audio content using Google Cloud Speech-to-Text.

    Args:
        audio_content: The audio data as bytes.
        language_code: The language of the speech in the audio (e.g., "en-US").
        sample_rate_hertz: The sample rate of the audio recording (e.g., 16000).
                           This MUST match the sample rate of the audio sent from the frontend.

    Returns:
        The transcribed text as a string, or None if transcription fails.
    """

    try:
        # Instantiates a client. Relies on GOOGLE_APPLICATION_CREDENTIALS env var.
        client = speech.SpeechClient()

        # Prepare the audio object
        audio = speech.RecognitionAudio(content=audio_content)

        # Prepare the configuration object
        # The frontend sends audio/webm which typically uses Opus codec.
        # For WEBM_OPUS, the sample rate is usually included in the header,
        # so we don't need to specify sample_rate_hertz explicitly.
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
            # sample_rate_hertz is omitted; API will detect from WebM header
            language_code=language_code,
            # Explicitly set channel count based on error message (WebM header indicates 2)
            audio_channel_count=2,
            # enable_separate_recognition_per_channel=True, # Keep removed for now, add back if needed after fixing channel count
            # model="telephony", # Optional: Specify model for better accuracy in some cases
            # enable_automatic_punctuation=True, # Optional: Add punctuation
        )

        logger.info(
            f"Sending audio to Google Speech-to-Text Long Running API (Language: {language_code}, Encoding: WEBM_OPUS, Channels: 2)"
        )
        # Use long_running_recognize for potentially longer audio files
        operation = client.long_running_recognize(config=config, audio=audio)

        logger.info("Waiting for long-running transcription operation to complete...")
        # Set a timeout (e.g., 300 seconds = 5 minutes) to avoid hanging indefinitely
        response = operation.result(timeout=300)
        logger.info("Long-running transcription operation finished.")

        # Process the response
        if response.results:
            # Get the most likely raw transcript
            raw_transcript = response.results[0].alternatives[0].transcript
            logger.info(f"Raw transcription successful: '{raw_transcript[:50]}...'")

            # Post-process the transcript using the LLM cleaner
            logger.info("Attempting to clean up the transcript...")
            cleaned_transcript = clean_up_transcript(raw_transcript)

            # Check if cleanup returned the original or a cleaned version
            if cleaned_transcript == raw_transcript:
                logger.warning(
                    "Transcript cleanup failed or returned original. Using raw transcript."
                )
            else:
                logger.info(f"Cleaned transcript: '{cleaned_transcript[:50]}...'")

            return cleaned_transcript  # Return the cleaned (or original if cleanup failed) transcript

        else:
            logger.warning("Transcription returned no results.")
            return ""  # Return empty string for no results vs None for error

    except InvalidArgument as e:
        logger.error(
            f"Google Speech API Invalid Argument: {e}. Ensure audio encoding matches the file format.",
            exc_info=True,
        )
        # You might want to inspect e.details() or specific error codes
        return None
    except GoogleAPICallError as e:
        logger.error(f"Google Speech API call failed: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during transcription: {e}", exc_info=True
        )
        return None


# --- NEW: Non-Streaming Transcription Function ---
def transcribe_audio_file(audio_bytes: bytes, language_code: str = "en-US", encoding: str = "WEBM_OPUS") -> str | None:
    """
    Transcribes a complete audio file using Google Cloud Speech-to-Text non-streaming API.

    Args:
        audio_bytes: The raw bytes of the audio file.
        language_code: The language code for transcription.
        encoding: The audio encoding format. Needs to match the frontend recording format.
                  Supported values correspond to RecognitionConfig.AudioEncoding names.

    Returns:
        The full transcript string, or None if transcription fails.
    """
    logger.info(f"Starting non-streaming transcription for audio chunk ({len(audio_bytes)} bytes), encoding: {encoding}")
    try:
        client = speech.SpeechClient() # Assumes GOOGLE_APPLICATION_CREDENTIALS is set

        # Determine the correct RecognitionConfig.AudioEncoding based on the input string
        try:
            google_encoding = getattr(speech.RecognitionConfig.AudioEncoding, encoding.upper())
        except AttributeError:
            logger.error(f"Unsupported audio encoding string for Google API: {encoding}")
            # Fallback or raise error - Returning None is safer than guessing
            return None

        # Prepare configuration
        # Note: sample_rate_hertz might be needed for uncompressed formats like LINEAR16
        # but often not required for compressed formats like WEBM_OPUS/OGG_OPUS.
        # If needed, you might have to get this info from the frontend or assume a standard rate.
        config = speech.RecognitionConfig(
            encoding=google_encoding,
            language_code=language_code,
            # sample_rate_hertz=48000, # Example: Add if needed for your encoding (e.g., LINEAR16)
            # --- FIX: Explicitly set channel count to match WEBM header ---
            audio_channel_count=2,
            # enable_separate_recognition_per_channel=True, # Consider if stereo separation is needed
            # -------------------------------------------------------------
            enable_automatic_punctuation=True,
        )

        audio = speech.RecognitionAudio(content=audio_bytes)

        logger.info("Sending audio data to Google Speech-to-Text non-streaming API (long_running_recognize)...")
        # Use long_running_recognize for audio > 60 seconds
        operation = client.long_running_recognize(config=config, audio=audio)
        logger.info("Waiting for long-running transcription operation to complete...")

        # Wait for the operation to complete. Timeout needs to be long enough for transcription.
        # Example: 300 seconds (5 minutes). Adjust as needed based on expected max audio length.
        # Consider making this timeout configurable.
        try:
            # Use google.api_core.exceptions.TimeoutError if needed, but standard TimeoutError should work
            from concurrent.futures import TimeoutError
            response = operation.result(timeout=300)
            logger.info("Long-running transcription operation finished.")
        except TimeoutError:
            logger.error("Timeout waiting for long-running transcription operation to complete.")
            # Optionally try to cancel the operation: operation.cancel()
            return None
        except Exception as op_error:
            logger.error(f"Error during long-running transcription operation: {op_error}", exc_info=True)
            return None


        if not response.results:
            logger.warning("Long-running transcription response contained no results.")
            return "" # Return empty string if no speech detected

        # Concatenate results if multiple are returned (unlikely for recognize but safe)
        full_transcript = " ".join(
            result.alternatives[0].transcript for result in response.results if result.alternatives
        )
        logger.info(f"Non-streaming transcription successful. Transcript length: {len(full_transcript)}")

        # --- Optional: Apply LLM cleanup ---
        # logger.info("Attempting to clean up the non-streaming transcript...")
        # cleaned_transcript = clean_up_transcript(full_transcript.strip())
        # if cleaned_transcript == full_transcript.strip():
        #     logger.warning("Non-streaming transcript cleanup failed or returned original. Using raw transcript.")
        # else:
        #     logger.info(f"Cleaned non-streaming transcript: '{cleaned_transcript[:50]}...'")
        # return cleaned_transcript
        # --- End Optional Cleanup ---

        # Return raw transcript for now
        return full_transcript.strip()

    except InvalidArgument as e:
        logger.error(
            f"Google Speech API Invalid Argument during non-streaming: {e}. Check encoding/sample rate.",
            exc_info=True,
        )
        return None
    except GoogleAPICallError as e:
        logger.error(f"Google Speech API call failed during non-streaming: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error during non-streaming transcription: {e}", exc_info=True)
        return None


# --- Streaming Transcription ---

# Google API constraints
STREAM_LIMIT_SECONDS = 290  # ~5 minutes, slightly less than Google's limit


def transcribe_stream(language_code: str = "en-US", encoding: str = "WEBM_OPUS"):
    """
    Sets up and manages a streaming transcription request with Google Cloud Speech-to-Text.

    This function is designed to be called when a WebSocket client connects and requests
    to start transcription. It sets up the Google API stream and starts a background
    thread to listen for transcript responses. It provides a mechanism (queue) for the
    WebSocket handler to send audio chunks.

    Args:
        language_code: Language code for transcription.
        encoding: Audio encoding ('WEBM_OPUS', 'LINEAR16', etc.).
        # sample_rate: Sample rate (required for LINEAR16, not for WEBM_OPUS).
        # audio_channel_count: Channel count (required for LINEAR16, not for WEBM_OPUS).

    Returns:
        A tuple: (audio_queue, streaming_config)
        - audio_queue: A queue.Queue object where audio chunks should be put.
                       Putting None into the queue signals the end of the stream.
        - streaming_config: The RecognitionConfig used for the stream.

    Raises:
        Exception: If setup fails.
    """
    from flask import (
        request,
    )  # Import request here to get SID within the context of the socket event

    sid = request.sid  # Get the session ID of the client initiating the stream

    logger.info(
        f"Setting up transcription stream for SID: {sid}, Lang: {language_code}, Enc: {encoding}"
    )

    try:
        # Get Google client (consider caching if performance is critical)
        # Using 'g' might be tricky with background threads, create client directly for now
        client = speech.SpeechClient()

        # Configure recognition settings
        recognition_config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding[encoding],
            language_code=language_code,
            # Explicitly set sample rate for WEBM_OPUS streaming, as auto-detection seems unreliable here.
            # Browsers typically record WebM Opus at 48000 Hz.
            sample_rate_hertz=48000,
            # audio_channel_count is still omitted for WEBM_OPUS, API should detect this.
            enable_automatic_punctuation=True,  # Enable punctuation
            # Use enhanced model if available and configured
            # use_enhanced=True,
            # model='telephony', # Or other specialized models
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=recognition_config,
            interim_results=True,  # Get interim results for real-time feedback
        )

        # Create a thread-safe queue for this client's audio chunks
        audio_queue = queue.Queue()
        with _queue_lock:
            audio_queues[sid] = audio_queue
        logger.info(f"Audio queue created for SID: {sid}")

        # Start the background thread that will handle Google API interaction
        listener_thread = threading.Thread(
            target=_google_listen_print_loop,
            args=(client, streaming_config, audio_queue, sid),
            daemon=True,  # Daemonize thread so it exits when main process exits
        )
        listener_thread.start()
        logger.info(f"Transcription listener thread started for SID: {sid}")

        # Return the queue and config (caller uses the queue to send audio)
        return audio_queue, streaming_config

    except Exception as e:
        logger.error(
            f"Failed to setup transcription stream for SID {sid}: {e}", exc_info=True
        )
        # Clean up queue if partially created
        with _queue_lock:
            if sid in audio_queues:
                del audio_queues[sid]
        raise  # Re-raise exception to be caught by the socket handler


def _google_request_generator(
    audio_queue: queue.Queue, streaming_config: speech.StreamingRecognitionConfig
):
    """
    A generator that yields audio chunks from the queue to the Google API.
    The first request sends the configuration.
    Putting None in the queue signals the end.
    """
    # The configuration is sent via the 'config' parameter in the streaming_recognize call.
    # This generator should ONLY yield audio content.
    # logger.debug("Starting Google request generator.") # Removed redundant log

    while True:
        chunk = audio_queue.get()
        if chunk is None:
            logger.info(
                "Received None (end signal) in audio queue. Stopping request generator."
            )
            break  # End of stream signaled

        # logger.debug(f"Sending audio chunk size {len(chunk)} to Google API.") # Very verbose
        yield speech.StreamingRecognizeRequest(audio_content=chunk)

        # Signal task completion (important for queue management)
        audio_queue.task_done()

    logger.debug("Google request generator finished.")


def _google_listen_print_loop(
    client: speech.SpeechClient,
    streaming_config: speech.StreamingRecognitionConfig,
    audio_queue: queue.Queue,
    sid: str,
):
    """
    Listens to the Google API response stream in a background thread,
    processes results, and emits them via SocketIO.
    """
    logger.info(f"Google listener loop started for SID: {sid}")
    responses = None
    try:
        # Create the request generator using the queue
        requests = _google_request_generator(audio_queue, streaming_config)

        # Call the Google API's streaming_recognize method
        # Pass the streaming_config object directly as the 'config' argument.
        # The 'requests' generator will yield only the audio chunks.
        responses = client.streaming_recognize(
            config=streaming_config, # Pass the config object here
            requests=requests,
            timeout=STREAM_LIMIT_SECONDS + 10
        )  # Add buffer to timeout

        # Process responses from Google
        for response in responses:
            if not response.results:
                # logger.debug("Received empty response from Google.")
                continue

            # The results list is consecutive. For streaming, we only care about
            # the first result being considered, since alternatives are less likely
            # to change rapidly.
            result = response.results[0]
            if not result.alternatives:
                # logger.debug("Received response with no alternatives.")
                continue

            transcript = result.alternatives[0].transcript

            # Display interim results, but don't store them permanently yet
            if not result.is_final:
                logger.debug(f"SID {sid} - Emitting Interim transcript: {transcript}") # Add specific log
                # Use socketio.emit directly
                socketio.emit('transcript_update', {'transcript': transcript, 'is_final': False}, room=sid)
            else:
                logger.info(f"SID {sid} - Emitting Final transcript: {transcript}") # Add specific log
                # Use socketio.emit directly
                socketio.emit('transcript_update', {'transcript': transcript, 'is_final': True}, room=sid)
                # Here you could potentially trigger the LLM cleanup if desired,
                # but it would happen *after* this final segment is received.
                # For now, we just send the final raw segment.

                # If the stream limit was reached by Google, the is_final flag might be true
                # Check for specific error types if needed (though OutOfRange is caught below)

    except OutOfRange as e:
        # Stream limit reached
        logger.warning(f"Google API stream limit likely reached for SID {sid}: {e}")
        # Use socketio.emit directly
        socketio.emit('transcription_error', {'error': "Transcription stream duration limit reached."}, room=sid)
    except GoogleAPICallError as e:
        logger.error(
            f"Google API call error during streaming for SID {sid}: {e}", exc_info=True
        )
        # Use socketio.emit directly
        socketio.emit('transcription_error', {'error': f"Google API Error: {e}"}, room=sid)
    except Exception as e:
        logger.error(
            f"Unexpected error in Google listener loop for SID {sid}: {e}",
            exc_info=True,
        )
        # Use socketio.emit directly
        socketio.emit('transcription_error', {'error': f"Unexpected Transcription Error: {e}"}, room=sid)
    finally:
        # Clean up the audio queue associated with this SID
        with _queue_lock:
            if sid in audio_queues:
                # Ensure the queue is empty and generator is signaled if needed
                try:
                    while not audio_queue.empty():
                        audio_queue.get_nowait()
                        audio_queue.task_done()
                    # Signal generator to stop if it hasn't already
                    audio_queue.put(None)
                except queue.Empty:
                    pass  # Queue already empty
                except Exception as q_err:
                    logger.error(f"Error cleaning up queue for SID {sid}: {q_err}")
                # Remove the queue
                del audio_queues[sid]
                logger.info(f"Cleaned up audio queue for SID: {sid}")

        # Emit a final completion signal AFTER cleanup attempt
        try:
            # Use socketio.emit directly
            socketio.emit('transcription_complete', {'message': 'Transcription processing finished.'}, room=sid)
            logger.info(f"Emitted transcription_complete for SID: {sid}")
        except Exception as emit_err:
            logger.error(f"Error emitting transcription_complete for SID {sid}: {emit_err}")

        logger.info(f"Google listener loop finished for SID: {sid}")


def send_audio_chunk_to_queue(sid: str, chunk: bytes):
    """Puts an audio chunk onto the appropriate client's queue."""
    with _queue_lock:
        if sid in audio_queues:
            # logger.debug(f"Putting audio chunk size {len(chunk)} into queue for SID {sid}") # Verbose
            audio_queues[sid].put(chunk)
            return True
        else:
            logger.warning(
                f"Attempted to send chunk to non-existent queue for SID: {sid}"
            )
            return False


def signal_end_of_stream(sid: str):
    """Signals the end of audio by putting None into the queue."""
    with _queue_lock:
        if sid in audio_queues:
            logger.info(f"Signaling end of audio stream for SID: {sid}")
            audio_queues[sid].put(None)
            return True
        else:
            logger.warning(
                f"Attempted to signal end for non-existent queue for SID: {sid}"
            )
            return False
