import asyncio
import logging
import os

from browser_use import Agent
from browser_use.browser import BrowserProfile, BrowserSession  # Added imports

# from langchain_openai import ChatOpenAI  # browser-use examples use this LLM
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

# from dotenv import load_dotenv # No longer loading .env directly here

logger = logging.getLogger(__name__)


async def _run_agent_async(task_instruction: str, llm) -> dict:
    """
    Helper async function to run the browser-use agent.
    Ensures Playwright is set up for Firefox.
    """
    try:
        # The user should have run `playwright install chromium --with-deps`
        # Configure browser session for Chromium
        browser_profile = BrowserProfile(
            browser="chromium",  # Explicitly set chromium
            executable_path=None, # Let Playwright find the default Chromium
            headless=False, # Make browser visible
            user_data_dir=None,  # Use a temporary profile
            chromium_sandbox=False, # Explicitly disable sandbox via browser-use parameter
            playwright_launch_options={
                "args": ["--no-sandbox"] # Keep for Playwright, just in case
            },
        )
        browser_session = BrowserSession(browser_profile=browser_profile)

        agent = Agent(
            task=task_instruction,
            llm=llm,
            browser_session=browser_session,  # Use browser_session instead of browser_config
            enable_memory=False,
        )
        logger.info(
            f'Running browser-use agent with Chromium for task: "{task_instruction}"'
        )
        history = await agent.run() # Capture the history object

        outcome = None
        if history:
            final_result_data = history.final_result()
            if final_result_data:
                # final_result_data could be a string (often JSON) or a dict
                outcome = final_result_data
                logger.info(f"Browser-use agent finished. Final result: {outcome}")
            else:
                # Check for model thoughts or actions if final_result is empty
                # This part can be expanded based on how browser-use 0.2.7 structures history
                model_actions = history.model_actions()
                if model_actions: # Get the last action/thought
                    last_action = model_actions[-1] if isinstance(model_actions, list) and model_actions else model_actions
                    outcome = f"Browser task completed. Last agent action/thought: {str(last_action)[:500]}" # Truncate if too long
                    logger.info(f"Browser-use agent finished. No specific final_result. Last action: {outcome}")
                else:
                    outcome = f"Browser task '{task_instruction}' completed, but no specific result was extracted from the agent's history."
                    logger.info(outcome)
        else:
            outcome = f"Browser task '{task_instruction}' completed, but the agent did not return a history object."
            logger.warning(outcome)
            
        return {"status": "success", "outcome": outcome}
    except Exception as e:
        logger.error(f"Error during browser-use agent execution: {e}", exc_info=True)
        # Check if the exception itself has a 'message' attribute, common in some error objects
        error_message = getattr(e, "message", str(e))
        return {
            "status": "error",
            "message": f"Agent execution failed: {error_message}",
        }


def run_browser_task(
    task_instruction: str, google_api_key: str, model_name: str
) -> dict:
    """
    Performs a browser-based task using the browser-use agent with Playwright and Firefox.

    Args:
        task_instruction: The natural language instruction for the task.
        google_api_key: The Google API key to use for the LLM.
        model_name: The Gemini model name to use for the LLM.

    Returns:
        A dictionary with the status and outcome of the task.
        e.g., {"status": "success", "outcome": "Task completed successfully."}
              {"status": "error", "message": "Error details."}
    """
    logger.info(
        f'Received browser task: "{task_instruction}" with model "{model_name}"'
    )

    if not google_api_key:
        logger.error("Google API key not provided to run_browser_task.")
        return {
            "status": "error",
            "message": "Google API Key not configured for browser agent.",
        }
    if not model_name:
        logger.error("Model name not provided to run_browser_task.")
        return {
            "status": "error",
            "message": "Model name not configured for browser agent.",
        }

    # Initialize the LLM for the browser-use agent.
    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name, google_api_key=SecretStr(google_api_key), temperature=0
        )
    except Exception as e:
        logger.error(
            f"Failed to initialize ChatGoogleGenerativeAI with model {model_name}: {e}",
            exc_info=True,
        )
        return {
            "status": "error",
            "message": f"Failed to initialize LLM for agent: {str(e)}",
        }

    try:
        # Run the asynchronous agent function.
        # asyncio.run() is used to call the async function from this synchronous context.
        result = asyncio.run(_run_agent_async(task_instruction, llm))
        return result
    except RuntimeError as e:
        # Handle potential asyncio.run() issues if an event loop is already running.
        # This is less common in typical Flask setups where requests are handled in threads.
        logger.error(f"Asyncio runtime error during browser task: {e}", exc_info=True)
        return {"status": "error", "message": f"Asyncio runtime error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error running browser task: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Unexpected error in browser task execution: {str(e)}",
        }
