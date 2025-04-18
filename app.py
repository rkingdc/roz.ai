import os
import sqlite3
import json
from flask import Flask, request, jsonify, render_template, g # Added g
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = 'assistant_chat_v2.db' # Use a new DB name to avoid conflicts

if not API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set. AI features will be disabled.")

# Configure Gemini client
if API_KEY:
    genai.configure(api_key=API_KEY)
    try:
        # Check available models (optional, good for debugging)
        # print("Available Gemini Models:")
        # for m in genai.list_models():
        #     if 'generateContent' in m.supported_generation_methods:
        #         print(m.name)
        model = genai.GenerativeModel('gemini-1.5-flash') # Or another suitable model like gemini-pro
        print("Gemini model loaded successfully.")
    except Exception as e:
        print(f"Error initializing Gemini model: {e}")
        model = None
else:
    model = None

# --- Flask App Setup ---
app = Flask(__name__) # Looks for templates in 'templates' folder

# --- Database Setup ---
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row # Return rows as dictionary-like objects
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    db = get_db()
    cursor = db.cursor()
    # Create chats table to store metadata for each chat session
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT 'New Chat',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Create messages table to store individual messages linked to a chat
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL, -- 'user' or 'assistant'
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE -- Delete messages if chat is deleted
        )
    ''')
    # Index for faster message retrieval
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages (chat_id)')
    db.commit()
    print("Database initialized.")

# --- Database Interaction Functions ---

def create_new_chat_entry():
    """Creates a new chat entry in the chats table and returns its ID."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute("INSERT INTO chats (created_at, last_updated_at) VALUES (?, ?)", (now, now))
    db.commit()
    new_chat_id = cursor.lastrowid
    print(f"Created new chat with ID: {new_chat_id}")
    return new_chat_id

def update_chat_timestamp(chat_id):
    """Updates the last_updated_at timestamp for a given chat."""
    db = get_db()
    cursor = db.cursor()
    now = datetime.now()
    cursor.execute("UPDATE chats SET last_updated_at = ? WHERE id = ?", (now, chat_id))
    db.commit()

def add_message_to_db(chat_id, role, content):
    """Adds a message to the messages table for a specific chat."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
                       (chat_id, role, content))
        db.commit()
        update_chat_timestamp(chat_id) # Update chat timestamp when a message is added
        return True
    except sqlite3.Error as e:
        print(f"Database error adding message: {e}")
        return False

def get_chat_history_from_db(chat_id, limit=100):
    """Retrieves messages for a specific chat_id."""
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
        # Convert Row objects to dictionaries for JSON serialization
        return [dict(row) for row in history]
    except sqlite3.Error as e:
        print(f"Database error getting history for chat {chat_id}: {e}")
        return []

def get_chat_details_from_db(chat_id):
    """Retrieves details (like name) for a specific chat_id."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, created_at, last_updated_at FROM chats WHERE id = ?", (chat_id,))
        chat_details = cursor.fetchone()
        return dict(chat_details) if chat_details else None
    except sqlite3.Error as e:
        print(f"Database error getting details for chat {chat_id}: {e}")
        return None


def get_saved_chats_from_db():
    """Retrieves a list of all chats, ordered by last updated."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, last_updated_at FROM chats ORDER BY last_updated_at DESC")
        chats = cursor.fetchall()
        # Convert Row objects to dictionaries
        return [dict(row) for row in chats]
    except sqlite3.Error as e:
        print(f"Database error getting saved chats: {e}")
        return []

def save_chat_name_in_db(chat_id, name):
    """Updates the name of a specific chat."""
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

def delete_chat_from_db(chat_id):
    """Deletes a chat and its associated messages."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Cascading delete should handle messages due to FOREIGN KEY constraint
        cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        db.commit()
        print(f"Deleted chat with ID: {chat_id}")
        return True
    except sqlite3.Error as e:
        print(f"Database error deleting chat {chat_id}: {e}")
        return False

# --- Plugin System (Placeholder - Unchanged) ---
def run_plugin(plugin_name, data):
    print(f"Attempting to run plugin: {plugin_name} with data: {data}")
    if plugin_name == "read_file":
        try:
            file_path = data.get("path")
            if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
                 with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                     content = f.read(5000) # Read max 5000 chars
                 return f"Successfully read content from {file_path}:\n\n{content}"
            else:
                return f"Error: File not found or invalid path: {file_path}"
        except Exception as e:
            return f"Error reading file {file_path}: {e}"
    elif plugin_name == "google_calendar":
        return "Google Calendar plugin not implemented yet."
    else:
        return f"Unknown plugin: {plugin_name}"

# --- Flask Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('main.html') # Renders templates/main.html

@app.route('/api/chats', methods=['GET'])
def get_saved_chats():
    """API endpoint to get the list of saved chats."""
    chats = get_saved_chats_from_db()
    return jsonify(chats)

@app.route('/api/chat', methods=['POST'])
def create_new_chat():
    """API endpoint to create a new chat session."""
    try:
        new_chat_id = create_new_chat_entry()
        chat_details = get_chat_details_from_db(new_chat_id)
        return jsonify(chat_details), 201 # 201 Created
    except Exception as e:
        print(f"Error creating new chat: {e}")
        return jsonify({"error": "Failed to create new chat"}), 500

@app.route('/api/chat/<int:chat_id>', methods=['GET'])
def get_chat(chat_id):
    """API endpoint to get details and history for a specific chat."""
    details = get_chat_details_from_db(chat_id)
    if not details:
        return jsonify({"error": "Chat not found"}), 404
    history = get_chat_history_from_db(chat_id)
    return jsonify({
        "details": details,
        "history": history
    })

@app.route('/api/chat/<int:chat_id>/name', methods=['PUT'])
def save_chat_name(chat_id):
    """API endpoint to update the name of a chat."""
    data = request.json
    new_name = data.get('name')
    if not new_name:
        return jsonify({"error": "New name not provided"}), 400

    if save_chat_name_in_db(chat_id, new_name):
        return jsonify({"message": "Chat name updated successfully."})
    else:
        return jsonify({"error": "Failed to update chat name"}), 500

@app.route('/api/chat/<int:chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """API endpoint to delete a chat."""
    if delete_chat_from_db(chat_id):
        return jsonify({"message": "Chat deleted successfully."})
    else:
        return jsonify({"error": "Failed to delete chat"}), 500

@app.route('/api/chat/<int:chat_id>/message', methods=['POST'])
def send_message(chat_id):
    """API endpoint to handle user messages and get assistant responses for a specific chat."""
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Add user message to DB for the specific chat
    if not add_message_to_db(chat_id, 'user', user_message):
         return jsonify({"error": "Failed to save user message"}), 500

    assistant_reply = "[AI response disabled or error occurred]" # Default reply

    # --- Gemini Interaction ---
    if model:
        try:
            # --- Build context for Gemini ---
            # Retrieve recent history for context (adjust limit as needed)
            history_for_gemini_raw = get_chat_history_from_db(chat_id, limit=20) # Get last 20 messages

            # Format history for Gemini API (alternating user/model roles)
            gemini_context = []
            for msg in history_for_gemini_raw:
                # Map DB role ('user', 'assistant') to Gemini role ('user', 'model')
                role = 'model' if msg['role'] == 'assistant' else 'user'
                gemini_context.append({"role": role, "parts": [msg['content']]})

            # Ensure the last message sent for context isn't the one we just added
            if gemini_context and gemini_context[-1]['role'] == 'user':
                 gemini_context.pop() # Remove the user message we just added

            # Add the current user message
            # gemini_context.append({"role": "user", "parts": [user_message]}) # Already added above

            print(f"--- Sending to Gemini (Chat ID: {chat_id}) ---")
            # print(f"Context: {json.dumps(gemini_context, indent=2)}") # DEBUG: Print context
            print(f"User Message: {user_message}")
            print("--- End Gemini Send ---")

            # Start chat session if needed or send message with history
            # Note: For simple Q&A, sending only the user_message might suffice.
            # For conversation, use model.start_chat(history=...) or send history with generate_content
            # Using generate_content with history directly:
            response = model.generate_content(gemini_context + [{"role": "user", "parts": [user_message]}])

            assistant_reply = response.text
            print(f"Gemini Response: {assistant_reply[:100]}...") # Print start of response

            # --- Basic Plugin Trigger (Example - Unchanged) ---
            if user_message.lower().startswith("read file:"):
                file_path = user_message.split(":", 1)[1].strip()
                plugin_result = run_plugin("read_file", {"path": file_path})
                assistant_reply = plugin_result # Override Gemini reply

            elif user_message.lower().startswith("check calendar"):
                 plugin_result = run_plugin("google_calendar", {})
                 assistant_reply = plugin_result # Override Gemini reply

        except Exception as e:
            print(f"Error calling Gemini API for chat {chat_id}: {e}")
            # Check for specific API errors if possible
            if "API key not valid" in str(e):
                 assistant_reply = "[Error: Invalid Gemini API Key. Please check your configuration.]"
            else:
                assistant_reply = f"[Error communicating with AI: {e}]"
        # except ConnectionError as e: # Often caught by the general Exception
        #      print(f"Connection error: {e}")
        #      assistant_reply = f"[Error: Could not connect to Gemini API. Check network or API key.]"
    else:
         assistant_reply = "[AI is not configured. Check API Key.]"


    # Add assistant reply to DB
    add_message_to_db(chat_id, 'assistant', assistant_reply)

    return jsonify({"reply": assistant_reply})


# --- Main Execution ---
if __name__ == '__main__':
    with app.app_context(): # Need app context to initialize DB
        print("Initializing database...")
        init_db()
    print(f"Starting Flask server on http://127.0.0.1:5000 (DB: {DB_NAME})")
    app.run(debug=True, host='127.0.0.1', port=5000)
