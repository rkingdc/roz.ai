# app/routes/chat_routes.py
from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from .. import database as db  # Use relative import for database module
from .. import ai_services  # Use relative import for ai services

# Configure logging
import logging

logging.basicConfig(level=logging.INFO)
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
        chat_details = db.get_chat_details_from_db(new_chat_id)
        if not chat_details:
            # Should not happen right after creation, but handle defensively
            return (
                jsonify({"error": "Failed to retrieve newly created chat details"}),
                500,
            )
        return jsonify(chat_details), 201  # 201 Created
    except Exception as e:
        logger.error(f"Error creating new chat: {e}", exc_info=True)
        return jsonify({"error": "Failed to create new chat"}), 500


@bp.route("/chat/<int:chat_id>", methods=["GET"])
def get_chat(chat_id):
    """API endpoint to get details and history for a specific chat."""
    details = db.get_chat_details_from_db(chat_id)
    if not details:
        return jsonify({"error": "Chat not found"}), 404
    history = db.get_chat_history_from_db(chat_id)
    return jsonify({"details": details, "history": history})


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
        # Log error? DB function already prints
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
        return jsonify({"error": "Failed to update chat model"}), 500


@bp.route("/chat/<int:chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    """API endpoint to delete a chat."""
    if db.delete_chat_from_db(chat_id):
        return jsonify({"message": "Chat deleted successfully."})
    else:
        return jsonify({"error": "Failed to delete chat"}), 500


@bp.route("/chat/<int:chat_id>/message", methods=["POST"])
def send_message_route(chat_id):
    """API endpoint to handle user messages, potentially with attached files/calendar context, and get assistant responses."""
    data = request.json
    user_message = data.get("message", "")
    attached_files = data.get("attached_files", []) # List of {id, filename, type}
    calendar_context = data.get("calendar_context")  # Get calendar context from request
    session_files = data.get("session_files", [])  # Get session files from request, list of {filename, mimetype, content}
    enable_web_search = data.get(
        "enable_web_search", False
    )  # Get web search flag, default to False
    enable_streaming = data.get(
        "enable_streaming", False
    ) # Get streaming flag, default to False

    # Check if there's any actual input to process
    # Allow sending if web search is enabled, even without user message, if that's desired behavior
    # The AI service function handles the case where user_message is empty but context/files are present.
    if (
        not user_message
        and not attached_files
        and not calendar_context
        and not session_files
        and not enable_web_search # Added check for web search
    ):
        return jsonify({"error": "No message, files, context, or search request provided"}), 400

    try:
        # Call the AI service function to handle the core logic
        # This function is now *always* a generator function because it contains 'yield'
        assistant_response_generator = ai_services.generate_chat_response(
            chat_id=chat_id,
            user_message=user_message,
            attached_files=attached_files, # Pass the list of {id, filename, type}
            session_files=session_files,  # Pass the list of {filename, mimetype, content}
            calendar_context=calendar_context,  # Pass calendar context
            web_search_enabled=enable_web_search,  # Pass web search flag
            streaming_enabled=enable_streaming, # Pass streaming flag
        )

        if enable_streaming:
            # If streaming is enabled, iterate the generator and yield chunks to the client
            def stream_generator():
                full_reply = ""
                try:
                    for chunk in assistant_response_generator: # Iterate the generator
                        full_reply += chunk
                        yield chunk # Yield to the Flask stream
                except Exception as e:
                    # Log error during streaming
                    logger.error(f"Error during streaming for chat {chat_id}: {e}", exc_info=True)
                    # Yield an error message chunk to the client
                    yield f"\n[Streaming Error: {e}]"
                    full_reply += f"\n[Streaming Error: {e}]" # Append to full reply for saving
                finally:
                    # Save the full accumulated reply to the database after streaming finishes or errors
                    if full_reply:
                        # Ensure the role is 'assistant' when saving the final message
                        if not db.add_message_to_db(chat_id, "assistant", full_reply):
                            logger.warning(f"Failed to save full streamed assistant message for chat {chat_id}.")
                    else:
                         # Handle case where generator yielded nothing (e.g., immediate error)
                         logger.warning(f"Streaming generator for chat {chat_id} yielded no content.")
                         # Optionally save a placeholder error if nothing was yielded
                         # if not db.add_message_to_db(chat_id, "assistant", "[No content streamed]"):
                         #     logger.warning(f"Failed to save empty streamed message placeholder for chat {chat_id}.")


            # Return a streaming response
            return Response(stream_with_context(stream_generator()), mimetype='text/plain')

        else:
            # If streaming is disabled, iterate the generator to get the full reply
            full_reply = ""
            try:
                for chunk in assistant_response_generator: # Iterate the generator
                    full_reply += chunk
            except Exception as e:
                 # Handle errors during non-streaming iteration
                 logger.error(f"Error during non-streaming iteration for chat {chat_id}: {e}", exc_info=True)
                 full_reply += f"\n[Non-Streaming Iteration Error: {type(e).__name__}]"

            assistant_reply = full_reply # Now assistant_reply is the full string

            # Check if the reply indicates an internal error occurred
            # Use a default status code of 200 unless an error is detected
            status_code = 200
            if isinstance(assistant_reply, str) and (assistant_reply.startswith("[Error:") or assistant_reply.startswith("[Unexpected AI Error:")):
                # Determine appropriate status code based on error message if possible
                status_code = 500  # Default to internal server error for AI errors
                if "not found" in assistant_reply.lower():
                    status_code = 404
                elif (
                    "quota exceeded" in assistant_reply.lower()
                    or "too many requests" in assistant_reply.lower()
                ):
                    status_code = 429
                elif "invalid api key" in assistant_reply.lower():
                    status_code = 503  # Service unavailable due to config
                elif "request too large" in assistant_reply.lower():
                    status_code = 413  # Payload too large
                elif "timed out" in assistant_reply.lower():
                     status_code = 504 # Gateway Timeout
                # Note: Other specific errors from ai_services might also warrant different codes

                # Save the error message to the database
                if not db.add_message_to_db(chat_id, "assistant", assistant_reply):
                     logger.warning(f"Failed to save non-streaming error message for chat {chat_id}.")

                return jsonify({"reply": assistant_reply}), status_code
            else:
                # Save the successful non-streaming reply to the database
                if not db.add_message_to_db(chat_id, "assistant", assistant_reply):
                     logger.warning(f"Failed to save non-streaming assistant message for chat {chat_id}.")
                return jsonify({"reply": assistant_reply}), status_code # Return with 200 OK

    except Exception as e:
        # Catch unexpected errors *within this route handler* before calling ai_services
        # or if ai_services raises an exception not caught internally (less likely now)
        logger.error(
            f"Unexpected error in send_message route for chat {chat_id}: {e}",
            exc_info=True,
        )
        error_reply = f"[Unexpected Server Error in route: {e}]"
        # Attempt to save the unexpected error message
        if not db.add_message_to_db(chat_id, "assistant", error_reply):
             logger.warning(f"Failed to save unexpected route error message for chat {chat_id}.")

        return (
            jsonify({"reply": error_reply}), # More specific error message
            500,
        )

