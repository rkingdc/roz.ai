import google.genai as genai
from google.genai.types import Part # Added Part for transcribe_pdf_bytes
from google.api_core.exceptions import (
    GoogleAPIError,
    DeadlineExceeded,
    ClientError,
    NotFound,
    InvalidArgument,
)
from flask import current_app, g
import logging
import tempfile
import os
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


# --- Transcript Cleaning ---
def clean_up_transcript(raw_transcript: str) -> str:
    """
    Uses an LLM to clean up a raw transcript, removing filler words, etc.
    Falls back to the original transcript if cleaning fails.
    """
    logger.info("Entering clean_up_transcript.")

    if not raw_transcript or raw_transcript.isspace():
        logger.warning("clean_up_transcript received empty input.")
        return ""  # Return empty if input is empty

    # --- AI Readiness Check ---
    try:
        try:
            _ = current_app.config
            logger.debug("clean_up_transcript: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "clean_up_transcript called outside active Flask context.",
                exc_info=True,
            )
            return raw_transcript  # Fallback

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY missing for clean_up_transcript.")
            return raw_transcript  # Fallback

        try:
            if "genai_client" not in g:
                logger.info("Creating new genai.Client for clean_up_transcript.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client for clean_up_transcript.")
            client = g.genai_client
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(f"Failed to get genai.Client for cleanup: {e}", exc_info=True)
            return raw_transcript  # Fallback

    except Exception as e:
        logger.error(
            f"Unexpected error during readiness check for cleanup: {e}", exc_info=True
        )
        return raw_transcript  # Fallback
    # --- End AI Readiness Check ---

    # Determine model (use default or a specific one for cleaning if configured)
    raw_model_name = current_app.config.get(
        "DEFAULT_MODEL",
    )
    model_to_use = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )

    prompt = f"""
    ---
    You are a skilled technical writer whose role is to reformat audio transcription streams into well-structured transcripts.

    The transcript may contain multiple speakers. Do not try to guess who is speaking. Only notate the speaker when it is clear from context who is speaking. Otherwise use **Unknown:**. If it is likely a speaker but you lack full confidence, use **Unknown(possibly <speaker>)**:

===Example_Format

**Unknown(possible Roz):** Ok, let's get this meeting started. Jane is everyone here?

**Jane:** Yes, I think we have quorum. Roz do you want to kick us off?

**Roz:** Yes. Ok sales are up this quarter...

===
 **Additional Instructions**:
Some keywords and nouns that are commonly used but missidentified by the transcription software
People: Roz(not Ross), Nikhil, Sagar, Vijay, Haritha, Vikas, Ajay, Shridar, Vipin
Companies: LakeFusion, Newmark, Dun & Bradstreet, Databricks, Frisco Analytics
Technical Terms: DUNS or DUNS Number, match, enrich, kubectl
    
Make replacements where appropriate.

Reply only with the reformatted transcript. Include an empty line break between each speaker's text. 
---

The raw transcript:{raw_transcript}
The reformatted transcript:
"""

    logger.info(f"Attempting transcript cleanup using model '{model_to_use}'...")
    response = None
    try:
        # Use non-streaming generation for cleanup
        response = client.models.generate_content(
            model=model_to_use,
            contents=prompt,
        )

        # Process response
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            logger.warning(
                f"Transcript cleanup blocked by safety settings. Reason: {reason}"
            )
            return raw_transcript  # Fallback

        if (
            response.candidates
            and hasattr(response.candidates[0], "content")
            and hasattr(response.candidates[0].content, "parts")
            and response.candidates[0].content.parts
        ):
            cleaned_text = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            ).strip()  # Strip whitespace from the final result

            if cleaned_text:
                logger.info("Transcript cleaned successfully.")
                return cleaned_text
            else:
                logger.warning(
                    "Transcript cleanup resulted in empty text. Falling back."
                )
                return raw_transcript  # Fallback if result is empty
        else:
            logger.warning(
                f"Transcript cleanup did not produce usable content. Falling back. Response: {response!r}"
            )
            return raw_transcript  # Fallback

    except (
        GoogleAPIError,
        InvalidArgument,
        DeadlineExceeded,
        NotFound,
        Exception,
    ) as e:
        logger.error(f"Error during transcript cleanup API call: {e}", exc_info=True)
        return raw_transcript  # Fallback


# --- PDF Transcription ---
def transcribe_pdf_bytes(pdf_bytes: bytes, filename: str) -> str:
    """
    Transcribes the content of a PDF provided as bytes using the SUMMARY_MODEL.
    Uses the File API for processing.
    Returns the transcribed text or an error string.
    """
    logger.info(f"Entering transcribe_pdf_bytes for '{filename}'.")

    # --- AI Readiness Check ---
    try:
        try:
            _ = current_app.config
            logger.debug("transcribe_pdf_bytes: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "transcribe_pdf_bytes called outside active Flask context.",
                exc_info=True,
            )
            return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY missing for transcribe_pdf_bytes.")
            return "[Error: AI Service API Key not configured]"

        try:
            if "genai_client" not in g:
                logger.info("Creating new genai.Client for transcribe_pdf_bytes.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client for transcribe_pdf_bytes.")
            client = g.genai_client
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to get genai.Client for PDF transcription: {e}", exc_info=True
            )
            if "api key not valid" in str(e).lower():
                return "[Error: Invalid Gemini API Key]"
            return "[Error: Failed to initialize AI client]"

    except Exception as e:
        logger.error(
            f"Unexpected error during readiness check for PDF transcription: {e}",
            exc_info=True,
        )
        return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
    # --- End AI Readiness Check ---

    raw_model_name = current_app.config["SUMMARY_MODEL"]
    model_to_use = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )
    logger.info(
        f"Attempting PDF transcription for '{filename}' using model '{model_to_use}'..."
    )

    content_parts = []
    temp_file_to_clean = None
    prompt = f"Please transcribe the full text content of the attached PDF file named '{filename}'. Output only the transcribed text."
    response = None

    try:
        # --- File Upload Logic ---
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{secure_filename(filename)}"
            ) as temp_file:
                temp_file.write(pdf_bytes)
                temp_filepath = temp_file.name
                temp_file_to_clean = temp_filepath

            logger.info(
                f"Uploading temp file '{temp_filepath}' for PDF transcription..."
            )
            uploaded_file = client.files.upload(
                file=temp_filepath,
                config={"display_name": filename, "mime_type": "application/pdf"},
            )
            logger.info(
                f"File '{filename}' uploaded for transcription, URI: {uploaded_file.uri}"
            )
            content_parts = [
                Part(text=prompt), # Use Part from google.genai.types
                uploaded_file,
            ]
        except Exception as upload_err:
            logger.error(
                f"Error preparing/uploading PDF for transcription: {upload_err}",
                exc_info=True,
            )
            if "api key not valid" in str(upload_err).lower():
                return "[Error: Invalid Gemini API Key during file upload]"
            return f"[Error preparing/uploading PDF for transcription: {type(upload_err).__name__}]"

        # --- Generate Content using the Client ---
        logger.info(f"Calling generate_content with model '{model_to_use}'.")
        response = client.models.generate_content(
            model=model_to_use,
            contents=content_parts,
        )

        # --- Process Response ---
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            logger.warning(
                f"PDF transcription blocked by safety settings for {filename}. Reason: {reason}"
            )
            return f"[Error: PDF transcription blocked due to safety settings (Reason: {reason})]"

        if (
            response.candidates
            and hasattr(response.candidates[0], "content")
            and hasattr(response.candidates[0].content, "parts")
            and response.candidates[0].content.parts
        ):
            transcribed_text = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            )
            if transcribed_text.strip():
                logger.info(f"PDF transcription successful for '{filename}'.")
                return transcribed_text
            else:
                logger.warning(
                    f"PDF transcription for '{filename}' resulted in empty text content."
                )
                return "[System Note: AI generated an empty transcription.]"
        else:
            logger.warning(
                f"PDF transcription for '{filename}' did not produce usable content. Response: {response!r}"
            )
            finish_reason = "UNKNOWN"
            if response.candidates and hasattr(response.candidates[0], "finish_reason"):
                finish_reason = response.candidates[0].finish_reason.name
            return f"[Error: AI did not generate transcription content (Finish Reason: {finish_reason})]"

    # --- Error Handling ---
    except InvalidArgument as e:
        logger.error(
            f"InvalidArgument error during PDF transcription for '{filename}': {e}.",
            exc_info=True,
        )
        return f"[Error transcribing PDF: Invalid argument or unsupported file type ({type(e).__name__}).]"
    except DeadlineExceeded:
        logger.error(f"PDF transcription timed out for '{filename}'.")
        return "[Error: PDF transcription timed out.]"
    except NotFound as e:
        logger.error(f"Model '{model_to_use}' not found or inaccessible: {e}")
        return f"[Error: AI Model '{raw_model_name}' not found or access denied.]"
    except GoogleAPIError as e:
        logger.error(f"Google API error during PDF transcription for '{filename}': {e}")
        err_str = str(e).lower()
        if "api key not valid" in err_str:
            return "[Error: Invalid Gemini API Key]"
        if "resource has been exhausted" in err_str or "429" in str(e):
            logger.warning(
                f"Quota/Rate limit hit during PDF transcription for {filename}."
            )
            return "[Error: API quota or rate limit exceeded. Please try again later.]"
        return f"[Error transcribing PDF via API: {type(e).__name__}]"
    except Exception as e:
        logger.error(
            f"Unexpected error during PDF transcription for '{filename}': {e}",
            exc_info=True,
        )
        return f"[Error transcribing PDF: An unexpected error occurred ({type(e).__name__}).]"
    finally:
        if temp_file_to_clean:
            try:
                if os.path.exists(temp_file_to_clean):
                    os.remove(temp_file_to_clean)
                    logger.info(
                        f"Cleaned up temp transcription file: {temp_file_to_clean}"
                    )
            except OSError as e:
                logger.warning(
                    f"Error removing temp transcription file {temp_file_to_clean}: {e}"
                )
