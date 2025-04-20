# app/ai_services.py
import google.generativeai as genai
from flask import current_app
import tempfile
import os
import re
import base64  # Needed for decoding session file content
from . import database  # Use relative import
from .plugins.web_search import perform_web_search

# Configure logging
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to hold configured status
gemini_configured = False


def configure_gemini(app):
    """Configures the Gemini client using API key from the passed app's config."""
    global gemini_configured
    api_key = app.config.get("API_KEY")
    if api_key:
        try:
            genai.configure(api_key=api_key)
            gemini_configured = True
            logger.info("Gemini API configured successfully.")
        except Exception as e:
            logger.error(f"Error configuring Gemini API: {e}")
            gemini_configured = False
    else:
        logger.error("Gemini API key not found in config. AI features disabled.")
        gemini_configured = False
    return gemini_configured


# --- Summary Generation ---
def generate_summary(file_id):
    """
    Generates a summary for a file using a designated multi-modal model.
    Handles text directly and uses file upload API for other types.
    """
    if not gemini_configured:
        return "[Error: AI model not configured]"
    file_details = database.get_file_details_from_db(file_id, include_content=True)
    if not file_details or "content" not in file_details:
        return "[Error: File content not found]"

    filename = file_details["filename"]
    mimetype = file_details["mimetype"]
    content_blob = file_details["content"]
    summary_model_name = current_app.config["SUMMARY_MODEL"]
    logger.info(
        f"Attempting summary generation for '{filename}' (Type: {mimetype}) using model '{summary_model_name}'..."
    )

    parts = []
    temp_file_to_clean = None
    prompt = f"Please provide a concise summary of the attached file named '{filename}'. Focus on the main points and key information."

    try:
        if mimetype.startswith("text/"):
            try:
                text_content = content_blob.decode("utf-8", errors="ignore")
                prompt = f"Please provide a concise summary of the following text content from the file named '{filename}':\n\n{text_content}"
                parts = [prompt]
            except Exception as decode_err:
                return "[Error: Could not decode text content for summary]"
        elif mimetype.startswith(("image/", "audio/", "video/", "application/pdf")):
            try:
                from werkzeug.utils import secure_filename

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f"_{secure_filename(filename)}"
                ) as temp_file:
                    temp_file.write(content_blob)
                    temp_filepath = temp_file.name
                    temp_file_to_clean = temp_filepath
                logger.info(
                    f"Uploading temp file '{temp_filepath}' for summary generation..."
                )
                uploaded_file = genai.upload_file(
                    path=temp_filepath, display_name=filename, mime_type=mimetype
                )
                parts.append(prompt)
                parts.append(uploaded_file)
                logger.info(
                    f"File '{filename}' uploaded for summary, URI: {uploaded_file.uri}"
                )
            except Exception as upload_err:
                # Let the finally block handle cleanup
                return f"[Error preparing file for summary: {upload_err}]"
        else:
            return "[Summary generation not supported for this file type]"

        summary_model_instance = genai.GenerativeModel(summary_model_name)
        timeout = current_app.config.get("GEMINI_REQUEST_TIMEOUT", 300)
        response = summary_model_instance.generate_content(
            parts, request_options={"timeout": timeout}
        )
        summary = response.text
        logger.info(f"Summary generated successfully for '{filename}'.")
        return summary
    except Exception as e:
        logger.error(f"Error during summary generation API call for '{filename}': {e}")
        if "prompt was blocked" in str(e).lower():
            return "[Error: Summary generation blocked due to safety settings]"
        return f"[Error generating summary via API: {e}]"
    finally:
        if temp_file_to_clean:
            try:
                os.remove(temp_file_to_clean)
                logger.info(f"Cleaned up temp summary file: {temp_file_to_clean}")
            except OSError as e:
                logger.info(
                    f"Error removing temp summary file {temp_file_to_clean}: {e}"
                )


def get_or_generate_summary(file_id):
    """Gets summary from DB or generates+saves it if not present."""
    file_details = database.get_file_details_from_db(file_id)
    if not file_details:
        return "[Error: File details not found]"
    if (
        file_details["has_summary"]
        and file_details["summary"]
        and not file_details["summary"].startswith("[")
    ):
        logger.info(f"Retrieved existing summary for file ID: {file_id}")
        return file_details["summary"]
    else:
        logger.info(f"Generating summary for file ID: {file_id}...")
        new_summary = generate_summary(file_id)
        if database.save_summary_in_db(file_id, new_summary):
            return new_summary
        else:
            logger.info(
                f"Error: Failed to save newly generated summary for file ID: {file_id}"
            )
            return new_summary


# --- Chat Response Generation (MODIFIED Signature) ---
def generate_search_query(user_message: str, max_retries=1) -> str | None:
    """
    Uses the default LLM to generate a concise web search query based on the user's message.

    Args:
        user_message (str): The original message from the user.
        max_retries (int): Maximum number of retries in case of transient API errors.

    Returns:
        str | None: The generated search query string, or None if generation fails
                    or the LLM couldn't produce a useful query.
    """
    if not gemini_configured:
        logger.info(
            "ERROR: Cannot generate search query - Gemini API Key not configured."
        )
        return None
    if not user_message or user_message.isspace():
        logger.info("INFO: Cannot generate search query from empty user message.")
        return None

    model_name = current_app.config.get("SUMMARY_MODEL")
    logger.info(f"Attempting to generate search query using model '{model_name}'...")

    # Construct the prompt for the LLM
    prompt = f"""Analyze the following user message and generate a concise and effective web search query (ideally 3-7 words) that would find information directly helpful in answering or augmenting the user's request.

User Message:
"{user_message}"

Focus on the core information needed. Output *only* the raw search query string itself. Do not add explanations, quotation marks (unless essential for the search phrase), or any other surrounding text.

Search Query:"""

    retries = 0
    while retries <= max_retries:
        try:
            # Initialize the model
            model = genai.GenerativeModel(model_name)

            # Generate the content
            response = model.generate_content(
                prompt,
                # safety_settings=safety_settings, # Optional
                generation_config=genai.types.GenerationConfig(
                    # candidate_count=1, # Default is 1
                    # stop_sequences=['\n'], # Could try stopping at newline, but LLM might ignore
                    max_output_tokens=50,  # Limit output tokens significantly for just a query
                    temperature=0.2,  # Lower temperature for more focused, less creative query
                ),
            )

            # --- Response Cleaning ---
            if not response.parts:
                logger.info(
                    f"Warning: LLM response for query generation had no parts. Prompt Blocked? Text: {response.text}"
                )
                # Check if prompt was blocked
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    logger.info(
                        f"Prompt blocked, reason: {response.prompt_feedback.block_reason}"
                    )
                    # Don't retry if blocked by safety/policy
                    return None
                # Otherwise, maybe transient issue, allow retry
                raise ValueError(
                    "LLM response contained no parts."
                )  # Raise error to trigger retry


            generated_query = response.text.strip()
            logger.info(f"Raw query:{generated_query}")
            # Further cleaning: Remove potential surrounding quotes if the LLM added them
            generated_query = re.sub(r'^"|"$', "", generated_query)
            # Remove potential markdown list markers or similar artifacts
            generated_query = re.sub(r"^\s*[-\*\d]+\.?\s*", "", generated_query)
            # Remove potential introductory phrases sometimes added by LLMs
            generated_query = re.sub(
                r"^(?:Search Query:|Here is a search query:|query:)\s*",
                "",
                generated_query,
                flags=re.IGNORECASE,
            )

            if generated_query:
                logger.info(f"Generated Search Query: '{generated_query}'")
                return generated_query
            else:
                logger.info("Warning: LLM generated an empty search query.")
                # Don't retry if the LLM deliberately returned empty, treat as failure
                return None

        except Exception as e:
            retries += 1
            logger.info(
                f"Error generating search query (Attempt {retries}/{max_retries+1}): {e}"
            )
            if retries > max_retries:
                logger.info("Max retries reached for search query generation.")
                return None
            # Optional: Add a small delay before retrying
            # import time
            # time.sleep(1)

    return None  # Should technically be unreachable if loop condition is correct, but safety return


def generate_chat_response(
    chat_id,
    user_message,
    attached_files,
    calendar_context=None,
    session_files=None,
    enable_web_search=False,
):  # Added session_files parameter
    """
    Generates a chat response using the appropriate model and context.
    Handles file uploads via API and includes optional calendar context and session files.
    Returns the assistant's reply string.
    """
    if not gemini_configured:
        return "[Error: Gemini API Key not configured]"

    chat_details = database.get_chat_details_from_db(chat_id)
    if not chat_details:
        return "[Error: Chat session not found]"

    model_name = chat_details.get("model_name", current_app.config["DEFAULT_MODEL"])
    logger.info(f"Using model '{model_name}' for chat {chat_id} response.")

    gemini_parts = []
    temp_files_to_clean = []
    files_info_for_history = []  # Only permanent file markers go into history

    # Use a non-None default for session_files if it's None
    session_files = session_files or []

    try:
        # --- Add Calendar Context FIRST if provided ---
        if calendar_context:
            logger.info("Prepending calendar context to AI query.")
            gemini_parts.extend(
                [
                    "--- Start Calendar Context ---",
                    calendar_context,
                    "--- End Calendar Context ---",
                ]
            )

        # --- Process Session Files SECOND ---
        if session_files:
            logger.info(f"Processing {len(session_files)} session files for Gemini...")
            for session_file in session_files:
                filename = session_file.get("filename", "unknown_session_file")
                base64_content = session_file.get(
                    "content"
                )  # Expected format: data:mime/type;base64,xxxxx
                mimetype = session_file.get(
                    "mimetype", "application/octet-stream"
                )  # Get mimetype if available

                if not base64_content:
                    logger.info(
                        f"Warning: Skipping session file '{filename}' due to missing content."
                    )
                    continue

                try:
                    # Decode Base64 content
                    # Format is "data:[<mediatype>][;base64],<data>"
                    header, encoded = base64_content.split(",", 1)
                    decoded_data = base64.b64decode(encoded)

                    logger.info(
                        f"Preparing session file '{filename}' (Type: {mimetype}) for API upload..."
                    )
                    from werkzeug.utils import secure_filename

                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=f"_session_{secure_filename(filename)}"
                    ) as temp_file:
                        temp_file.write(decoded_data)
                        temp_filepath = temp_file.name
                        temp_files_to_clean.append(temp_filepath)

                    logger.info(
                        f"Uploading temp session file '{temp_filepath}' for '{filename}' via API..."
                    )
                    try:
                        uploaded_file = genai.upload_file(
                            path=temp_filepath,
                            display_name=f"session_{filename}",
                            mime_type=mimetype,
                        )
                        gemini_parts.append(
                            uploaded_file
                        )  # Add file reference to parts for AI
                        logger.info(
                            f"Session file '{filename}' uploaded, URI: {uploaded_file.uri}"
                        )
                        # DO NOT add marker to files_info_for_history for session files
                    except Exception as api_upload_err:
                        logger.info(
                            f"Error uploading session file '{filename}' to Gemini API: {api_upload_err}"
                        )
                        gemini_parts.append(
                            f"[System: Error processing session file '{filename}'. Upload failed.]"
                        )  # Add system message part for AI

                except Exception as processing_err:
                    logger.info(
                        f"Error processing session file '{filename}' for Gemini: {processing_err}"
                    )
                    gemini_parts.append(
                        f"[System: Error processing session file '{filename}'.]"
                    )

        # --- Process Attached (Permanent) Files THIRD ---
        if attached_files:
            logger.info(
                f"Processing {len(attached_files)} attached permanent files for Gemini..."
            )
            for file_info in attached_files:
                # (File processing logic remains the same as v6 - using temp files)
                file_id = file_info.get("id")
                attach_type = file_info.get("type", "full")
                if not file_id:
                    continue

                # Fetch basic details first (no content yet)
                basic_file_details = database.get_file_details_from_db(file_id)
                if not basic_file_details:
                    files_info_for_history.append(
                        f"[Error: File ID {file_id} not found]"
                    )
                    continue

                filename = basic_file_details["filename"]
                mimetype = basic_file_details["mimetype"]
                history_marker = f"[Attached File: '{filename}' (ID: {file_id}, Type: {attach_type})]"  # Marker for DB history

                if attach_type == "summary":
                    # Handle summary retrieval/generation separately
                    try:
                        logger.info(
                            f"Getting/Generating summary for '{filename}' (ID: {file_id})"
                        )
                        summary = get_or_generate_summary(file_id)
                        if summary.startswith("[Error"):
                             files_info_for_history.append(f"[Error retrieving summary: '{filename}']")
                             gemini_parts.append(f"[System: Error retrieving summary for file '{filename}'. {summary}]")
                        else:
                            gemini_parts.append(
                                f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                            )
                            files_info_for_history.append(history_marker) # Add success marker
                    except Exception as summary_err:
                         logger.info(f"Unexpected error getting summary for file ID {file_id} ('{filename}'): {summary_err}")
                         files_info_for_history.append(f"[Error retrieving summary: '{filename}']")
                         gemini_parts.append(f"[System: Error retrieving summary for file '{filename}'.]")

                elif attach_type == "full":
                    # Process full file content within the try/except block
                    try:
                        # Now fetch content only if needed
                        full_file_details = database.get_file_details_from_db(file_id, include_content=True)
                        if not full_file_details or "content" not in full_file_details:
                             files_info_for_history.append(
                                f"[Error: Content for File ID {file_id} ('{filename}') missing]"
                            )
                             gemini_parts.append(f"[System: Error processing file '{filename}'. Content missing.]")
                             continue # Skip to next file

                        content_blob = full_file_details["content"]
                        from werkzeug.utils import secure_filename

                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=f"_{secure_filename(filename)}"
                        ) as temp_file:
                            temp_file.write(content_blob)
                            temp_filepath = temp_file.name
                            temp_files_to_clean.append(temp_filepath)
                        logger.info(
                            f"Uploading temp file '{temp_filepath}' for '{filename}' via API..."
                        )
                        try:
                            uploaded_file = genai.upload_file(
                                path=temp_filepath,
                                display_name=filename,
                                mime_type=mimetype,
                            )
                            gemini_parts.append(uploaded_file)
                            logger.info(
                                f"File '{filename}' uploaded, URI: {uploaded_file.uri}"
                            )
                            files_info_for_history.append(history_marker) # Add success marker
                        except Exception as api_upload_err:
                            logger.info(
                                f"Error uploading file '{filename}' to Gemini API: {api_upload_err}"
                            )
                            files_info_for_history.append(
                                f"[Error uploading file to AI: '{filename}']"
                            )
                            gemini_parts.append(
                                f"[System: Error processing file '{filename}'. Upload failed.]"
                            )
                    # Summary type is handled above, outside this try/except
                    except Exception as processing_err:
                         # This now only catches errors specific to 'full' file processing
                         logger.info(
                            f"Error processing file ID {file_id} ('{filename}') for Gemini: {processing_err}"
                    )
                    files_info_for_history.append(
                        f"[Error processing file: '{filename}' (ID: {file_id})]"
                    )
                    gemini_parts.append(
                        f"[System: Error processing file '{filename}'.]"
                    )

        web_search_error_for_user = (
            None  # Initialize variable to hold user-facing errors
        )
        if enable_web_search:
            try:
                search_query = generate_search_query(
                    user_message
                )  
                logger.info(
                    f"Web search enabled, searching for: '{search_query}'"
                )  # Using user_message for search now
                search_results = perform_web_search(
                    search_query
                )  # Call the new function
                if search_results:
                    # Check if the first result indicates a system error from the search function
                    if search_results[0].startswith("[System Error:"):
                        gemini_parts.append(
                            search_results[0]
                        )  # Pass the error message to Gemini
                        files_info_for_history.append("[Web search failed]")
                    else:
                        gemini_parts.extend(
                            [
                                "--- Start Web Search Results ---",
                                "The following information was retrieved from a web search and may contain inaccuracies. Please verify the information before relying on it.",
                                "\n".join(search_results),
                                "--- End Web Search Results ---",
                            ]
                        )
                        files_info_for_history.append("[Web search performed]")
                else:
                    # This now correctly handles the case where perform_web_search returns an empty list (no results found)
                    gemini_parts.append(
                        "[System Note: Web search returned no relevant results.]"
                    )
                    files_info_for_history.append("[Web search attempted, no results]")
            except Exception as search_err:
                # This outer catch might catch errors *calling* perform_web_search, though most errors should be handled *inside* it.
                logger.info(f"Error during web search integration logic: {search_err}")
                gemini_parts.append(
                    f"[System: Error occurred trying to perform web search: {search_err}]"
                )
                files_info_for_history.append(
                    f"[Web search integration error: {search_err}]"
                )

        # --- Add user text message LAST to parts ---
        if user_message:
            gemini_parts.append(user_message)

        # --- Save user message with ONLY permanent file markers to DB ---
        history_message = (
            "\n".join(files_info_for_history)
            + ("\n" if files_info_for_history else "")
            + user_message
        )
        if not database.add_message_to_db(chat_id, "user", history_message):
            logger.info(
                f"Warning: Failed to save user message for chat {chat_id} after processing files."
            )
            return "[Error: Failed to save user message to history]"

        assistant_reply = "[AI response error occurred]"  # Default error state

        # --- Gemini Interaction ---
        try:
            try:
                chat_model = genai.GenerativeModel(model_name)
            except Exception as model_init_error:
                logger.info(
                    f"Error initializing model '{model_name}': {model_init_error}. Falling back to default '{current_app.config['DEFAULT_MODEL']}'."
                )
                chat_model = genai.GenerativeModel(current_app.config["DEFAULT_MODEL"])
                assistant_reply = f"[System: Model '{model_name}' not found, using default '{current_app.config['DEFAULT_MODEL']}'.] "

            history_for_gemini_raw = database.get_chat_history_from_db(
                chat_id, limit=20
            )
            gemini_context = []
            for msg in history_for_gemini_raw:
                role = "model" if msg["role"] == "assistant" else "user"
                gemini_context.append({"role": role, "parts": [msg["content"]]})
            if gemini_context and gemini_context[-1]["role"] == "user":
                gemini_context.pop()

            logger.info(
                f"--- Sending to Gemini (Chat ID: {chat_id}, Model: {model_name}) ---"
            )
            logger.info(
                f"Content Parts: {[str(p)[:100]+'...' if isinstance(p, str) else type(p) for p in gemini_parts]}"
            )
            logger.info("--- End Gemini Send ---")

            full_request_content = gemini_context + [
                {"role": "user", "parts": gemini_parts}
            ]
            timeout = current_app.config.get("GEMINI_REQUEST_TIMEOUT", 300)
            response = chat_model.generate_content(
                full_request_content, request_options={"timeout": timeout}
            )

            current_reply = response.text
            if assistant_reply != "[AI response error occurred]":
                assistant_reply += current_reply
            else:
                assistant_reply = current_reply
            logger.info(f"Gemini Response: {assistant_reply[:100]}...")

        except Exception as e:
            logger.info(
                f"Error calling Gemini API for chat {chat_id} with model {model_name}: {e}"
            )
            error_message = f"[Error communicating with AI: {e}]"
            # (Error handling details omitted for brevity - same as before)
            if "API key not valid" in str(e):
                error_message = "[Error: Invalid Gemini API Key.]"
            elif (
                "token" in str(e).lower()
                or "size" in str(e).lower()
                or "request payload size" in str(e).lower()
            ):
                error_message = (
                    "[Error: Request too large. Try summaries or fewer/smaller files.]"
                )
            elif "prompt was blocked" in str(e).lower():
                error_message = "[Error: Request blocked by safety settings.]"
            elif "resource has been exhausted" in str(e).lower():
                error_message = "[Error: API quota exceeded. Please try again later.]"
            elif "429" in str(e):
                error_message = "[Error: Too many requests. Please try again later.]"
            elif "Deadline Exceeded" in str(e):
                error_message = (
                    "[Error: Request timed out. The operation took too long.]"
                )

            if assistant_reply != "[AI response error occurred]":
                assistant_reply += "\n" + error_message
            else:
                assistant_reply = error_message

        # Add assistant reply to DB
        database.add_message_to_db(chat_id, "assistant", assistant_reply)
        return assistant_reply  # Return the final reply string

    finally:
        # Clean up temporary files
        logger.info(f"Cleaning up {len(temp_files_to_clean)} temporary files...")
        for temp_path in temp_files_to_clean:
            try:
                os.remove(temp_path)
                logger.info(f"Removed temp file: {temp_path}")
            except OSError as e:
                logger.info(f"Error removing temp file {temp_path}: {e}")
