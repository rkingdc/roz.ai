# app/ai_services.py
import google.generativeai as genai
from flask import current_app
import tempfile
import os
from . import database # Use relative import

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
            print("Gemini API configured successfully.")
        except Exception as e:
            print(f"Error configuring Gemini API: {e}")
            gemini_configured = False
    else:
        print("Gemini API key not found in config. AI features disabled.")
        gemini_configured = False
    return gemini_configured

# --- Summary Generation ---
def generate_summary(file_id):
    """Generates a summary for a file using a designated multi-modal model."""
    if not gemini_configured: return "[Error: AI model not configured]"
    file_details = database.get_file_details_from_db(file_id, include_content=True)
    if not file_details or 'content' not in file_details: return "[Error: File content not found]"

    filename = file_details['filename']; mimetype = file_details['mimetype']
    content_blob = file_details['content']
    summary_model_name = current_app.config['SUMMARY_MODEL']
    print(f"Attempting summary generation for '{filename}' (Type: {mimetype}) using model '{summary_model_name}'...")

    parts = []; temp_file_to_clean = None
    prompt = f"Please provide a concise summary of the attached file named '{filename}'. Focus on the main points and key information."

    try:
        if mimetype.startswith('text/'):
            try:
                text_content = content_blob.decode('utf-8', errors='ignore')
                prompt = f"Please provide a concise summary of the following text content from the file named '{filename}':\n\n{text_content}"
                parts = [prompt]
            except Exception as decode_err: return "[Error: Could not decode text content for summary]"
        elif mimetype.startswith(('image/', 'audio/', 'video/', 'application/pdf')):
            try:
                from werkzeug.utils import secure_filename
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{secure_filename(filename)}") as temp_file:
                    temp_file.write(content_blob); temp_filepath = temp_file.name
                    temp_file_to_clean = temp_filepath
                print(f"Uploading temp file '{temp_filepath}' for summary generation...")
                uploaded_file = genai.upload_file(path=temp_filepath, display_name=filename, mime_type=mimetype)
                parts.append(prompt); parts.append(uploaded_file)
                print(f"File '{filename}' uploaded for summary, URI: {uploaded_file.uri}")
            except Exception as upload_err: return f"[Error preparing file for summary: {upload_err}]"
        else: return "[Summary generation not supported for this file type]"

        summary_model_instance = genai.GenerativeModel(summary_model_name)
        response = summary_model_instance.generate_content(parts)
        summary = response.text
        print(f"Summary generated successfully for '{filename}'.")
        return summary
    except Exception as e:
        print(f"Error during summary generation API call for '{filename}': {e}")
        if "prompt was blocked" in str(e).lower(): return "[Error: Summary generation blocked due to safety settings]"
        return f"[Error generating summary via API: {e}]"
    finally:
        if temp_file_to_clean:
            try: os.remove(temp_file_to_clean); print(f"Cleaned up temp summary file: {temp_file_to_clean}")
            except OSError as e: print(f"Error removing temp summary file {temp_file_to_clean}: {e}")

def get_or_generate_summary(file_id):
    """Gets summary from DB or generates+saves it if not present."""
    file_details = database.get_file_details_from_db(file_id)
    if not file_details: return "[Error: File details not found]"
    if file_details['has_summary'] and file_details['summary'] and not file_details['summary'].startswith("["):
        print(f"Retrieved existing summary for file ID: {file_id}")
        return file_details['summary']
    else:
        print(f"Generating summary for file ID: {file_id}...")
        new_summary = generate_summary(file_id)
        if database.save_summary_in_db(file_id, new_summary): return new_summary
        else: print(f"Error: Failed to save newly generated summary for file ID: {file_id}"); return new_summary

# --- Chat Response Generation (MODIFIED) ---

def generate_chat_response(chat_id, user_message, attached_files, calendar_context=None): # Added calendar_context arg
    """
    Generates a chat response using the appropriate model and context.
    Handles file uploads via API and includes optional calendar context.
    Returns the assistant's reply string.
    """
    if not gemini_configured: return "[Error: Gemini API Key not configured]"

    chat_details = database.get_chat_details_from_db(chat_id)
    if not chat_details: return "[Error: Chat session not found]"

    model_name = chat_details.get('model_name', current_app.config['DEFAULT_MODEL'])
    print(f"Using model '{model_name}' for chat {chat_id} response.")

    gemini_parts = []
    temp_files_to_clean = []
    files_info_for_history = [] # Only file markers go into history

    try:
        # --- Add Calendar Context FIRST if provided ---
        if calendar_context:
            print("Prepending calendar context to AI query.")
            gemini_parts.append("--- Start Calendar Context ---")
            gemini_parts.append(calendar_context)
            gemini_parts.append("--- End Calendar Context ---")
            # DO NOT add calendar_context to files_info_for_history

        # --- Process Attached Files ---
        if attached_files:
            print(f"Processing {len(attached_files)} attached files for Gemini...")
            for file_info in attached_files:
                # (File processing logic remains the same as v6 - using temp files)
                file_id = file_info.get('id'); attach_type = file_info.get('type', 'full')
                if not file_id: continue
                file_details = database.get_file_details_from_db(file_id, include_content=True)
                if not file_details or 'content' not in file_details:
                    files_info_for_history.append(f"[Error: File ID {file_id} not found or content missing]")
                    continue
                filename = file_details['filename']; mimetype = file_details['mimetype']
                content_blob = file_details['content']
                history_marker = f"[Attached File: '{filename}' (ID: {file_id}, Type: {attach_type})]"
                try:
                    if attach_type == 'full':
                        from werkzeug.utils import secure_filename
                        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{secure_filename(filename)}") as temp_file:
                            temp_file.write(content_blob); temp_filepath = temp_file.name
                            temp_files_to_clean.append(temp_filepath)
                        print(f"Uploading temp file '{temp_filepath}' for '{filename}' via API...")
                        try:
                            uploaded_file = genai.upload_file(path=temp_filepath, display_name=filename, mime_type=mimetype)
                            gemini_parts.append(uploaded_file)
                            print(f"File '{filename}' uploaded, URI: {uploaded_file.uri}")
                            files_info_for_history.append(history_marker)
                        except Exception as api_upload_err:
                             print(f"Error uploading file '{filename}' to Gemini API: {api_upload_err}")
                             files_info_for_history.append(f"[Error uploading file to AI: '{filename}']")
                             gemini_parts.append(f"[System: Error processing file '{filename}'. Upload failed.]")
                    elif attach_type == 'summary':
                        print(f"Getting/Generating summary for '{filename}' (ID: {file_id})")
                        summary = get_or_generate_summary(file_id)
                        gemini_parts.append(f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---")
                        files_info_for_history.append(history_marker)
                except Exception as processing_err:
                     print(f"Error processing file ID {file_id} ('{filename}') for Gemini: {processing_err}")
                     files_info_for_history.append(f"[Error processing file: '{filename}' (ID: {file_id})]")
                     gemini_parts.append(f"[System: Error processing file '{filename}'.]")

        # --- Add user text message to parts ---
        if user_message:
            gemini_parts.append(user_message)

        # --- Save user message with ONLY file markers to DB ---
        history_message = "\n".join(files_info_for_history) + ("\n" if files_info_for_history else "") + user_message
        if not database.add_message_to_db(chat_id, 'user', history_message):
             print(f"Warning: Failed to save user message for chat {chat_id}.")
             return "[Error: Failed to save user message to history]"

        assistant_reply = "[AI response error occurred]"

        # --- Gemini Interaction ---
        try:
            try: chat_model = genai.GenerativeModel(model_name)
            except Exception as model_init_error:
                 print(f"Error initializing model '{model_name}': {model_init_error}. Falling back to default '{current_app.config['DEFAULT_MODEL']}'.")
                 chat_model = genai.GenerativeModel(current_app.config['DEFAULT_MODEL'])
                 assistant_reply = f"[System: Model '{model_name}' not found, using default '{current_app.config['DEFAULT_MODEL']}'.] "

            history_for_gemini_raw = database.get_chat_history_from_db(chat_id, limit=20)
            gemini_context = []
            for msg in history_for_gemini_raw:
                role = 'model' if msg['role'] == 'assistant' else 'user'
                gemini_context.append({"role": role, "parts": [msg['content']]})
            if gemini_context and gemini_context[-1]['role'] == 'user': gemini_context.pop()

            print(f"--- Sending to Gemini (Chat ID: {chat_id}, Model: {model_name}) ---")
            print(f"Content Parts: {[str(p)[:100]+'...' if isinstance(p, str) else type(p) for p in gemini_parts]}")
            print("--- End Gemini Send ---")

            full_request_content = gemini_context + [{"role": "user", "parts": gemini_parts}]
            timeout = current_app.config.get('GEMINI_REQUEST_TIMEOUT', 300)
            response = chat_model.generate_content(full_request_content, request_options={"timeout": timeout})

            current_reply = response.text
            if assistant_reply != "[AI response error occurred]": assistant_reply += current_reply
            else: assistant_reply = current_reply
            print(f"Gemini Response: {assistant_reply[:100]}...")

        except Exception as e:
            print(f"Error calling Gemini API for chat {chat_id} with model {model_name}: {e}")
            error_message = f"[Error communicating with AI: {e}]"
            # (Error handling details omitted for brevity - same as before)
            if "API key not valid" in str(e): error_message = "[Error: Invalid Gemini API Key.]"
            elif "token" in str(e).lower() or "size" in str(e).lower() or "request payload size" in str(e).lower(): error_message = "[Error: Request too large. Try summaries or fewer/smaller files.]"
            elif "prompt was blocked" in str(e).lower(): error_message = "[Error: Request blocked by safety settings.]"
            elif "resource has been exhausted" in str(e).lower(): error_message = "[Error: API quota exceeded. Please try again later.]"
            elif "429" in str(e): error_message = "[Error: Too many requests. Please try again later.]"
            elif "Deadline Exceeded" in str(e): error_message = "[Error: Request timed out. The operation took too long.]"

            if assistant_reply != "[AI response error occurred]": assistant_reply += "\n" + error_message
            else: assistant_reply = error_message

        # Add assistant reply to DB
        database.add_message_to_db(chat_id, 'assistant', assistant_reply)
        return assistant_reply

    finally:
        # Clean up temporary files
        print(f"Cleaning up {len(temp_files_to_clean)} temporary files...")
        for temp_path in temp_files_to_clean:
            try: os.remove(temp_path); print(f"Removed temp file: {temp_path}")
            except OSError as e: print(f"Error removing temp file {temp_path}: {e}")
