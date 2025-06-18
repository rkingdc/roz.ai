import asyncio
import logging
import os

from browser_use import Agent
from browser_use.browser import BrowserProfile, BrowserSession # Added imports
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
        # The user should have run `playwright install firefox --with-deps`
        # Configure browser session for Firefox
        browser_profile = BrowserProfile(
            browser="firefox", # Explicitly set firefox
            # user_data_dir can be set if persistent profiles are needed, e.g.,
            # user_data_dir='~/.config/browseruse/profiles/firefox_assistant' 
        )
        browser_session = BrowserSession(browser_profile=browser_profile)

        agent = Agent(
            task=task_instruction,
            llm=llm,
            browser_session=browser_session # Use browser_session instead of browser_config
        )
        logger.info(f"Running browser-use agent with Firefox for task: \"{task_instruction}\"")
        await agent.run()
        
        # Attempt to get a result from the agent.
        # The agent.messages list contains the interaction history.
        # The last message from the 'assistant' (agent) might contain the summary or result.
        outcome = "Browser task executed." # Default outcome
        if agent.messages:
            # Iterate backwards to find the last assistant message with content
            for msg in reversed(agent.messages):
                if msg.get('role') == 'assistant' and msg.get('content'):
                    outcome = msg['content']
                    break
            else: # No suitable assistant message found
                outcome = "Browser task executed, but no specific outcome message from agent."
        else:
            outcome = "Browser task executed, no agent messages recorded."

        logger.info(f"Browser-use agent finished. Outcome: {outcome}")
        return {"status": "success", "outcome": outcome}
    except Exception as e:
        logger.error(f"Error during browser-use agent execution: {e}", exc_info=True)
        return {"status": "error", "message": f"Agent execution failed: {str(e)}"}

def run_browser_task(task_instruction: str, google_api_key: str, model_name: str) -> dict:
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
    logger.info(f"Received browser task: \"{task_instruction}\" with model \"{model_name}\"")

    if not google_api_key:
        logger.error("Google API key not provided to run_browser_task.")
        return {"status": "error", "message": "Google API Key not configured for browser agent."}
    if not model_name:
        logger.error("Model name not provided to run_browser_task.")
        return {"status": "error", "message": "Model name not configured for browser agent."}

    # Initialize the LLM for the browser-use agent.
    try:
        llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=SecretStr(google_api_key), temperature=0)
    except Exception as e:
        logger.error(f"Failed to initialize ChatGoogleGenerativeAI with model {model_name}: {e}", exc_info=True)
        return {"status": "error", "message": f"Failed to initialize LLM for agent: {str(e)}"}

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
        return {"status": "error", "message": f"Unexpected error in browser task execution: {str(e)}"}
