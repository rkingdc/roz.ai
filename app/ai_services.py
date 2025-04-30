# app/ai_services.py
import google.genai as genai  # Use the new SDK

# Import necessary types, including the one for FileDataPart
from google.genai.types import (
    GenerationConfig,
    Part,
    Content,
    GenerateContentResponse,
    Blob,  # Import Blob for inline data
    Candidate,  # Import Candidate for error response structure
    FileData,  # Import FileData for referencing uploaded files
)
import binascii  # Import binascii for the correct exception type
from flask import current_app, g  # Import g for request context caching
import tempfile
import os
import re
import base64
from . import database
from .plugins.web_search import perform_web_search # Remove fetch_web_content import
from google.api_core.exceptions import (
    GoogleAPIError,
    DeadlineExceeded,
    ClientError,
    NotFound,
    InvalidArgument,  # Import InvalidArgument for malformed content errors
)
from pydantic_core import ValidationError
import grpc
import logging

# from functools import wraps # Remove this import
from werkzeug.utils import secure_filename

# Configure logging - Removed basicConfig and setLevel here
logger = logging.getLogger(__name__)

# --- Configuration Check ---
# Remove gemini_api_key_present global and configure_gemini function

# --- Helper Functions for Client Instantiation ---
# Remove _get_api_key and get_gemini_client functions

# --- Decorator for AI Readiness Check ---
# Remove the entire decorator function


# --- Summary Generation ---
# Remove the decorator
def generate_summary(file_id):
    """
    Generates a summary for a file using a designated multi-modal model via the client.
    Handles text directly and uses file upload API for other types.
    Uses the NEW google.genai library structure (client-based).
    """
    logger.info(f"Entering generate_summary for file {file_id}.")

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
            _ = (
                current_app.config
            )  # Simple check that raises RuntimeError if no context
            logger.debug("generate_summary: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "generate_summary called outside of active Flask request context.",
                exc_info=True,  # Log traceback
            )
            return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return "[Error: AI Service API Key not configured]"

        try:
            # Use client caching via Flask's 'g' object if in request context
            if "genai_client" not in g:
                logger.info("Creating new genai.Client and caching in 'g'.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client from 'g'.")
            client = g.genai_client
            # Test the client connection minimally (optional, can add latency)
            # client.models.list() # Example test
            logger.info("Successfully obtained genai.Client for summary generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to initialize/get genai.Client for summary: {e}", exc_info=True
            )
            # Check for invalid key specifically
            if "api key not valid" in str(e).lower():
                return "[Error: Invalid Gemini API Key]"
            return "[Error: Failed to initialize AI client]"

    except Exception as e:
        # Catch any unexpected errors during the readiness check itself
        logger.error(
            f"generate_summary: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
    # --- End AI Readiness Check ---

    try:
        file_details = database.get_file_details_from_db(file_id, include_content=True)
        if not file_details or not file_details.get("content"):
            logger.error(
                f"Could not retrieve file details or content for file ID: {file_id}"
            )
            return "[Error: File details or content not found]"
    except Exception as db_err:
        logger.error(f"Database error fetching file {file_id}: {db_err}", exc_info=True)
        return "[Error: Database error retrieving file]"

    filename = file_details["filename"]
    mimetype = file_details["mimetype"]
    content_blob = file_details["content"]
    # Ensure model name from config includes the 'models/' prefix if needed by API
    raw_model_name = current_app.config["SUMMARY_MODEL"]
    summary_model_name = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )

    logger.info(
        f"Attempting summary generation for '{filename}' (Type: {mimetype}) using model '{summary_model_name}'..."
    )

    content_parts = []  # Renamed from 'parts' to avoid confusion with genai.types.Part
    temp_file_to_clean = None
    prompt = f"Please provide a concise summary of the attached file named '{filename}'. Focus on the main points and key information."
    response = None  # Initialize response to None

    try:
        # --- Text Handling ---
        if mimetype.startswith("text/") or filename.lower().endswith(
            (".js", ".py", ".css", ".html", ".json", ".xml", ".csv", ".log")
        ):  # Expanded text types
            try:
                effective_mimetype = (
                    mimetype
                    if mimetype.startswith("text/")
                    else "application/octet-stream"
                )  # Use generic for code if not text/*
                logger.info(
                    f"Treating '{filename}' as text ({effective_mimetype}) for summary."
                )
                text_content = content_blob.decode("utf-8", errors="ignore")
                # Construct parts for the client's generate_content
                # Wrap text components in Part()
                content_parts = [
                    Part(text=prompt),  # Initial prompt part
                    Part(text=f"\n--- File Content ({filename}) ---\n"),
                    Part(text=text_content),  # Content part
                ]
            except Exception as decode_err:
                logger.error(f"Error decoding text content for summary: {decode_err}")
                return "[Error: Could not decode text content for summary]"

        # --- File Upload Logic ---
        # Check supported types for the specific model being used if possible
        # This example uses generic checks
        elif mimetype.startswith(("image/", "audio/", "video/", "application/pdf")):
            try:
                # Use File API for supported types by creating a FileDataPart
                logger.info(
                    f"Preparing FileDataPart for '{filename}' ({mimetype}) for summary."
                )
                # Ensure the client has access to the file data (e.g., via temp file or directly)
                # Using temp file approach here for broader compatibility
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{secure_filename(filename)}"
                ) as temp_file:
                    temp_file.write(content_blob)
                    temp_filepath = temp_file.name
                    temp_file_to_clean = temp_filepath  # Schedule for cleanup

                logger.info(
                    f"Uploading temp file '{temp_filepath}' for summary generation..."
                )
                # Use the client's file upload method
                uploaded_file = client.files.upload(
                    file=temp_filepath,
                    config={"display_name": filename, "mime_type": mimetype},
                )
                logger.info(
                    f"File '{filename}' uploaded for summary, URI: {uploaded_file.uri}"
                )
                # Construct parts including the prompt (as Part) and the uploaded file reference
                content_parts = [
                    Part(text=prompt),
                    uploaded_file,  # Add the File object directly
                ]
            except Exception as upload_err:
                logger.error(
                    f"Error preparing/uploading file for summary: {upload_err}",
                    exc_info=True,
                )
                if "api key not valid" in str(upload_err).lower():
                    return "[Error: Invalid Gemini API Key during file upload]"
                return f"[Error preparing/uploading file for summary: {type(upload_err).__name__}]"
        else:
            logger.warning(f"Summary generation not supported for mimetype: {mimetype}")
            return "[Summary generation not supported for this file type]"

        # --- Generate Content using the Client ---
        logger.info(f"Calling generate_content with model '{summary_model_name}'.")

        # Use the client.models attribute to generate content
        # Summary generation is NOT streamed, always get full response
        response = client.models.generate_content(
            model=summary_model_name,
            contents=content_parts,
        )

        # --- Process Response ---
        # Check for safety issues first
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            logger.warning(
                f"Summary generation blocked by safety settings for {filename}. Reason: {reason}"
            )
            return f"[Error: Summary generation blocked due to safety settings (Reason: {reason})]"

        # Check if candidates exist and have text
        if (
            response.candidates
            and hasattr(response.candidates[0], "content")
            and hasattr(response.candidates[0].content, "parts")
            and response.candidates[0].content.parts
        ):
            # Extract text from all parts and join them (though usually there's one)
            summary = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            )
            if summary.strip():  # Check if summary is not just whitespace
                logger.info(f"Summary generated successfully for '{filename}'.")
                return summary
            else:
                logger.warning(
                    f"Summary generation for '{filename}' resulted in empty text content."
                )
                return "[System Note: AI generated an empty summary.]"
        else:
            # Handle cases where response is empty or has unexpected structure
            logger.warning(
                f"Summary generation for '{filename}' did not produce usable content. Response: {response!r}"
            )
            # Check finish reason if available
            finish_reason = "UNKNOWN"
            if response.candidates and hasattr(response.candidates[0], "finish_reason"):
                finish_reason = response.candidates[0].finish_reason.name
            return f"[Error: AI did not generate summary content (Finish Reason: {finish_reason})]"

    # --- Error Handling for API Call ---
    except InvalidArgument as e:
        logger.error(
            f"InvalidArgument error during summary generation for '{filename}': {e}. Often due to unsupported file type or malformed request.",
            exc_info=True,
        )
        return f"[Error generating summary: Invalid argument or unsupported file type ({type(e).__name__}).]"
    except TypeError as e:
        logger.error(
            f"TypeError during summary generation for '{filename}': {e}. Check SDK method signature.",
            exc_info=True,
        )
        return f"[Error generating summary: SDK usage error ({type(e).__name__}).]"
    except AttributeError as e:
        logger.error(
            f"AttributeError during summary generation for '{filename}': {e}. Check SDK usage.",
            exc_info=True,
        )
        return f"[Error generating summary: SDK usage error ({type(e).__name__}).]"
    except DeadlineExceeded:
        logger.error(f"Summary generation timed out for '{filename}'.")
        return "[Error: Summary generation timed out.]"
    except NotFound as e:
        logger.error(f"Model '{summary_model_name}' not found or inaccessible: {e}")
        return f"[Error: AI Model '{raw_model_name}' not found or access denied.]"
    except GoogleAPIError as e:
        logger.error(
            f"Google API error during summary generation for '{filename}': {e}"
        )
        err_str = str(e).lower()
        if "api key not valid" in err_str:
            return "[Error: Invalid Gemini API Key]"
        # Safety check moved to response processing above
        if "resource has been exhausted" in err_str or "429" in str(e):
            logger.warning(
                f"Quota/Rate limit hit during summary generation for {filename}."
            )
            return "[Error: API quota or rate limit exceeded. Please try again later.]"
        return f"[Error generating summary via API: {type(e).__name__}]"  # Generic API error
    except Exception as e:
        logger.error(
            f"Unexpected error during summary generation for '{filename}': {e}",
            exc_info=True,
        )
        return f"[Error generating summary: An unexpected error occurred ({type(e).__name__}).]"
    finally:
        if temp_file_to_clean:
            try:
                if os.path.exists(temp_file_to_clean):
                    os.remove(temp_file_to_clean)
                    logger.info(f"Cleaned up temp summary file: {temp_file_to_clean}")
            except OSError as e:
                logger.warning(
                    f"Error removing temp summary file {temp_file_to_clean}: {e}"
                )


# --- Get Or Generate Summary ---
# No decorator needed here as it calls generate_summary which now handles its own readiness
def get_or_generate_summary(file_id):
    """Gets summary from DB or generates+saves it if not present."""
    try:
        file_details = database.get_file_details_from_db(file_id)
        if not file_details:
            logger.error(f"File details not found in DB for ID: {file_id}")
            return "[Error: File details not found]"

        # Check if a valid summary already exists
        if (
            file_details.get("has_summary")
            and file_details.get("summary")
            and not file_details["summary"].startswith(
                ("[Error", "[System Note", "[AI Error")
            )  # Check if it's not an old error/note message
        ):
            logger.info(f"Retrieved existing summary for file ID: {file_id}")
            return file_details["summary"]
        else:
            logger.info(f"Generating summary for file ID: {file_id}...")
            # Call the refactored function (which now handles its own readiness)
            new_summary = generate_summary(file_id)

            # Only save if generation was successful (doesn't start with error/note prefixes)
            error_prefixes = ("[Error", "[System Note", "[AI Error")
            if isinstance(new_summary, str) and not new_summary.startswith(
                error_prefixes
            ):
                if database.save_summary_in_db(file_id, new_summary):
                    logger.info(
                        f"Successfully generated and saved summary for file ID: {file_id}"
                    )
                    return new_summary
                else:
                    logger.error(
                        f"Failed to save newly generated summary for file ID: {file_id}"
                    )
                    # Return the summary anyway, but log the save error
                    return new_summary
            else:
                # If generation failed or returned a system note, return it directly
                logger.warning(
                    f"Summary generation failed or produced note for file ID {file_id}: {new_summary}"
                )
                # Optionally save the error/note state to prevent retries?
                # database.save_summary_in_db(file_id, new_summary) # Uncomment to save errors/notes
                return new_summary
    except Exception as e:
        logger.error(
            f"Error in get_or_generate_summary for file ID {file_id}: {e}",
            exc_info=True,
        )
        return f"[Error retrieving or generating summary: {type(e).__name__}]"


# --- Generate Search Query ---
# Remove the decorator
def generate_search_query(user_message: str, max_retries=1) -> str | None:
    """
    Uses the default LLM via client to generate a concise web search query.
    """
    logger.info("Entering generate_search_query.")

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
            _ = (
                current_app.config
            )  # Simple check that raises RuntimeError if no context
            logger.debug("generate_search_query: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "generate_search_query called outside of active Flask request context.",
                exc_info=True,  # Log traceback
            )
            return None  # Return None as expected by the caller

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return None  # Return None as expected by the caller

        try:
            # Use client caching via Flask's 'g' object if in request context
            if "genai_client" not in g:
                logger.info("Creating new genai.Client and caching in 'g'.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client from 'g'.")
            client = g.genai_client
            logger.info("Successfully obtained genai.Client for query generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to initialize/get genai.Client for query: {e}", exc_info=True
            )
            if "api key not valid" in str(e).lower():
                return None  # Return None
            return None  # Return None

    except Exception as e:
        # Catch any unexpected errors during the readiness check itself
        logger.error(
            f"generate_search_query: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        return None  # Return None as expected by the caller
    # --- End AI Readiness Check ---

    if not user_message or user_message.isspace():
        logger.info("Cannot generate search query from empty user message.")
        return None

    # Use a specific model or the default one for this task
    raw_model_name = current_app.config.get(
        "QUERY_MODEL", current_app.config["DEFAULT_MODEL"]
    )
    model_name = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )
    logger.info(f"Attempting to generate search query using model '{model_name}'...")

    prompt = f"""Analyze the following user message and generate a concise and effective web search query (ideally 3-7 words) that would find information directly helpful in answering or augmenting the user's request.

User Message:
"{user_message}"

Focus on the core information needed. Output *only* the raw search query string itself. Do not add explanations, quotation marks (unless essential for the search phrase), or any other surrounding text.

Search Query:"""

    retries = 0
    while retries <= max_retries:
        response = None  # Initialize response to None
        try:
            # Use the client.models attribute to generate content
            # Query generation is NOT streamed
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            # Check for blocked prompt before accessing text
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                logger.warning(f"Prompt blocked for query gen, reason: {reason}")
                return None  # Don't retry if blocked

            # Extract text safely
            generated_query = ""
            if (
                response.candidates
                and hasattr(response.candidates[0], "content")
                and hasattr(response.candidates[0].content, "parts")
                and response.candidates[0].content.parts
            ):
                generated_query = "".join(
                    part.text
                    for part in response.candidates[0].content.parts
                    if hasattr(part, "text")
                ).strip()

            # Clean the generated query
            if generated_query:
                logger.info(f"Raw query generated: '{generated_query}'")
                generated_query = re.sub(
                    r'^"|"$', "", generated_query
                )  # Remove leading/trailing quotes
                generated_query = re.sub(
                    r"^\s*[-\*\d]+\.?\s*", "", generated_query
                )  # Remove leading list markers
                generated_query = re.sub(
                    r"^(?:Search Query:|Here is a search query:|query:)\s*",
                    "",
                    generated_query,
                    flags=re.IGNORECASE,
                )  # Remove common prefixes
                generated_query = generated_query.strip()  # Final strip

                if generated_query:
                    logger.info(f"Cleaned Search Query: '{generated_query}'")
                    return generated_query
                else:
                    logger.warning(
                        "LLM generated an empty search query after cleaning."
                    )
                    # Don't retry empty query, likely a model issue
                    return None
            else:
                # Handle cases where response is empty or has unexpected structure
                logger.warning(
                    f"Query generation did not produce usable content. Response: {response!r}"
                )
                finish_reason = "UNKNOWN"
                if response.candidates and hasattr(
                    response.candidates[0], "finish_reason"
                ):
                    finish_reason = response.candidates[0].finish_reason.name
                logger.warning(f"Query generation finish reason: {finish_reason}")
                return None  # Don't retry if no content

        except InvalidArgument as e:
            logger.error(
                f"InvalidArgument error during query generation: {e}.", exc_info=True
            )
            return None  # Don't retry
        except TypeError as e:
            logger.error(
                f"TypeError during search query generation: {e}. Check SDK method signature.",
                exc_info=True,
            )
            return None  # Don't retry SDK usage errors
        except AttributeError as e:
            logger.error(
                f"AttributeError during search query generation: {e}. Check SDK usage.",
                exc_info=True,
            )
            return None  # Don't retry SDK usage errors
        except DeadlineExceeded:
            logger.warning(
                f"Search query generation timed out (Attempt {retries+1}/{max_retries+1})."
            )
            retries += 1
        except NotFound as e:
            logger.error(f"Model '{model_name}' not found for query generation: {e}")
            return None  # Don't retry if model not found
        except GoogleAPIError as e:
            logger.error(
                f"Google API error during search query generation (Attempt {retries+1}/{max_retries+1}): {e}"
            )
            err_str = str(e).lower()
            if "api key not valid" in err_str:
                logger.error(
                    "API key invalid during search query generation. Aborting."
                )
                return None  # Don't retry if key is invalid
            if "resource has been exhausted" in err_str or "429" in str(e):
                logger.warning("Quota/Rate limit hit during query generation.")
                # Could implement backoff here, but for now just retry once if allowed
                retries += 1
            # Safety check moved to response processing above
            else:
                # For other API errors, retry once if allowed
                retries += 1
        except Exception as e:
            logger.error(
                f"Unexpected error during search query generation (Attempt {retries+1}/{max_retries+1}): {e}",
                exc_info=True,
            )
            retries += 1  # Retry unexpected errors once

    logger.error(f"Search query generation failed after {max_retries+1} attempts.")
    return None


# --- Internal Helper for Streaming Error Handling ---
def _yield_streaming_error(error_msg: str):
    """Helper to yield an error message in a valid GenerateContentResponse structure for streaming."""
    logger.debug(f"Yielding streaming error: {error_msg}")
    # Create a valid structure: Response -> Candidates -> Candidate -> Content -> Parts -> Part
    error_part = Part(text=error_msg)
    error_content = Content(role="model", parts=[error_part])  # Assign role for Content
    error_candidate = Candidate(
        content=error_content, finish_reason="ERROR"
    )  # Use ERROR finish reason
    yield GenerateContentResponse(candidates=[error_candidate])


# --- Chat Response Generation ---
# This function is now DESIGNED to return EITHER a generator (if streaming) OR a string (if not streaming)
def generate_chat_response(
    chat_id,
    user_message,
    attached_files=None,
    session_files=None,
    calendar_context=None,
    web_search_enabled=False,
    streaming_enabled=False,  # This flag determines the *return type*
):
    """
    Generates a chat response using the Gemini API via the client.
    Handles history, context, files, web search. Handles errors gracefully.

    Args:
        ... (standard args) ...
        streaming_enabled (bool): If True, returns a generator yielding response chunks.
                                  If False, returns a string with the full response or error message.

    Returns:
        - Generator[GenerateContentResponse, None, None]: If streaming_enabled is True.
        - str: If streaming_enabled is False.
    """
    logger.info(
        f"Entering generate_chat_response for chat {chat_id}. Streaming: {streaming_enabled}"
    )

    # --- AI Readiness Check ---
    # This check needs to return/yield correctly based on streaming_enabled
    try:
        try:
            _ = current_app.config
            logger.debug("generate_chat_response: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "generate_chat_response called outside of active Flask request context.",
                exc_info=True,
            )
            error_msg = "[Error: AI Service called outside request context]"
            if streaming_enabled:
                # Must return a generator immediately, even for errors
                return _yield_streaming_error(error_msg)
            else:
                return error_msg  # Return string directly

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            error_msg = "[Error: AI Service API Key not configured]"
            if streaming_enabled:
                return _yield_streaming_error(error_msg)
            else:
                return error_msg

        try:
            if "genai_client" not in g:
                logger.info("Creating new genai.Client and caching in 'g'.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client from 'g'.")
            client = g.genai_client
            logger.info("Successfully obtained genai.Client for chat response.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to initialize/get genai.Client for chat: {e}", exc_info=True
            )
            error_msg = "[Error: Failed to initialize AI client]"
            if "api key not valid" in str(e).lower():
                error_msg = "[Error: Invalid Gemini API Key]"
            if streaming_enabled:
                return _yield_streaming_error(error_msg)
            else:
                return error_msg

    except Exception as e:
        logger.error(
            f"generate_chat_response: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        error_msg = f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
        if streaming_enabled:
            return _yield_streaming_error(error_msg)
        else:
            return error_msg
    # --- End AI Readiness Check ---

    # --- Main Logic ---
    # This part needs to be structured differently depending on streaming
    # We can use a helper function for the core API call and processing
    # to avoid code duplication and keep the main function clean.

    if streaming_enabled:
        # If streaming, call a helper that IS a generator
        return _generate_chat_response_stream(
            client=client,  # Pass the initialized client
            chat_id=chat_id,
            user_message=user_message,
            attached_files=attached_files,
            session_files=session_files,
            calendar_context=calendar_context,
            web_search_enabled=web_search_enabled,
        )
    else:
        # If not streaming, call a helper that returns a string
        return _generate_chat_response_non_stream(
            client=client,  # Pass the initialized client
            chat_id=chat_id,
            user_message=user_message,
            attached_files=attached_files,
            session_files=session_files,
            calendar_context=calendar_context,
            web_search_enabled=web_search_enabled,
        )


# --- Helper Function for NON-STREAMING Response ---
def _generate_chat_response_non_stream(
    client,
    chat_id,
    user_message,
    attached_files,
    session_files,
    calendar_context,
    web_search_enabled,
) -> str:
    """Internal helper to generate a full chat response string."""
    logger.info(f"_generate_chat_response_non_stream called for chat {chat_id}")
    temp_files_to_clean = []
    try:
        # --- Prepare History and Parts (Common Logic) ---
        history, current_turn_parts, temp_files_to_clean = _prepare_chat_content(
            client,
            chat_id,
            user_message,
            attached_files,
            session_files,
            calendar_context,
            web_search_enabled,
        )

        # Check if preparation returned an error message (string)
        if isinstance(
            history, str
        ):  # Using history variable to signal error from preparation
            logger.error(
                f"Error preparing content for non-streaming chat {chat_id}: {history}"
            )
            return history  # Return the error string

        if not current_turn_parts:
            logger.error(
                f"Chat {chat_id}: No parts generated for the current turn (non-streaming)."
            )
            return (
                "[Error: No content (message, files, context) provided for this turn.]"
            )

        # --- Determine Model ---
        raw_model_name = current_app.config.get(
            "PRIMARY_MODEL", current_app.config["DEFAULT_MODEL"]
        )
        model_to_use = (
            f"models/{raw_model_name}"
            if not raw_model_name.startswith("models/")
            else raw_model_name
        )
        logger.info(f"Non-streaming model for chat {chat_id}: '{model_to_use}'.")

        # --- Call Gemini API (Non-Streaming) ---
        full_conversation = history + [Content(role="user", parts=current_turn_parts)]

        logger.info(
            f"Calling model.generate_content (non-streaming) for chat {chat_id}"
        )

        system_prompt = f"""You are a helpful assistant. Please format your responses using Markdown. Use headings (H1 to H6) to structure longer answers and use bold text selectively to highlight key information or terms. Your goal is to make the response clear and easy to read."""

        response = client.models.generate_content(
            model=model_to_use,
            contents=full_conversation,
            system_instruction=system_prompt,  # Add system instruction
        )
        logger.info(f"Non-streaming generate_content call returned for chat {chat_id}.")

        # --- Process Non-Streaming Response ---
        logger.debug(f"Non-streaming raw response object: {response!r}")

        # Check for safety issues first
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            logger.warning(
                f"Non-streaming response blocked by safety settings for chat {chat_id}. Reason: {reason}"
            )
            return f"[AI Safety Error: Request blocked due to safety settings (Reason: {reason})]"

        # Check candidates and extract text
        if (
            response.candidates
            and hasattr(response.candidates[0], "content")
            and hasattr(response.candidates[0].content, "parts")
            and response.candidates[0].content.parts
        ):
            assistant_reply = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            )
            if assistant_reply.strip():
                logger.info(
                    f"Successfully received full response text (length {len(assistant_reply)}) for chat {chat_id}."
                )
                return assistant_reply
            else:
                logger.warning(
                    f"Non-streaming response for chat {chat_id} was empty or whitespace."
                )
                return "[System Note: The AI returned an empty response.]"
        else:
            logger.warning(
                f"Non-streaming response for chat {chat_id} did not produce usable content. Response: {response!r}"
            )
            finish_reason = "UNKNOWN"
            if response.candidates and hasattr(response.candidates[0], "finish_reason"):
                finish_reason = response.candidates[0].finish_reason.name
            # Check prompt feedback again
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                return f"[AI Safety Error: Request blocked (Reason: {reason}, Finish Reason: {finish_reason})]"
            else:
                return f"[AI Error: The AI did not return any content (Finish Reason: {finish_reason})]"

    # --- Error Handling for Non-Streaming API Call ---
    except InvalidArgument as e:
        logger.error(
            f"InvalidArgument error during non-streaming chat {chat_id}: {e}.",
            exc_info=True,
        )
        return f"[AI Error: Invalid argument or unsupported file type ({type(e).__name__}).]"
    except ValidationError as e:
        logger.error(
            f"Data validation error calling non-streaming Gemini API for chat {chat_id}: {e}",
            exc_info=True,
        )
        try:
            error_details = f"{e.errors()[0]['type']} on field '{'.'.join(map(str,e.errors()[0]['loc']))}'"
        except Exception:
            error_details = "Check logs."
        return f"[AI Error: Internal data format error. {error_details}]"
    except DeadlineExceeded:
        logger.error(f"Non-streaming Gemini API call timed out for chat {chat_id}.")
        return "[AI Error: The request timed out. Please try again.]"
    except NotFound as e:
        raw_model_name = current_app.config.get(
            "PRIMARY_MODEL", current_app.config["DEFAULT_MODEL"]
        )  # Get model name again for error msg
        logger.error(f"Model for non-streaming chat {chat_id} not found: {e}")
        return f"[AI Error: Model '{raw_model_name}' not found or access denied.]"
    except GoogleAPIError as e:
        logger.error(
            f"Google API error for non-streaming chat {chat_id}: {e}", exc_info=False
        )
        err_str = str(e).lower()
        if "api key not valid" in err_str:
            return "[Error: Invalid Gemini API Key]"
        if "permission denied" in err_str:
            return (
                f"[AI Error: Permission denied for model. Check API key permissions.]"
            )
        if "resource has been exhausted" in err_str or "429" in str(e):
            logger.warning(f"Quota/Rate limit hit for non-streaming chat {chat_id}.")
            return (
                "[AI Error: API quota or rate limit exceeded. Please try again later.]"
            )
        if "prompt was blocked" in err_str or "SAFETY" in str(e).upper():
            logger.warning(
                f"API error indicates safety block for non-streaming chat {chat_id}: {e}"
            )
            return f"[AI Safety Error: Request or response blocked due to safety settings (Reason: SAFETY)]"
        if "internal error" in err_str or "500" in str(e):
            logger.error(
                f"Internal server error from Gemini API for non-streaming chat {chat_id}: {e}"
            )
            return "[AI Error: The AI service encountered an internal error.]"
        return f"[AI API Error: {type(e).__name__}]"  # Generic API error
    except Exception as e:
        logger.error(
            f"Unexpected error during non-streaming Gemini API interaction for chat {chat_id}: {e}",
            exc_info=True,
        )
        return f"[Unexpected AI Error: {type(e).__name__}]"
    finally:
        _cleanup_temp_files(temp_files_to_clean, f"non-streaming chat {chat_id}")


# --- Helper Function for STREAMING Response ---
def _generate_chat_response_stream(
    client,
    chat_id,
    user_message,
    attached_files,
    session_files,
    calendar_context,
    web_search_enabled,
):  # -> Generator[GenerateContentResponse, None, None] implicitly
    """Internal helper that IS a generator yielding chat response chunks."""
    logger.info(f"_generate_chat_response_stream called for chat {chat_id}")
    temp_files_to_clean = []
    response_iterator = None  # Initialize
    try:
        # --- Prepare History and Parts (Common Logic) ---
        history, current_turn_parts, temp_files_to_clean = _prepare_chat_content(
            client,
            chat_id,
            user_message,
            attached_files,
            session_files,
            calendar_context,
            web_search_enabled,
        )

        # Check if preparation returned an error message (string)
        if isinstance(history, str):  # Using history variable to signal error
            logger.error(
                f"Error preparing content for streaming chat {chat_id}: {history}"
            )
            yield from _yield_streaming_error(history)  # Yield the error and stop
            return

        if not current_turn_parts:
            logger.error(
                f"Chat {chat_id}: No parts generated for the current turn (streaming)."
            )
            yield from _yield_streaming_error(
                "[Error: No content (message, files, context) provided for this turn.]"
            )
            return

        # --- Determine Model ---
        raw_model_name = current_app.config.get(
            "PRIMARY_MODEL", current_app.config["DEFAULT_MODEL"]
        )
        model_to_use = (
            f"models/{raw_model_name}"
            if not raw_model_name.startswith("models/")
            else raw_model_name
        )
        logger.info(f"Streaming model for chat {chat_id}: '{model_to_use}'.")

        # --- Call Gemini API (Streaming) ---
        full_conversation = history + [Content(role="user", parts=current_turn_parts)]

        system_prompt = """You are a helpful assistant. Please format your responses using Markdown. Use headings (H1 to H6) to structure longer answers and use bold text selectively to highlight key information or terms. Your goal is to make the response clear and easy to read."""

        logger.info(f"Calling model.generate_content (streaming) for chat {chat_id}")
        # NOTE: system_instruction is NOT supported directly in generate_content_stream in this SDK version.
        # It might need to be prepended to 'contents' if the model supports it that way,
        # but removing the unsupported keyword argument is the immediate fix for the TypeError.
        response_iterator = client.models.generate_content_stream(
            model=model_to_use,
            contents=full_conversation,
            # system_instruction=system_prompt, # REMOVED: Unsupported keyword argument
        )
        logger.info(
            f"Streaming generate_content call returned iterator for chat {chat_id}."
        )

        # --- Yield Chunks from Iterator ---
        chunk_count = 0
        for chunk in response_iterator:
            # logger.debug(f"Yielding chunk {chunk_count} for chat {chat_id}: {chunk!r}") # Very verbose
            yield chunk
            chunk_count += 1
        logger.info(f"Finished yielding {chunk_count} chunks for chat {chat_id}.")

    # --- Error Handling for Streaming API Call ---
    # Handle errors that might occur during iteration or the initial call
    except InvalidArgument as e:
        logger.error(
            f"InvalidArgument error during streaming chat {chat_id}: {e}.",
            exc_info=True,
        )
        yield from _yield_streaming_error(
            f"[AI Error: Invalid argument or unsupported file type ({type(e).__name__}).]"
        )
    except ValidationError as e:
        logger.error(
            f"Data validation error calling streaming Gemini API for chat {chat_id}: {e}",
            exc_info=True,
        )
        try:
            error_details = f"{e.errors()[0]['type']} on field '{'.'.join(map(str,e.errors()[0]['loc']))}'"
        except Exception:
            error_details = "Check logs."
        yield from _yield_streaming_error(
            f"[AI Error: Internal data format error. {error_details}]"
        )
    except DeadlineExceeded:
        logger.error(f"Streaming Gemini API call timed out for chat {chat_id}.")
        yield from _yield_streaming_error(
            "[AI Error: The request timed out. Please try again.]"
        )
    except NotFound as e:
        raw_model_name = current_app.config.get(
            "PRIMARY_MODEL", current_app.config["DEFAULT_MODEL"]
        )
        logger.error(f"Model for streaming chat {chat_id} not found: {e}")
        yield from _yield_streaming_error(
            f"[AI Error: Model '{raw_model_name}' not found or access denied.]"
        )
    except GoogleAPIError as e:
        logger.error(
            f"Google API error for streaming chat {chat_id}: {e}", exc_info=False
        )
        err_str = str(e).lower()
        error_message = f"[AI API Error: {type(e).__name__}]"  # Default
        if "api key not valid" in err_str:
            error_message = "[Error: Invalid Gemini API Key]"
        elif "permission denied" in err_str:
            error_message = (
                f"[AI Error: Permission denied for model. Check API key permissions.]"
            )
        elif "resource has been exhausted" in err_str or "429" in str(e):
            logger.warning(f"Quota/Rate limit hit for streaming chat {chat_id}.")
            error_message = (
                "[AI Error: API quota or rate limit exceeded. Please try again later.]"
            )
        elif "prompt was blocked" in err_str or "SAFETY" in str(e).upper():
            logger.warning(
                f"API error indicates safety block for streaming chat {chat_id}: {e}"
            )
            error_message = f"[AI Safety Error: Request or response blocked due to safety settings (Reason: SAFETY)]"
        elif "internal error" in err_str or "500" in str(e):
            logger.error(
                f"Internal server error from Gemini API for streaming chat {chat_id}: {e}"
            )
            error_message = "[AI Error: The AI service encountered an internal error.]"
        yield from _yield_streaming_error(error_message)
    except Exception as e:
        # This catches errors during the iteration over `response_iterator` as well
        logger.error(
            f"Unexpected error during streaming Gemini API interaction for chat {chat_id}: {e}",
            exc_info=True,
        )
        yield from _yield_streaming_error(f"[Unexpected AI Error: {type(e).__name__}]")
    finally:
        # Ensure cleanup happens even if the generator isn't fully consumed
        _cleanup_temp_files(temp_files_to_clean, f"streaming chat {chat_id}")


# --- Helper Function to Prepare History and Content Parts ---
def _prepare_chat_content(
    client,
    chat_id,
    user_message,
    attached_files,
    session_files,
    calendar_context,
    web_search_enabled,
):
    """Prepares history list and current turn parts list. Returns (history, parts, temp_files) or (error_string, None, None)."""
    logger.info(f"Preparing content for chat {chat_id}")
    history = []
    current_turn_parts = []
    temp_files_to_clean = []

    # --- Fetch History ---
    try:
        history_data = database.get_chat_history_from_db(chat_id)
        history = []
        for msg in history_data:
            role = "user" if msg["role"] == "user" else "model"
            if msg.get("content"):
                history.append(Content(role=role, parts=[Part(text=msg["content"])]))
            else:
                logger.warning(
                    f"Skipping history message with empty content for chat {chat_id}: Role={role}"
                )
        logger.info(f"Prepared {len(history)} history turns for chat {chat_id}.")

        # Ensure history starts with 'user' if not empty
        if history and history[0].role != "user":
            logger.warning(
                f"Chat history for {chat_id} does not start with user. Removing leading non-user messages."
            )
            while history and history[0].role != "user":
                history.pop(0)

    except Exception as e:
        logger.error(
            f"Failed to fetch/prepare history for chat {chat_id}: {e}", exc_info=True
        )
        return (
            "[Error: Could not load or prepare chat history]",
            None,
            None,
        )  # Return error string

    # --- Prepare Current Turn Parts ---
    # Wrap the rest in try/except to catch errors during part preparation
    try:
        # 1. Calendar Context
        if calendar_context:
            current_turn_parts.extend(
                [
                    Part(text="--- Start Calendar Context ---"),
                    Part(text=calendar_context),
                    Part(text="--- End Calendar Context ---"),
                ]
            )

        # 2. Attached Files (DB)
        if attached_files:
            logger.info(
                f"Processing {len(attached_files)} attached files for chat {chat_id}."
            )
            for file_detail in attached_files:
                # ... (Existing logic for attached files - summary/full) ...
                # Ensure this logic appends Parts or FileDataParts to current_turn_parts
                # and adds temp file paths to temp_files_to_clean
                file_id = file_detail.get("id")
                attachment_type = file_detail.get("type")
                frontend_filename = file_detail.get("filename", "Unknown File")
                logger.debug(
                    f"Processing attached file: ID={file_id}, Type={attachment_type}, Name={frontend_filename}"
                )

                if file_id is None or attachment_type is None:
                    logger.warning(
                        f"Skipping invalid attached file detail: {file_detail}"
                    )
                    current_turn_parts.append(
                        Part(text=f"[System: Skipped invalid attached file detail.]")
                    )
                    continue
                try:
                    db_file_details = database.get_file_details_from_db(
                        file_id, include_content=True
                    )
                    if not db_file_details or not db_file_details.get("content"):
                        logger.warning(
                            f"Could not get details/content for attached file_id {file_id} ('{frontend_filename}') in chat {chat_id}."
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Error retrieving attached file '{frontend_filename}']"
                            )
                        )
                        continue

                    filename = db_file_details["filename"]
                    mimetype = db_file_details["mimetype"]
                    content_blob = db_file_details["content"]

                    if attachment_type == "summary":
                        summary = get_or_generate_summary(file_id)
                        current_turn_parts.append(
                            Part(
                                text=f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                            )
                        )
                    elif attachment_type == "full":
                        supported_mimetypes = (
                            "image/",
                            "audio/",
                            "video/",
                            "application/pdf",
                            "text/",
                        )  # Simplified check
                        if mimetype.startswith(supported_mimetypes):
                            try:
                                with tempfile.NamedTemporaryFile(
                                    delete=False, suffix=f"_{secure_filename(filename)}"
                                ) as temp_file:
                                    temp_file.write(content_blob)
                                    temp_filepath = temp_file.name
                                    temp_files_to_clean.append(temp_filepath)
                                uploaded_file = client.files.upload(
                                    file=temp_filepath,
                                    config={
                                        "display_name": filename,
                                        "mime_type": mimetype,
                                    },
                                )
                                # Create a Part with FileData referencing the uploaded file URI
                                file_data_part = Part(
                                    file_data=FileData(
                                        mime_type=mimetype, file_uri=uploaded_file.uri
                                    )
                                )
                                current_turn_parts.append(file_data_part)
                                logger.info(
                                    f"Attached DB file '{filename}' via File API using URI: {uploaded_file.uri}"
                                )
                            except Exception as upload_err:
                                logger.error(
                                    f"Failed to upload attached DB file '{filename}': {upload_err}",
                                    exc_info=True,
                                )
                                current_turn_parts.append(
                                    Part(
                                        text=f"[System: Error uploading attached file '{filename}'. {type(upload_err).__name__}]"
                                    )
                                )
                        else:
                            logger.warning(
                                f"Full content attachment via File API not supported for DB file mimetype: {mimetype}"
                            )
                            current_turn_parts.append(
                                Part(
                                    text=f"[System: Full content attachment not supported for file '{filename}' ({mimetype}).]"
                                )
                            )
                    else:
                        logger.warning(
                            f"Unknown attachment type '{attachment_type}' for file '{filename}'."
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Unknown attachment type '{attachment_type}'.]"
                            )
                        )

                except Exception as file_proc_err:
                    logger.error(
                        f"Error processing attached file_id {file_id} ('{frontend_filename}'): {file_proc_err}",
                        exc_info=True,
                    )
                    current_turn_parts.append(
                        Part(
                            text=f"[System: Error processing attached file '{frontend_filename}'.]"
                        )
                    )

        # 3. Session Files (Base64)
        if session_files:
            logger.info(
                f"Processing {len(session_files)} session files for chat {chat_id}."
            )
            for session_file_detail in session_files:
                # ... (Existing logic for session files) ...
                # Ensure this logic appends Parts or FileDataParts to current_turn_parts
                # and adds temp file paths to temp_files_to_clean
                filename = session_file_detail.get("filename", "Unknown Session File")
                mimetype = session_file_detail.get("mimetype")
                content_base64 = session_file_detail.get("content")
                logger.debug(
                    f"Processing session file: {filename}, Mimetype: {mimetype}"
                )

                if not filename or not mimetype or not content_base64:
                    logger.warning(
                        f"Skipping invalid session file detail: {filename or 'No Name'}"
                    )
                    current_turn_parts.append(
                        Part(
                            text=f"[System: Skipped invalid session file detail '{filename or 'No Name'}'.]"
                        )
                    )
                    continue
                try:
                    if "," in content_base64:
                        _, base64_string = content_base64.split(",", 1)
                    else:
                        base64_string = content_base64
                    content_blob = base64.b64decode(base64_string)

                    supported_mimetypes = (
                        "image/",
                        "audio/",
                        "video/",
                        "application/pdf",
                        "text/",
                    )  # Simplified check for inline data support
                    if mimetype.startswith(supported_mimetypes):
                        # Create an inline data Part directly using Blob
                        inline_part = Part(
                            inline_data=Blob(mime_type=mimetype, data=content_blob)
                        )
                        current_turn_parts.append(inline_part)
                        logger.info(
                            f"Attached session file '{filename}' ({mimetype}) as inline data."
                        )
                    else:
                        logger.warning(
                            f"Session file attachment as inline data not supported for mimetype: {mimetype}"
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Session file attachment not supported for file '{filename}' ({mimetype}).]"
                            )
                        )

                except base64.BinasciiError as b64_err:
                    logger.error(
                        f"Base64 decoding failed for session file '{filename}': {b64_err}"
                    )
                    current_turn_parts.append(
                        Part(
                            text=f"[System: Error decoding session file '{filename}'.]"
                        )
                    )
                except Exception as file_proc_err:
                    logger.error(
                        f"Error processing session file '{filename}': {file_proc_err}",
                        exc_info=True,
                    )
                    current_turn_parts.append(
                        Part(
                            text=f"[System: Error processing session file '{filename}'.]"
                        )
                    )

        # 4. Web Search
        if web_search_enabled:
            logger.info(f"Web search enabled for chat {chat_id}. Generating query...")
            search_query = generate_search_query(user_message)
            if search_query:
                logger.info(f"Performing web search for query: '{search_query}'")
                search_results_list = perform_web_search(search_query) # Returns list of dicts

                if search_results_list:
                    logger.info(f"Received {len(search_results_list)} search results.")
                    current_turn_parts.append(Part(text="--- Start Web Search Results ---"))

                    for i, result_item in enumerate(search_results_list):
                        title = result_item.get('title', 'No Title')
                        link = result_item.get('link', 'No Link')
                        snippet = result_item.get('snippet', 'No Snippet')
                        fetch_result = result_item.get('fetch_result', {})
                        result_type = fetch_result.get('type', 'error')
                        result_content = fetch_result.get('content', 'Unknown error')

                        # Add text part describing the result source
                        # This text part serves as the citation reference point for the AI
                        current_turn_parts.append(Part(text=f"[{i+1}] Title: {title}\n   Link: {link}\n   Snippet: {snippet}"))

                        # Process based on fetched content type
                        if result_type == 'html':
                            if result_content:
                                current_turn_parts.append(Part(text=f"   Content:\n{result_content}\n---"))
                            else:
                                current_turn_parts.append(Part(text="   Content: [Could not extract text content.]\n---"))
                        elif result_type == 'pdf':
                            # perform_web_search already called fetch_web_content,
                            # so result_content should contain the PDF bytes.
                            if isinstance(result_content, bytes):
                                pdf_bytes = result_content
                                pdf_filename = fetch_result.get('filename', f'search_result_{i+1}.pdf')
                                logger.info(f"Attempting to transcribe PDF search result: {pdf_filename} ({len(pdf_bytes)} bytes)")

                                # Call the transcription function
                                transcription_result = transcribe_pdf_bytes(pdf_bytes, pdf_filename)

                                # Check if transcription was successful or returned an error string
                                if transcription_result.startswith(("[Error", "[System Note", "[AI Error")):
                                    logger.warning(f"PDF transcription failed for web search result {pdf_filename}: {transcription_result}")
                                    # Append error/note about transcription failure
                                    current_turn_parts.append(Part(text=f"   Content: [Transcription Failed for PDF '{pdf_filename}': {transcription_result}]\n---"))
                                else:
                                    logger.info(f"Successfully transcribed PDF from web search: {pdf_filename}")
                                    # Append transcribed text
                                    current_turn_parts.append(Part(text=f"   Content (Transcribed from PDF '{pdf_filename}'):\n{transcription_result.strip()}\n---"))
                            else:
                                logger.error(f"Expected bytes for PDF content from web search result {i+1}, but got {type(result_content)}. Link: {link}")
                                current_turn_parts.append(Part(text=f"   Content: [System Error: Expected PDF bytes but received different type for link {link}]\n---"))

                        elif result_type == 'error':
                            # This handles errors reported by fetch_web_content within perform_web_search
                            current_turn_parts.append(Part(text=f"   Content: [Error fetching content: {result_content}]\n---"))
                        else: # Handle other unexpected types
                            logger.warning(f"Unknown fetch result type '{result_type}' for link {link}")
                            current_turn_parts.append(Part(text=f"   Content: [Unknown content type: {result_type}]\n---"))

                    current_turn_parts.append(Part(text="--- End Web Search Results ---"))
                else:
                    logger.info("Web search performed, but returned no results.")
                    current_turn_parts.append(Part(text="[System Note: Web search performed, no results found.]"))
            else:
                logger.info("Web search was enabled, but no search query was generated.")
                current_turn_parts.append(Part(text="[System Note: Web search enabled, but failed to generate a query.]"))

        # 5. User Message
        if user_message:
            current_turn_parts.append(Part(text=user_message))
        elif not current_turn_parts:  # Only add placeholder if nothing else was added
            current_turn_parts.append(
                Part(text="[User provided no text, only attachments or context.]")
            )
        if web_search_enabled:
            # Update prompt instructions to reflect attached PDFs
            current_turn_parts.extend([
                Part(text="--- special instructions ---"),
                Part(
                    text="""When responding, prioritize using information from the provided web search results (both text snippets and attached PDF documents) to ensure accuracy and up-to-dateness.

If information from the web search results is used to answer a question:
*   For text content: Cite the source using bracketed numerical citations (e.g., [1], [2]) directly after the relevant statement.
*   For PDF documents: Refer to the attached document explicitly (e.g., "According to the attached PDF document from source [3]..."). Do NOT attempt to summarize the PDF unless specifically asked to.

At the end of your response, include a list of the cited sources, formatted as follows, noting the markdown-style links:

[1] [First Source Title](https://www.the.first.source.com) - "A quote from the source that was used.."
[2] [Other Source Title](https://www.the.other.source.com) - "A snippet from the source **and a specific important word** from that source"
[3] [PDF Source Title](https://www.pdf.example.com) - [Attached PDF Document]
"""
                ),
                Part(text="--- End special instructions ---"),
           ] )

        logger.info(
            f"Prepared {len(current_turn_parts)} current turn parts for chat {chat_id}."
        )
        return history, current_turn_parts, temp_files_to_clean

    except Exception as prep_err:
        logger.error(
            f"Unexpected error preparing content parts for chat {chat_id}: {prep_err}",
            exc_info=True,
        )
        return (
            f"[Error: Failed to prepare content for AI ({type(prep_err).__name__})]",
            None,
            None,
        )


# --- Helper Function to Clean Up Temporary Files ---
def _cleanup_temp_files(temp_files: list, context_msg: str):
    """Safely removes a list of temporary files."""
    if temp_files:
        logger.info(
            f"Cleaning up {len(temp_files)} temporary files for {context_msg}..."
        )
        for temp_path in temp_files:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.debug(f"Removed temp file: {temp_path}")
                else:
                    logger.debug(f"Temp file not found, already removed? {temp_path}")
            except OSError as e:
                logger.warning(f"Error removing temp file {temp_path}: {e}")
        logger.info(f"Finished cleaning temp files for {context_msg}.")


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
        "SUMMARY_MODEL", current_app.config["DEFAULT_MODEL"]
    )
    model_to_use = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )

    prompt = f"""
    You are a skilled technical writer whose role is to format audio transcriptions into well-structured Markdown documents while preserving *as much detail as possible*. Your focus is on formatting, *not summarizing unless absolutely necessary*.

*   **Headings:** Identify all distinct topics and subtopics in the transcript and create corresponding headings and subheadings (using #, ##, ###, etc.). Headings should be descriptive but concise.

*   **Bullet Points (Detailed):** Extract key points, examples, arguments, and supporting details and represent them as bullet points (* or -). *Each bullet point should contain enough information to be understood independently.* Avoid overly concise summaries that lose important nuances.

*   **Numbered Lists:** Accurately format all numbered lists, steps, or sequences from the transcript as numbered lists (1., 2., 3., etc.). Do not omit steps or details.

*   **Order Preservation:** Maintain the original order of topics, bullet points, and numbered list items as closely as possible. Only reorder if the original order is demonstrably illogical.

*   **Limited Filler Removal:** Remove filler words (um, uh, okay, you know, etc.) *only if their removal does not alter the meaning or clarity of the sentence*. In some cases, these words may convey emphasis or tone, which should be preserved.

*   **Verbatim Phrases (When Appropriate):** If a particular phrase or sentence is especially well-articulated or insightful, consider including it verbatim (within quotation marks) as a bullet point or within the text.

*   **Markdown Output Only:** Provide the complete Markdown document as the sole output.

Here is the transcribed speech:
    {raw_transcript}
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


# --- Note Diff Summary Generation ---
def generate_note_diff_summary(version_1_content: str, version_2_content: str) -> str:
    """
    Uses an LLM to generate a concise summary of the differences between two versions of a note.
    """
    logger.info("Entering generate_note_diff_summary.")

    # --- AI Readiness Check ---
    try:
        try:
            _ = current_app.config
            logger.debug("generate_note_diff_summary: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "generate_note_diff_summary called outside active Flask context.",
                exc_info=True,
            )
            return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY missing for generate_note_diff_summary.")
            return "[Error: AI Service API Key not configured]"

        try:
            if "genai_client" not in g:
                logger.info("Creating new genai.Client for generate_note_diff_summary.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug(
                    "Using cached genai.Client for generate_note_diff_summary."
                )
            client = g.genai_client
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to get genai.Client for diff summary: {e}", exc_info=True
            )
            if "api key not valid" in str(e).lower():
                return "[Error: Invalid Gemini API Key]"
            return "[Error: Failed to initialize AI client]"

    except Exception as e:
        logger.error(
            f"Unexpected error during readiness check for diff summary: {e}",
            exc_info=True,
        )
        return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
    # --- End AI Readiness Check ---

    # Determine model (use default or summary model)
    raw_model_name = current_app.config.get(
        "SUMMARY_MODEL", current_app.config["DEFAULT_MODEL"]
    )
    model_to_use = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )

    prompt = f"""Provide a concise summary of the changes made in Version 2 of the note below, compared to Version 1. Focus on the key differences.

Version 1:
{version_1_content}

Version 2:
{version_2_content}

Summary of Changes:"""

    logger.info(f"Attempting note diff summary using model '{model_to_use}'...")
    response = None
    try:
        # Use non-streaming generation
        response = client.models.generate_content(
            model=model_to_use,
            contents=prompt,
        )

        # Process response
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            logger.warning(
                f"Note diff summary blocked by safety settings. Reason: {reason}"
            )
            return f"[Error: Diff summary generation blocked due to safety settings (Reason: {reason})]"

        if (
            response.candidates
            and hasattr(response.candidates[0], "content")
            and hasattr(response.candidates[0].content, "parts")
            and response.candidates[0].content.parts
        ):
            diff_summary = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            ).strip()

            if diff_summary:
                logger.info("Note diff summary generated successfully.")
                return diff_summary
            else:
                logger.warning("Note diff summary generation resulted in empty text.")
                return "[System Note: AI generated an empty diff summary.]"
        else:
            logger.warning(
                f"Note diff summary generation did not produce usable content. Response: {response!r}"
            )
            finish_reason = "UNKNOWN"
            if response.candidates and hasattr(response.candidates[0], "finish_reason"):
                finish_reason = response.candidates[0].finish_reason.name
            return f"[Error: AI did not generate diff summary content (Finish Reason: {finish_reason})]"

    except InvalidArgument as e:
        logger.error(
            f"InvalidArgument error during note diff summary generation: {e}.",
            exc_info=True,
        )
        return f"[AI Error: Invalid argument ({type(e).__name__}).]"
    except NotFound:
        return f"[Error: Model '{model_to_use}' not found for diff summary]"
    except GoogleAPIError as e:
        logger.error(f"API error during note diff summary generation: {e}")
        if "api key not valid" in str(e).lower():
            return "[Error: Invalid Gemini API Key]"
        if "resource has been exhausted" in str(e).lower() or "429" in str(e):
            return "[Error: API quota or rate limit exceeded. Please try again later.]"
        return f"[AI API Error: {type(e).__name__}]"
    except Exception as e:
        logger.error(
            f"Unexpected error during note diff summary generation: {e}", exc_info=True
        )
        return f"[Unexpected AI Error: {type(e).__name__}]"


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
                Part(text=prompt),
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
        logger.error(
            f"Google API error during PDF transcription for '{filename}': {e}"
        )
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
                    logger.info(f"Cleaned up temp transcription file: {temp_file_to_clean}")
            except OSError as e:
                logger.warning(
                    f"Error removing temp transcription file {temp_file_to_clean}: {e}"
                )


# --- Standalone Text Generation (Example) ---
# Remove the decorator
def generate_text(prompt: str, model_name: str = None) -> str:
    """Generates text using a specified model or the default."""
    logger.info("Entering generate_text.")

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
            _ = (
                current_app.config
            )  # Simple check that raises RuntimeError if no context
            logger.debug("generate_text: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "generate_text called outside of active Flask app/request context.",
                exc_info=True,  # Log traceback
            )
            return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return "[Error: AI Service API Key not configured]"

        try:
            # Use client caching via Flask's 'g' object if in request context
            if "genai_client" not in g:
                logger.info("Creating new genai.Client and caching in 'g'.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client from 'g'.")
            client = g.genai_client
            logger.info("Successfully obtained genai.Client for text generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to initialize/get genai.Client for text: {e}", exc_info=True
            )
            if "api key not valid" in str(e).lower():
                return "[Error: Invalid Gemini API Key]"
            return "[Error: Failed to initialize AI client]"

    except Exception as e:
        # Catch any unexpected errors during the readiness check itself
        logger.error(
            f"generate_text: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
    # --- End AI Readiness Check ---

    if not model_name:
        raw_model_name = current_app.config["DEFAULT_MODEL"]
        model_to_use = (
            f"models/{raw_model_name}"
            if not raw_model_name.startswith("models/")
            else raw_model_name
        )
    else:
        model_to_use = (
            f"models/{model_name}"
            if not model_name.startswith("models/")
            else model_name
        )

    logger.info(f"Generating text with model '{model_to_use}'...")
    response = None  # Initialize
    try:
        # Use the client.models attribute for simple generation
        # Standalone text generation is NOT streamed
        response = client.models.generate_content(
            model=model_to_use,
            contents=prompt,
        )

        # Process response similar to non-streaming chat
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            logger.warning(
                f"Text generation blocked by safety settings. Reason: {reason}"
            )
            return f"[Error: Text generation blocked due to safety settings (Reason: {reason})]"

        if (
            response.candidates
            and hasattr(response.candidates[0], "content")
            and hasattr(response.candidates[0].content, "parts")
            and response.candidates[0].content.parts
        ):
            text_reply = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if hasattr(part, "text")
            )
            if text_reply.strip():
                return text_reply
            else:
                logger.warning("Text generation resulted in empty text content.")
                return "[System Note: AI generated empty text.]"
        else:
            logger.warning(
                f"Text generation did not produce usable content. Response: {response!r}"
            )
            finish_reason = "UNKNOWN"
            if response.candidates and hasattr(response.candidates[0], "finish_reason"):
                finish_reason = response.candidates[0].finish_reason.name
            return f"[Error: AI did not generate text content (Finish Reason: {finish_reason})]"

    except InvalidArgument as e:
        logger.error(
            f"InvalidArgument error during text generation: {e}.", exc_info=True
        )
        return f"[AI Error: Invalid argument ({type(e).__name__}).]"
    except NotFound:
        return f"[Error: Model '{model_to_use}' not found]"
    except GoogleAPIError as e:
        # Simplified error handling for this example
        logger.error(f"API error during text generation: {e}")
        if "api key not valid" in str(e).lower():
            return "[Error: Invalid Gemini API Key]"
        # Add other common checks if needed (quota, etc.)
        return f"[AI API Error: {type(e).__name__}]"
    except Exception as e:
        logger.error(f"Unexpected error during text generation: {e}", exc_info=True)
        return f"[Unexpected AI Error: {type(e).__name__}]"
