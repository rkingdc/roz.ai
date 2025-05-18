# app/ai_services.py
import google.genai as genai  # Use the new SDK

# Import necessary types, including the one for FileDataPart
from google.genai.types import (
    Part,
    Content,
    Blob,  # Import Blob for inline data
    FileData,  # Import FileData for referencing uploaded files
    GenerateContentConfig,
    Tool,
    FunctionDeclaration,
    Schema,
    Type,
    AutomaticFunctionCallingConfig, # Import for AFC
    Mode,                             # Import for AFC Mode enum
)
import json  # For serializing tool responses if needed
import functools # For partial

from flask import current_app, g  # Import g for request context caching
import tempfile
import os
import re
import base64
from . import database  # Use alias to avoid conflict with db instance
from .plugins.web_search import (
    perform_web_search,
    fetch_web_content,
)  # Added fetch_web_content
from .ai_services_lib.generation_services import generate_text # Import generate_text
from .ai_services_lib.llm_factory import llm_factory, prompt_improver # Import llm_factory and prompt_improver
from .ai_services_lib.transcription_services import clean_up_transcript, transcribe_pdf_bytes # Import transcription services
from .ai_services_lib.chat_services import generate_chat_response # Import chat services
from .ai_services_lib.summary_services import get_or_generate_summary, generate_summary # Import summary services
from .ai_services_lib.tool_definitions import WEB_SEARCH_TOOL, WEB_SCRAPE_TOOL # Import tool definitions

from google.api_core.exceptions import (
    GoogleAPIError,
    DeadlineExceeded,
    ClientError,
    NotFound,
    InvalidArgument,  # Import InvalidArgument for malformed content errors
)
from pydantic_core import ValidationError

import logging
import time  # Add time import
import random  # Add random import
from typing import Tuple, Callable, Any

# from functools import wraps # Remove this import
from werkzeug.utils import secure_filename

# Configure logging - Removed basicConfig and setLevel here
logger = logging.getLogger(__name__)



# llm_factory and prompt_improver have been moved to app/ai_services_lib/llm_factory.py



# --- Generate Search Query --- (REMOVED - Functionality to be handled by LLM Tool)
# def generate_search_query(user_message: str, max_retries=1) -> str | None:
#    ... (entire function content removed) ...


# Removed _yield_streaming_error helper function (This comment line is also removed as part of the block)




# --- Helper Function for NON-STREAMING Response --- (REMOVED)
# def _generate_chat_response_non_stream(...):
# ... entire function removed ...


