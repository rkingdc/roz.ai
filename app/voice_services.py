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

        logger.info(f"Sending audio to Google Speech-to-Text API (Language: {language_code}, Encoding: WEBM_OPUS, Channels: 2)")
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
         logger.error(f"Google Speech API Invalid Argument: {e}. Ensure audio encoding matches the file format.", exc_info=True)
         # You might want to inspect e.details() or specific error codes
         return None
    except GoogleAPICallError as e:
        logger.error(f"Google Speech API call failed: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during transcription: {e}", exc_info=True)
        return None
