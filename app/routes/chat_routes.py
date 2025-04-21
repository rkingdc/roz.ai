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
                logger.info(f"Starting iteration over streaming generator for chat {chat_id}.")
                try:
                    for chunk in assistant_response_generator: # Iterate the generator
                        # *** FIX: Extract text or system message from chunk ***
                        chunk_to_send = "" # What we will send to the client for this chunk
                        log_message = f"Processing raw chunk: {chunk!r}" # Log representation

                        try:
                            # Prioritize extracting text content
                            if hasattr(chunk, 'text') and chunk.text:
                                chunk_to_send = chunk.text
                                log_message = f"Streaming chunk text (length {len(chunk_to_send)}): {chunk_to_send[:100]}..." # Log start of text
                            # Check for prompt feedback (safety blocking) if no text
                            elif hasattr(chunk, 'prompt_feedback') and chunk.prompt_feedback:
                                feedback_reason = "N/A"
                                try:
                                    # Access block_reason safely
                                    if chunk.prompt_feedback.block_reason:
                                        feedback_reason = chunk.prompt_feedback.block_reason.name # Use .name for enum
                                except AttributeError:
                                    feedback_reason = str(chunk.prompt_feedback.block_reason) # Fallback to string
                                except Exception:
                                    pass # Ignore other errors getting reason
                                chunk_to_send = f"\n[AI Safety Error: Request or response blocked due to safety settings (Reason: {feedback_reason})]"
                                log_message = f"Streaming chunk has prompt feedback: {chunk.prompt_feedback}. Yielding system message."
                            # Check candidates finish reason (another way safety can manifest)
                            elif hasattr(chunk, 'candidates') and chunk.candidates:
                                first_candidate = chunk.candidates[0]
                                if hasattr(first_candidate, 'finish_reason'):
                                    # FINISH_REASON_SAFETY = 3
                                    if first_candidate.finish_reason == 3: # Check for safety finish reason enum/value
                                        safety_reason = "SAFETY"
                                        try:
                                            # Try to get more specific rating if available
                                            if first_candidate.safety_ratings:
                                                safety_reason = "; ".join([f"{r.category.name}: {r.probability.name}" for r in first_candidate.safety_ratings])
                                        except Exception:
                                            pass # Ignore errors getting details
                                        chunk_to_send = f"\n[AI Safety Error: Response blocked due to safety settings (Reason: {safety_reason})]"
                                        log_message = f"Streaming chunk candidate finished due to SAFETY. Ratings: {safety_reason}"
                                    else:
                                         log_message = f"Streaming chunk has candidates but no text. Finish Reason: {first_candidate.finish_reason}"
                                else:
                                     log_message = f"Streaming chunk has candidates but no text or finish reason: {chunk}"
                            else:
                                 log_message = f"Streaming chunk has no text, candidates, or feedback: {chunk!r}"

                            logger.info(log_message) # Log before yielding

                        except AttributeError as ae:
                             logger.error(f"AttributeError processing chunk: {ae} - Chunk: {chunk!r}", exc_info=True)
                             # Optionally yield an error message, but be careful not to break client parsing
                             # yield f"\n[System Error: Problem processing AI response chunk ({type(ae).__name__})]"
                        except Exception as e:
                             logger.error(f"Unexpected error processing chunk: {e} - Chunk: {chunk!r}", exc_info=True)
                             # Optionally yield an error message
                             # yield f"\n[System Error: Problem processing AI response chunk ({type(e).__name__})]"


                        # Only yield and accumulate if we have something to send to the client
                        if chunk_to_send:
                            full_reply += chunk_to_send
                            yield chunk_to_send # Yield the extracted text/message

                    logger.info(f"Finished iteration over streaming generator for chat {chat_id}.")
                    # After the loop finishes, check if any content was yielded
                    if not full_reply:
                         logger.warning(f"Streaming generator for chat {chat_id} yielded no content.")
                         # Optionally yield a final message if nothing was ever yielded
                         # final_message = "[System Note: The AI did not return any content.]"
                         # yield final_message
                         # full_reply = final_message # Update full_reply for saving

                except StopIteration:
                     logger.info(f"Streaming generator for chat {chat_id} stopped.") # Normal exit
                except Exception as e:
                    # Log error during streaming iteration
                    logger.error(f"Error during streaming iteration for chat {chat_id}: {e}", exc_info=True)
                    # Yield an error message chunk to the client
                    error_chunk = f"\n[Streaming Error: {type(e).__name__}]"
                    yield error_chunk
                    full_reply += error_chunk # Append to full reply for saving
                finally:
                    # Save the full accumulated reply to the database after streaming finishes or errors
                    # Ensure the role is 'assistant' when saving the final message
                    if not full_reply:
                         # If no content was yielded, save a placeholder or the warning message
                         # Use a specific placeholder that indicates no content was received
                         full_reply = "[System Note: The AI did not return any content.]"
                         logger.warning(f"Streaming generator for chat {chat_id} yielded no content. Saving placeholder.")

                    # Only save if full_reply is not empty after processing
                    if full_reply:
                        if not db.add_message_to_db(chat_id, "assistant", full_reply):
                            logger.warning(f"Failed to save full streamed assistant message for chat {chat_id}.")
                    else:
                         logger.info(f"No content accumulated from stream for chat {chat_id}, not saving empty message.")


            # Return a streaming response
            # Consider using text/event-stream for Server-Sent Events standard
            return Response(stream_with_context(stream_generator()), mimetype='text/plain') # Or text/event-stream

        else:
            # If streaming is disabled, iterate the generator to get the full reply
            full_reply = ""
            try:
                # The generate_chat_response function handles non-streaming internally now
                # It returns the full string or an error string directly
                assistant_reply = assistant_response_generator # It's not a generator if streaming_enabled=False

                if not isinstance(assistant_reply, str):
                    # This case should ideally not happen if ai_services is correct
                    logger.error(f"Non-streaming call to ai_services did not return a string. Got: {type(assistant_reply)}. Forcing to error string.")
                    assistant_reply = "[System Error: Unexpected non-string response from AI service]"

            except Exception as e:
                 # Handle errors during non-streaming call (e.g., if ai_services raises before returning)
                 logger.error(f"Error calling non-streaming ai_services for chat {chat_id}: {e}", exc_info=True)
                 assistant_reply = f"\n[System Error calling AI Service: {type(e).__name__}]"

            # Check if the reply indicates an internal error occurred
            # Use a default status code of 200 unless an error is detected
            status_code = 200
            # Refine error checking based on common prefixes from ai_services
            error_prefixes = ("[Error:", "[AI Error:", "[Unexpected AI Error:", "[CRITICAL", "[System Error", "[AI Safety Error", "[AI API Error")
            if isinstance(assistant_reply, str) and assistant_reply.strip().startswith(error_prefixes):
                logger.warning(f"Non-streaming response indicates an error for chat {chat_id}: {assistant_reply}")
                # Determine appropriate status code based on error message if possible
                status_code = 500  # Default to internal server error for AI errors
                # Add more specific status codes if needed based on error content
                # (e.g., 4xx for client-side errors like invalid input if detectable)

                # Save the error message to the database
                if not db.add_message_to_db(chat_id, "assistant", assistant_reply):
                     logger.warning(f"Failed to save non-streaming error message for chat {chat_id}.")

                return jsonify({"reply": assistant_reply}), status_code
            else:
                # Save the successful non-streaming reply to the database
                if not assistant_reply:
                     logger.warning(f"Non-streaming response for chat {chat_id} was empty. Saving placeholder.")
                     assistant_reply = "[System Note: The AI returned an empty response.]"

                if not db.add_message_to_db(chat_id, "assistant", assistant_reply):
                     logger.warning(f"Failed to save non-streaming assistant message for chat {chat_id}.")
                return jsonify({"reply": assistant_reply}), status_code # Return with 200 OK

    except Exception as e:
        # Catch unexpected errors *within this route handler* before calling ai_services
        # or if ai_services raises an exception not caught internally
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
