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


@bp.route("/chat/<int:chat_id>/message", methods=["POST"])
def send_message_route(chat_id):
    """API endpoint to handle user messages, potentially with attached files/calendar context, and get assistant responses."""
    logger.debug(f"Entering send_message_route for chat {chat_id}") # Added log
    data = request.json
    user_message = data.get("message", "")
    logger.debug(f"Received message: '{user_message[:50]}...' (length {len(user_message)}) for chat {chat_id}") # Added log
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

    # First, save the user message to the database
    if user_message:
        logger.debug(f"User message present, attempting to save for chat {chat_id}.") # Added log
        logger.info(f"Attempting to save user message for chat {chat_id}...")
        logger.debug(f"Calling db.add_message_to_db for user message (chat_id={chat_id}).") # Added log
        user_save_success = db.add_message_to_db(chat_id, "user", user_message)
        logger.debug(f"db.add_message_to_db for user message returned: {user_save_success}") # Added log
        if not user_save_success:
            logger.error(f"Failed to save user message for chat {chat_id} to database.")
            # Decide how to handle failure to save user message.
            # Option 1: Return error immediately (prevents AI response)
            # return jsonify({"error": "Failed to save user message to database."}), 500
            # Option 2: Log error and continue (AI response might still work, but history is incomplete)
            # We'll choose Option 2 for now, as the AI call might still succeed.
            pass # Continue execution even if user message save fails
        else:
            logger.info(f"Successfully saved user message for chat {chat_id}. Save success: {user_save_success}")
    else:
        logger.debug(f"No user message provided for chat {chat_id}, skipping user message save.") # Added log


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

                            logger.debug(log_message) # Log before yielding (changed to debug)

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
                    final_reply_content = full_reply # Use a new variable for clarity

                    if not final_reply_content.strip(): # Check if content is empty or just whitespace
                         # If no content was yielded, save a placeholder or the warning message
                         # Use a specific placeholder that indicates no content was received
                         final_reply_content = "[System Note: The AI did not return any content.]"
                         logger.warning(f"Streaming generator for chat {chat_id} yielded no content. Saving placeholder.")

                    # Attempt to save the final accumulated content (which is guaranteed non-empty here)
                    logger.info(f"Attempting to save final streamed assistant message for chat {chat_id} (length: {len(final_reply_content)}).")
                    logger.debug(f"Calling db.add_message_to_db for assistant message (chat_id={chat_id}).") # Added log
                    save_success = db.add_message_to_db(chat_id, "assistant", final_reply_content)
                    logger.debug(f"db.add_message_to_db for assistant message returned: {save_success}") # Added log
                    if save_success:
                        logger.info(f"Successfully saved final streamed assistant message for chat {chat_id}. Save success: {save_success}")
                    else:
                        logger.error(f"Failed to save final streamed assistant message for chat {chat_id}. Save success: {save_success}")


            # Return a streaming response
            # Consider using text/event-stream for Server-Sent Events standard
            return Response(stream_with_context(stream_generator()), mimetype='text/plain') # Or text/event-stream

        else:
            # If streaming is disabled, iterate the generator to get the full reply
            # The generate_chat_response function handles non-streaming internally now
            # It returns the full string or an error string directly
            assistant_reply = None # Initialize to None
            try:
                # Call the generator function, but expect it to return the full string immediately
                # when streaming_enabled=False is passed to ai_services.generate_chat_response
                # Note: The ai_services function should handle this internally.
                # We call it here as if it might still be a generator that yields one item,
                # or just returns the item directly depending on its implementation.
                # Assuming it returns the full string directly when streaming is off:
                assistant_reply = ai_services.generate_chat_response(
                    chat_id=chat_id,
                    user_message=user_message,
                    attached_files=attached_files,
                    session_files=session_files,
                    calendar_context=calendar_context,
                    web_search_enabled=enable_web_search,
                    streaming_enabled=False, # Explicitly False for this branch
                )


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
            is_error_reply = isinstance(assistant_reply, str) and assistant_reply.strip().startswith(error_prefixes)

            if is_error_reply:
                logger.warning(f"Non-streaming response indicates an error for chat {chat_id}: {assistant_reply}")
                status_code = 500  # Default to internal server error for AI errors
                # Add more specific status codes if needed based on error content
                # (e.g., 4xx for client-side errors like invalid input if detectable)

            # Save the assistant reply (whether success or error) to the database
            final_reply_content = assistant_reply if assistant_reply else "[System Note: The AI returned an empty response.]"
            if not final_reply_content.strip(): # Ensure we don't save empty/whitespace
                 final_reply_content = "[System Note: The AI returned an empty response.]"
                 logger.warning(f"Non-streaming response for chat {chat_id} was empty. Saving placeholder.")

            logger.info(f"Attempting to save non-streaming assistant message for chat {chat_id} (length: {len(final_reply_content)}).")
            logger.debug(f"Calling db.add_message_to_db for assistant message (chat_id={chat_id}).") # Added log
            save_success = db.add_message_to_db(chat_id, "assistant", final_reply_content)
            logger.debug(f"db.add_message_to_db for assistant message returned: {save_success}") # Added log
            if save_success:
                 logger.info(f"Successfully saved non-streaming assistant message for chat {chat_id}. Save success: {save_success}")
            else:
                 logger.error(f"Failed to save non-streaming assistant message for chat {chat_id}. Save success: {save_success}")
                 # If saving the *assistant* message fails, should we return an error to the client?
                 # The AI response was generated, but history is incomplete.
                 # For now, we'll return the AI response but log the save failure.

            return jsonify({"reply": assistant_reply}), status_code # Return with 200 OK (or 500 if error reply)

    except Exception as e:
        # Catch unexpected errors *within this route handler* before calling ai_services
        # or if ai_services raises an exception not caught internally
        logger.error(
            f"Unexpected error in send_message route for chat {chat_id}: {e}",
            exc_info=True,
        )
        error_reply = f"[Unexpected Server Error in route: {type(e).__name__}]" # More specific error message
        # Attempt to save the unexpected error message
        # Note: Saving here might fail if the error is related to the database connection itself
        logger.info(f"Attempting to save unexpected route error message for chat {chat_id}.")
        logger.debug(f"Calling db.add_message_to_db for error message (chat_id={chat_id}).") # Added log
        save_success = db.add_message_to_db(chat_id, "assistant", error_reply)
        logger.debug(f"db.add_message_to_db for error message returned: {save_success}") # Added log
        if save_success:
             logger.info(f"Successfully saved unexpected route error message for chat {chat_id}. Save success: {save_success}")
        else:
             logger.error(f"Failed to save unexpected route error message for chat {chat_id}. Save success: {save_success}")


        return (
            jsonify({"reply": error_reply}), # More specific error message
            500,
        )
