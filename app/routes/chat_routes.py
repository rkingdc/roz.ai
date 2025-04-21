# app/routes/chat_routes.py
from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
from .. import database as db  # Use relative import for database module
from .. import ai_services  # Use relative import for ai services

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
                logger.info(f"Starting iteration over streaming generator for chat {chat_id}.") # Add log before loop
                try:
                    for chunk in assistant_response_generator: # Iterate the generator
                        # *** ADDED LOGGING FOR CHUNK INSPECTION ***
                        logger.debug(f"Received chunk type: {type(chunk)}")
                        try:
                            # Attempt to log chunk contents, handle potential errors
                            if hasattr(chunk, '__dict__'):
                                logger.debug(f"Chunk __dict__: {chunk.__dict__}")
                            elif hasattr(chunk, '__slots__'):
                                slot_data = {slot: getattr(chunk, slot) for slot in chunk.__slots__ if hasattr(chunk, slot)}
                                logger.debug(f"Chunk __slots__ data: {slot_data}")
                            else:
                                logger.debug(f"Chunk representation: {chunk!r}") # Use !r for representation
                        except Exception as log_e:
                            logger.error(f"Error logging chunk details: {log_e}", exc_info=True)
                        # *** END ADDED LOGGING ***


                        chunk_to_send = "" # What we will send to the client for this chunk
                        log_message = f"Processing chunk: {chunk}" # Default log

                        # *** FIX: Extract text or system message from chunk ***
                        # Prioritize text content
                        if hasattr(chunk, 'text') and chunk.text:
                            chunk_to_send = chunk.text
                            log_message = f"Streaming chunk text (length {len(chunk_to_send)}): {chunk_to_send[:100]}..." # Log start of text
                        # Check for prompt feedback if no text
                        elif hasattr(chunk, 'prompt_feedback') and chunk.prompt_feedback:
                            feedback_reason = "N/A"
                            try:
                                if chunk.prompt_feedback.block_reason:
                                    feedback_reason = chunk.prompt_feedback.block_reason
                            except Exception:
                                pass
                            chunk_to_send = f"\n[AI Safety Error: Request or response blocked due to safety settings (Reason: {feedback_reason})]"
                            log_message = f"Streaming chunk has prompt feedback: {chunk.prompt_feedback}. Yielding system message."
                        # Log other types of chunks without yielding
                        elif hasattr(chunk, 'candidates') and chunk.candidates:
                             log_message = f"Streaming chunk has candidates but no text: {chunk}"
                        else:
                             log_message = f"Streaming chunk has no text, candidates, or feedback: {chunk}"

                        logger.info(log_message)

                        if chunk_to_send: # Only yield and accumulate if we have something to send
                            full_reply += chunk_to_send
                            yield chunk_to_send

                    logger.info(f"Finished iteration over streaming generator for chat {chat_id}.") # Add log after loop
                    # After the loop finishes, check if any content was yielded
                    if not full_reply:
                         logger.warning(f"Streaming generator for chat {chat_id} yielded no content.")
                         # Optionally yield a final message if nothing was ever yielded
                         # final_message = "[System Note: The AI did not return any content.]"
                         # yield final_message
                         # full_reply = final_message # Update full_reply for saving


                except Exception as e:
                    # Log error during streaming
                    logger.error(f"Error during streaming iteration for chat {chat_id}: {e}", exc_info=True)
                    # Yield an error message chunk to the client
                    error_chunk = f"\n[Streaming Error: {type(e).__name__}]"
                    yield error_chunk
                    full_reply += error_chunk # Append to full reply for saving
                finally:
                    # Save the full accumulated reply to the database after streaming finishes or errors
                    # *** FIX: Always attempt to save the reply, even if empty ***
                    # Ensure the role is 'assistant' when saving the final message
                    if not full_reply:
                         # If no content was yielded, save a placeholder or the warning message
                         # Use a specific placeholder that indicates no content was received
                         full_reply = "[System Note: The AI did not return any content.]"
                         logger.warning(f"Streaming generator for chat {chat_id} yielded no content. Saving placeholder.")

                    # Only save if full_reply is not None or empty after processing
                    if full_reply:
                        if not db.add_message_to_db(chat_id, "assistant", full_reply):
                            logger.warning(f"Failed to save full streamed assistant message for chat {chat_id}.")
                    # Removed the else block that logged "yielded no content" here,
                    # as that warning is now handled inside the try block after the loop.


            # Return a streaming response
            return Response(stream_with_context(stream_generator()), mimetype='text/plain')

        else:
            # If streaming is disabled, iterate the generator to get the full reply
            full_reply = ""
            try:
                for chunk in assistant_response_generator: # Iterate the generator
                    # *** FIX: Access the .text attribute of the chunk for non-streaming accumulation ***
                    chunk_text = ""
                    if hasattr(chunk, 'text'):
                         chunk_text = chunk.text
                    elif hasattr(chunk, 'candidates') and chunk.candidates:
                         logger.info(f"Non-streaming chunk has candidates but no text: {chunk}")
                    elif hasattr(chunk, 'prompt_feedback'):
                         logger.info(f"Non-streaming chunk has prompt feedback: {chunk.prompt_feedback}")
                    else:
                         logger.info(f"Non-streaming chunk has no text, candidates, or feedback: {chunk}")

                    full_reply += chunk_text

            except Exception as e:
                 # Handle errors during non-streaming iteration
                 logger.error(f"Error during non-streaming iteration for chat {chat_id}: {e}", exc_info=True)
                 full_reply += f"\n[Non-Streaming Iteration Error: {type(e).__name__}]"

            assistant_reply = full_reply # Now assistant_reply is the full string

            # Check if the reply indicates an internal error occurred
            # Use a default status code of 200 unless an error is detected
            status_code = 200
            if isinstance(assistant_reply, str) and (assistant_reply.startswith("[Error:") or assistant_reply.startswith("[Unexpected AI Error:") or assistant_reply.startswith("[CRITICAL Unexpected AI Service Error:")):
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
        error_reply = f"[Unexpected Server Error in route: {type(e).__name__}]" # More specific error message
        # Attempt to save the unexpected error message
        if not db.add_message_to_db(chat_id, "assistant", error_reply):
             logger.warning(f"Failed to save unexpected route error message for chat {chat_id}.")

        return (
            jsonify({"reply": error_reply}), # More specific error message
            500,
        )

