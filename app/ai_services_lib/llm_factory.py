import logging
from typing import Tuple, Callable, Any
from string import Formatter

# Import generate_text from the generation_services module within the same library
from .generation_services import generate_text

logger = logging.getLogger(__name__)


def llm_factory(prompt_template: str, params: Tuple[str] = ()) -> Callable[..., str]:
    """
    Creates a function that formats a prompt template and sends it to the LLM.

    Args:
        prompt_template: The base prompt string with placeholders in the format {param_name}.
        params: A sequence (tuple or list) of parameter names expected by the template.

    Returns:
        A function that takes keyword arguments corresponding to the `params`
        and returns the LLM's response string.

    Raises:
        ValueError: If the returned function is called with missing parameters.
        KeyError: If the prompt_template contains placeholders not listed in params,
                  or if formatting fails for other reasons related to placeholders.

    Important Note:
        The returned function relies on `generate_text` from this library, which expects
        to be run within an active Flask request context to access configuration
        (API key) and the Gemini client via Flask's `g` object. Calling the
        returned function outside of a Flask request context will likely result
        in errors within `generate_text`.
    """
    required_params = set(params)

    try:
        template_placeholders = {
            field_name
            for _, field_name, _, _ in Formatter().parse(prompt_template)
            if field_name is not None
        }
        missing_in_params = template_placeholders - required_params
        if missing_in_params:
            logger.warning(
                f"Factory Warning: Placeholders {missing_in_params} exist in template but not in provided 'params'. Formatting will fail if these are required."
            )
    except Exception as e:
        logger.error(
            f"Error parsing prompt template during factory creation: {e}", exc_info=True
        )

    def llm_caller(**kwargs: Any) -> str:
        """
        Formats the prompt with provided arguments and calls the LLM.

        Args:
            **kwargs: Keyword arguments corresponding to the `params` defined
                      in the factory.

        Returns:
            The response string from the LLM via generate_text.

        Raises:
            ValueError: If any required parameters (defined in factory `params`)
                        are missing in kwargs.
            KeyError: If the prompt_template formatting fails (e.g., placeholder mismatch).
        """
        provided_params = set(kwargs.keys())
        missing_params = required_params - provided_params
        if missing_params:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing_params)}"
            )

        extra_params = provided_params - required_params
        if extra_params:
            logger.warning(
                f"Ignoring extra parameters provided to caller: {', '.join(extra_params)}"
            )
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in required_params}
        else:
            filtered_kwargs = kwargs

        try:
            formatted_prompt = prompt_template.format(**filtered_kwargs)
            logger.info(f"Formatted prompt: {formatted_prompt[:200]}...")
        except KeyError as e:
            logger.error(
                f"Error formatting prompt template. Placeholder {e} likely missing or misspelled in the template string itself."
            )
            raise KeyError(
                f"Prompt template formatting error: Placeholder {e} not found in template string or mismatch."
            ) from e
        except Exception as e:
            logger.error(
                f"An unexpected error occurred during prompt formatting: {e}",
                exc_info=True,
            )
            raise

        try:
            response = generate_text(prompt=formatted_prompt)
            return response
        except Exception as e:
            logger.error(f"Error calling generate_text: {e}", exc_info=True)
            return f"[Error calling LLM service: {type(e).__name__}]"

    return llm_caller


prompt_improver = llm_factory(
    prompt_template="""---
Role: You are a highly skilled and conservative LLM Prompt Engineering AI. Your task is to analyze the user's provided prompt string to accurately identify the core intent and specific requirements, understanding that this prompt likely originated within an ongoing conversational context. Then, rewrite this prompt to be significantly more clear, specific, and effective for eliciting the desired information from an LLM *within that assumed conversational context*.

Crucially, your absolute highest priority is to faithfully capture and clarify the *original user intent* as understood within its potential conversational setting. Do NOT invent new tasks, add new requests, or introduce requirements that were not explicitly present or strongly implied in the original prompt *or* would have been clear from assumed prior conversation turns.

Specifically, when rewriting brief or ambiguous original prompts that likely relied on context:
1.  **Assume Conversational Context:** Understand that elements like format, subject matter, or constraints might have been established in previous turns of a chat.
2.  **Preserve Implicit Context Reliance:** Do not explicitly state that context is missing or add generic descriptions/placeholders for items/formats that would likely be understood from that assumed prior conversation. Your rewrite should rely on the same assumed context the original prompt did.
3.  **Clarify within Context:** Aim to make the request clearer and more direct *using* the assumed context, rather than trying to make the prompt stand alone by adding definitions that were previously understood.

You must respond *only* with the final, rewritten prompt. Do not include any introductory text, explanations, commentary, or conversational filler before or after the rewritten prompt. Start directly with the rewritten prompt.

---
The user prompt string to rewrite is:
{prompt}

Your rewritten prompt:""",
    params=["prompt"],
)
