import os
import sqlite3
import json
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
import time

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = 'assistant_chat_v5.db' # New DB version for schema change
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DEFAULT_MODEL = 'gemini-1.5-flash' # Define a default model

# List of models to offer in the frontend (can be updated)
# Ensure these are valid and available model names for your API key/region
AVAILABLE_MODELS = [
    'gemini-1.5-flash',
    'gemini-1.5-pro-latest',
    'gemini-pro', # Older model, might still be useful
    # Add other models as needed, e.g., 'gemini-1.0-pro'
]

if not API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set. AI features will be disabled.")
    # Keep track that the model setup failed
    gemini_configured = False
else:
    genai.configure(api_key=API_KEY)
    # We won't instantiate a default model here anymore,
    # it will be instantiated per request based on the chat's setting.
    gemini_configured = True
    print("Gemini API configured.")


# --- Flask App Setup ---
app = Flask(__name__)

# --- Database Setup ---
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cursor = db.cursor()
    # Chats table (Added 'model_name' column)
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_name TEXT DEFAULT '{DEFAULT_MODEL}'
        )
    ''')
    # Messages table (Unchanged)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)')

    # Uploaded Files table (Unchanged from previous version)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL,
            filesize INTEGER NOT NULL,
            summary TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_filename ON uploaded_files (filename)')

    # --- Schema Migrations ---
    # Check if model_name column exists, add if not
    try:
        cursor.execute("SELECT model_name FROM chats LIMIT 1")
    except sqlite3.OperationalError:
        print("Adding 'model_name' column to 'chats' table.")
        cursor.execute(f"ALTER TABLE chats ADD COLUMN model_name TEXT DEFAULT '{DEFAULT_MODEL}'")

    # Check if summary column exists, add if not (from previous migration)
    try:
        cursor.execute("SELECT summary FROM uploaded_files LIMIT 1")
    except sqlite3.OperationalError:
        print("Adding 'summary' column to 'uploaded_files' table.")
        cursor.execute("ALTER TABLE uploaded_files ADD COLUMN summary TEXT")

    db.commit()
    print(f"Database initialized. Default model: {DEFAULT_MODEL}")

# --- Database Interaction Functions (Chats & Messages - Modified) ---

def create_new_chat_entry():
    """Creates a new chat entry with the default model."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    # Insert with default name and default model
    cursor.execute("INSERT INTO chats (created_at, last_updated_at, model_name) VALUES (?, ?, ?)",
                   (now, now, DEFAULT_MODEL))
    db.commit()
    new_chat_id = cursor.lastrowid
    print(f"Created new chat with ID: {new_chat_id}, Model: {DEFAULT_MODEL}")
    return new_chat_id

def update_chat_timestamp(chat_id):
    # (Unchanged)
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute("UPDATE chats SET last_updated_at = ? WHERE id = ?", (now, chat_id))
    db.commit()

def add_message_to_db(chat_id, role, content):
    # (Unchanged)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                       (chat_id, role, content))
        db.commit()
        update_chat_timestamp(chat_id)
        return True
    except sqlite3.Error as e:
        print(f"Database error adding message: {e}")
        return False

def get_chat_history_from_db(chat_id, limit=100):
    # (Unchanged)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT role, content, timestamp
            FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (chat_id, limit))
        history = cursor.fetchall()
        return [dict(row) for row in history]
    except sqlite3.Error as e:
        print(f"Database error getting history for chat {chat_id}: {e}")
        return []

def get_chat_details_from_db(chat_id):
    """Retrieves details (including model_name) for a specific chat_id."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Select all relevant chat details
        cursor.execute("SELECT id, name, created_at, last_updated_at, model_name FROM chats WHERE id = ?", (chat_id,))
        chat_details = cursor.fetchone()
        return dict(chat_details) if chat_details else None
    except sqlite3.Error as e:
        print(f"Database error getting details for chat {chat_id}: {e}")
        return None

def get_saved_chats_from_db():
    # (Unchanged)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, last_updated_at FROM chats ORDER BY last_updated_at DESC")
        chats = cursor.fetchall()
        return [dict(row) for row in chats]
    except sqlite3.Error as e:
        print(f"Database error getting saved chats: {e}")
        return []

def save_chat_name_in_db(chat_id, name):
    # (Unchanged)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE chats SET name = ?, last_updated_at = ? WHERE id = ?", (name, datetime.now(), chat_id))
        db.commit()
        print(f"Updated name for chat {chat_id} to '{name}'")
        return True
    except sqlite3.Error as e:
        print(f"Database error saving chat name for {chat_id}: {e}")
        return False

def update_chat_model(chat_id, model_name):
    """Updates the model name for a specific chat."""
    # Optional: Validate model_name against AVAILABLE_MODELS here if desired
    # if model_name not in AVAILABLE_MODELS:
    #     print(f"Warning: Attempted to save invalid model name '{model_name}' for chat {chat_id}")
    #     return False # Or allow saving anyway
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE chats SET model_name = ?, last_updated_at = ? WHERE id = ?",
                       (model_name, datetime.now(), chat_id))
        db.commit()
        print(f"Updated model for chat {chat_id} to '{model_name}'")
        return True
    except sqlite3.Error as e:
        print(f"Database error updating model for chat {chat_id}: {e}")
        return False


def delete_chat_from_db(chat_id):
    # (Unchanged)
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        db.commit()
        print(f"Deleted chat with ID: {chat_id}")
        return True
    except sqlite3.Error as e:
        print(f"Database error deleting chat {chat_id}: {e}")
        return False

# --- Database Interaction Functions (Files - Unchanged from v2) ---
# (Functions save_file_to_db, get_uploaded_files_from_db,
#  get_file_content_and_name_from_db, get_summary_from_db, save_summary_in_db
#  remain the same as before)
# --- Start of Unchanged File DB Functions ---
def save_file_to_db(filename, content, filesize):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO uploaded_files (filename, content, filesize, summary) VALUES (?, ?, ?, NULL)",
                       (filename, content, filesize))
        db.commit()
        file_id = cursor.lastrowid
        print(f"Saved file '{filename}' (ID: {file_id}, Size: {filesize} bytes) to DB.")
        return file_id
    except sqlite3.Error as e:
        print(f"Database error saving file '{filename}': {e}")
        return None

def get_uploaded_files_from_db():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT id, filename, filesize, uploaded_at, (summary IS NOT NULL) as has_summary
            FROM uploaded_files ORDER BY uploaded_at DESC
        """)
        files = cursor.fetchall()
        return [dict(row) for row in files]
    except sqlite3.Error as e:
        print(f"Database error getting file list: {e}")
        return []

def get_file_content_and_name_from_db(file_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT content, filename FROM uploaded_files WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        if file_data:
            # print(f"Retrieved content for file ID: {file_id} (Filename: {file_data['filename']})") # Less verbose logging
            return dict(file_data)
        else:
            print(f"File content not found for ID: {file_id}")
            return None
    except sqlite3.Error as e:
        print(f"Database error getting content for file {file_id}: {e}")
        return None

def get_summary_from_db(file_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT summary FROM uploaded_files WHERE id = ?", (file_id,))
        result = cursor.fetchone()
        return result['summary'] if result and result['summary'] else None
    except sqlite3.Error as e:
        print(f"Database error getting summary for file {file_id}: {e}")
        return None

def save_summary_in_db(file_id, summary):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE uploaded_files SET summary = ? WHERE id = ?", (summary, file_id))
        db.commit()
        print(f"Saved summary for file ID: {file_id}")
        return True
    except sqlite3.Error as e:
        print(f"Database error saving summary for file {file_id}: {e}")
        return False
# --- End of Unchanged File DB Functions ---


# --- Summary Generation (Unchanged from v2) ---
def generate_summary(content, filename=""):
    if not gemini_configured: return "[Error: AI model not configured]"
    if not content: return "[Error: No content provided for summary]"
    prompt = f"Please provide a concise summary of the following file content (from file '{filename}'). Focus on the main points and key information:\n\n--- File Content Start ---\n{content}\n--- File Content End ---"
    try:
        print(f"Requesting summary generation for file '{filename}'...")
        # Use the default model for summarization for now
        # TODO: Consider using a specific model or allowing selection
        summary_model = genai.GenerativeModel(DEFAULT_MODEL)
        response = summary_model.generate_content(prompt)
        summary = response.text
        print(f"Summary generated successfully for '{filename}'.")
        return summary
    except Exception as e:
        print(f"Error generating summary for file '{filename}': {e}")
        if "prompt was blocked" in str(e).lower(): return "[Error: Summary generation blocked due to safety settings]"
        return f"[Error generating summary: {e}]"

def get_or_generate_summary(file_id):
    summary = get_summary_from_db(file_id)
    if summary:
        print(f"Retrieved existing summary for file ID: {file_id}")
        return summary
    else:
        print(f"No summary found for file ID: {file_id}. Attempting generation...")
        file_data = get_file_content_and_name_from_db(file_id)
        if file_data and file_data['content']:
            new_summary = generate_summary(file_data['content'], file_data['filename'])
            if save_summary_in_db(file_id, new_summary): return new_summary
            else: return "[Error: Failed to save generated summary]"
        else: return "[Error: Could not retrieve content to generate summary]"


# --- Flask Routes ---
@app.route('/')
def index():
    # Pass the list of available models to the frontend template
    return render_template('main.html', available_models=AVAILABLE_MODELS, default_model=DEFAULT_MODEL)

# --- Chat API Endpoints ---
@app.route('/api/chats', methods=['GET'])
def get_saved_chats():
    chats = get_saved_chats_from_db()
    return jsonify(chats)

@app.route('/api/chat', methods=['POST'])
def create_new_chat():
    try:
        new_chat_id = create_new_chat_entry() # Creates with default model
        chat_details = get_chat_details_from_db(new_chat_id)
        return jsonify(chat_details), 201
    except Exception as e:
        print(f"Error creating new chat: {e}")
        return jsonify({"error": "Failed to create new chat"}), 500

@app.route('/api/chat/<int:chat_id>', methods=['GET'])
def get_chat(chat_id):
    """Gets chat details (including model) and history."""
    details = get_chat_details_from_db(chat_id)
    if not details:
        return jsonify({"error": "Chat not found"}), 404
    history = get_chat_history_from_db(chat_id)
    return jsonify({"details": details, "history": history})

@app.route('/api/chat/<int:chat_id>/name', methods=['PUT'])
def save_chat_name(chat_id):
    # (Unchanged logic)
    data = request.json
    new_name = data.get('name', '').strip()
    if not new_name: new_name = 'New Chat'
    if save_chat_name_in_db(chat_id, new_name):
        return jsonify({"message": "Chat name updated successfully."})
    else:
        return jsonify({"error": "Failed to update chat name"}), 500

@app.route('/api/chat/<int:chat_id>/model', methods=['PUT'])
def save_chat_model(chat_id):
    """API endpoint to update the model for a specific chat."""
    data = request.json
    new_model_name = data.get('model_name')

    if not new_model_name:
        return jsonify({"error": "Model name not provided"}), 400

    # Optional: Validate if the model name is in our known list
    if new_model_name not in AVAILABLE_MODELS:
         print(f"Warning: Saving potentially unknown model '{new_model_name}' for chat {chat_id}.")
         # return jsonify({"error": f"Invalid model name: {new_model_name}"}), 400

    if update_chat_model(chat_id, new_model_name):
        return jsonify({"message": f"Chat model updated to {new_model_name}."})
    else:
        return jsonify({"error": "Failed to update chat model"}), 500


@app.route('/api/chat/<int:chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    # (Unchanged logic)
    if delete_chat_from_db(chat_id):
        return jsonify({"message": "Chat deleted successfully."})
    else:
        return jsonify({"error": "Failed to delete chat"}), 500

# --- File API Endpoints (Unchanged from v2) ---
@app.route('/api/files', methods=['GET'])
def get_files():
    files = get_uploaded_files_from_db()
    return jsonify(files)

@app.route('/api/files', methods=['POST'])
def upload_file():
    data = request.json
    filename = data.get('filename')
    content = data.get('content')
    if not filename or content is None: return jsonify({"error": "Filename and content are required"}), 400
    filesize = len(content.encode('utf-8'))
    if filesize > MAX_FILE_SIZE_BYTES: return jsonify({"error": f"File exceeds maximum size of {MAX_FILE_SIZE_MB} MB"}), 413
    file_id = save_file_to_db(filename, content, filesize)
    if file_id:
        new_file_data = {"id": file_id, "filename": filename, "filesize": filesize, "uploaded_at": datetime.now().isoformat(), "has_summary": False}
        return jsonify(new_file_data), 201
    else: return jsonify({"error": "Failed to save file to database"}), 500

@app.route('/api/files/<int:file_id>/summary', methods=['GET'])
def get_summary(file_id):
    summary = get_or_generate_summary(file_id)
    if summary: return jsonify({"summary": summary})
    else: return jsonify({"error": "Could not retrieve or generate summary"}), 500

@app.route('/api/files/<int:file_id>/summary', methods=['PUT'])
def update_summary(file_id):
    data = request.json
    new_summary = data.get('summary')
    if new_summary is None: return jsonify({"error": "Summary content not provided"}), 400
    if save_summary_in_db(file_id, new_summary): return jsonify({"message": "Summary updated successfully."})
    else: return jsonify({"error": "Failed to update summary"}), 500

# --- Modified Message Sending Endpoint ---
@app.route('/api/chat/<int:chat_id>/message', methods=['POST'])
def send_message(chat_id):
    """Handles messages, uses chat-specific model, includes file context."""
    if not gemini_configured:
        return jsonify({"reply": "[Error: Gemini API Key not configured]"}), 503 # Service Unavailable

    data = request.json
    user_message = data.get('message', '')
    attached_files = data.get('attached_files', [])

    if not user_message and not attached_files:
        return jsonify({"error": "No message or attached files provided"}), 400

    # --- Get Chat-Specific Model ---
    chat_details = get_chat_details_from_db(chat_id)
    if not chat_details:
        return jsonify({"error": "Chat not found"}), 404

    model_name = chat_details.get('model_name', DEFAULT_MODEL)
    print(f"Using model '{model_name}' for chat {chat_id}.")

    # --- Prepare context from attached files (same logic as v2) ---
    files_context = ""
    files_info_for_history = []
    if attached_files:
        print(f"Processing {len(attached_files)} attached files...")
        for file_info in attached_files:
            file_id = file_info.get('id')
            attach_type = file_info.get('type', 'full')
            if not file_id: continue
            file_data = get_file_content_and_name_from_db(file_id)
            filename = file_data['filename'] if file_data else f"File ID {file_id}"
            content_to_add = f"[Error: Could not process file '{filename}']"
            history_marker = f"[Attached File: '{filename}' (ID: {file_id}, Type: {attach_type})]"
            if attach_type == 'full':
                if file_data and file_data['content']:
                    print(f"Attaching full content for file '{filename}' (ID: {file_id})")
                    content_to_add = f"--- Start of file '{filename}' ---\n{file_data['content']}\n--- End of file '{filename}' ---"
                else:
                     print(f"Warning: Could not get full content for file '{filename}' (ID: {file_id})")
                     history_marker = f"[Error attaching full file: '{filename}' (ID: {file_id})]"
            elif attach_type == 'summary':
                print(f"Attaching summary for file '{filename}' (ID: {file_id})")
                summary = get_or_generate_summary(file_id)
                if summary: content_to_add = f"--- Summary of file '{filename}' ---\n{summary}\n--- End of Summary ---"
                else:
                    content_to_add = f"[Error: Could not get or generate summary for '{filename}']"
                    history_marker = f"[Error attaching summary: '{filename}' (ID: {file_id})]"
            else:
                print(f"Warning: Unknown attachment type '{attach_type}' for file ID {file_id}")
                history_marker = f"[Error: Unknown attachment type for file '{filename}' (ID: {file_id})]"
            files_context += content_to_add + "\n\n"
            files_info_for_history.append(history_marker)

    # --- Combine context and user message ---
    full_user_content_for_ai = files_context + f"User message: {user_message}"
    history_message = "\n".join(files_info_for_history) + ("\n" if files_info_for_history else "") + user_message

    # Add user message (with markers) to DB history
    if not add_message_to_db(chat_id, 'user', history_message):
         return jsonify({"error": "Failed to save user message"}), 500

    assistant_reply = "[AI response error occurred]"

    # --- Gemini Interaction ---
    try:
        # Instantiate the specific model for this chat
        try:
             chat_model = genai.GenerativeModel(model_name)
        except Exception as model_init_error:
             print(f"Error initializing model '{model_name}': {model_init_error}. Falling back to default '{DEFAULT_MODEL}'.")
             # Optionally save the default model back to the chat settings
             # update_chat_model(chat_id, DEFAULT_MODEL)
             chat_model = genai.GenerativeModel(DEFAULT_MODEL)
             assistant_reply = f"[System: Model '{model_name}' not found, using default '{DEFAULT_MODEL}'.] "


        # Build context from history (markers only)
        history_for_gemini_raw = get_chat_history_from_db(chat_id, limit=20)
        gemini_context = []
        for msg in history_for_gemini_raw:
            role = 'model' if msg['role'] == 'assistant' else 'user'
            gemini_context.append({"role": role, "parts": [msg['content']]})
        if gemini_context and gemini_context[-1]['role'] == 'user':
             gemini_context.pop() # Remove last user msg context

        print(f"--- Sending to Gemini (Chat ID: {chat_id}, Model: {model_name}) ---")
        print(f"Combined Content Start: {full_user_content_for_ai[:300]}...")
        print("--- End Gemini Send ---")

        # Generate content using the selected model
        response = chat_model.generate_content(gemini_context + [{"role": "user", "parts": [full_user_content_for_ai]}])

        # Prepend system message if model fallback occurred
        if assistant_reply != "[AI response error occurred]": # Check if fallback message was set
             assistant_reply += response.text
        else:
             assistant_reply = response.text

        print(f"Gemini Response: {assistant_reply[:100]}...")

    except Exception as e:
        print(f"Error calling Gemini API for chat {chat_id} with model {model_name}: {e}")
        error_message = f"[Error communicating with AI: {e}]"
        # More specific error handling
        if "API key not valid" in str(e): error_message = "[Error: Invalid Gemini API Key.]"
        elif "token" in str(e).lower() or "size" in str(e).lower(): error_message = "[Error: Request too large. Try summaries or fewer files.]"
        elif "prompt was blocked" in str(e).lower(): error_message = "[Error: Request blocked by safety settings.]"
        elif "resource has been exhausted" in str(e).lower(): error_message = "[Error: API quota exceeded. Please try again later.]"
        # Append specific error to any fallback message
        if assistant_reply != "[AI response error occurred]": assistant_reply += "\n" + error_message
        else: assistant_reply = error_message


    # Add assistant reply to DB
    add_message_to_db(chat_id, 'assistant', assistant_reply)

    return jsonify({"reply": assistant_reply})


# --- Main Execution ---
if __name__ == '__main__':
    with app.app_context():
        print("Initializing database...")
        init_db()
    print(f"Starting Flask server on http://127.0.0.1:5000 (DB: {DB_NAME})")
    app.run(debug=True, host='127.0.0.1', port=5000)

