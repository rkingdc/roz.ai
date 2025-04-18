import os
import sqlite3
import json
from flask import Flask, request, jsonify, render_template, g
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = "assistant_chat_v3.db"  # Use a new DB name for schema changes
MAX_FILE_SIZE_MB = 5  # Limit file upload size
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

if not API_KEY:
    print(
        "Warning: GEMINI_API_KEY environment variable not set. AI features will be disabled."
    )

# Configure Gemini client
if API_KEY:
    genai.configure(api_key=API_KEY)
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        print("Gemini model loaded successfully.")
    except Exception as e:
        print(f"Error initializing Gemini model: {e}")
        model = None
else:
    model = None

# --- Flask App Setup ---
app = Flask(__name__)


# --- Database Setup ---
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    cursor = db.cursor()
    # Chats table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    # Messages table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL, -- 'user' or 'assistant'
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
        )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)"
    )

    # Uploaded Files table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL, -- Store content directly (consider alternatives for large files)
            filesize INTEGER NOT NULL, -- Store size in bytes
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_filename ON uploaded_files (filename)"
    )

    db.commit()
    print("Database initialized with chats, messages, and uploaded_files tables.")


# --- Database Interaction Functions (Chats & Messages - Unchanged from previous) ---


def create_new_chat_entry():
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute(
        "INSERT INTO chats (created_at, last_updated_at) VALUES (?, ?)", (now, now)
    )
    db.commit()
    new_chat_id = cursor.lastrowid
    print(f"Created new chat with ID: {new_chat_id}")
    return new_chat_id


def update_chat_timestamp(chat_id):
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute("UPDATE chats SET last_updated_at = ? WHERE id = ?", (now, chat_id))
    db.commit()


def add_message_to_db(chat_id, role, content):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        db.commit()
        update_chat_timestamp(chat_id)
        return True
    except sqlite3.Error as e:
        print(f"Database error adding message: {e}")
        return False


def get_chat_history_from_db(chat_id, limit=100):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT role, content, timestamp
            FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        """,
            (chat_id, limit),
        )
        history = cursor.fetchall()
        return [dict(row) for row in history]
    except sqlite3.Error as e:
        print(f"Database error getting history for chat {chat_id}: {e}")
        return []


def get_chat_details_from_db(chat_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, created_at, last_updated_at FROM chats WHERE id = ?",
            (chat_id,),
        )
        chat_details = cursor.fetchone()
        return dict(chat_details) if chat_details else None
    except sqlite3.Error as e:
        print(f"Database error getting details for chat {chat_id}: {e}")
        return None


def get_saved_chats_from_db():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, last_updated_at FROM chats ORDER BY last_updated_at DESC"
        )
        chats = cursor.fetchall()
        return [dict(row) for row in chats]
    except sqlite3.Error as e:
        print(f"Database error getting saved chats: {e}")
        return []


def save_chat_name_in_db(chat_id, name):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE chats SET name = ?, last_updated_at = ? WHERE id = ?",
            (name, datetime.now(), chat_id),
        )
        db.commit()
        print(f"Updated name for chat {chat_id} to '{name}'")
        return True
    except sqlite3.Error as e:
        print(f"Database error saving chat name for {chat_id}: {e}")
        return False


def delete_chat_from_db(chat_id):
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


# --- Database Interaction Functions (Files) ---


def save_file_to_db(filename, content, filesize):
    """Saves file information to the database."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO uploaded_files (filename, content, filesize) VALUES (?, ?, ?)",
            (filename, content, filesize),
        )
        db.commit()
        file_id = cursor.lastrowid
        print(f"Saved file '{filename}' (ID: {file_id}, Size: {filesize} bytes) to DB.")
        return file_id
    except sqlite3.Error as e:
        print(f"Database error saving file '{filename}': {e}")
        return None


def get_uploaded_files_from_db():
    """Retrieves a list of all uploaded files (metadata only)."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Select metadata, excluding the large content field
        cursor.execute(
            "SELECT id, filename, filesize, uploaded_at FROM uploaded_files ORDER BY uploaded_at DESC"
        )
        files = cursor.fetchall()
        return [dict(row) for row in files]
    except sqlite3.Error as e:
        print(f"Database error getting file list: {e}")
        return []


def get_file_content_from_db(file_id):
    """Retrieves the content of a specific file."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT content, filename FROM uploaded_files WHERE id = ?", (file_id,)
        )
        file_data = cursor.fetchone()
        if file_data:
            print(
                f"Retrieved content for file ID: {file_id} (Filename: {file_data['filename']})"
            )
            return dict(file_data)
        else:
            print(f"File not found for ID: {file_id}")
            return None
    except sqlite3.Error as e:
        print(f"Database error getting content for file {file_id}: {e}")
        return None


# --- Flask Routes ---
@app.route("/")
def index():
    return render_template("main.html")


# --- Chat API Endpoints (Mostly Unchanged) ---
@app.route("/api/chats", methods=["GET"])
def get_saved_chats():
    chats = get_saved_chats_from_db()
    return jsonify(chats)


@app.route("/api/chat", methods=["POST"])
def create_new_chat():
    try:
        new_chat_id = create_new_chat_entry()
        chat_details = get_chat_details_from_db(new_chat_id)
        return jsonify(chat_details), 201
    except Exception as e:
        print(f"Error creating new chat: {e}")
        return jsonify({"error": "Failed to create new chat"}), 500


@app.route("/api/chat/<int:chat_id>", methods=["GET"])
def get_chat(chat_id):
    details = get_chat_details_from_db(chat_id)
    if not details:
        return jsonify({"error": "Chat not found"}), 404
    history = get_chat_history_from_db(chat_id)
    return jsonify({"details": details, "history": history})


@app.route("/api/chat/<int:chat_id>/name", methods=["PUT"])
def save_chat_name(chat_id):
    data = request.json
    new_name = data.get("name")
    if not new_name:
        # Allow setting back to default 'New Chat' if empty string is provided
        new_name = "New Chat"
    # if not new_name:
    #     return jsonify({"error": "New name not provided"}), 400

    if save_chat_name_in_db(chat_id, new_name):
        return jsonify({"message": "Chat name updated successfully."})
    else:
        return jsonify({"error": "Failed to update chat name"}), 500


@app.route("/api/chat/<int:chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    if delete_chat_from_db(chat_id):
        return jsonify({"message": "Chat deleted successfully."})
    else:
        return jsonify({"error": "Failed to delete chat"}), 500


# --- File API Endpoints ---
@app.route("/api/files", methods=["GET"])
def get_files():
    """API endpoint to get the list of uploaded files."""
    files = get_uploaded_files_from_db()
    return jsonify(files)


@app.route("/api/files", methods=["POST"])
def upload_file():
    """API endpoint to upload a new file."""
    data = request.json
    filename = data.get("filename")
    content = data.get("content")  # Assume content is sent as string

    if not filename or content is None:  # Check for None explicitly
        return jsonify({"error": "Filename and content are required"}), 400

    # Basic validation (e.g., file size)
    filesize = len(content.encode("utf-8"))  # Calculate size in bytes
    if filesize > MAX_FILE_SIZE_BYTES:
        return (
            jsonify({"error": f"File exceeds maximum size of {MAX_FILE_SIZE_MB} MB"}),
            413,
        )  # Payload Too Large

    file_id = save_file_to_db(filename, content, filesize)

    if file_id:
        # Return the newly created file's metadata
        new_file_data = {
            "id": file_id,
            "filename": filename,
            "filesize": filesize,
            "uploaded_at": datetime.now().isoformat(),  # Provide timestamp
        }
        return jsonify(new_file_data), 201
    else:
        return jsonify({"error": "Failed to save file to database"}), 500


# --- Modified Message Sending Endpoint ---
@app.route("/api/chat/<int:chat_id>/message", methods=["POST"])
def send_message(chat_id):
    """Handles user messages, potentially with attached files, and gets assistant responses."""
    data = request.json
    user_message = data.get("message")
    attached_file_id = data.get("attached_file_id")  # Get attached file ID

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # --- Prepare message content (potentially with file) ---
    full_user_content = user_message
    file_info_for_history = ""  # Store file info separately for DB history

    if attached_file_id:
        file_data = get_file_content_from_db(attached_file_id)
        if file_data:
            file_content = file_data["content"]
            file_name = file_data["filename"]
            print(
                f"Attaching content from file ID {attached_file_id} ('{file_name}') to message."
            )
            # How to combine? Prepend file content to user message for the AI.
            # WARNING: This can easily exceed token limits for large files!
            # Consider summarizing or using more advanced context management in production.
            full_user_content = f"--- Start of file '{file_name}' ---\n{file_content}\n--- End of file '{file_name}' ---\n\nUser message: {user_message}"
            file_info_for_history = (
                f"[Attached file: '{file_name}' (ID: {attached_file_id})]\n"
            )
        else:
            print(f"Warning: Attached file ID {attached_file_id} not found.")
            file_info_for_history = (
                f"[Error: Attached file ID {attached_file_id} not found]\n"
            )
            # Decide whether to proceed without file or return error. Let's proceed.

    # Add user message (without full file content) + file marker to DB history
    history_message = file_info_for_history + user_message
    if not add_message_to_db(chat_id, "user", history_message):
        return jsonify({"error": "Failed to save user message"}), 500

    assistant_reply = "[AI response disabled or error occurred]"  # Default reply

    # --- Gemini Interaction ---
    if model:
        try:
            # Build context for Gemini - retrieve history (without full file content)
            history_for_gemini_raw = get_chat_history_from_db(chat_id, limit=20)

            gemini_context = []
            for msg in history_for_gemini_raw:
                role = "model" if msg["role"] == "assistant" else "user"
                # Use the message as stored in DB (which has file marker, not full content)
                gemini_context.append({"role": role, "parts": [msg["content"]]})

            # Remove the last user message from context (we'll add the full version below)
            if gemini_context and gemini_context[-1]["role"] == "user":
                gemini_context.pop()

            print(f"--- Sending to Gemini (Chat ID: {chat_id}) ---")
            # Send the potentially combined user message + file content
            print(
                f"User Content (potentially w/ file): {full_user_content[:200]}..."
            )  # Log start
            print("--- End Gemini Send ---")

            # Use generate_content with history + the full user content
            response = model.generate_content(
                gemini_context + [{"role": "user", "parts": [full_user_content]}]
            )

            assistant_reply = response.text
            print(f"Gemini Response: {assistant_reply[:100]}...")

        except Exception as e:
            print(f"Error calling Gemini API for chat {chat_id}: {e}")
            if "API key not valid" in str(e):
                assistant_reply = "[Error: Invalid Gemini API Key.]"
            # Handle potential token limit errors specifically if possible
            elif "token" in str(e).lower():
                assistant_reply = "[Error: Request too large. The message or attached file might exceed the model's input limit.]"
            else:
                assistant_reply = f"[Error communicating with AI: {e}]"
    else:
        assistant_reply = "[AI is not configured. Check API Key.]"

    # Add assistant reply to DB
    add_message_to_db(chat_id, "assistant", assistant_reply)

    return jsonify({"reply": assistant_reply})


# --- Main Execution ---
if __name__ == "__main__":
    with app.app_context():
        print("Initializing database...")
        init_db()
    print(f"Starting Flask server on http://127.0.0.1:5000 (DB: {DB_NAME})")
    app.run(debug=True, host="127.0.0.1", port=5000)
