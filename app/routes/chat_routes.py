# app/routes/chat_routes.py
from flask import Blueprint, request, jsonify, current_app
from .. import database as db # Use relative import for database module
from .. import ai_services # Use relative import for ai services

# Create Blueprint for chat API, using '/api' prefix
bp = Blueprint('chat_api', __name__, url_prefix='/api')

@bp.route('/chats', methods=['GET'])
def get_saved_chats():
    """API endpoint to get the list of saved chats."""
    chats = db.get_saved_chats_from_db()
    return jsonify(chats)

@bp.route('/chat', methods=['POST'])
def create_new_chat():
    """API endpoint to create a new chat session."""
    try:
        new_chat_id = db.create_new_chat_entry()
        chat_details = db.get_chat_details_from_db(new_chat_id)
        if not chat_details:
             # Should not happen right after creation, but handle defensively
             return jsonify({"error": "Failed to retrieve newly created chat details"}), 500
        return jsonify(chat_details), 201 # 201 Created
    except Exception as e:
        current_app.logger.error(f"Error creating new chat: {e}", exc_info=True)
        return jsonify({"error": "Failed to create new chat"}), 500

@bp.route('/chat/<int:chat_id>', methods=['GET'])
def get_chat(chat_id):
    """API endpoint to get details and history for a specific chat."""
    details = db.get_chat_details_from_db(chat_id)
    if not details:
        return jsonify({"error": "Chat not found"}), 404
    history = db.get_chat_history_from_db(chat_id)
    return jsonify({
        "details": details,
        "history": history
    })

@bp.route('/chat/<int:chat_id>/name', methods=['PUT'])
def save_chat_name(chat_id):
    """API endpoint to update the name of a chat."""
    data = request.json
    new_name = data.get('name', '').strip()
    if not new_name: new_name = 'New Chat' # Default if empty

    if db.save_chat_name_in_db(chat_id, new_name):
        return jsonify({"message": "Chat name updated successfully."})
    else:
        # Log error? DB function already prints
        return jsonify({"error": "Failed to update chat name"}), 500

@bp.route('/chat/<int:chat_id>/model', methods=['PUT'])
def save_chat_model(chat_id):
    """API endpoint to update the model for a specific chat."""
    data = request.json
    new_model_name = data.get('model_name')
    available_models = current_app.config.get('AVAILABLE_MODELS', [])

    if not new_model_name:
        return jsonify({"error": "Model name not provided"}), 400

    # Optional: Strict validation against available models
    if new_model_name not in available_models:
         print(f"Warning: Saving potentially unknown model '{new_model_name}' for chat {chat_id}.")
         # Depending on requirements, you might return an error here:
         # return jsonify({"error": f"Invalid model name specified. Choose from: {', '.join(available_models)}"}), 400

    if db.update_chat_model(chat_id, new_model_name):
        return jsonify({"message": f"Chat model updated to {new_model_name}."})
    else:
        return jsonify({"error": "Failed to update chat model"}), 500

@bp.route('/chat/<int:chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    """API endpoint to delete a chat."""
    if db.delete_chat_from_db(chat_id):
        return jsonify({"message": "Chat deleted successfully."})
    else:
        return jsonify({"error": "Failed to delete chat"}), 500

@bp.route('/chat/<int:chat_id>/message', methods=['POST'])
def send_message_route(chat_id):
    """API endpoint to handle user messages, potentially with attached files, and get assistant responses."""
    data = request.json
    user_message = data.get('message', '')
    attached_files = data.get('attached_files', []) # Expecting [{id, type}]

    if not user_message and not attached_files:
        return jsonify({"error": "No message or attached files provided"}), 400

    try:
        # Call the AI service function to handle the core logic
        assistant_reply = ai_services.generate_chat_response(
            chat_id,
            user_message,
            attached_files
        )
        # Check if the reply indicates an internal error occurred
        if assistant_reply.startswith("[Error:"):
             # Return a 500 status for internal errors signaled this way
             return jsonify({"reply": assistant_reply}), 500
        else:
            return jsonify({"reply": assistant_reply})

    except Exception as e:
        # Catch unexpected errors during the process
        current_app.logger.error(f"Unexpected error in send_message route for chat {chat_id}: {e}", exc_info=True)
        return jsonify({"reply": f"[Unexpected Server Error: {e}]"}), 500

