import logging
from google.cloud import speech
from google.api_core.exceptions import GoogleAPICallError, NotFound, InvalidArgument, OutOfRange
import os
from flask import current_app, g # Import g for potential context caching if needed
import threading
import queue # For passing audio chunks between threads

# Import the new cleanup function
from app.ai_services import clean_up_transcript
# Import socket emission functions (assuming sockets.py is created)
try:
    from app.sockets import emit_transcript_update, emit_transcription_error_from_service
except ImportError:
    # Handle case where sockets.py might not exist yet or circular import issues during setup
    logger.warning("Could not import socket emission functions. Streaming transcription updates will not be sent.")
    def emit_transcript_update(sid, transcript, is_final): pass
    def emit_transcription_error_from_service(sid, error_message): pass


logger = logging.getLogger(__name__)

# --- Thread-safe storage for audio queues ---
# Key: session ID (sid), Value: queue.Queue
audio_queues = {}
_queue_lock = threading.Lock()

# Ensure credentials are set (the library often picks up the env var automatically)
# You might need to explicitly point to the credentials file if the env var isn't set
# before the app starts, though relying on the standard env var is preferred.
# Example: client = speech.SpeechClient.from_service_account_json(current_app.config['GOOGLE_APPLICATION_CREDENTIALS'])

def transcribe_audio(audio_content: bytes, language_code: str = "en-US", sample_rate_hertz: int = 16000) -> str | None:
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

        logger.info(f"Sending audio to Google Speech-to-Text Long Running API (Language: {language_code}, Encoding: WEBM_OPUS, Channels: 2)")
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
                logger.warning("Transcript cleanup failed or returned original. Using raw transcript.")
            else:
                logger.info(f"Cleaned transcript: '{cleaned_transcript[:50]}...'")

            return cleaned_transcript # Return the cleaned (or original if cleanup failed) transcript

        else:
            logger.warning("Transcription returned no results.")
            return "" # Return empty string for no results vs None for error

    except InvalidArgument as e:
         logger.error(f"Google Speech API Invalid Argument: {e}. Ensure audio encoding matches the file format.", exc_info=True)
         # You might want to inspect e.details() or specific error codes
         return None
    except GoogleAPICallError as e:
        logger.error(f"Google Speech API call failed: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during transcription: {e}", exc_info=True)
        return None
