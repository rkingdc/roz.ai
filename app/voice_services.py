import logging
from google.cloud import speech
from google.api_core.exceptions import GoogleAPICallError, NotFound, InvalidArgument
import os
from flask import current_app

logger = logging.getLogger(__name__)

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
    if not current_app.config.get('GOOGLE_APPLICATION_CREDENTIALS'):
        logger.error("GOOGLE_APPLICATION_CREDENTIALS environment variable not set. Cannot initialize SpeechClient.")
        # Optionally check if the file path exists: os.path.exists(current_app.config['GOOGLE_APPLICATION_CREDENTIALS'])
        return None

    try:
        # Instantiates a client. Relies on GOOGLE_APPLICATION_CREDENTIALS env var.
        client = speech.SpeechClient()

        # Prepare the audio object
        audio = speech.RecognitionAudio(content=audio_content)

        # Prepare the configuration object
        # TODO: Determine the best Encoding based on frontend capture (LINEAR16, WEBM_OPUS, etc.)
        # For now, assuming LINEAR16 (like WAV). Frontend must match this.
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16, # Adjust if frontend sends Opus/WebM etc.
            sample_rate_hertz=sample_rate_hertz, # Must match frontend recording sample rate
            language_code=language_code,
            # model="telephony", # Optional: Specify model for better accuracy in some cases
            # enable_automatic_punctuation=True, # Optional: Add punctuation
        )

        logger.info(f"Sending audio to Google Speech-to-Text API (Language: {language_code}, Sample Rate: {sample_rate_hertz})")
        response = client.recognize(config=config, audio=audio)
        logger.info("Received response from Google Speech-to-Text API")

        # Process the response
        if response.results:
            # Get the most likely transcript
            transcript = response.results[0].alternatives[0].transcript
            logger.info(f"Transcription successful: '{transcript[:50]}...'")
            return transcript
        else:
            logger.warning("Transcription returned no results.")
            return "" # Return empty string for no results vs None for error

    except InvalidArgument as e:
         logger.error(f"Google Speech API Invalid Argument: {e}. Check audio encoding/sample rate match.", exc_info=True)
         # You might want to inspect e.details() or specific error codes
         return None
    except GoogleAPICallError as e:
        logger.error(f"Google Speech API call failed: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during transcription: {e}", exc_info=True)
        return None
