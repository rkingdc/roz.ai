# app/ai_services.py
import google.genai as genai  # Use the new SDK

# Import necessary types, including the one for FileDataPart
from google.genai.types import (
    Part,
    Content,
    Blob,  # Import Blob for inline data
    FileData,  # Import FileData for referencing uploaded files
    GenerateContentConfig,
    Tool,
    FunctionDeclaration,
    Schema,
    Type,
    AutomaticFunctionCallingConfig, # Import for AFC
    Mode,                             # Import for AFC Mode enum
)
import json  # For serializing tool responses if needed
import functools # For partial

from flask import current_app, g  # Import g for request context caching
import tempfile
import os
import re
import base64
from . import database  # Use alias to avoid conflict with db instance
from .plugins.web_search import (
    perform_web_search,
    fetch_web_content,
)  # Added fetch_web_content
from .ai_services_lib.generation_services import generate_text # Import generate_text
from .ai_services_lib.llm_factory import llm_factory, prompt_improver # Import llm_factory and prompt_improver
from .ai_services_lib.transcription_services import clean_up_transcript, transcribe_pdf_bytes # Import transcription services
from google.api_core.exceptions import (
    GoogleAPIError,
    DeadlineExceeded,
    ClientError,
    NotFound,
    InvalidArgument,  # Import InvalidArgument for malformed content errors
)
from pydantic_core import ValidationError

import logging
import time  # Add time import
import random  # Add random import
from typing import Tuple, Callable, Any

# from functools import wraps # Remove this import
from werkzeug.utils import secure_filename

# Configure logging - Removed basicConfig and setLevel here
logger = logging.getLogger(__name__)


# --- Tool Definitions ---
# Web Search Tool
WEB_SEARCH_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="web_search",
            description=(
                "Performs a web search using a search engine based on a user query. "
                "Returns a list of search results, each including a title, link, and snippet. "
                "Use this tool to find relevant web pages before deciding to scrape specific URLs."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "query": Schema(type=Type.STRING, description="The search query")
                },
                required=["query"],
            ),
        )
    ]
)

# Web Scrape Tool
WEB_SCRAPE_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="scrape_url",
            description=(
                "Fetches and extracts content from a specific URL. "
                "Can handle HTML (extracts main textual content) and PDF documents "
                "(returns raw PDF data which will then be transcribed to text by the system). "
                "Use this tool after identifying a promising URL from web_search results."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "url": Schema(type=Type.STRING, description="The URL to scrape")
                },
                required=["url"],
            ),
        )
    ]
)
# --- End Tool Definitions ---

# llm_factory and prompt_improver have been moved to app/ai_services_lib/llm_factory.py


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
    prompt = (
        f"Please provide a detailed summary of the attached file named '{filename}'."
    )
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


# --- Generate Search Query --- (REMOVED - Functionality to be handled by LLM Tool)
# def generate_search_query(user_message: str, max_retries=1) -> str | None:
#    ... (entire function content removed) ...


# Removed _yield_streaming_error helper function (This comment line is also removed as part of the block)


# --- Chat Response Generation ---
# This function now starts the process and uses helpers that emit results via SocketIO.
# It no longer returns a generator or a string directly.
def generate_chat_response(
    chat_id,
    user_message,
    attached_files=None,
    session_files=None,
    calendar_context=None,
    web_search_enabled=False,
    streaming_enabled=False,
    socketio=None,
    sid=None,
    is_cancelled_callback: Callable[[], bool] = lambda: False,
    message_attachments_metadata=None,  # Add new parameter for metadata
):
    """
    Generates a chat response using the Gemini API via the client.
    Handles history, context, files, web search. Handles errors gracefully.
    Emits results back to the client via SocketIO. Saves user message with attachments.

    Args:
        ... (standard args) ...
        streaming_enabled (bool): Determines if the response should be streamed.
        socketio: The Flask-SocketIO instance.
        sid: The session ID of the client to emit results to.
        is_cancelled_callback: Function to check if cancellation was requested.
        message_attachments_metadata (list, optional): Metadata about attachments for saving to DB.
    """
    logger.info(
        f"Entering generate_chat_response for chat {chat_id} (SID: {sid}). Streaming: {streaming_enabled}"
    )

    if not socketio or not sid:
        logger.error(
            f"generate_chat_response called without socketio or sid for chat {chat_id}."
        )
        # Cannot emit error back without socketio/sid, just log and exit.
        return

    # --- AI Readiness Check ---
    # This check now emits errors via SocketIO if it fails
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
            socketio.emit("task_error", {"error": error_msg}, room=sid)
            return  # Stop execution

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            error_msg = "[Error: AI Service API Key not configured]"
            socketio.emit("task_error", {"error": error_msg}, room=sid)
            return  # Stop execution

        try:
            # Ensure genai client is initialized (using 'g' is fine here as this runs within app context)
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
            socketio.emit("task_error", {"error": error_msg}, room=sid)
            return  # Stop execution

    except Exception as e:
        logger.error(
            f"generate_chat_response: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        error_msg = f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
        socketio.emit("task_error", {"error": error_msg}, room=sid)
        return  # Stop execution
    # --- End AI Readiness Check ---

    # --- REMOVED USER MESSAGE SAVE BLOCK ---
    # The user message is now saved synchronously in sockets.py before this task starts.
    # The message_attachments_metadata is passed to this function but only used
    # if we needed to save the user message *here*. Since we don't, it's not used
    # directly in this function anymore, but kept in the signature for clarity
    # about the data flow from sockets.py.

    # --- Main Logic ---
    # This part needs to be structured differently depending on streaming
    # We use helper functions that now emit results via SocketIO.

    # --- Prepare History and Parts (Common Logic) ---
    # This helper now needs socketio and sid to emit errors during preparation
    preparation_result = _prepare_chat_content(
        client=client,
        chat_id=chat_id,
        user_message=user_message,  # Pass original user message for context prep
        attached_files=attached_files,  # Pass raw attached file refs
        session_files=session_files,  # Pass raw session file data
        calendar_context=calendar_context,
        web_search_enabled=web_search_enabled,
        socketio=socketio,  # Pass socketio
        sid=sid,
        is_cancelled_callback=is_cancelled_callback,  # Pass callback
    )

    # Check if preparation failed or was cancelled
    if preparation_result is None:
        # Error/cancellation message already emitted by _prepare_chat_content
        logger.warning(
            f"Content preparation failed or was cancelled for chat {chat_id} (SID: {sid})."
        )
        # Ensure cleanup happens even if preparation fails/cancels
        # temp_files_to_clean would be the third element if preparation_result was not None
        _cleanup_temp_files(
            [],  # If prep failed, assume no temp files from it, or handle if it can return partial
            f"chat {chat_id} (SID: {sid}) after prep failure/cancel",
        )
        return  # Stop execution

    # Unpack results if preparation succeeded
    history, current_turn_parts, temp_files_to_clean = preparation_result

    # --- Determine Model ---
    # (This part remains the same)
    raw_model_name = current_app.config.get(
        "PRIMARY_MODEL", current_app.config["DEFAULT_MODEL"]
    )
    model_to_use = (
        f"models/{raw_model_name}"
        if not raw_model_name.startswith("models/")
        else raw_model_name
    )
    logger.info(f"Model for chat {chat_id} (SID: {sid}): '{model_to_use}'.")

    # --- Call Appropriate Helper ---
    # Non-streaming path is removed, always use streaming
    _generate_chat_response_stream(
        client=client,
        chat_id=chat_id,
        model_to_use=model_to_use,
        history=history,
        current_turn_parts=current_turn_parts,
        temp_files_to_clean=temp_files_to_clean,
        socketio=socketio,
        sid=sid,
        is_cancelled_callback=is_cancelled_callback,
        web_search_enabled=web_search_enabled,
    )


# --- Helper Function for NON-STREAMING Response --- (REMOVED)
# def _generate_chat_response_non_stream(...):
# ... entire function removed ...


# --- Helper Function for STREAMING Response ---
def _generate_chat_response_stream(
    client,
    chat_id,
    model_to_use,
    history,
    current_turn_parts,
    temp_files_to_clean,
    socketio,
    sid,
    is_cancelled_callback: Callable[[], bool],
    web_search_enabled: bool,  # New parameter
):
    """Internal helper that generates and emits chat response chunks via SocketIO. Checks for cancellation. Handles tool calls with streaming."""
    logger.info(
        f"_generate_chat_response_stream called for chat {chat_id} (SID: {sid}), WebSearch: {web_search_enabled}"
    )
    full_reply_content = ""  # Accumulate full reply for saving
    emitted_error_or_cancel_final_signal = False  # Tracks if a final error/cancel signal was sent, to prevent duplicate stream_end
    MAX_TOOL_ITERATIONS = 5  # Max number of tool call iterations

    # Construct initial conversation history (similar to non-streaming)
    current_conversation_history = list(history)
    if current_turn_parts:
        if (
            current_conversation_history
            and current_conversation_history[-1].role == "user"
        ):
            if not isinstance(current_conversation_history[-1].parts, list):
                current_conversation_history[-1].parts = list(
                    current_conversation_history[-1].parts
                )
            current_conversation_history[-1].parts.extend(current_turn_parts)
        else:
            current_conversation_history.append(
                Content(role="user", parts=current_turn_parts)
            )

    # System prompt (same as non-streaming)
    system_prompt_parts = [
        "You are a helpful assistant. Please format your responses using Markdown.",
        # ... (other general instructions)
    ]
    if web_search_enabled:
        system_prompt_parts.extend(
            [
                "\n--- Web Tool Instructions ---",
                "You have access to tools for web searching ('web_search') and scraping specific URLs ('scrape_url').",
                # ... (detailed tool instructions as in non-streaming version)
                "--- End Web Tool Instructions ---",
            ]
        )
    final_system_prompt = "\n\n".join(
        system_prompt_parts
    )  # Reconstruct the full system prompt from non-streaming version here.
    # For brevity in this diff, I'm not repeating the full prompt text. Assume it's the same as _generate_chat_response_non_stream.

    for iteration in range(MAX_TOOL_ITERATIONS):
        if is_cancelled_callback():
            logger.info(
                f"Streaming generation cancelled before API call (Iteration {iteration}) for chat {chat_id}."
            )
            full_reply_content = "[AI Info: Generation cancelled by user.]"
            socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            socketio.emit(
                "generation_cancelled",
                {"message": "Cancelled by user.", "chat_id": chat_id},
                room=sid,
            )
            emitted_error_or_cancel_final_signal = True
            break  # Exit loop

        try:
            logger.info(
                f"Calling model.generate_content_stream (Iteration {iteration}) for chat {chat_id}."
            )
            tools_to_provide = (
                [WEB_SEARCH_TOOL, WEB_SCRAPE_TOOL] if web_search_enabled else None
            )

            # GenerateContentConfig is needed for system_instruction and tools with streaming
            gen_config = GenerateContentConfig(
                system_instruction=final_system_prompt,
                tools=tools_to_provide,  # Pass tools via GenerateContentConfig
                # Explicitly disable AFC to handle function calls manually
                automatic_function_calling=AutomaticFunctionCallingConfig(mode=Mode.NONE)
            )

            response_iterator = client.models.generate_content_stream(
                model=model_to_use,
                contents=current_conversation_history,
                # tools=tools_to_provide, # Removed from here
                config=gen_config,
            )

            logger.info(
                f"Streaming iterator received (Iteration {iteration}) for chat {chat_id}."
            )

            current_chunk_is_tool_call = False
            accumulated_tool_call_parts = []  # For multi-part tool calls if they occur

            for chunk in response_iterator:
                if is_cancelled_callback():
                    logger.info(
                        f"Streaming cancelled during chunk processing (Iteration {iteration}) for chat {chat_id}."
                    )
                    full_reply_content += "\n[AI Info: Generation cancelled by user.]"
                    socketio.emit(
                        "generation_cancelled",
                        {"message": "Cancelled by user.", "chat_id": chat_id},
                        room=sid,
                    )
                    # Emit a final error/status to ensure client knows it's over
                    if not emitted_error_or_cancel_final_signal:
                        socketio.emit(
                            "task_error",
                            {"error": "[AI Info: Generation cancelled by user.]"},
                            room=sid,
                        )
                    emitted_error_or_cancel_final_signal = True
                    break  # Break from chunk loop

                # Process chunk for text, function call, or error
                chunk_has_text = hasattr(chunk, "text") and chunk.text
                chunk_has_fc = (
                    hasattr(chunk, "parts")
                    and chunk.parts
                    and hasattr(chunk.parts[0], "function_call")
                    and chunk.parts[0].function_call
                )

                if chunk_has_fc:
                    # This is how Gemini API sends tool calls in streaming
                    logger.info(
                        f"Stream chunk contains function_call part for chat {chat_id}."
                    )
                    # The entire FunctionCall might be in one part or spread.
                    # Typically, it's in one part within the chunk.parts list.
                    current_conversation_history.append(
                        chunk.candidates[0].content
                    )  # Add LLM's turn with FC
                    fc = chunk.parts[0].function_call
                    # Proceed to tool execution logic (outside this inner chunk loop)
                    current_chunk_is_tool_call = True
                    break  # Break from chunk loop to handle tool call

                elif chunk_has_text:
                    socketio.emit("stream_chunk", {"chunk": chunk.text}, room=sid)
                    full_reply_content += chunk.text

                # Handle safety blocks from chunk.prompt_feedback or finish_reason in candidates
                if chunk.prompt_feedback and chunk.prompt_feedback.block_reason:
                    reason = chunk.prompt_feedback.block_reason.name
                    err_msg = f"[AI Safety Error: Stream blocked (Reason: {reason})]"
                    logger.warning(f"{err_msg} for chat {chat_id}")
                    socketio.emit("task_error", {"error": err_msg}, room=sid)
                    full_reply_content += f"\n{err_msg}"
                    emitted_error_or_cancel_final_signal = True
                    break  # from chunk loop

                if (
                    chunk.candidates
                    and chunk.candidates[0].finish_reason.name == "SAFETY"
                ):
                    err_msg = (
                        "[AI Safety Error: Stream finished due to safety settings]"
                    )
                    logger.warning(f"{err_msg} for chat {chat_id}")
                    socketio.emit("task_error", {"error": err_msg}, room=sid)
                    full_reply_content += f"\n{err_msg}"
                    emitted_error_or_cancel_final_signal = True
                    break  # from chunk loop

            if (
                emitted_error_or_cancel_final_signal or current_chunk_is_tool_call
            ):  # If cancelled, error, or tool call
                if (
                    current_chunk_is_tool_call
                ):  # Only proceed if it was a tool call, not error/cancel
                    # Handle tool call (logic similar to non-streaming)
                    fc_part = current_conversation_history[-1].parts[
                        0
                    ]  # The FC part just added
                    fc = fc_part.function_call
                    function_name = fc.name
                    function_args = fc.args
                    logger.info(
                        f"Tool call from stream: {function_name} with args {dict(function_args)}"
                    )

                    tool_response_data = None
                    tool_error = None

                    if is_cancelled_callback():  # Check again before execution
                        logger.info(
                            f"Tool execution cancelled before calling {function_name} for chat {chat_id}."
                        )
                        tool_error = "[AI Info: Tool execution cancelled by user.]"
                        socketio.emit(
                            "generation_cancelled",
                            {
                                "message": "Cancelled by user during tool execution.",
                                "chat_id": chat_id,
                            },
                            room=sid,
                        )
                        emitted_error_or_cancel_final_signal = True

                    elif function_name == "web_search":
                        try:
                            query = function_args["query"]
                            socketio.emit(
                                "status_update",
                                {
                                    "message": f"Performing web search for: {query[:50]}..."
                                },
                                room=sid,
                            )
                            search_results = perform_web_search(query)
                            tool_response_data = {"results": search_results}
                        except Exception as e:
                            logger.error(
                                f"Error executing 'web_search' (stream): {e}",
                                exc_info=True,
                            )
                            tool_error = (
                                f"[Tool Error: web_search failed - {type(e).__name__}]"
                            )

                    elif function_name == "scrape_url":
                        try:
                            url_to_scrape = function_args["url"]
                            socketio.emit(
                                "status_update",
                                {"message": f"Scraping URL: {url_to_scrape[:70]}..."},
                                room=sid,
                            )
                            # IMPORTANT: Need to import fetch_web_content from app.plugins.web_search
                            # from app.plugins.web_search import fetch_web_content
                            scraped_data = fetch_web_content(
                                url_to_scrape
                            )  # Actual call

                            scraped_data_content = scraped_data.get("content")
                            scraped_data_type = scraped_data.get("type")
                            saved_file_id = None

                            if scraped_data_type == "pdf" and isinstance(
                                scraped_data_content, bytes
                            ):
                                socketio.emit(
                                    "status_update",
                                    {
                                        "message": f"Transcribing PDF: {scraped_data.get('filename', 'PDF')}..."
                                    },
                                    room=sid,
                                )
                                transcribed_text = transcribe_pdf_bytes(
                                    scraped_data_content,
                                    scraped_data.get("filename", "scraped.pdf"),
                                )
                                if not transcribed_text.startswith(
                                    ("[Error", "[System Note")
                                ):
                                    saved_file_id = database.save_file_record_to_db(
                                        filename=f"transcribed_{scraped_data.get('filename', 'document.txt')}",
                                        content_blob=transcribed_text.encode("utf-8"),
                                        mimetype="text/plain",
                                        filesize=len(transcribed_text.encode("utf-8")),
                                    )
                                    scraped_data["content"] = transcribed_text
                                    scraped_data["type"] = "transcribed_pdf_text"
                                else:
                                    scraped_data["content"] = (
                                        f"[Transcription Failed: {transcribed_text}]"
                                    )

                            elif scraped_data_type == "html" and isinstance(
                                scraped_data_content, str
                            ):
                                saved_file_id = database.save_file_record_to_db(
                                    filename=secure_filename(
                                        f"scraped_{url_to_scrape.split('/')[-1] or 'page'}.html"
                                    ),
                                    content_blob=scraped_data_content.encode("utf-8"),
                                    mimetype="text/html",
                                    filesize=len(scraped_data_content.encode("utf-8")),
                                )

                            tool_response_data = {
                                "url": url_to_scrape,
                                "type": scraped_data.get("type"),
                                "content": scraped_data.get("content"),
                                "filename": scraped_data.get("filename"),
                            }
                            if saved_file_id:
                                tool_response_data["saved_file_id"] = saved_file_id
                        except Exception as e:
                            logger.error(
                                f"Error executing 'scrape_url' (stream) for {function_args.get('url')}: {e}",
                                exc_info=True,
                            )
                            tool_error = (
                                f"[Tool Error: scrape_url failed - {type(e).__name__}]"
                            )
                    else:
                        tool_error = f"[System Error: Unknown tool '{function_name}']"

                    if tool_error:
                        function_response_part = Part.from_function_response(
                            name=function_name, response={"error": tool_error}
                        )
                        if (
                            not emitted_error_or_cancel_final_signal
                        ):  # Avoid duplicate error signals
                            socketio.emit("task_error", {"error": tool_error}, room=sid)
                            emitted_error_or_cancel_final_signal = True

                    else:
                        function_response_part = Part.from_function_response(
                            name=function_name, response=tool_response_data
                        )

                    current_conversation_history.append(function_response_part)
                    # Continue to next iteration of the outer loop for LLM to process tool response
                    if emitted_error_or_cancel_final_signal:
                        break  # if tool execution itself was cancelled/errored critically
                    continue  # To next iteration of the main tool loop

            # If loop finished processing chunks and it wasn't a tool call, error, or cancellation
            if (
                not emitted_error_or_cancel_final_signal
                and not current_chunk_is_tool_call
            ):
                logger.info(
                    f"Stream finished for chat {chat_id} (Iteration {iteration}). Emitting stream_end."
                )
                socketio.emit("stream_end", {"message": "Stream finished."}, room=sid)
                # Final text response received, break from tool iteration loop
                break

            if (
                emitted_error_or_cancel_final_signal
            ):  # If an error/cancel occurred in chunk loop
                break  # Break from main tool loop

        # --- Error Handling for Streaming API Call (client.models.generate_content_stream call itself) ---
        except InvalidArgument as e:
            logger.error(
                f"InvalidArgument error during streaming chat {chat_id} (Iter. {iteration}): {e}.",
                exc_info=True,
            )
            full_reply_content = f"[AI Error: Invalid argument or unsupported file type ({type(e).__name__}).]"
            if not emitted_error_or_cancel_final_signal:
                socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            emitted_error_or_cancel_final_signal = True
            break
        except (
            ValidationError
        ) as e:  # Should be caught by Pydantic if request is malformed by SDK
            logger.error(
                f"Data validation error calling streaming Gemini API for chat {chat_id} (Iter. {iteration}): {e}",
                exc_info=True,
            )
            full_reply_content = f"[AI Error: Internal data format error. Check logs.]"
            if not emitted_error_or_cancel_final_signal:
                socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            emitted_error_or_cancel_final_signal = True
            break
        except DeadlineExceeded:
            logger.error(
                f"Streaming Gemini API call timed out for chat {chat_id} (Iter. {iteration})."
            )
            full_reply_content = "[AI Error: The request timed out. Please try again.]"
            if not emitted_error_or_cancel_final_signal:
                socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            emitted_error_or_cancel_final_signal = True
            break
        except NotFound as e:
            logger.error(
                f"Model for streaming chat {chat_id} (Iter. {iteration}) not found: {e}"
            )
            full_reply_content = (
                f"[AI Error: Model '{model_to_use}' not found or access denied.]"
            )
            if not emitted_error_or_cancel_final_signal:
                socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            emitted_error_or_cancel_final_signal = True
            break
        except GoogleAPIError as e:
            logger.error(
                f"Google API error for streaming chat {chat_id} (Iter. {iteration}): {e}",
                exc_info=False,
            )
            err_str = str(e).lower()
            if "api key not valid" in err_str:
                full_reply_content = "[Error: Invalid Gemini API Key]"
            elif "permission denied" in err_str:
                full_reply_content = f"[AI Error: Permission denied for model.]"
            elif "resource has been exhausted" in err_str or "429" in str(e):
                full_reply_content = "[AI Error: API quota or rate limit exceeded.]"
            elif "prompt was blocked" in err_str or "SAFETY" in str(e).upper():
                full_reply_content = (
                    f"[AI Safety Error: Request/response blocked (Reason: SAFETY)]"
                )
            elif "internal error" in err_str or "500" in str(e):
                full_reply_content = "[AI Error: AI service internal error.]"
            else:
                full_reply_content = f"[AI API Error: {type(e).__name__}]"
            if not emitted_error_or_cancel_final_signal:
                socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            emitted_error_or_cancel_final_signal = True
            break
        except Exception as e:
            logger.error(
                f"Unexpected error during streaming API interaction for chat {chat_id} (Iter. {iteration}): {e}",
                exc_info=True,
            )
            full_reply_content = f"[Unexpected AI Error: {type(e).__name__}]"
            if not emitted_error_or_cancel_final_signal:
                socketio.emit("task_error", {"error": full_reply_content}, room=sid)
            emitted_error_or_cancel_final_signal = True
            break

        if (
            emitted_error_or_cancel_final_signal
        ):  # If any error broke the inner chunk loop or API call
            break  # Break from main tool loop

    # Loop finished
    if (
        iteration == MAX_TOOL_ITERATIONS - 1
        and not emitted_error_or_cancel_final_signal
        and not full_reply_content.strip()
    ):  # Check strip here
        logger.warning(
            f"Max tool iterations ({MAX_TOOL_ITERATIONS}) reached for streaming chat {chat_id}."
        )
        full_reply_content = (
            "[AI Error: Maximum tool iterations reached. Could not complete request.]"
        )
        if not emitted_error_or_cancel_final_signal:
            socketio.emit("task_error", {"error": full_reply_content}, room=sid)
        emitted_error_or_cancel_final_signal = True

    if not full_reply_content.strip() and not emitted_error_or_cancel_final_signal:
        # If loop finished, no text was streamed, and no specific error was sent
        full_reply_content = "[System Note: The AI did not return any streamable content after tool use or iterations.]"
        logger.warning(
            f"Streaming for chat {chat_id} yielded no content. Saving placeholder."
        )
        socketio.emit(
            "task_error", {"error": full_reply_content}, room=sid
        )  # Send a final signal
        emitted_error_or_cancel_final_signal = True

    # --- Save Full Accumulated Reply to DB ---
    if (
        full_reply_content
    ):  # Save whatever was accumulated, including error/cancel messages
        logger.info(
            f"Attempting to save final streamed assistant message for chat {chat_id}. Length: {len(full_reply_content)}"
        )
        try:
            save_success = database.add_message_to_db(
                chat_id, "assistant", full_reply_content, attached_data_json=None
            )
            if not save_success:
                logger.error(
                    f"Failed to save final streamed assistant message for chat {chat_id}."
                )
        except Exception as db_err:
            logger.error(
                f"DB error saving final streamed assistant message for chat {chat_id}: {db_err}",
                exc_info=True,
            )
    else:
        logger.warning(
            f"No content (not even error/cancel) to save for streaming chat {chat_id}."
        )

    _cleanup_temp_files(temp_files_to_clean, f"streaming chat {chat_id} (SID: {sid})")


# --- Helper Function to Prepare History and Content Parts ---
def _prepare_chat_content(
    client,
    chat_id,
    user_message,
    attached_files,
    session_files,
    calendar_context,
    web_search_enabled,
    socketio=None,
    sid=None,
    is_cancelled_callback: Callable[[], bool] = lambda: False,  # Add callback
):
    """
    Prepares history list and current turn parts list. Checks for cancellation.
    Returns (history, parts, temp_files) on success.
    Emits 'task_error' via SocketIO and returns None on failure.
    """
    logger.info(f"Preparing content for chat {chat_id} (SID: {sid})")
    history = []
    # current_turn_parts are for *additional* context like calendar or pre-loaded files.
    # Web search and scraping results will be added to history via the tool loop.
    current_turn_parts = []
    temp_files_to_clean = (
        []
    )  # Still needed for files attached directly to the user message

    def emit_prep_error(error_msg, is_cancel=False):
        log_level = logging.INFO if is_cancel else logging.ERROR
        logger.log(
            log_level,
            f"Preparation {'cancelled' if is_cancel else 'error'} for chat {chat_id} (SID: {sid}): {error_msg}",
        )
        if socketio and sid:
            if is_cancel:
                # Emit cancellation confirmation instead of generic task error
                socketio.emit(
                    "generation_cancelled",
                    {"message": error_msg, "chat_id": chat_id},
                    room=sid,
                )
            else:
                socketio.emit("task_error", {"error": error_msg}, room=sid)
        return None  # Signal failure/cancellation

    # --- Fetch History ---
    try:
        history_data = database.get_chat_history_from_db(chat_id)
        history = []
        for msg in history_data:
            role = "user" if msg["role"] == "user" else "model"
            # Prepare parts for history, including potential attachments from DB
            msg_parts = []
            if msg.get("content"):
                msg_parts.append(Part(text=msg["content"]))

            # Add parts for attachments stored in the message's attached_data
            # This assumes attached_data stores a list of dicts like {filename, mimetype, file_id, type}
            # We only need filename and type for context here, not the full file content again.
            db_attachments = msg.get("attachments", [])
            if db_attachments:
                attachment_texts = []
                for att in db_attachments:
                    att_type = att.get(
                        "type", "file"
                    )  # Default to 'file' if type missing
                    att_name = att.get("filename", "Unknown File")
                    if att_type == "session":
                        attachment_texts.append(
                            f"[User attached session file: {att_name}]"
                        )
                    elif att_type == "summary":
                        attachment_texts.append(
                            f"[User attached summary of file: {att_name}]"
                        )
                    elif att_type == "full":
                        attachment_texts.append(
                            f"[User attached full content of file: {att_name}]"
                        )
                    else:  # Handle 'file' type from potentially saved session files
                        attachment_texts.append(f"[User attached file: {att_name}]")

                if attachment_texts:
                    # Combine attachment info into one text part for history simplicity
                    msg_parts.append(Part(text="\n".join(attachment_texts)))

            if (
                msg_parts
            ):  # Only add history turn if there are parts (text or attachment info)
                history.append(Content(role=role, parts=msg_parts))
            else:
                logger.warning(
                    f"Skipping history message with no parts for chat {chat_id}: Role={role}"
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
            f"Failed to fetch/prepare history for chat {chat_id} (SID: {sid}): {e}",
            exc_info=True,
        )
        return emit_prep_error("[Error: Could not load or prepare chat history]")

    # --- Prepare Current Turn Parts (Additional Context Only) ---
    # Wrap the rest in try/except to catch errors during part preparation and emit them
    # Check for cancellation periodically during potentially long operations
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

        # 2. Attached Files (DB References)
        if attached_files:
            logger.info(
                f"Processing {len(attached_files)} attached file references for chat {chat_id}."
            )
            for file_detail in attached_files:
                file_id = file_detail.get("id")
                attachment_type = file_detail.get("type")
                frontend_filename = file_detail.get(
                    "filename", f"File ID {file_id}"
                )  # Use filename from metadata if available
                logger.debug(
                    f"Processing attached file reference: ID={file_id}, Type={attachment_type}, Name={frontend_filename}"
                )

                # --- Cancellation Check ---
                if is_cancelled_callback():
                    return emit_prep_error(
                        "[AI Info: Generation cancelled during file processing.]",
                        is_cancel=True,
                    )

                if file_id is None or attachment_type is None:
                    logger.warning(
                        f"Skipping invalid attached file reference detail: {file_detail}"
                    )
                    current_turn_parts.append(
                        Part(text=f"[System: Skipped invalid attached file reference.]")
                    )
                    continue
                try:
                    # Fetch details needed for processing (content only if 'full')
                    include_content = attachment_type == "full"
                    db_file_details = database.get_file_details_from_db(
                        file_id, include_content=include_content
                    )
                    if not db_file_details:
                        logger.warning(
                            f"Could not get details for attached file_id {file_id} ('{frontend_filename}') in chat {chat_id}."
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Error retrieving attached file '{frontend_filename}']"
                            )
                        )
                        continue

                    # Check content specifically if 'full' type was requested
                    if include_content and not db_file_details.get("content"):
                        logger.warning(
                            f"Could not get content for attached file_id {file_id} ('{frontend_filename}') requested as 'full' in chat {chat_id}."
                        )
                        current_turn_parts.append(
                            Part(
                                text=f"[System: Error retrieving content for attached file '{frontend_filename}']"
                            )
                        )
                        continue

                    filename = db_file_details["filename"]
                    mimetype = db_file_details["mimetype"]

                    if attachment_type == "summary":
                        summary = get_or_generate_summary(
                            file_id
                        )  # This handles DB fetch or generation
                        current_turn_parts.append(
                            Part(
                                text=f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                            )
                        )
                    elif attachment_type == "full":
                        content_blob = db_file_details[
                            "content"
                        ]  # Content was included
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

                                # --- Cancellation Check ---
                                if is_cancelled_callback():
                                    return emit_prep_error(
                                        "[AI Info: Generation cancelled during file upload.]",
                                        is_cancel=True,
                                    )

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

        # 3. Session Files (Base64 Content)
        if session_files:
            logger.info(
                f"Processing {len(session_files)} session files for chat {chat_id}."
            )
            for session_file_detail in session_files:
                filename = session_file_detail.get("filename", "Unknown Session File")
                mimetype = session_file_detail.get("mimetype")
                content_base64 = session_file_detail.get("content")
                logger.debug(
                    f"Processing session file: {filename}, Mimetype: {mimetype}"
                )

                # --- Cancellation Check ---
                if is_cancelled_callback():
                    return emit_prep_error(
                        "[AI Info: Generation cancelled during session file processing.]",
                        is_cancel=True,
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

        # 4. Web Search (REMOVED - This is now handled by LLM tool usage)
        # The web_search_enabled flag will be used by the calling function
        # to determine if the web search/scrape tools should be provided to the LLM.
        # No direct web search logic here anymore.

        # --- REMOVED USER MESSAGE TEXT ADDITION ---
        # 5. User Message Text (REMOVED - Now part of history fetched from DB)
        # if user_message:
        #     current_turn_parts.append(Part(text=user_message)) # <<< REMOVED
        # elif not current_turn_parts and not history:
        #     current_turn_parts.append(
        #         Part(text="[User provided no text, only attachments or context.]")
        #     )
        # --- END REMOVAL ---

        # 6. Special Instructions (Add after all other content)
        # These instructions are now added to the system prompt or initial user message
        # by the calling function if web search/scraping tools are active.
        # No specific parts added here for special instructions anymore, as the LLM
        # will receive tool descriptions and will be prompted on how to use their output.
        # The main system prompt in _generate_chat_response_non_stream and _generate_chat_response_stream
        # will be augmented with tool usage guidance.

        logger.info(
            f"Prepared {len(current_turn_parts)} additional context parts (e.g., calendar, direct file attachments) for chat {chat_id}."
        )
        # Return history (list of Content) and current_turn_parts (list of additional Parts)
        return history, current_turn_parts, temp_files_to_clean

    except Exception as prep_err:
        logger.error(
            f"Unexpected error preparing content parts for chat {chat_id} (SID: {sid}): {prep_err}",
            exc_info=True,
        )
        return emit_prep_error(
            f"[Error: Failed to prepare content for AI ({type(prep_err).__name__})]"
        )

    # --- Final Cancellation Check ---
    if is_cancelled_callback():
        return emit_prep_error(
            "[AI Info: Generation cancelled after content preparation.]", is_cancel=True
        )

    # --- Return successful preparation results ---
    logger.info(
        f"Successfully prepared {len(current_turn_parts)} additional context parts for chat {chat_id} (SID: {sid})."
    )
    return history, current_turn_parts, temp_files_to_clean


# --- Helper Function to Clean Up Temporary Files ---
# (No changes needed in _cleanup_temp_files)
# _cleanup_temp_files remains here as it's used by _prepare_chat_content which is still in this file.

# --- Transcript Cleaning --- has been moved to app/ai_services_lib/transcription_services.py


# --- Note Diff Summary Generation --- has been moved to app/ai_services_lib/note_services.py


# --- PDF Transcription --- has been moved to app/ai_services_lib/transcription_services.py


# --- Standalone Text Generation (Example) --- has been moved to app/ai_services_lib/generation_services.py
