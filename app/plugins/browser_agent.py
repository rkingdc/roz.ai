import asyncio
import logging
import os

from typing import Optional, List, Dict, Any, Union # For Pydantic model
from pydantic import BaseModel # For Pydantic model
from browser_use import Agent, Controller # Import Controller
from browser_use.browser import BrowserProfile, BrowserSession

# from langchain_openai import ChatOpenAI  # browser-use examples use this LLM
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

# from dotenv import load_dotenv # No longer loading .env directly here

logger = logging.getLogger(__name__)

# Define a Pydantic model for structured output from the browser agent
class BrowserTaskOutput(BaseModel):
    status_message: str  # e.g., "Task completed successfully." or "Task partially completed."
    summary_of_actions: str # Brief summary of what the agent did.
    extracted_information: Optional[Union[Dict[str, Any], str]] = None # Specific data points extracted.
    key_urls: Optional[List[str]] = None # Relevant URLs encountered or used.
    errors_encountered: Optional[List[str]] = None # Any errors or issues the agent faced.


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
            downloads_path=os.path.join(os.getcwd(), "instance", "browser_downloads"), # Define downloads path
            playwright_launch_options={
                "args": ["--no-sandbox"] # Keep for Playwright, just in case
            },
        )
        # Ensure the downloads directory exists
        downloads_dir = browser_profile.downloads_path
        if downloads_dir and not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
            logger.info(f"Created downloads directory: {downloads_dir}")

        browser_session = BrowserSession(browser_profile=browser_profile)

        # Instantiate a Controller with the output model
        controller = Controller(output_model=BrowserTaskOutput)

        agent = Agent(
            task=task_instruction,
            llm=llm,
            browser_session=browser_session,
            controller=controller, # Pass the controller to the agent
            enable_memory=False,
        )
        logger.info(
            f'Running browser-use agent with Chromium for task: "{task_instruction}"'
        )
        history = await agent.run() # Capture the history object

        outcome = None
        if history:
            final_result_json_str = history.final_result()
            if final_result_json_str and isinstance(final_result_json_str, str):
                try:
                    # Attempt to parse the final_result using the Pydantic model
                    parsed_output = BrowserTaskOutput.model_validate_json(final_result_json_str)
                    outcome = parsed_output.model_dump() # Convert Pydantic model to dict
                    logger.info(f"Browser-use agent finished. Parsed structured result: {outcome}")
                except Exception as pydantic_error: # Catch Pydantic validation or JSON parsing errors
                    logger.warning(f"Failed to parse final_result as BrowserTaskOutput: {pydantic_error}. Falling back to raw string.")
                    outcome = {"status_message": "Task completed, but output parsing failed.", "summary_of_actions": "Agent executed the task.", "raw_output": final_result_json_str}
            elif final_result_json_str: # If it's not a string but some other data (e.g. already a dict)
                 outcome = {"status_message": "Task completed.", "summary_of_actions": "Agent executed the task.", "raw_output": final_result_json_str}
                 logger.info(f"Browser-use agent finished. Final result (non-string): {outcome}")
            else:
                # Fallback if final_result is empty
                model_actions = history.model_actions()
                last_action_summary = str(model_actions[-1])[:500] if model_actions and isinstance(model_actions, list) else "No specific actions recorded."
                outcome = {
                    "status_message": "Task completed, but no specific structured result was provided by the agent.",
                    "summary_of_actions": f"Last agent action/thought: {last_action_summary}"
                }
                logger.info(f"Browser-use agent finished. No specific final_result. Fallback outcome: {outcome}")
        else:
            outcome = {
                "status_message": "Task completed, but the agent did not return a history object.",
                "summary_of_actions": "Agent execution did not yield a history object."
            }
            logger.warning(str(outcome))
            
        return {"status": "success", "outcome": outcome} # outcome is now a dict
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
