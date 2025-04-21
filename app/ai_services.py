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
)  # Added NotFound
from pydantic_core import (
    ValidationError,
)  # Import ValidationError for specific handling
import grpc
import logging
from functools import wraps
from werkzeug.utils import secure_filename  # Moved import here for clarity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration Check ---

gemini_api_key_present = False


def configure_gemini(app):
    """
    Checks if the Gemini API key is present in the Flask app config.
    Sets a flag indicating presence.
    """
    global gemini_api_key_present
    api_key = app.config.get("API_KEY")
    if api_key:
        gemini_api_key_present = True
        logger.info("Gemini API key found in configuration.")
    else:
        gemini_api_key_present = False
        logger.error(
            "Gemini API key NOT found in config. AI features relying on it will fail."
        )
    return gemini_api_key_present


# --- Helper Functions for Client Instantiation ---


def _get_api_key():
    """Safely retrieves the API key from Flask's current_app config."""
    if not gemini_api_key_present:
        logger.error(
            "Attempted to get API key, but it was not found during initial configuration."
        )
        return None
    try:
        key = current_app.config.get("API_KEY")
        if not key:
            logger.error("API_KEY is missing from current_app.config.")
            return None
        return key
    except RuntimeError:
        logger.error("Attempted to get API key outside of Flask app/request context.")
        return None


def get_gemini_client():
    """
    Creates and returns a configured genai.Client instance using the API key
    from the application config. Returns None on failure.
    Caches the client in Flask's request context (g).
    """
    # Check if client already exists in the current request context
    # Also check if the key was previously found invalid in this request
    if g.get("gemini_api_key_invalid", False):
        logger.debug(
            "Skipping client creation, API key marked invalid for this request."
        )
        return None
    if "gemini_client" in g:
        # Return cached client if it's not None (i.e., wasn't a cached failure)
        if g.gemini_client is not None:
            logger.debug("Returning cached genai.Client for this request.")
            return g.gemini_client
        else:
            logger.debug("Cached client state was None (failure), skipping.")
            return None  # Explicitly return None if cached state is failure

    api_key = _get_api_key()
    if not api_key:
        g.gemini_client = None  # Cache failure state
        return None  # Error logged in _get_api_key

    try:
        # Note: Client-level options like transport or client_options might be
        # configurable here if needed for things like default timeouts,
        # but we'll stick to the basic client for now.
        client = genai.Client(api_key=api_key)
        # Optional: Perform a lightweight check to validate the key early
        # client.models.list() # Example check using the models attribute
        g.gemini_client = client  # Cache successful client in request context
        logger.debug("Successfully created and cached genai.Client for this request.")
        return client
    except (GoogleAPIError, ClientError, ValueError, Exception) as e:
        logger.error(f"Failed to initialize genai.Client: {e}", exc_info=True)
        g.gemini_client = None  # Cache failure state
        if "api key not valid" in str(e).lower():
            g.gemini_api_key_invalid = True  # Mark key as invalid for this request
        return None


# --- Decorator for AI Readiness Check ---
def ai_ready_required(f):
    """
    Decorator to ensure the API key is configured and we have a client
    before running an AI function. Ensures request context.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Check if configure_gemini found the key initially
            if not gemini_api_key_present:
                logger.warning(
                    f"AI function '{f.__name__}' called but API key was missing at startup."
                )
                # Return a string error message for non-streaming, or yield for streaming
                if kwargs.get('streaming_enabled', False):
                     yield "[Error: AI Service API Key not configured]"
                     return # Stop generator
                else:
                     return "[Error: AI Service API Key not configured]"

            # Check if we have a valid request context (needed for g and current_app)
            _ = (
                current_app.config
            )  # Simple check that raises RuntimeError if no context

            # Attempt to get the client (this also checks the invalid key flag in g)
            client = get_gemini_client()
            if not client:
                if g.get("gemini_api_key_invalid", False):
                    logger.warning(
                        f"AI function '{f.__name__}' called but API key was found invalid in this request."
                    )
                    error_msg = "[Error: Invalid Gemini API Key]"
                else:
                    logger.error(
                        f"AI function '{f.__name__}' called but failed to get Gemini client."
                    )
                    error_msg = "[Error: Failed to initialize AI client]"

                # Return error message based on streaming preference
                if kwargs.get('streaming_enabled', False):
                    yield error_msg
                    return # Stop generator
                else:
                    return error_msg

            # If client is obtained, proceed with the function
            return f(*args, **kwargs)
        except RuntimeError:
            logger.error(
                f"AI function '{f.__name__}' called outside of active Flask request context."
            )
            error_msg = "[Error: AI Service called outside request context]"
            if kwargs.get('streaming_enabled', False):
                 yield error_msg
                 return # Stop generator
            else:
                 return error_msg


    return decorated_function


# --- Summary Generation ---
@ai_ready_required  # Apply the decorator
def generate_summary(file_id):
    """
    Generates a summary for a file using a designated multi-modal model via the client.
    Handles text directly and uses file upload API for other types.
    Uses the NEW google.genai library structure (client-based).
    """
    client = get_gemini_client()  # Get client via helper (already checked by decorator)
    if not client:  # Should not happen if decorator works, but belt-and-suspenders
        return "[Error: Failed to initialize AI client - Check Logs]"

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
                    config={'display_name':filename},
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
                if "api key not valid" in str(upload_err).lower():
                    g.gemini_api_key_invalid = True
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
            stream=False # Summary generation is not streamed
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
            g.gemini_api_key_invalid = True
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
# No decorator needed here as it calls generate_summary which has it
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
            # Call the refactored function (which is decorated)
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
@ai_ready_required  # Apply the decorator
def generate_search_query(user_message: str, max_retries=1) -> str | None:
    """
    Uses the default LLM via client to generate a concise web search query.
    """
    client = get_gemini_client()  # Get client via helper
    if not client:
        return None  # Should be caught by decorator

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
                contents=prompt,  # Prompt is just text, passed directly
                stream=False # Query generation is not streamed
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
                g.gemini_api_key_invalid = True
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
@ai_ready_required
def generate_chat_response(
    chat_id,
    user_message,
    attached_files=None,  # Renamed from session_file_ids, expects list of {id, filename, type}
    session_files=None,  # New parameter, expects list of {filename, mimetype, content}
    calendar_context=None,
    web_search_enabled=False,  # Added this parameter
    streaming_enabled=False, # Added this parameter
):
    """
    Generates a chat response using the Gemini API via the client,
    incorporating history, context, file summaries, and optional web search.
    Handles potential errors gracefully.
    Uses the NEW google.genai library structure (client-based).
    Supports streaming responses if streaming_enabled is True.
    """
    client = get_gemini_client()
    if not client:
        # Decorator should handle this and return/yield error message
        # If it somehow fails here, return/yield a generic error
        error_msg = "[Error: Failed to initialize AI client - Check Logs]"
        if streaming_enabled:
            yield error_msg
            return # Stop generator
        else:
            return error_msg


    # --- Determine Model ---
    # Use primary model by default, check for override if needed
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
    try:
        history_data = database.get_chat_history_from_db(
            chat_id
        )  # Use the correct DB function name
        # Convert DB history to list of genai.types.Content objects
        history = []
        for msg in history_data:
            # Simple conversion assuming text parts only for history
            # If history could contain files, this needs adjustment
            history.append(Content(role=msg["role"], parts=[Part(text=msg["content"])]))
        logger.info(f"Fetched {len(history)} history turns for chat {chat_id}.")

        # Ensure history starts with 'user' role for the API
        # The API expects alternating user/model turns starting with user.
        # If the last message in history was 'user', the new turn is 'model'.
        # If the last message was 'model', the new turn is 'user'.
        # The API handles the current turn's role implicitly based on history.
        # We just need to ensure the history itself is valid (starts with user, alternates).
        # The DB query orders by timestamp, so the last item is the most recent.
        # If the history is not empty and the last message is 'user', the next turn is 'model'.
        # If the history is not empty and the last message is 'assistant', the next turn is 'user'.
        # If history is empty, the first turn is 'user'.
        # The genai SDK's chat.send_message handles this state internally based on the history provided.
        # We just need to ensure the history list itself is correctly formatted (alternating roles).
        # The DB query should return history in chronological order.
        # The SDK expects history in chronological order, starting with the first user turn.
        # If the very first message in the DB is 'assistant', something is wrong with the history.
        # Let's add a check for the first message role if history is not empty.
        if history and history[0].role != "user":
             logger.error(
                 f"Chat history for {chat_id} does not start with a user turn. First role: {history[0].role}. Attempting to correct by removing first message."
             )
             # Remove the first message if it's not a user message
             # This is a heuristic fix; ideally, history should be correct from the start.
             history.pop(0)
             if history:
                 logger.warning(f"History for chat {chat_id} now starts with role: {history[0].role}")
             else:
                 logger.warning(f"History for chat {chat_id} is now empty after correction attempt.")


    except Exception as e:
        logger.error(f"Failed to fetch history for chat {chat_id}: {e}", exc_info=True)
        error_msg = "[Error: Could not load chat history]"
        if streaming_enabled:
            yield error_msg
            return # Stop generator
        else:
            return error_msg


    # --- Prepare Current Turn Parts ---
    # This list will hold all components (text, files) for the *current* user message turn
    current_turn_parts = []
    temp_files_to_clean = []  # Keep track of temp files for cleanup

    # 1. Add Calendar Context (if provided)
    if calendar_context:
        logger.info(f"Adding calendar context to chat {chat_id} prompt.")
        # MODIFIED: Wrap strings in Part()
        current_turn_parts.extend(
            [
                Part(text="--- Start Calendar Context ---"),
                Part(text=calendar_context),
                Part(text="--- End Calendar Context ---"),
            ]
        )

    # 2. Process Attached Files (from DB by ID, with type)
    if attached_files:  # Use the new parameter name
        logger.info(
            f"Processing {len(attached_files)} attached files (from DB) for chat {chat_id}."
        )
        for (
            file_detail
        in attached_files):  # Iterate over the list of objects {id, filename, type}
            file_id = file_detail.get("id")
            attachment_type = file_detail.get("type")  # 'full' or 'summary'
            frontend_filename = file_detail.get(
                "filename", "Unknown File"
            )  # Get filename from frontend list

            if file_id is None or attachment_type is None:
                logger.warning(f"Skipping invalid attached file detail: {file_detail}")
                current_turn_parts.append(
                    Part(text=f"[System: Skipped invalid attached file detail.]")
                )
                continue

            try:
                # Fetch file details from DB using the ID
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

                filename = db_file_details["filename"]  # Use DB filename
                mimetype = db_file_details["mimetype"]
                content_blob = db_file_details["content"]

                if attachment_type == "summary":
                    # Use existing summary or generate if needed
                    summary = get_or_generate_summary(
                        file_id
                    )  # This function handles DB fetch/save/gen
                    current_turn_parts.append(
                        Part(
                            text=f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                        )
                    )
                elif attachment_type == "full":
                    # Upload the full content if supported
                    if mimetype.startswith(
                        ("image/", "audio/", "video/", "application/pdf", "text/")
                    ):  # Include text for full upload
                        logger.info(
                            f"Attaching full content for '{filename}' ({mimetype}) for chat {chat_id}."
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

                            uploaded_file = client.files.upload(
                                file=temp_filepath,
                                config={'display_name':filename},
                            )
                            current_turn_parts.append(uploaded_file)
                            logger.info(
                                f"Successfully uploaded '{filename}' (URI: {uploaded_file.uri}) for chat {chat_id}."
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
                                g.gemini_api_key_invalid = True  # Mark key invalid
                        # Removed the 'else' block here that warned about unsupported types for 'full'
                        # The check is now done implicitly by the 'if mimetype.startswith(...)'
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

    # 3. Process Session Files (with content)
    if session_files:  # Use the new parameter name
        logger.info(
            f"Processing {len(session_files)} session files (with content) for chat {chat_id}."
        )
        for (
            session_file_detail
        ) in (
            session_files
        ):  # Iterate over the list of objects {filename, mimetype, content}
            filename = session_file_detail.get("filename", "Unknown Session File")
            mimetype = session_file_detail.get("mimetype")
            content_base64 = session_file_detail.get(
                "content"
            )  # This is base64 encoded

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

                        uploaded_file = client.files.upload(
                            file=temp_filepath,
                            config={'display_name':filename},
                        )
                        current_turn_parts.append(uploaded_file)
                        logger.info(
                            f"Successfully uploaded session file '{filename}' (URI: {uploaded_file.uri}) for chat {chat_id}."
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
                            g.gemini_api_key_invalid = True  # Mark key invalid
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

    # 4. Perform Web Search (if enabled and seems appropriate)
    search_results = None
    if web_search_enabled:  # Use the new parameter name
        logger.info(f"Web search enabled for chat {chat_id}. Generating query...")
        # Pass streaming_enabled=False to generate_search_query as it's not streamed
        search_query = generate_search_query(user_message, streaming_enabled=False)
        if search_query:
            logger.info(
                f"Performing web search for chat {chat_id} with query: '{search_query}'"
            )
            search_results = perform_web_search(
                search_query
            )  # Assumes this returns a list of strings or None
            if search_results:
                logger.info(f"Adding web search results to chat {chat_id} prompt.")
                # MODIFIED: Wrap search results in Part()
                current_turn_parts.extend(
                    [
                        Part(text="--- Start Web Search Results ---"),
                        *[Part(text=s) for s in search_results],
                        Part(text="--- End Web Search Results ---"),
                    ]
                )
            else:
                logger.info(f"Web search yielded no results for chat {chat_id}.")
                # MODIFIED: Wrap system note in Part()
                current_turn_parts.append(
                    Part(
                        text="[System Note: Web search was performed but returned no results.]"
                    )
                )
        else:
            logger.info(
                f"Could not generate a suitable web search query for chat {chat_id}."
            )
            # MODIFIED: Wrap system note in Part()
            current_turn_parts.append(
                Part(
                    text="[System Note: Web search was enabled but no query could be generated.]"
                )
            )

    # 5. Add User's Text Message
    if user_message:
        # MODIFIED: Wrap user message in Part()
        current_turn_parts.append(Part(text=user_message))
    else:
        # Handle cases where maybe only files were sent?
        # If current_turn_parts is still empty, we might need a placeholder
        if not current_turn_parts:
            logger.warning(
                f"Chat {chat_id}: User message is empty and no files/context were added."
            )
            # MODIFIED: Add a placeholder Part
            current_turn_parts.append(
                Part(text="[User provided no text, only attached files or context.]")
            )

    # --- Call Gemini API ---
    # The return type depends on streaming_enabled
    # If streaming_enabled is True, return a generator
    # If streaming_enabled is False, return a string

    try:
        logger.info(
            f"Sending request to Gemini for chat {chat_id} with {len(history)} history turns and {len(current_turn_parts)} current parts. Streaming: {streaming_enabled}"
        )

        # Create the ChatSession object using the client
        chat_session = client.chats.create(model=model_to_use, history=history)

        # Send the message using the ChatSession
        # The 'parts' are the content of the *current* user message turn
        response = chat_session.send_message(
            message=current_turn_parts,  # Pass the constructed list of Parts/Files
            stream=streaming_enabled # Use the streaming flag here
        )

        if streaming_enabled:
            # Return the generator directly
            logger.info(f"Returning streaming response generator for chat {chat_id}.")
            return (chunk.text for chunk in response) # Yield text from each chunk
        else:
            # Return the full text response
            assistant_reply = response.text
            logger.info(f"Successfully received full response for chat {chat_id}.")
            # Saving to DB is handled by the route for both streaming and non-streaming
            return assistant_reply

    # --- Specific Error Handling ---
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
        error_msg = f"[AI Error: Model '{raw_model_name}' not found or access denied.]"
        if streaming_enabled:
            yield error_msg
            return
        else:
            return error_msg
    except GoogleAPIError as e:
        logger.error(f"Google API error for chat {chat_id}: {e}")
        err_str = str(e).lower()
        error_message = f"[AI API Error: {type(e).__name__}]"  # Default API error

        if "api key not valid" in err_str:
            g.gemini_api_key_invalid = True
            error_message = "[Error: Invalid Gemini API Key]"
        elif "prompt was blocked" in err_str or "SAFETY" in str(e):
            feedback_reason = "N/A"
            try:
                # Check if response object exists from the try block
                # For streaming, response is the generator itself, need to check its properties if available
                # For non-streaming, response is the result object
                if not streaming_enabled and response and hasattr(response, "prompt_feedback") and response.prompt_feedback:
                    feedback_reason = response.prompt_feedback.block_reason
                # Check candidate finish reason if prompt feedback isn't the cause (more common in streaming)
                elif streaming_enabled and hasattr(e, 'response') and e.response and e.response.candidates and e.response.candidates[0].finish_reason == 3:
                     feedback_reason = "Response Content Safety"
                elif hasattr(e, 'response') and e.response and hasattr(e.response, 'prompt_feedback') and e.response.prompt_feedback:
                     feedback_reason = e.response.prompt_feedback.block_reason # Sometimes feedback is on the exception object
            except Exception:
                pass # Ignore errors getting feedback reason
            logger.warning(
                f"API error indicates safety block for chat {chat_id}. Reason: {feedback_reason}"
            )
            error_message = f"[AI Safety Error: Request or response blocked due to safety settings (Reason: {feedback_reason})]"
        elif "resource has been exhausted" in err_str or "429" in err_str:
            logger.warning(f"Quota/Rate limit hit for chat {chat_id}.")
            error_message = (
                "[AI Error: API quota or rate limit exceeded. Please try again later.]"
            )
        elif "internal error" in err_str or "500" in str(e):
            logger.error(
                f"Internal server error from Gemini API for chat {chat_id}: {e}"
            )
            error_message = "[AI Error: The AI service encountered an internal error. Please try again later.]"
        # Add other specific GoogleAPIError checks here if needed

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
        # but only after the try/except/return/yield block is exited.
        # For streaming, this runs *after* the generator is exhausted or an exception occurs during iteration.
        if temp_files_to_clean:
            logger.info(
                f"Cleaning up {len(temp_files_to_clean)} temporary files for chat {chat_id}..."
            )
            for temp_path in temp_files_to_clean:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        logger.debug(
                            f"Removed temp file: {temp_path}"
                        )  # Debug level for successful cleanup
                    else:
                        logger.debug(f"Temp file not found, already removed? {temp_path}")
                except OSError as e:
                    logger.warning(f"Error removing temp file {temp_path}: {e}")


# --- Standalone Text Generation (Example) ---
@ai_ready_required
def generate_text(prompt: str, model_name: str = None) -> str:
    """Generates text using a specified model or the default."""
    client = get_gemini_client()
    if not client:
        return "[Error: Failed to initialize AI client]"

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
            stream=False # Not streamed
        )
        return response.text

    except NotFound:
        return f"[Error: Model '{model_to_use}' not found]"
    except GoogleAPIError as e:
        # Simplified error handling for this example
        logger.error(f"API error during text generation: {e}")
        if "api key not valid" in str(e).lower():
            g.gemini_api_key_invalid = True
            return "[Error: Invalid Gemini API Key]"
        return f"[AI API Error: {type(e).__name__}]"
    except Exception as e:
        logger.error(f"Unexpected error during text generation: {e}", exc_info=True)
        return f"[Unexpected AI Error: {type(e).__name__}]"
