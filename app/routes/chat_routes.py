# app/routes/chat_routes.py
from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from .. import database as db  # Use relative import for database module
from .. import ai_services  # Use relative import for ai services
from .. import deep_research # Import the deep_research module

# Configure logging
import logging
# Removed basicConfig here, logging level is set in app/__init__.py
logger = logging.getLogger(__name__)


# Create Blueprint for chat API, using '/api' prefix
bp = Blueprint("chat_api", __name__, url_prefix="/api")


@bp.route("/chats", methods=["GET"])
def get_saved_chats():
    """API endpoint to get the list of saved chats."""
    chats = db.get_saved_chats_from_db()
    return jsonify(chats)


@bp.route("/chat", methods=["POST"])
def create_new_chat():
    """API endpoint to create a new chat session."""
    try:
        new_chat_id = db.create_new_chat_entry()
        if new_chat_id is None: # Check for None return on failure
             logger.error("Failed to create new chat entry in database.")
             return jsonify({"error": "Failed to create new chat entry"}), 500

        chat_details = db.get_chat_details_from_db(new_chat_id)
        if not chat_details:
            # Should not happen right after creation, but handle defensively
            logger.error(f"Failed to retrieve details for newly created chat ID {new_chat_id}")
            return (
                jsonify({"error": "Failed to retrieve newly created chat details"}),
                500,
            )
        return jsonify(chat_details), 201  # 201 Created
    except Exception as e:
        logger.error(f"Error creating new chat: {e}", exc_info=True)
        return jsonify({"error": "Failed to create new chat"}), 500


@bp.route("/chat/<int:chat_id>", methods=["GET", "DELETE"])
def get_chat(chat_id):
    """API endpoint to get details and history for a specific chat."""
    if request.method == "GET":
        details = db.get_chat_details_from_db(chat_id)
        if not details:
            return jsonify({"error": "Chat not found"}), 404
        history = db.get_chat_history_from_db(chat_id)
        return jsonify({"details": details, "history": history})
    elif request.method == "DELETE":
        # Handle DELETE request
        logger.info(f"Received DELETE request for chat {chat_id}")
        if db.delete_chat_from_db(chat_id):
            logger.info(f"Chat {chat_id} deleted successfully.")
            return jsonify({"message": f"Chat {chat_id} deleted."}), 200
        else:
            # delete_chat_from_db returns False if chat not found or db error
            # We can't distinguish easily here, assume not found for 404
            logger.warning(f"Failed to delete chat {chat_id} (possibly not found or DB error).")
            # Check if chat exists before returning 404
            if db.get_chat_details_from_db(chat_id):
                 # Chat exists but delete failed - likely DB error
                 logger.error(f"Database error occurred while trying to delete chat {chat_id}.")
                 return jsonify({"error": f"Failed to delete chat {chat_id} due to a database error."}), 500
            else:
                 # Chat did not exist
                 logger.warning(f"Attempted to delete non-existent chat {chat_id}.")
                 return jsonify({"error": f"Chat {chat_id} not found"}), 404
    else:
        # This case should technically not be reached due to methods=["GET", "DELETE"]
        # but included for robustness.
        return jsonify({"error": "Method not allowed"}), 405


@bp.route("/chat/<int:chat_id>/name", methods=["PUT"])
def save_chat_name(chat_id):
    """API endpoint to update the name of a chat."""
    data = request.json
    new_name = data.get("name", "").strip()
    if not new_name:
        new_name = "New Chat"  # Default if empty

    if db.save_chat_name_in_db(chat_id, new_name):
        return jsonify({"message": "Chat name updated successfully."})
    else:
        logger.error(f"Failed to save chat name for chat {chat_id} in database.")
        return jsonify({"error": "Failed to update chat name"}), 500


@bp.route("/chat/<int:chat_id>/model", methods=["PUT"])
def save_chat_model(chat_id):
    """API endpoint to update the model for a specific chat."""
    data = request.json
    new_model_name = data.get("model_name")
    available_models = current_app.config.get("AVAILABLE_MODELS", [])

    if not new_model_name:
        return jsonify({"error": "Model name not provided"}), 400

    # Optional: Strict validation against available models
    if new_model_name not in available_models:
        logger.warning(
            f"Warning: Saving potentially unknown model '{new_model_name}' for chat {chat_id}. Available: {', '.join(available_models)}"
        )
        # Depending on requirements, you might return an error here:
        # return jsonify({"error": f"Invalid model name specified. Choose from: {', '.join(available_models)}"}), 400

    if db.update_chat_model(chat_id, new_model_name):
        return jsonify({"message": f"Chat model updated to {new_model_name}."})
    else:
        logger.error(f"Failed to update chat model for chat {chat_id} in database.")
        return jsonify({"error": "Failed to update chat model"}), 500

# Removed the HTTP route for sending messages (@bp.route("/chat/<int:chat_id>/message", methods=["POST"]))
# Message sending is now handled by the 'send_chat_message' SocketIO event in app/sockets.py
