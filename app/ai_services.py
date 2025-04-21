# app/ai_services.py
import google.genai as genai # Use the new SDK
from google.genai.types import GenerationConfig, Part, Content # Import necessary types
from flask import current_app, g # Import g for request context caching
import tempfile
import os
import re
import base64
from . import database
from .plugins.web_search import perform_web_search
from google.api_core.exceptions import GoogleAPIError, DeadlineExceeded, ClientError, NotFound # Added NotFound
import grpc
import logging
from functools import wraps
from werkzeug.utils import secure_filename # Moved import here for clarity

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
        logger.error("Gemini API key NOT found in config. AI features relying on it will fail.")
    return gemini_api_key_present

# --- Helper Functions for Client Instantiation ---

def _get_api_key():
    """Safely retrieves the API key from Flask's current_app config."""
    if not gemini_api_key_present:
         logger.error("Attempted to get API key, but it was not found during initial configuration.")
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
    if g.get('gemini_api_key_invalid', False):
        logger.debug("Skipping client creation, API key marked invalid for this request.")
        return None
    if 'gemini_client' in g:
        # Return cached client if it's not None (i.e., wasn't a cached failure)
        if g.gemini_client is not None:
             logger.debug("Returning cached genai.Client for this request.")
             return g.gemini_client
        else:
             logger.debug("Cached client state was None (failure), skipping.")
             return None # Explicitly return None if cached state is failure

    api_key = _get_api_key()
    if not api_key:
        g.gemini_client = None # Cache failure state
        return None # Error logged in _get_api_key

    try:
        # Note: Client-level options like transport or client_options might be
        # configurable here if needed for things like default timeouts,
        # but we'll stick to the basic client for now.
        client = genai.Client(api_key=api_key)
        # Optional: Perform a lightweight check to validate the key early
        # client.models.list() # Example check using the models attribute
        g.gemini_client = client # Cache successful client in request context
        logger.debug("Successfully created and cached genai.Client for this request.")
        return client
    except (GoogleAPIError, ClientError, ValueError, Exception) as e:
        logger.error(f"Failed to initialize genai.Client: {e}", exc_info=True)
        g.gemini_client = None # Cache failure state
        if "api key not valid" in str(e).lower():
             g.gemini_api_key_invalid = True # Mark key as invalid for this request
        return None

# --- REMOVED get_gemini_model function ---
# The new SDK primarily uses the client object for interactions.
# Model instances are not typically created and cached in the same way.
# Model names are passed directly to client methods like generate_content.

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
                logger.warning(f"AI function '{f.__name__}' called but API key was missing at startup.")
                return "[Error: AI Service API Key not configured]"

            # Check if we have a valid request context (needed for g and current_app)
            _ = current_app.config # Simple check that raises RuntimeError if no context

            # Attempt to get the client (this also checks the invalid key flag in g)
            client = get_gemini_client()
            if not client:
                 if g.get('gemini_api_key_invalid', False):
                      logger.warning(f"AI function '{f.__name__}' called but API key was found invalid in this request.")
                      return "[Error: Invalid Gemini API Key]"
                 else:
                      logger.error(f"AI function '{f.__name__}' called but failed to get Gemini client.")
                      return "[Error: Failed to initialize AI client]"

            # If client is obtained, proceed with the function
            return f(*args, **kwargs)
        except RuntimeError:
            logger.error(f"AI function '{f.__name__}' called outside of active Flask request context.")
            return "[Error: AI Service called outside request context]"
    return decorated_function


# --- Summary Generation ---
@ai_ready_required # Apply the decorator
def generate_summary(file_id):
    """
    Generates a summary for a file using a designated multi-modal model via the client.
    Handles text directly and uses file upload API for other types.
    Uses the NEW google.genai library structure (client-based).
    """
    client = get_gemini_client() # Get client via helper (already checked by decorator)
    if not client: # Should not happen if decorator works, but belt-and-suspenders
         return "[Error: Failed to initialize AI client - Check Logs]"

    try:
        file_details = database.get_file_details_from_db(file_id, include_content=True)
        if not file_details or not file_details.get("content"):
            logger.error(f"Could not retrieve file details or content for file ID: {file_id}")
            return "[Error: File details or content not found]"
    except Exception as db_err:
        logger.error(f"Database error fetching file {file_id}: {db_err}", exc_info=True)
        return "[Error: Database error retrieving file]"

    filename = file_details["filename"]
    mimetype = file_details["mimetype"]
    content_blob = file_details["content"]
    # Ensure model name from config includes the 'models/' prefix if needed by API
    raw_model_name = current_app.config["SUMMARY_MODEL"]
    summary_model_name = f"models/{raw_model_name}" if not raw_model_name.startswith("models/") else raw_model_name

    logger.info(
        f"Attempting summary generation for '{filename}' (Type: {mimetype}) using model '{summary_model_name}'..."
    )

    content_parts = [] # Renamed from 'parts' to avoid confusion with genai.types.Part
    temp_file_to_clean = None
    prompt = f"Please provide a concise summary of the attached file named '{filename}'. Focus on the main points and key information."
    response = None # Initialize response to None

    try:
        # --- Text Handling ---
        if mimetype.startswith("text/") or filename.lower().endswith((".js", ".py", ".css", ".html", ".json", ".xml", ".csv", ".log")): # Expanded text types
            try:
                effective_mimetype = mimetype if mimetype.startswith("text/") else 'application/octet-stream' # Use generic for code if not text/*
                logger.info(f"Treating '{filename}' as text ({effective_mimetype}) for summary.")
                text_content = content_blob.decode("utf-8", errors="ignore")
                # Construct parts for the client's generate_content
                content_parts = [
                    prompt, # Initial prompt part
                    f"\n--- File Content ({filename}) ---\n",
                    text_content # Content part
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
                 # Use the client's file upload method (client.files.upload as per original code)
                 # Note: Ensure this matches the installed library version. client.upload_file is also common.
                 uploaded_file = client.files.upload(
                     path=temp_filepath, display_name=filename # Removed mime_type, often inferred
                 )
                 # Construct parts including the prompt and the uploaded file reference (as a Part)
                 content_parts = [prompt, uploaded_file] # Pass the file object directly
                 logger.info(
                     f"File '{filename}' uploaded for summary, URI: {uploaded_file.uri}"
                 )
             except Exception as upload_err:
                 logger.error(f"Error preparing/uploading file for summary: {upload_err}", exc_info=True)
                 if "api key not valid" in str(upload_err).lower():
                    g.gemini_api_key_invalid = True
                    return "[Error: Invalid Gemini API Key during file upload]"
                 # Add more specific error checks if needed (e.g., file size limits)
                 return f"[Error preparing/uploading file for summary: {type(upload_err).__name__}]"
        else:
            logger.warning(f"Summary generation not supported for mimetype: {mimetype}")
            return "[Summary generation not supported for this file type]"

        # --- Generate Content using the Client ---
        # timeout = current_app.config.get("GEMINI_REQUEST_TIMEOUT", 300) # Timeout removed from call
        logger.info(f"Calling generate_content with model '{summary_model_name}'.") # Removed timeout from log

        # Use the client.models attribute to generate content
        response = client.models.generate_content( # CORRECTED: Added .models
            model=summary_model_name,
            contents=content_parts, # Pass the constructed parts/contents
            # request_options={"timeout": timeout}, # REMOVED: This argument caused TypeError
            # Add generation_config here if needed:
            # generation_config=GenerationConfig(...)
        )
        summary = response.text
        logger.info(f"Summary generated successfully for '{filename}'.")
        return summary

    # --- Error Handling for API Call ---
    except TypeError as e:
        # Catch the specific error if arguments are still wrong
        logger.error(f"TypeError during summary generation for '{filename}': {e}. Check SDK method signature.", exc_info=True)
        return f"[Error generating summary: SDK usage error ({type(e).__name__}).]"
    except AttributeError as e:
        # Catch the specific error if .models was still wrong, though unlikely now
        logger.error(f"AttributeError during summary generation for '{filename}': {e}. Check SDK usage.", exc_info=True)
        return f"[Error generating summary: SDK usage error ({type(e).__name__}).]"
    except DeadlineExceeded:
        logger.error(f"Summary generation timed out for '{filename}'.")
        return "[Error: Summary generation timed out.]"
    except NotFound as e:
        logger.error(f"Model '{summary_model_name}' not found or inaccessible: {e}")
        return f"[Error: AI Model '{raw_model_name}' not found or access denied.]"
    except GoogleAPIError as e:
        logger.error(f"Google API error during summary generation for '{filename}': {e}")
        err_str = str(e).lower()
        if "api key not valid" in err_str:
            g.gemini_api_key_invalid = True
            return "[Error: Invalid Gemini API Key]"
        if "prompt was blocked" in err_str or "SAFETY" in str(e): # Broader safety check
            # Attempt to get feedback if available on the response object
            feedback_reason = "N/A"
            try:
                # Check if response exists and has feedback before accessing
                if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                     feedback_reason = response.prompt_feedback.block_reason
            except Exception: # Catch any error during feedback access
                 pass
            logger.warning(f"Summary generation blocked by safety settings for {filename}. Reason: {feedback_reason}")
            return f"[Error: Summary generation blocked due to safety settings (Reason: {feedback_reason})]"
        if "resource has been exhausted" in err_str or "429" in err_str:
             logger.warning(f"Quota/Rate limit hit during summary generation for {filename}.")
             return "[Error: API quota or rate limit exceeded. Please try again later.]"
        # Add other specific error checks if needed
        return f"[Error generating summary via API: {type(e).__name__}]"
    except Exception as e:
        logger.error(f"Unexpected error during summary generation for '{filename}': {e}", exc_info=True)
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
            and not file_details["summary"].startswith("[Error") # Check if it's not an old error message
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
                    logger.info(f"Successfully generated and saved summary for file ID: {file_id}")
                    return new_summary
                else:
                    logger.error(
                        f"Failed to save newly generated summary for file ID: {file_id}"
                    )
                    # Return the summary anyway, but log the save error
                    return new_summary
            else:
                # If generation failed, return the error message directly
                logger.warning(f"Summary generation failed for file ID {file_id}: {new_summary}")
                # Optionally save the error state to prevent retries?
                # database.save_summary_in_db(file_id, new_summary) # Uncomment to save errors
                return new_summary
    except Exception as e:
        logger.error(f"Error in get_or_generate_summary for file ID {file_id}: {e}", exc_info=True)
        return f"[Error retrieving or generating summary: {type(e).__name__}]"


# --- Generate Search Query ---
@ai_ready_required # Apply the decorator
def generate_search_query(user_message: str, max_retries=1) -> str | None:
    """
    Uses the default LLM via client to generate a concise web search query.
    """
    client = get_gemini_client() # Get client via helper
    if not client: return None # Should be caught by decorator

    if not user_message or user_message.isspace():
        logger.info("Cannot generate search query from empty user message.")
        return None

    # Use a specific model or the default one for this task
    raw_model_name = current_app.config.get("QUERY_MODEL", current_app.config["DEFAULT_MODEL"])
    model_name = f"models/{raw_model_name}" if not raw_model_name.startswith("models/") else raw_model_name
    logger.info(f"Attempting to generate search query using model '{model_name}'...")

    prompt = f"""Analyze the following user message and generate a concise and effective web search query (ideally 3-7 words) that would find information directly helpful in answering or augmenting the user's request.

User Message:
"{user_message}"

Focus on the core information needed. Output *only* the raw search query string itself. Do not add explanations, quotation marks (unless essential for the search phrase), or any other surrounding text.

Search Query:"""

    retries = 0
    while retries <= max_retries:
        response = None # Initialize response to None
        try:
            # Use the client.models attribute to generate content
            response = client.models.generate_content( # CORRECTED: Added .models
                 model=model_name,
                 contents=prompt, # Pass the prompt as contents
                 generation_config=GenerationConfig( # Use imported GenerationConfig
                     max_output_tokens=50,
                     temperature=0.2,
                 ),
                 # request_options={"timeout": current_app.config.get("GEMINI_REQUEST_TIMEOUT", 60)} # REMOVED: This argument caused TypeError
            )

            # Check for blocked prompt before accessing text
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(
                    f"Prompt blocked for query gen, reason: {response.prompt_feedback.block_reason}"
                )
                return None # Don't retry if blocked

            # Check if parts exist before accessing text (though .text usually handles this)
            if not response.parts:
                 logger.warning(
                    f"LLM response for query generation had no parts. Raw response: {response}"
                 )
                 # Maybe retry once if no block reason?
                 if retries < max_retries:
                      retries += 1
                      logger.info(f"Retrying query generation due to empty parts (Attempt {retries+1}/{max_retries+1})")
                      continue
                 else:
                      return None # Give up after retry

            generated_query = response.text.strip()

            # Clean the generated query
            logger.info(f"Raw query generated: '{generated_query}'")
            generated_query = re.sub(r'^"|"$', "", generated_query) # Remove leading/trailing quotes
            generated_query = re.sub(r"^\s*[-\*\d]+\.?\s*", "", generated_query) # Remove leading list markers
            generated_query = re.sub(
                r"^(?:Search Query:|Here is a search query:|query:)\s*",
                "",
                generated_query,
                flags=re.IGNORECASE,
            ) # Remove common prefixes
            generated_query = generated_query.strip() # Final strip

            if generated_query:
                logger.info(f"Cleaned Search Query: '{generated_query}'")
                return generated_query
            else:
                logger.warning("LLM generated an empty search query after cleaning.")
                # Don't retry empty query, likely a model issue
                return None

        except TypeError as e:
            logger.error(f"TypeError during search query generation: {e}. Check SDK method signature.", exc_info=True)
            return None # Don't retry SDK usage errors
        except AttributeError as e:
            logger.error(f"AttributeError during search query generation: {e}. Check SDK usage.", exc_info=True)
            return None # Don't retry SDK usage errors
        except DeadlineExceeded:
            logger.warning(f"Search query generation timed out (Attempt {retries+1}/{max_retries+1}).")
            retries += 1
        except NotFound as e:
             logger.error(f"Model '{model_name}' not found for query generation: {e}")
             return None # Don't retry if model not found
        except GoogleAPIError as e:
            logger.error(f"Google API error during search query generation (Attempt {retries+1}/{max_retries+1}): {e}")
            err_str = str(e).lower()
            if "api key not valid" in err_str:
                g.gemini_api_key_invalid = True
                logger.error("API key invalid during search query generation. Aborting.")
                return None # Don't retry if key is invalid
            if "resource has been exhausted" in err_str or "429" in err_str:
                 logger.error("Quota/Rate limit hit during search query generation. Aborting retries.")
                 return None # Don't retry quota/rate limit errors
            # Retry other potentially transient API errors
            retries += 1
        except Exception as e:
            logger.error(
                f"Unexpected error generating search query (Attempt {retries+1}/{max_retries+1}): {e}", exc_info=True
            )
            retries += 1 # Retry unexpected errors

        # Check retry count at the end of the loop
        if retries > max_retries:
             logger.error("Max retries reached for search query generation.")
             return None

    return None # Fallback


# --- Chat Response Generation ---
@ai_ready_required # Apply the decorator
def generate_chat_response(
    chat_id,
    user_message,
    attached_files,
    calendar_context=None,
    session_files=None,
    enable_web_search=False,
):
    """
    Generates a chat response using the client, appropriate model, and context.
    Handles file uploads via API and includes optional context.
    Returns the assistant's reply string.
    """
    client = get_gemini_client() # Get client via helper
    if not client: return "[Error: Failed to initialize AI client - Check Logs]"

    try:
        chat_details = database.get_chat_details_from_db(chat_id)
        if not chat_details:
            logger.error(f"Chat session not found in DB for ID: {chat_id}")
            return "[Error: Chat session not found]"
    except Exception as db_err:
        logger.error(f"Database error fetching chat {chat_id}: {db_err}", exc_info=True)
        return "[Error: Database error retrieving chat session]"

    # Determine the primary model for this chat
    raw_primary_model_name = chat_details.get("model_name", current_app.config["DEFAULT_MODEL"])
    primary_model_name = f"models/{raw_primary_model_name}" if not raw_primary_model_name.startswith("models/") else raw_primary_model_name
    logger.info(f"Primary model for chat {chat_id} response: '{primary_model_name}'.")

    # Prepare contents for the API call
    current_turn_parts = [] # Parts for the *current* user message turn
    temp_files_to_clean = []
    files_info_for_history = [] # Metadata about files for saving in DB history

    session_files = session_files or []

    try:
        # --- Calendar Context ---
        if calendar_context:
            logger.info("Prepending calendar context to AI query.")
            # Add as distinct text parts
            current_turn_parts.extend(
                [
                    "--- Start Calendar Context ---",
                    calendar_context,
                    "--- End Calendar Context ---",
                ]
            )

        # --- Process Session Files (Temporary for this turn) ---
        if session_files:
            logger.info(f"Processing {len(session_files)} session files for chat {chat_id}...")
            for session_file in session_files:
                filename = session_file.get("filename", "unknown_session_file")
                base64_content = session_file.get("content")
                mimetype = session_file.get("mimetype", "application/octet-stream")

                if not base64_content:
                    logger.warning(f"Skipping session file '{filename}' due to missing content.")
                    continue

                try:
                    # Decode base64 content
                    if "," in base64_content:
                         header, encoded = base64_content.split(",", 1)
                    else:
                         encoded = base64_content # Assume no header if comma missing
                    decoded_data = base64.b64decode(encoded)

                    # Write to temp file for upload
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=f"_session_{secure_filename(filename)}"
                    ) as temp_file:
                        temp_file.write(decoded_data)
                        temp_filepath = temp_file.name
                        temp_files_to_clean.append(temp_filepath)

                    logger.info(f"Uploading temp session file '{temp_filepath}' for '{filename}' via API...")
                    try:
                        # Use the client to upload the file
                        uploaded_file = client.files.upload(
                            path=temp_filepath,
                            display_name=f"session_{filename}" # Removed mime_type
                        )
                        # Append the file object (which acts as a Part)
                        current_turn_parts.append(uploaded_file)
                        logger.info(f"Session file '{filename}' uploaded, URI: {uploaded_file.uri}")
                        # Add info for DB history (don't include content)
                        files_info_for_history.append(f"[Session File Attached: '{filename}' ({mimetype})]")
                    except Exception as api_upload_err:
                        logger.error(f"Error uploading session file '{filename}' to Gemini API: {api_upload_err}")
                        # Handle specific errors like invalid key
                        if "api key not valid" in str(api_upload_err).lower():
                             g.gemini_api_key_invalid = True
                             current_turn_parts.append(f"[System: Error uploading session file '{filename}' - Invalid API Key]")
                             files_info_for_history.append(f"[Session File Upload Failed (Invalid Key): '{filename}']")
                        else:
                             current_turn_parts.append(f"[System: Error processing session file '{filename}'. Upload failed.]")
                             files_info_for_history.append(f"[Session File Upload Failed: '{filename}']")

                except (base64.binascii.Error, ValueError) as decode_err:
                     logger.error(f"Error decoding base64 for session file '{filename}': {decode_err}")
                     current_turn_parts.append(f"[System: Error decoding session file '{filename}'.]")
                     files_info_for_history.append(f"[Session File Decoding Failed: '{filename}']")
                except Exception as processing_err:
                    logger.error(f"Error processing session file '{filename}' for Gemini: {processing_err}")
                    current_turn_parts.append(f"[System: Error processing session file '{filename}'.]")
                    files_info_for_history.append(f"[Session File Processing Failed: '{filename}']")

        # --- Process Attached (Permanent) Files ---
        if attached_files:
            logger.info(f"Processing {len(attached_files)} attached permanent files for chat {chat_id}...")
            for file_info in attached_files:
                file_id = file_info.get("id")
                attach_type = file_info.get("type", "full")
                filename = file_info.get("filename", f"file_{file_id}") # Get filename early
                history_marker = f"[File Attached ({attach_type}): '{filename}' (ID: {file_id})]"

                if not file_id:
                     logger.warning("Skipping attached file due to missing ID.")
                     files_info_for_history.append("[Attached File Skipped (Missing ID)]")
                     continue

                if attach_type == "summary":
                    logger.info(f"Fetching or generating summary for file ID: {file_id}")
                    summary = get_or_generate_summary(file_id) # This handles internal checks/errors
                    if isinstance(summary, str) and not summary.startswith("[Error"):
                        current_turn_parts.append(f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---")
                        files_info_for_history.append(history_marker)
                    else:
                        # Append error message from summary generation to parts and history
                        error_msg = summary if isinstance(summary, str) else "[Unknown Summary Error]"
                        current_turn_parts.append(f"[System: Error retrieving summary for file '{filename}'. {error_msg}]")
                        files_info_for_history.append(f"[Error retrieving summary: '{filename}']")

                elif attach_type == "full":
                    logger.info(f"Processing full attachment for file ID: {file_id}")
                    try:
                        # Fetch file content from DB
                        file_details = database.get_file_details_from_db(file_id, include_content=True)
                        if not file_details or not file_details.get("content"):
                            logger.error(f"Could not retrieve content for attached file ID: {file_id}")
                            current_turn_parts.append(f"[System: Error retrieving content for file '{filename}'.]")
                            files_info_for_history.append(f"[Error retrieving content: '{filename}']")
                            continue

                        content_blob = file_details["content"]
                        mimetype = file_details.get("mimetype", "application/octet-stream")

                        # Write to temp file
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=f"_attach_{secure_filename(filename)}"
                        ) as temp_file:
                            temp_file.write(content_blob)
                            temp_filepath = temp_file.name
                            temp_files_to_clean.append(temp_filepath)

                        logger.info(f"Uploading temp attachment file '{temp_filepath}' for '{filename}' via API...")
                        try:
                            # Use the client to upload the file
                            uploaded_file = client.files.upload(
                                path=temp_filepath,
                                display_name=filename # Removed mime_type
                            )
                            current_turn_parts.append(uploaded_file) # Append the file object
                            logger.info(f"Attachment '{filename}' uploaded, URI: {uploaded_file.uri}")
                            files_info_for_history.append(history_marker)
                        except Exception as api_upload_err:
                            logger.error(f"Error uploading attachment '{filename}' to Gemini API: {api_upload_err}")
                            if "api key not valid" in str(api_upload_err).lower():
                                 g.gemini_api_key_invalid = True
                                 current_turn_parts.append(f"[System: Error uploading file '{filename}' - Invalid API Key]")
                                 files_info_for_history.append(f"[File Upload Failed (Invalid Key): '{filename}']")
                            else:
                                 current_turn_parts.append(f"[System: Error processing file '{filename}'. Upload failed.]")
                                 files_info_for_history.append(f"[File Upload Failed: '{filename}']")

                    except Exception as processing_err:
                        logger.error(f"Error processing attachment file ID {file_id} ('{filename}') for Gemini: {processing_err}", exc_info=True)
                        current_turn_parts.append(f"[System: Error processing file '{filename}'.]")
                        files_info_for_history.append(f"[File Processing Failed: '{filename}']")
                else:
                     logger.warning(f"Unknown attachment type '{attach_type}' for file ID {file_id}")
                     files_info_for_history.append(f"[Unknown Attachment Type: '{filename}']")


        # --- Web Search ---
        if enable_web_search:
             logger.info("Web search enabled, generating query...")
             search_query = generate_search_query(user_message) # Calls decorated function
             if search_query:
                 logger.info(f"Performing web search with query: '{search_query}'")
                 search_results = perform_web_search(search_query) # Assuming this returns a string
                 if search_results:
                      logger.info("Appending web search results to context.")
                      current_turn_parts.extend([
                           "--- Start Web Search Results ---",
                           search_results,
                           "--- End Web Search Results ---"
                      ])
                      files_info_for_history.append(f"[Web Search Performed: '{search_query}']")
                 else:
                      logger.info("Web search executed but returned no results.")
                      current_turn_parts.append("[System Note: Web search yielded no results.]")
                      files_info_for_history.append(f"[Web Search No Results: '{search_query}']")
             else:
                 logger.info("Web search enabled but query generation failed.")
                 current_turn_parts.append("[System Note: Could not generate a suitable web search query.]")
                 files_info_for_history.append("[Web search query generation failed]")

        # --- Add user text message LAST to the current turn's parts ---
        if user_message:
            current_turn_parts.append(user_message)
        elif not current_turn_parts:
             # If there's no user message and no files/context were added, it's an empty turn
             logger.warning(f"Empty user message and no files/context for chat {chat_id}. Aborting turn.")
             # Don't save anything, just return an indication?
             return "[System: Empty message received. Please provide input or attach files.]"


        # --- Save user message (including file markers) to DB BEFORE calling AI ---
        # This ensures the user message is saved even if the AI call fails
        history_message_content = (
            "\n".join(files_info_for_history) # File markers first
            + ("\n" if files_info_for_history and user_message else "") # Add newline if both exist
            + (user_message if user_message else "") # Add user text if it exists
        )
        # Ensure we don't save an empty message if only file errors occurred
        if history_message_content.strip() or user_message: # Check if there's actual content
             if not database.add_message_to_db(chat_id, "user", history_message_content):
                 logger.warning(f"Failed to save user message for chat {chat_id}.")
                 # Proceed with AI call anyway? Or return error? For now, proceed.
        else:
             logger.info(f"Skipping saving empty user turn history for chat {chat_id}.")


        # --- Gemini Interaction ---
        assistant_reply = "[AI response error occurred]"
        model_to_use = primary_model_name
        fallback_triggered = False
        system_instruction = chat_details.get("system_instruction") # Get system instruction if set
        response = None # Initialize response to None

        try:
            # --- History Preparation ---
            logger.info(f"Fetching history for chat {chat_id}...")
            history_for_gemini_raw = database.get_chat_history_from_db(
                chat_id, limit=current_app.config.get("CHAT_HISTORY_LIMIT", 20)
            )
            # Convert DB history to Gemini's expected Content format
            gemini_context = []
            for msg in history_for_gemini_raw:
                 # Skip empty messages just in case
                 if not msg.get("content") or msg["content"].isspace():
                      continue
                 role = "model" if msg["role"] == "assistant" else msg["role"] # Map 'assistant' to 'model'
                 gemini_context.append(Content(role=role, parts=[Part.from_text(msg["content"])]))

            # --- Construct Full Request ---
            # Combine history, current turn parts, and optional system instruction
            full_request_contents = gemini_context + [Content(role="user", parts=current_turn_parts)]

            # --- Logging Request ---
            logger.info(
                f"--- Sending to Gemini (Chat ID: {chat_id}, Model: {model_to_use}) ---"
            )
            # Log history turns
            for i, content in enumerate(gemini_context):
                logger.debug(f"  History Turn {i} ({content.role}): {str(content.parts)[:150]}...")
            # Log current turn parts (handle file objects)
            current_parts_log = []
            for part in current_turn_parts:
                 if isinstance(part, str):
                      current_parts_log.append(part[:150] + ('...' if len(part) > 150 else ''))
                 elif hasattr(part, 'uri'): # Check if it looks like a FileData object
                      current_parts_log.append(f"[File URI: {part.uri}]")
                 else:
                      current_parts_log.append("[Unknown Part Type]")
            logger.debug(f"  Current Turn (user): {' | '.join(current_parts_log)}")
            if system_instruction:
                 logger.debug(f"  System Instruction: {system_instruction[:150]}...")


            # --- API Call ---
            # timeout = current_app.config.get("GEMINI_REQUEST_TIMEOUT", 300) # Timeout removed from call
            generation_config = GenerationConfig( # Example config, adjust as needed
                 temperature=chat_details.get("temperature", 0.7),
                 top_p=chat_details.get("top_p", 0.95),
                 top_k=chat_details.get("top_k", 40),
                 max_output_tokens=chat_details.get("max_output_tokens", 2048),
            )

            try:
                # Use the client.models attribute to generate content
                response = client.models.generate_content( # CORRECTED: Added .models
                    model=model_to_use,
                    contents=full_request_contents,
                    generation_config=generation_config,
                    system_instruction=system_instruction if system_instruction else None, # Pass system instruction if present
                    # request_options={"timeout": timeout}, # REMOVED: This argument caused TypeError
                )
            except NotFound as e:
                 # --- Model Fallback Logic ---
                 logger.warning(f"Model '{model_to_use}' not found. Attempting fallback.")
                 raw_fallback_model_name = current_app.config["DEFAULT_MODEL"]
                 fallback_model_name = f"models/{raw_fallback_model_name}" if not raw_fallback_model_name.startswith("models/") else raw_fallback_model_name

                 if fallback_model_name != model_to_use: # Avoid infinite loop if default is the same
                     logger.info(f"Trying fallback model: '{fallback_model_name}'")
                     model_to_use = fallback_model_name # Update model for the next attempt
                     fallback_triggered = True
                     # Retry the API call with the fallback model
                     response = client.models.generate_content( # CORRECTED: Added .models
                         model=model_to_use,
                         contents=full_request_contents,
                         generation_config=generation_config,
                         system_instruction=system_instruction if system_instruction else None,
                         # request_options={"timeout": timeout}, # REMOVED: This argument caused TypeError
                     )
                     logger.info(f"Successfully generated response with fallback model '{model_to_use}'.")
                 else:
                     logger.error(f"Primary model '{model_to_use}' not found, and it is the default. Cannot fall back.")
                     raise e # Re-raise the NotFound error if primary is the default

            # --- Process Response ---
            # Check for blocked prompt/response *before* accessing text
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                 block_reason = response.prompt_feedback.block_reason
                 logger.warning(f"Prompt blocked for chat {chat_id}, reason: {block_reason}")
                 assistant_reply = f"[Error: Request blocked by safety settings (Reason: {block_reason})]"
            elif response.candidates and response.candidates[0].finish_reason != "STOP":
                 # Check if generation finished normally
                 finish_reason = response.candidates[0].finish_reason
                 logger.warning(f"Generation stopped for chat {chat_id}, reason: {finish_reason}")
                 # Try to get text anyway, but add a warning
                 partial_reply = response.text
                 assistant_reply = f"[Warning: AI response may be incomplete (Reason: {finish_reason})]\n{partial_reply}"
                 if finish_reason == "SAFETY":
                      assistant_reply = f"[Error: Response blocked by safety settings (Reason: {finish_reason})]"
                 elif finish_reason == "MAX_TOKENS":
                      assistant_reply = f"[Warning: AI response truncated due to maximum length.]\n{partial_reply}"

            else:
                 # Normal successful response
                 assistant_reply = response.text
                 logger.info(f"Gemini Response (Chat {chat_id}): {assistant_reply[:100]}...")

            # Prepend system message about fallback if it happened
            if fallback_triggered:
                 assistant_reply = f"[System: Using default model '{model_to_use}' due to issue with primary model.]\n\n{assistant_reply}"


        # --- Error Handling for Gemini Call ---
        except TypeError as e:
             logger.error(f"TypeError during chat response generation: {e}. Check SDK method signature.", exc_info=True)
             assistant_reply = f"[Error generating chat response: SDK usage error ({type(e).__name__}).]"
        except AttributeError as e:
             logger.error(f"AttributeError during chat response generation: {e}. Check SDK usage.", exc_info=True)
             assistant_reply = f"[Error generating chat response: SDK usage error ({type(e).__name__}).]"
        except DeadlineExceeded:
            logger.error(f"Gemini API request timed out for chat {chat_id} with model {model_to_use}.")
            assistant_reply = "[Error: AI request timed out. The operation took too long.]"
        except NotFound as e:
             # This handles the case where the fallback model *also* isn't found
             logger.error(f"Model '{model_to_use}' not found or inaccessible: {e}")
             assistant_reply = f"[Error: AI Model '{model_to_use.replace('models/','')}' not found or access denied.]"
        except GoogleAPIError as e:
            logger.error(f"Google API error during chat generation for chat {chat_id} with model {model_to_use}: {e}")
            error_message = f"[Error communicating with AI ({type(e).__name__})]" # Default
            err_str = str(e).lower()
            if "api key not valid" in err_str:
                g.gemini_api_key_invalid = True # Mark key as bad
                error_message = "[Error: Invalid Gemini API Key.]"
            elif "token" in err_str or "size" in err_str or "request payload size" in err_str or "400" in err_str:
                # Check if it might be context length
                if "context length" in err_str:
                     error_message = "[Error: Request too large (Context Length). Try a new chat or fewer attachments.]"
                else:
                     error_message = "[Error: Request too large or invalid. Try summaries or fewer/smaller files.]"
            elif "prompt was blocked" in err_str: # Should be caught by prompt_feedback check, but belt-and-suspenders
                 feedback_reason = "N/A"
                 try:
                      if response and response.prompt_feedback: # Check if response exists
                           feedback_reason = response.prompt_feedback.block_reason
                 except Exception: pass # Ignore errors getting feedback
                 error_message = f"[Error: Request blocked by safety settings (Reason: {feedback_reason})]"
            elif "resource has been exhausted" in err_str or "quota" in err_str:
                error_message = "[Error: API quota exceeded. Please try again later.]"
            elif "429" in err_str or "rate limit" in err_str:
                 error_message = "[Error: Too many requests (Rate Limit). Please try again later.]"
            # Use the generated error message
            assistant_reply = error_message

        except Exception as e:
            logger.error(
                f"Unexpected error calling Gemini API for chat {chat_id} with model {model_to_use}: {e}", exc_info=True
            )
            assistant_reply = f"[Unexpected AI Error: {type(e).__name__}]"

        # --- Save Assistant Reply ---
        # Ensure we save even if it's an error message
        if not database.add_message_to_db(chat_id, "assistant", assistant_reply):
             logger.warning(f"Failed to save assistant message for chat {chat_id}.")

        return assistant_reply

    finally:
        # --- Clean up temporary files ---
        if temp_files_to_clean:
            logger.info(f"Cleaning up {len(temp_files_to_clean)} temporary files for chat {chat_id}...")
            for temp_path in temp_files_to_clean:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        logger.debug(f"Removed temp file: {temp_path}") # Debug level for successful cleanup
                    else:
                        logger.debug(f"Temp file not found, already removed? {temp_path}")
                except OSError as e:
                    logger.warning(f"Error removing temp file {temp_path}: {e}")

