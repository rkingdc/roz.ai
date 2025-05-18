import google.genai as genai
# from google.genai.types import Part, Content # Not directly used by generate_text, but by client.models.generate_content response
from google.api_core.exceptions import (
    GoogleAPIError,
    DeadlineExceeded,
    ClientError,
    NotFound,
    InvalidArgument,
)
from flask import current_app, g
import logging
import time
import random

logger = logging.getLogger(__name__)


# --- Standalone Text Generation (Example) ---
def generate_text(
    prompt: str, model_name: str = None, max_retries=3, initial_backoff=1.0
) -> str:
    """
    Generates text using a specified model or the default.
    Includes exponential backoff with jitter for 429 errors.
    """
    logger.info(f"Entering generate_text. Max retries: {max_retries}")

    # --- AI Readiness Check (Moved from Decorator) ---
    try:
        # Check for Flask request context
        try:
            _ = (
                current_app.config
            )  # Simple check that raises RuntimeError if no context
            logger.debug("generate_text: Flask request context is active.")
        except RuntimeError:
            logger.error(
                "generate_text called outside of active Flask app/request context.",
                exc_info=True,  # Log traceback
            )
            return "[Error: AI Service called outside request context]"

        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config.")
            return "[Error: AI Service API Key not configured]"

        try:
            # Use client caching via Flask's 'g' object if in request context
            if "genai_client" not in g:
                logger.info("Creating new genai.Client and caching in 'g'.")
                g.genai_client = genai.Client(api_key=api_key)
            else:
                logger.debug("Using cached genai.Client from 'g'.")
            client = g.genai_client
            logger.info("Successfully obtained genai.Client for text generation.")
        except (GoogleAPIError, ClientError, ValueError, Exception) as e:
            logger.error(
                f"Failed to initialize/get genai.Client for text: {e}", exc_info=True
            )
            if "api key not valid" in str(e).lower():
                return "[Error: Invalid Gemini API Key]"
            return "[Error: Failed to initialize AI client]"

    except Exception as e:
        # Catch any unexpected errors during the readiness check itself
        logger.error(
            f"generate_text: Unexpected error during readiness check: {type(e).__name__} - {e}",
            exc_info=True,
        )
        return f"[CRITICAL Unexpected Error during AI Service readiness check: {type(e).__name__}]"
    # --- End AI Readiness Check ---

    if not model_name:
        raw_model_name = current_app.config["DEFAULT_MODEL"]
        model_to_use = (
            f"models/{raw_model_name}"
            if not raw_model_name.startswith("models/")
            else raw_model_name
        )
    else:
        model_to_use = (
            f"models/{model_name}"
            if not model_name.startswith("models/")
            else model_name
        )

    logger.info(f"Generating text with model '{model_to_use}'...")
    response = None
    retries = 0
    current_backoff = initial_backoff

    while retries <= max_retries:
        try:
            # Use the client.models attribute for simple generation
            # Standalone text generation is NOT streamed
            logger.info(
                f"Attempting generate_content (Attempt {retries + 1}/{max_retries + 1})"
            )
            response = client.models.generate_content(
                model=model_to_use,
                contents=prompt,
            )

            # --- Successful Response Processing ---
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
                logger.warning(
                    f"Text generation blocked by safety settings. Reason: {reason}"
                )
                return f"[Error: Text generation blocked due to safety settings (Reason: {reason})]"  # No retry for safety block

            if (
                response.candidates
                and hasattr(response.candidates[0], "content")
                and hasattr(response.candidates[0].content, "parts")
                and response.candidates[0].content.parts
            ):
                text_reply = "".join(
                    part.text
                    for part in response.candidates[0].content.parts
                    if hasattr(part, "text")
                )
                if text_reply.strip():
                    logger.info(f"Text generation successful on attempt {retries + 1}.")
                    return text_reply  # Success!
                else:
                    logger.warning("Text generation resulted in empty text content.")
                    return "[System Note: AI generated empty text.]"  # No retry for empty content
            else:
                logger.warning(
                    f"Text generation did not produce usable content. Response: {response!r}"
                )
                finish_reason = "UNKNOWN"
                if response.candidates and hasattr(
                    response.candidates[0], "finish_reason"
                ):
                    finish_reason = response.candidates[0].finish_reason.name
                # No retry if no usable content and not a retryable error
                return f"[Error: AI did not generate text content (Finish Reason: {finish_reason})]"

        # --- Error Handling with Retries ---
        except InvalidArgument as e:
            logger.error(
                f"InvalidArgument error during text generation: {e}.", exc_info=True
            )
            return f"[AI Error: Invalid argument ({type(e).__name__}).]"  # No retry
        except NotFound:
            logger.error(f"Model '{model_to_use}' not found.")
            return f"[Error: Model '{model_to_use}' not found]"  # No retry
        except GoogleAPIError as e:
            # Check specifically for 429 Resource Exhausted / Rate Limit
            is_rate_limit_error = False
            if hasattr(e, "status_code") and e.status_code == 429:
                is_rate_limit_error = True
            elif "resource_exhausted" in str(e).lower() or "429" in str(e):
                is_rate_limit_error = True

            if is_rate_limit_error and retries < max_retries:
                retries += 1
                # Exponential backoff with jitter
                sleep_time = current_backoff + random.uniform(0, current_backoff * 0.1)
                logger.warning(
                    f"Rate limit hit (429). Retrying in {sleep_time:.2f} seconds... (Attempt {retries}/{max_retries})"
                )
                time.sleep(sleep_time)
                current_backoff *= 2  # Increase backoff for next potential retry
                continue  # Go to next iteration of the while loop
            else:
                # Handle non-retryable API errors or max retries reached for 429
                logger.error(
                    f"API error during text generation (final attempt or non-retryable): {e}"
                )
                err_str = str(e).lower()
                if "api key not valid" in err_str:
                    return "[Error: Invalid Gemini API Key]"
                if is_rate_limit_error:  # Max retries reached
                    return f"[AI Error: API rate limit exceeded after {max_retries} retries.]"
                # Add other common checks if needed (quota, etc.)
                return f"[AI API Error: {type(e).__name__}]"  # Generic API error
        except Exception as e:
            logger.error(f"Unexpected error during text generation: {e}", exc_info=True)
            # Decide if unexpected errors should be retried? For now, no.
            return f"[Unexpected AI Error: {type(e).__name__}]"

    # If loop finishes without returning, it means max retries were hit for 429
    logger.error(
        f"Text generation failed after {max_retries} retries due to rate limiting."
    )
    return "[AI Error: API rate limit exceeded after maximum retries.]"
