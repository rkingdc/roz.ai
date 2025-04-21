# app/ai_services.py
import google.genai as genai  # Use the new SDK
from google.genai.types import GenerationConfig, Part, Content
from flask import current_app, g  # Import g for request context caching
import tempfile
import os
import re
import base64
from . import database
from .plugins.web_search import perform_web_search
from google.api_core.exceptions import (
    GoogleAPIError,
    DeadlineExceeded,
    ClientError,
    NotFound,
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
# gemini_api_key_present = False
# def configure_gemini(app): ... # Remove this function

# --- Helper Functions for Client Instantiation ---
# Remove _get_api_key and get_gemini_client functions
# def _get_api_key(): ... # Remove this function
# def get_gemini_client(): ... # Remove this function


# --- Decorator for AI Readiness Check ---
# Remove the entire decorator function
# def ai_ready_required(f): ... # Remove this function


# --- Summary Generation ---
# Remove the decorator
# @ai_ready_required
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
             _ = current_app.config # Simple check that raises RuntimeError if no context
             logger.debug("generate_summary: Flask request context is active.")
        except RuntimeError:
             logger.error(
                 "generate_summary called outside of active Flask request context.",
                 exc_info=True # Log traceback
             )
             return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return "[Error: AI Service API Key not configured]"

        try:
            client = genai.Client(api_key=api_key)
            logger.info("Successfully created genai.Client for summary generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(f"Failed to initialize genai.Client for summary: {e}", exc_info=True)
            # Check for invalid key specifically
            if "api key not valid" in str(e).lower():
                 # We can't use g here reliably if called outside request context,
                 # but the API call itself will fail anyway. Just return the error.
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
        elif mimetype.startswith(("image/", "audio/", "video/", "application/pdf")):
            try:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{secure_filename(filename)}"
                ) as temp_file:
                    temp_file.write(content_blob)
                    temp_filepath = temp_file.name
                    temp_file_to_clean = temp_filepath
                logger.info(
                    f"Uploading temp file '{temp_filepath}' for summary generation..."
                )
                # Use the client's file upload method (client.files.upload)
                uploaded_file = client.files.upload(
                    file=temp_filepath,
                    config={"display_name": filename},
                )
                # Construct parts including the prompt (as Part) and the uploaded file reference
                content_parts = [
                    Part(text=prompt),
                    uploaded_file,
                ]  # Wrap prompt, keep file object
                logger.info(
                    f"File '{filename}' uploaded for summary, URI: {uploaded_file.uri}"
                )
            except Exception as upload_err:
                logger.error(
                    f"Error preparing/uploading file for summary: {upload_err}",
                    exc_info=True,
                )
                # Check for invalid key specifically during upload
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
            contents=content_parts,  # Pass the constructed parts/contents
            stream=False,  # Summary generation is not streamed
        )
        summary = response.text
        logger.info(f"Summary generated successfully for '{filename}'.")
        return summary

    # --- Error Handling for API Call ---
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
            # No need to set g.gemini_api_key_invalid anymore
            return "[Error: Invalid Gemini API Key]"
        if "prompt was blocked" in err_str or "SAFETY" in str(
            e
        ):  # Broader safety check
            feedback_reason = "N/A"
            try:
                if (
                    response
                    and hasattr(response, "prompt_feedback")
                    and response.prompt_feedback
                ):
                    feedback_reason = response.prompt_feedback.block_reason
            except Exception:
                pass
            logger.warning(
                f"Summary generation blocked by safety settings for {filename}. Reason: {feedback_reason}"
            )
            return f"[Error: Summary generation blocked due to safety settings (Reason: {feedback_reason})]"
        if "resource has been exhausted" in err_str or "429" in err_str:
            logger.warning(
                f"Quota/Rate limit hit during summary generation for {filename}."
            )
            return "[Error: API quota or rate limit exceeded. Please try again later.]"
        return f"[Error generating summary via API: {type(e).__name__}]"
    except Exception as e:
        logger.error(
            f"Unexpected error during summary generation for '{filename}': {e}",
            exc_info=True,
        )
        return f"[Error generating summary: An unexpected error occurred ({type(e).__name__}).]"
    finally:
        if temp_file_to_clean:
            try:
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
                "[Error"
            )  # Check if it's not an old error message
        ):
            logger.info(f"Retrieved existing summary for file ID: {file_id}")
            return file_details["summary"]
        else:
            logger.info(f"Generating summary for file ID: {file_id}...")
            # Call the refactored function (which now handles its own readiness)
            new_summary = generate_summary(file_id)

            # Only save if generation was successful (doesn't start with "[Error")
            if isinstance(new_summary, str) and not new_summary.startswith("[Error"):
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
                # If generation failed, return the error message directly
                logger.warning(
                    f"Summary generation failed for file ID {file_id}: {new_summary}"
                )
                # Optionally save the error state to prevent retries?
                # database.save_summary_in_db(file_id, new_summary) # Uncomment to save errors
                return new_summary
    except Exception as e:
        logger.error(
            f"Error in get_or_generate_summary for file ID {file_id}: {e}",
            exc_info=True,
        )
        return f"[Error retrieving or generating summary: {type(e).__name__}]"


# --- Generate Search Query ---
# Remove the decorator
# @ai_ready_required
def generate_search_query(user_message: str, max_retries=1) -> str | None:
    """
    Uses the default LLM via client to generate a concise web search query.
    """
    logger.info("Entering generate_search_query.")

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
             _ = current_app.config # Simple check that raises RuntimeError if no context
             logger.debug("generate_search_query: Flask request context is active.")
        except RuntimeError:
             logger.error(
                 "generate_search_query called outside of active Flask request context.",
                 exc_info=True # Log traceback
             )
             return None # Return None as expected by the caller

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return None # Return None as expected by the caller

        try:
            client = genai.Client(api_key=api_key)
            logger.info("Successfully created genai.Client for query generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(f"Failed to initialize genai.Client for query: {e}", exc_info=True)
            if "api key not valid" in str(e).lower():
                 return None # Return None
            return None # Return None

    except Exception as e:
        # Catch any unexpected errors during the readiness check itself
        logger.error(
            f"generate_search_query: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        return None # Return None as expected by the caller
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
                contents=prompt,  # Simple text prompt
                stream=False,  # Not streamed
            )

            # Check for blocked prompt before accessing text
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(
                    f"Prompt blocked for query gen, reason: {response.prompt_feedback.block_reason}"
                )
                return None  # Don't retry if blocked

            generated_query = response.text.strip()

            # Clean the generated query
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
                logger.warning("LLM generated an empty search query after cleaning.")
                # Don't retry empty query, likely a model issue
                return None

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
                # No need to set g.gemini_api_key_invalid anymore
                logger.error(
                    "API key invalid during search query generation. Aborting."
                )
                return None  # Don't retry if key is invalid
            if "resource has been exhausted" in err_str or "429" in err_str:
                logger.warning("Quota/Rate limit hit during query generation.")
                # Could implement backoff here, but for now just retry once if allowed
                retries += 1
            elif "prompt was blocked" in err_str or "SAFETY" in str(e):
                # Attempt to get feedback if available on the response object
                feedback_reason = "N/A"
                try:
                    if (
                        response
                        and hasattr(response, "prompt_feedback")
                        and response.prompt_feedback
                    ):
                        feedback_reason = response.prompt_feedback.block_reason
                except Exception:
                    pass
                logger.warning(
                    f"Query generation blocked by safety settings. Reason: {feedback_reason}"
                )
                return None  # Don't retry if blocked by safety
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


# --- Chat Response Generation ---
# Remove the decorator
# @ai_ready_required
def generate_chat_response(
    chat_id,
    user_message,
    attached_files=None,
    session_files=None,
    calendar_context=None,
    web_search_enabled=False,
    streaming_enabled=False,
):
    """
    Generates a chat response using the Gemini API via the client,
    incorporating history, context, file summaries, and optional web search.
    Handles potential errors gracefully.
    Uses the NEW google.genai library structure (client-based).
    Supports streaming responses if streaming_enabled is True.
    """
    logger.info(
        f"Entering generate_chat_response (generator body starts here) for chat {chat_id}. Streaming: {streaming_enabled}"
    )

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
             _ = current_app.config # Simple check that raises RuntimeError if no context
             logger.debug("generate_chat_response: Flask request context is active.")
        except RuntimeError:
             logger.error(
                 "generate_chat_response called outside of active Flask request context.",
                 exc_info=True # Log traceback
             )
             error_msg = "[Error: AI Service called outside request context]"
             if streaming_enabled:
                 yield error_msg
                 return # Stop generator
             else:
                 return error_msg

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            error_msg = "[Error: AI Service API Key not configured]"
            if streaming_enabled:
                yield error_msg
                return # Stop generator
            else:
                return error_msg

        try:
            client = genai.Client(api_key=api_key)
            logger.info("Successfully created genai.Client for chat response.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(f"Failed to initialize genai.Client for chat: {e}", exc_info=True)
            error_msg = "[Error: Failed to initialize AI client]"
            # Check for invalid key specifically
            if "api key not valid" in str(e).lower():
                 error_msg = "[Error: Invalid Gemini API Key]"
                 # No need to set g.gemini_api_key_invalid anymore
            if streaming_enabled:
                yield error_msg
                return # Stop generator
            else:
                return error_msg

    except Exception as e:
        # Catch any unexpected errors during the readiness check itself
        logger.error(
            f"generate_chat_response: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        error_msg = f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
        if streaming_enabled:
            yield error_msg
            return # Stop generator
        else:
            return error_msg
    # --- End AI Readiness Check ---


    # Add a try...except block around the main logic to catch early errors
    # This outer block remains to catch errors *before* the inner try/finally
    try:
        # --- Determine Model ---
        raw_model_name = current_app.config.get(
            "PRIMARY_MODEL", current_app.config["DEFAULT_MODEL"]
        )
        model_to_use = (
            f"models/{raw_model_name}"
            if not raw_model_name.startswith("models/")
            else raw_model_name
        )
        logger.info(f"Primary model for chat {chat_id} response: '{model_to_use}'.")

        # --- Fetch History ---
        logger.info(f"Fetching history for chat {chat_id}...")
        history = []
        try:
            history_data = database.get_chat_history_from_db(chat_id)
            history = []  # Re-initialize history list
            for msg in history_data:
                # Ensure roles are 'user' or 'model' for the API
                # The API expects 'user' and 'model' roles, not 'assistant'
                role = "user" if msg["role"] == "user" else "model"
                history.append(Content(role=role, parts=[Part(text=msg["content"])]))
            logger.info(f"Fetched {len(history)} history turns for chat {chat_id}.")
            logger.info(f"History prepared for API: {history}")

            # Ensure history starts with 'user' role for the API
            # The API expects alternating user/model turns starting with user.
            # If the history is not empty and the first message is not 'user',
            # it indicates an issue with the history structure for the API.
            # The SDK's chat.send_message handles the current turn's role implicitly
            # based on the history provided. We just need to ensure the history list
            # itself is correctly formatted (alternating roles, starting with user).
            # The DB query should return history in chronological order.
            # If the very first message in the DB is 'assistant', something is wrong.
            # Let's check the *first* message role.
            if history and history[0].role != "user":
                logger.error(
                    f"Chat history for {chat_id} does not start with a user turn. First role: {history[0].role}. This may cause API errors."
                )
                # We won't attempt to fix the history here, as it might corrupt the chat.
                # The API call might fail, which will be caught below.

        except Exception as e:
            logger.error(
                f"Failed to fetch history for chat {chat_id}: {e}", exc_info=True
            )
            error_msg = "[Error: Could not load chat history]"
            if streaming_enabled:
                yield error_msg
                return  # Stop generator
            else:
                return error_msg

        # --- Prepare Current Turn Parts ---
        current_turn_parts = []
        temp_files_to_clean = []

        # Use a try...finally block for temp file cleanup *around* the main logic
        try:
            logger.info(
                f"Preparing current turn parts for chat {chat_id}..."
            )
            # 1. Add Calendar Context (if provided)
            if calendar_context:
                logger.info(f"Adding calendar context to chat {chat_id} prompt.")
                current_turn_parts.extend(
                    [
                        Part(text="--- Start Calendar Context ---"),
                        Part(text=calendar_context),
                        Part(text="--- End Calendar Context ---"),
                    ]
                )
                logger.info(
                    f"Added calendar context. Current parts count: {len(current_turn_parts)}"
                )

            # 2. Process Attached Files (from DB by ID, with type)
            if attached_files:
                logger.info(
                    f"Processing {len(attached_files)} attached files (from DB) for chat {chat_id}."
                )
                for file_detail in attached_files:
                    file_id = file_detail.get("id")
                    attachment_type = file_detail.get("type")
                    frontend_filename = file_detail.get("filename", "Unknown File")

                    logger.info(
                        f"Processing attached file: {file_detail}"
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
                                f"Could not get details/content for attached file_id {file_id} in chat {chat_id}."
                            )
                            current_turn_parts.append(
                                Part(
                                    text=f"[System: Error retrieving attached file details for ID {file_id}]"
                                )
                            )
                            continue

                        filename = db_file_details["filename"]
                        mimetype = db_file_details["mimetype"]
                        content_blob = db_file_details["content"]

                        if attachment_type == "summary":
                            logger.info(
                                f"Getting summary for file {file_id} ('{filename}')."
                            )
                            summary = get_or_generate_summary(file_id)
                            current_turn_parts.append(
                                Part(
                                    text=f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                                )
                            )
                            logger.info(
                                f"Added summary for file {file_id}. Current parts count: {len(current_turn_parts)}"
                            )
                        elif attachment_type == "full":
                            logger.info(
                                f"Attaching full content for file {file_id} ('{filename}')."
                            )
                            if mimetype.startswith(
                                ("image/", "audio/", "video/", "application/pdf", "text/")
                            ):
                                logger.info(
                                    f"Attaching full content for '{filename}' ({mimetype}) for chat {chat_id}."
                                )
                                try:
                                    with tempfile.NamedTemporaryFile(
                                        delete=False, suffix=f"_{secure_filename(filename)}"
                                    ) as temp_file:
                                        temp_file.write(content_blob)
                                        temp_filepath = temp_file.name
                                        temp_files_to_clean.append(temp_filepath)
                                    logger.info(
                                        f"Created temp file: {temp_filepath}"
                                    )

                                    uploaded_file = client.files.upload(
                                        file=temp_filepath,
                                        config={"display_name": filename},
                                    )
                                    current_turn_parts.append(uploaded_file)
                                    logger.info(
                                        f"Successfully uploaded '{filename}' (URI: {uploaded_file.uri}) for chat {chat_id}."
                                    )
                                    logger.info(
                                        f"Added uploaded file {uploaded_file.uri}. Current parts count: {len(current_turn_parts)}"
                                    )
                                except Exception as upload_err:
                                    logger.error(
                                        f"Failed to upload attached file '{filename}' for chat {chat_id}: {upload_err}",
                                        exc_info=True,
                                    )
                                    current_turn_parts.append(
                                        Part(
                                            text=f"[System: Error uploading attached file '{filename}'. {type(upload_err).__name__}]"
                                        )
                                    )
                                    if "api key not valid" in str(upload_err).lower():
                                        # No need to set g.gemini_api_key_invalid anymore
                                        pass # Error message already added to parts
                            else:
                                logger.warning(
                                    f"Full content attachment not supported for mimetype: {mimetype} for file '{filename}' in chat {chat_id}."
                                )
                                current_turn_parts.append(
                                    Part(
                                        text=f"[System: Full content attachment not supported for file '{filename}' ({mimetype}).]"
                                    )
                                )
                        else:
                            logger.warning(
                                f"Unknown attachment type '{attachment_type}' for file '{filename}' in chat {chat_id}."
                            )
                            current_turn_parts.append(
                                Part(
                                    text=f"[System: Unknown attachment type '{attachment_type}' for file '{filename}'.]"
                                )
                            )

                    except Exception as file_proc_err:
                        logger.error(
                            f"Error processing attached file_id {file_id} for chat {chat_id}: {file_proc_err}",
                            exc_info=True,
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Error processing attached file ID {file_id}. {type(file_proc_err).__name__}]"
                            )
                        )
                logger.info(
                    f"Finished processing attached files. Total parts: {len(current_turn_parts)}"
                )

            # 3. Process Session Files (with content)
            if session_files:
                logger.info(
                    f"Processing {len(session_files)} session files (with content) for chat {chat_id}."
                )
                for session_file_detail in session_files:
                    filename = session_file_detail.get("filename", "Unknown Session File")
                    mimetype = session_file_detail.get("mimetype")
                    content_base64 = session_file_detail.get("content")

                    logger.info(
                        f"Processing session file: {session_file_detail.get('filename')}"
                    )

                    if not filename or not mimetype or not content_base64:
                        logger.warning(
                            f"Skipping invalid session file detail: {session_file_detail}"
                        )
                        current_turn_parts.append(
                            Part(text=f"[System: Skipped invalid session file detail.]")
                        )
                        continue

                    try:
                        # Decode base64 content. Handle potential data URL prefix (e.g., "data:image/png;base64,...")
                        if "," in content_base64:
                            header, base64_string = content_base64.split(",", 1)
                        else:
                            base64_string = content_base64

                        content_blob = base64.b64decode(base64_string)
                        logger.info(
                            f"Decoded session file content for '{filename}'."
                        )

                        # Session files are always treated as 'full' content attachments
                        if mimetype.startswith(
                            ("image/", "audio/", "video/", "application/pdf", "text/")
                        ):  # Include text for full upload
                            logger.info(
                                f"Attaching session file '{filename}' ({mimetype}) for chat {chat_id}."
                            )
                            try:
                                with tempfile.NamedTemporaryFile(
                                    delete=False, suffix=f"_{secure_filename(filename)}"
                                ) as temp_file:
                                    temp_file.write(content_blob)
                                    temp_filepath = temp_file.name
                                    temp_files_to_clean.append(
                                        temp_filepath
                                    )  # Add to cleanup list
                                logger.info(
                                    f"Created temp file for session file: {temp_filepath}"
                                )

                                uploaded_file = client.files.upload(
                                    file=temp_filepath,
                                    config={"display_name": filename},
                                )
                                current_turn_parts.append(uploaded_file)
                                logger.info(
                                    f"Successfully uploaded session file '{filename}' (URI: {uploaded_file.uri}) for chat {chat_id}."
                                )
                                logger.info(
                                    f"Added uploaded session file {uploaded_file.uri}. Current parts count: {len(current_turn_parts)}"
                                )
                            except Exception as upload_err:
                                logger.error(
                                    f"Failed to upload session file '{filename}' for chat {chat_id}: {upload_err}",
                                    exc_info=True,
                                )
                                current_turn_parts.append(
                                    Part(
                                        text=f"[System: Error uploading session file '{filename}'. {type(upload_err).__name__}]"
                                    )
                                )
                                if "api key not valid" in str(upload_err).lower():
                                    # No need to set g.gemini_api_key_invalid anymore
                                    pass # Error message already added to parts
                        else:
                            logger.warning(
                                f"Session file attachment not supported for mimetype: {mimetype} for file '{filename}' in chat {chat_id}."
                            )
                            current_turn_parts.append(
                                Part(
                                    text=f"[System: Session file attachment not supported for file '{filename}' ({mimetype}).]"
                                )
                            )

                    except Exception as file_proc_err:
                        logger.error(
                            f"Error processing session file '{filename}' for chat {chat_id}: {file_proc_err}",
                            exc_info=True,
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Error processing session file '{filename}'. {type(file_proc_err).__name__}]"
                            )
                        )
                logger.info(
                    f"Finished processing session files. Total parts: {len(current_turn_parts)}"
                )

            # 4. Perform Web Search (if enabled and seems appropriate)
            search_results = None
            if web_search_enabled:
                logger.info(f"Web search enabled for chat {chat_id}. Generating query...")
                # Pass streaming_enabled=False to generate_search_query as it's not streamed
                search_query = generate_search_query(user_message) # Removed streaming_enabled=False arg as it's not needed by generate_search_query anymore
                logger.info(
                    f"Generated search query: '{search_query}'"
                )
                if search_query:
                    logger.info(
                        f"Performing web search for chat {chat_id} with query: '{search_query}'"
                    )
                    search_results = perform_web_search(
                        search_query
                    )  # Assumes this returns a list of strings or None
                    logger.info(
                        f"Web search results: {search_results}"
                    )
                    if search_results:
                        logger.info(f"Adding web search results to chat {chat_id} prompt.")
                        current_turn_parts.extend(
                            [
                                Part(text="--- Start Web Search Results ---"),
                                *[Part(text=s) for s in search_results],
                                Part(text="--- End Web Search Results ---"),
                            ]
                        )
                        logger.info(
                            f"Added web search results. Current parts count: {len(current_turn_parts)}"
                        )
                    else:
                        logger.info(f"Web search yielded no results for chat {chat_id}.")
                        current_turn_parts.append(
                            Part(
                                text="[System Note: Web search was performed but returned no results.]"
                            )
                        )
                else:
                    logger.info(
                        f"Could not generate a suitable web search query for chat {chat_id}."
                    )
                    current_turn_parts.append(
                        Part(
                            text="[System Note: Web search was enabled but no query could be generated.]"
                        )
                    )
                logger.info(
                    f"Finished processing web search. Total parts: {len(current_turn_parts)}"
                )

            # 5. Add User's Text Message
            if user_message:
                logger.info(
                    f"Adding user message to parts for chat {chat_id}."
                )
                current_turn_parts.append(Part(text=user_message))
                logger.info(
                    f"Added user message. Current parts count: {len(current_turn_parts)}"
                )
            else:
                # Handle cases where maybe only files were sent?
                # If current_turn_parts is still empty, we might need a placeholder
                if not current_turn_parts:
                    logger.warning(
                        f"Chat {chat_id}: User message is empty and no files/context were added."
                    )
                    current_turn_parts.append(
                        Part(
                            text="[User provided no text, only attached files or context.]"
                        )
                    )
                    logger.info(
                        f"Added placeholder for empty user message. Current parts count: {len(current_turn_parts)}"
                    )

            logger.info(f"Current turn parts prepared for API: {current_turn_parts}")

            # --- Call Gemini API ---
            logger.info(
                f"Sending request to Gemini for chat {chat_id} with {len(history)} history turns and {len(current_turn_parts)} current parts. Streaming: {streaming_enabled}"
            )

            try:
                logger.info(
                    f"Creating chat session with model '{model_to_use}' and history."
                )
                chat_session = client.chats.create(model=model_to_use, history=history)
                logger.info(f"Chat session created: {chat_session}")

                logger.info(
                    f"Sending message to chat session with parts: {current_turn_parts}"
                )
                response = chat_session.send_message(
                    message=current_turn_parts, stream=streaming_enabled
                )
                logger.info(f"send_message call returned.")

                # --- Debugging Logs for Response ---
                logger.info(f"Gemini API raw response object: {response}")
                logger.info(f"Gemini API response object type: {type(response)}")
                if hasattr(response, "candidates"):
                    logger.info(f"Response has {len(response.candidates)} candidates.")
                    if response.candidates:
                        logger.info(
                            f"First candidate finish reason: {response.candidates[0].finish_reason}"
                        )
                        if (
                            hasattr(response.candidates[0], "content")
                            and response.candidates[0].content
                        ):
                            logger.info(
                                f"First candidate content parts: {len(response.candidates[0].content.parts)}"
                            )
                            if response.candidates[0].content.parts:
                                logger.info(
                                    f"First part type: {type(response.candidates[0].content.parts[0])}"
                                )
                                if hasattr(response.candidates[0].content.parts[0], "text"):
                                    logger.info(
                                        f"First part text length: {len(response.candidates[0].content.parts[0].text)}"
                                    )
                                else:
                                    logger.info("First part has no 'text' attribute.")
                            else:
                                logger.info("First candidate content has no parts.")
                        else:
                            logger.info(
                                "First candidate has no 'content' or content is empty."
                            )
                    else:
                        logger.info("Response candidates list is empty.")
                elif hasattr(response, "prompt_feedback"):
                    logger.info(f"Response has prompt feedback: {response.prompt_feedback}")
                else:
                    logger.info("Response has no candidates or prompt feedback.")
                # --- End Debugging Logs ---

                if streaming_enabled:
                    # Iterate through the streaming response and yield text chunks
                    logger.info(
                        f"Starting streaming response iteration for chat {chat_id}."
                    )
                    # Use a separate try/except for the streaming iteration itself
                    try:
                        # Check if response is iterable (it should be for stream=True)
                        if not hasattr(response, "__iter__"):
                            logger.error(
                                f"Expected streaming response to be iterable, but got {type(response)}"
                            )
                            yield "[Streaming Error: Unexpected API response format]"
                            return

                        chunk_count = 0
                        for chunk in response:
                            chunk_count += 1
                            logger.info(
                                f"Received chunk {chunk_count}: {chunk}"
                            )
                            if (
                                hasattr(chunk, "text") and chunk.text
                            ):  # Only yield if there is text in the chunk
                                logger.info(
                                    f"Yielding chunk text (length {len(chunk.text)})."
                                )
                                yield chunk.text
                            elif hasattr(chunk, "candidates") and chunk.candidates:
                                # Sometimes chunks might contain candidates even if text is empty?
                                logger.info(
                                    f"Chunk {chunk_count} has candidates but no text."
                                )
                            elif hasattr(chunk, "prompt_feedback"):
                                logger.info(
                                    f"Chunk {chunk_count} has prompt feedback: {chunk.prompt_feedback}"
                                )
                                # Optionally yield a system message about feedback
                                # yield f"\n[System Note: Prompt feedback received: {chunk.prompt_feedback}]"
                            else:
                                logger.info(
                                    f"Chunk {chunk_count} has no text, candidates, or prompt feedback."
                                )

                        if chunk_count == 0:
                            logger.warning(
                                f"Streaming iteration for chat {chat_id} completed but yielded no chunks."
                            )
                            # Yield a message if no chunks were received at all
                            yield "[System Note: The AI did not return any content.]"

                    except Exception as stream_err:
                        logger.error(
                            f"Error during streaming iteration for chat {chat_id}: {stream_err}",
                            exc_info=True,
                        )
                        yield f"\n[Streaming Error: {type(stream_err).__name__}]"
                    logger.info(f"Streaming finished for chat {chat_id}.")
                    return  # Explicitly return after yielding all chunks

                else:
                    # Get the full text response for non-streaming
                    logger.info(
                        f"Processing non-streaming response for chat {chat_id}."
                    )
                    # Check if response has text attribute (should for stream=False)
                    if hasattr(response, "text"):
                        assistant_reply = response.text
                        logger.info(
                            f"Successfully received full response text (length {len(assistant_reply)}) for chat {chat_id}."
                        )
                        if not assistant_reply.strip():
                            logger.warning(
                                f"Non-streaming response for chat {chat_id} was empty or whitespace."
                            )
                            assistant_reply = "[System Note: The AI returned an empty response.]"  # Provide a user-friendly message
                        return assistant_reply  # Return the string
                    elif hasattr(response, "candidates") and not response.candidates:
                        logger.warning(
                            f"Non-streaming response for chat {chat_id} had no candidates."
                        )
                        # Check for prompt feedback if no candidates
                        if (
                            hasattr(response, "prompt_feedback")
                            and response.prompt_feedback
                        ):
                            logger.warning(
                                f"Non-streaming response had prompt feedback: {response.prompt_feedback}"
                            )
                            return f"[AI Safety Error: Request blocked due to safety settings (Reason: {response.prompt_feedback.block_reason})]"
                        else:
                            return "[AI Error: The AI did not return any candidates.]"
                    elif hasattr(response, "prompt_feedback"):
                        logger.warning(
                            f"Non-streaming response for chat {chat_id} had prompt feedback but no text/candidates."
                        )
                        return f"[AI Safety Error: Request blocked due to safety settings (Reason: {response.prompt_feedback.block_reason})]"
                    else:
                        logger.error(
                            f"Non-streaming response for chat {chat_id} had unexpected format: {type(response)}"
                        )
                        return "[AI Error: Unexpected API response format.]"

            # --- Specific Error Handling for API Call ---
            # These exceptions need to be caught here and returned/yielded as error messages
            # The route handler will catch any exceptions *not* caught here.
            except ValidationError as e:
                logger.error(
                    f"Data validation error calling Gemini API for chat {chat_id} with model {model_to_use}: {e}",
                    exc_info=True,
                )
                error_msg = f"[AI Error: Internal data format error. Please check logs. ({e.errors()[0]['type']} on field '{'.'.join(map(str,e.errors()[0]['loc']))}')]"
                if streaming_enabled:
                    yield error_msg
                    return
                else:
                    return error_msg
            except DeadlineExceeded:
                logger.error(f"Gemini API call timed out for chat {chat_id}.")
                error_msg = "[AI Error: The request timed out. Please try again.]"
                if streaming_enabled:
                    yield error_msg
                    return
                else:
                    return error_msg
            except NotFound as e:
                logger.error(
                    f"Model '{model_to_use}' not found or inaccessible for chat {chat_id}: {e}"
                )
                error_msg = (
                    f"[AI Error: Model '{raw_model_name}' not found or access denied.]"
                )
                if streaming_enabled:
                    yield error_msg
                    return
                else:
                    return error_msg
            except GoogleAPIError as e:
                logger.error(f"Google API error for chat {chat_id}: {e}")
                err_str = str(e).lower()
                error_message = f"[AI API Error: {type(e).__name__}]"

                if "api key not valid" in err_str:
                    # No need to set g.gemini_api_key_invalid anymore
                    error_message = "[Error: Invalid Gemini API Key]"
                elif "prompt was blocked" in err_str or "SAFETY" in str(e):
                    feedback_reason = "N/A"
                    try:
                        # Check if response object exists from the try block
                        # For streaming, response is the generator itself, need to check its properties if available
                        # For non-streaming, response is the result object
                        if (
                            not streaming_enabled
                            and response
                            and hasattr(response, "prompt_feedback")
                            and response.prompt_feedback
                        ):
                            feedback_reason = response.prompt_feedback.block_reason
                        # Check candidate finish reason if prompt feedback isn't the cause (more common in streaming)
                        elif (
                            streaming_enabled
                            and hasattr(e, "response")
                            and e.response
                            and e.response.candidates
                            and e.response.candidates[0].finish_reason == 3
                        ):
                            feedback_reason = "Response Content Safety"
                        elif (
                            hasattr(e, "response")
                            and e.response
                            and hasattr(e.response, "prompt_feedback")
                            and e.response.prompt_feedback
                        ):
                            feedback_reason = e.response.prompt_feedback.block_reason
                    except Exception:
                        pass
                    logger.warning(
                        f"API error indicates safety block for chat {chat_id}. Reason: {feedback_reason}"
                    )
                    error_message = f"[AI Safety Error: Request or response blocked due to safety settings (Reason: {feedback_reason})]"
                elif "resource has been exhausted" in err_str or "429" in err_str:
                    logger.warning(f"Quota/Rate limit hit for chat {chat_id}.")
                    error_message = "[AI Error: API quota or rate limit exceeded. Please try again later.]"
                elif "internal error" in err_str or "500" in str(e):
                    logger.error(
                        f"Internal server error from Gemini API for chat {chat_id}: {e}"
                    )
                    error_message = "[AI Error: The AI service encountered an internal error. Please try again later.]"

                if streaming_enabled:
                    yield error_message
                    return
                else:
                    return error_message

            except Exception as e:
                logger.error(
                    f"Unexpected error calling Gemini API for chat {chat_id} with model {model_to_use}: {e}",
                    exc_info=True,
                )
                error_msg = f"[Unexpected AI Error: {type(e).__name__}]"
                if streaming_enabled:
                    yield error_msg
                    return
                else:
                    return error_msg

        finally:
            # --- Clean up temporary files ---
            # This block runs regardless of whether an exception occurred,
            # but only after the try block is exited (either by return, yield, or exception).
            # For a generator, this runs when the generator is exhausted or closed.
            logger.info(
                f"Executing finally block for chat {chat_id}. Cleaning up temp files."
            )
            if temp_files_to_clean:
                logger.info(
                    f"Cleaning up {len(temp_files_to_clean)} temporary files for chat {chat_id}..."
                )
                for temp_path in temp_files_to_clean:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                            logger.info(f"Removed temp file: {temp_path}")
                        else:
                            logger.info(
                                f"Temp file not found, already removed? {temp_path}"
                            )
                    except OSError as e:
                        logger.warning(f"Error removing temp file {temp_path}: {e}")
            logger.info(
                f"Finished executing finally block for chat {chat_id}."
            )

    except Exception as e:
        # This outer catch block handles exceptions that occur *before* the inner try/finally
        # or exceptions that escape the inner blocks.
        logger.error(
            f"generate_chat_response (outer catch): CRITICAL UNEXPECTED ERROR for chat {chat_id}: {type(e).__name__} - {e}", # Make log message more prominent
            exc_info=True,
        )
        error_msg = f"[CRITICAL Unexpected AI Service Error: {type(e).__name__}]" # Make error message more prominent
        if streaming_enabled:
            yield error_msg
            return # Stop generator
        else:
            return error_msg


# --- Standalone Text Generation (Example) ---
# Remove the decorator
# @ai_ready_required
def generate_text(prompt: str, model_name: str = None) -> str:
    """Generates text using a specified model or the default."""
    logger.info("Entering generate_text.")

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
             _ = current_app.config # Simple check that raises RuntimeError if no context
             logger.debug("generate_text: Flask request context is active.")
        except RuntimeError:
             logger.error(
                 "generate_text called outside of active Flask app/request context.",
                 exc_info=True # Log traceback
             )
             return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return "[Error: AI Service API Key not configured]"

        try:
            client = genai.Client(api_key=api_key)
            logger.info("Successfully created genai.Client for text generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(f"Failed to initialize genai.Client for text: {e}", exc_info=True)
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
            contents=prompt,  # Simple text prompt
            stream=False,  # Not streamed
        )
        return response.text

    except NotFound:
        return f"[Error: Model '{model_to_use}' not found]"
    except GoogleAPIError as e:
        # Simplified error handling for this example
        logger.error(f"API error during text generation: {e}")
        if "api key not valid" in str(e).lower():
            # No need to set g.gemini_api_key_invalid anymore
            return "[Error: Invalid Gemini API Key]"
        return f"[AI API Error: {type(e).__name__}]"
    except Exception as e:
        logger.error(f"Unexpected error during text generation: {e}", exc_info=True)
        return f"[Unexpected AI Error: {type(e).__name__}]"
