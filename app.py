import os
import sqlite3
import json
# Import render_template along with other Flask components
from flask import Flask, request, jsonify, render_template_string, render_template
# Make sure to install google-generativeai: pip install google-generativeai
import google.generativeai as genai
from dotenv import load_dotenv # Optional: for loading API key from .env file

# --- Configuration ---
load_dotenv() # Load environment variables from .env file if it exists
API_KEY = os.getenv("GEMINI_API_KEY")
DB_NAME = 'assistant_chat.db'

if not API_KEY:
    print("Error: GEMINI_API_KEY environment variable not set.")
    # You might want to exit or raise an error here in a real application
    # For this example, we'll proceed but Gemini calls will fail.

# Configure the Gemini client (only if API key is available)
if API_KEY:
    genai.configure(api_key=API_KEY)
    # Select the model
    # Check available models:
    # for m in genai.list_models():
    #   if 'generateContent' in m.supported_generation_methods:
    #     print(m.name)
    model = genai.GenerativeModel('gemini-1.5-flash') # Or another suitable model
else:
    model = None # No model if API key is missing

# --- Flask App Setup ---
app = Flask(__name__) # Flask will automatically look for templates in a 'templates' folder

# --- Database Setup ---
def init_db():
    """Initializes the SQLite database and creates the chat_history table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL, -- 'user' or 'assistant'
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Potentially add tables for summaries or plugins later
    conn.commit()
    conn.close()

def add_message_to_db(role, content):
    """Adds a message to the chat_history table."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def get_chat_history_from_db(limit=50):
    """Retrieves the last 'limit' messages from the chat_history table."""
    try:
        conn = sqlite3.connect(DB_NAME)
        # So Jinja2 template can access columns by name
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT role, content, timestamp FROM chat_history ORDER BY timestamp DESC LIMIT ?", (limit,))
        history = cursor.fetchall()
        conn.close()
        # Return in chronological order for display
        return reversed(history)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

# --- Plugin System (Placeholder) ---
# This is a very basic concept. A real plugin system would be more complex,
# involving dynamic loading, registration, and potentially security sandboxing.
def run_plugin(plugin_name, data):
    """Placeholder function to simulate running a plugin."""
    print(f"Attempting to run plugin: {plugin_name} with data: {data}")
    if plugin_name == "read_file":
        try:
            # VERY UNSAFE - DO NOT USE IN PRODUCTION WITHOUT SANITIZATION/VALIDATION
            # In a real app, you'd restrict file access heavily.
            file_path = data.get("path")
            if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
                 # Limit file size read? Add encoding handling?
                 with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                     content = f.read(5000) # Read max 5000 chars
                 return f"Successfully read content from {file_path}:\n\n{content}"
            else:
                return f"Error: File not found or invalid path: {file_path}"
        except Exception as e:
            return f"Error reading file {file_path}: {e}"
    elif plugin_name == "google_calendar":
        # This would require Google API Client Library, OAuth setup, etc.
        return "Google Calendar plugin not implemented yet."
    else:
        return f"Unknown plugin: {plugin_name}"

# --- Flask Routes ---
@app.route('/')
def index():
    """Serves the main HTML page from the templates folder."""
    # Use render_template to serve 'main.html' from the 'templates' folder
    return render_template('main.html')

@app.route('/get_history', methods=['GET'])
def get_history():
    """API endpoint to get chat history."""
    history = get_chat_history_from_db()
    # Convert Row objects to dictionaries for JSON serialization
    history_list = [dict(row) for row in history]
    return jsonify(history_list)

@app.route('/send_message', methods=['POST'])
def send_message():
    """API endpoint to handle user messages and get assistant responses."""
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Add user message to DB
    add_message_to_db('user', user_message)

    # --- Gemini Interaction ---
    if not model:
         add_message_to_db('assistant', "[Error: Gemini API key not configured or model not loaded.]")
         return jsonify({"reply": "[Error: Gemini API key not configured or model not loaded.]"})

    try:
        # Basic interaction - just send the latest message
        # For conversational context, you'd retrieve history and format it
        # according to Gemini API requirements (alternating user/model roles)
        # Example (needs refinement):
        # history_for_gemini = [{"role": "user", "parts": [prev_user_msg]}, {"role": "model", "parts": [prev_model_reply]}, ...]
        # response = model.generate_content(history_for_gemini + [{"role": "user", "parts": [user_message]}])

        response = model.generate_content(user_message)
        assistant_reply = response.text

        # --- Basic Plugin Trigger (Example) ---
        # Look for a simple trigger phrase. A real implementation would use
        # function calling if the model supports it, or more robust NLP.
        if user_message.lower().startswith("read file:"):
            file_path = user_message.split(":", 1)[1].strip()
            plugin_result = run_plugin("read_file", {"path": file_path})
            # Optionally, send plugin result back to Gemini for summarization/processing
            # For now, just return the raw plugin result directly
            assistant_reply = plugin_result # Override Gemini reply

        elif user_message.lower().startswith("check calendar"):
             plugin_result = run_plugin("google_calendar", {})
             assistant_reply = plugin_result # Override Gemini reply


    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        assistant_reply = f"[Error communicating with AI: {e}]"
    except ConnectionError as e:
         print(f"Connection error: {e}")
         assistant_reply = f"[Error: Could not connect to Gemini API. Check network or API key.]"


    # Add assistant reply to DB
    add_message_to_db('assistant', assistant_reply)

    return jsonify({"reply": assistant_reply})

# --- Frontend HTML is now removed from here ---

# --- Main Execution ---
if __name__ == '__main__':
    print("Initializing database...")
    init_db()
    print("Starting Flask server on http://127.0.0.1:5000")
    # Use host='0.0.0.0' to make it accessible on your network
    app.run(debug=True, host='127.0.0.1', port=5000) # debug=True for development
