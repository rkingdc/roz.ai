from . import database  # Use alias to avoid conflict with db instance
from .plugins.web_search import (
    perform_web_search,
    fetch_web_content,
)  # Added fetch_web_content
from .ai_services_lib.generation_services import generate_text  # Import generate_text
from .ai_services_lib.llm_factory import (
    llm_factory,
    prompt_improver,
)  # Import llm_factory and prompt_improver
from .ai_services_lib.transcription_services import (
    clean_up_transcript,
    transcribe_pdf_bytes,
)  # Import transcription services
from .ai_services_lib.chat_services import (
    generate_chat_response,
)  # Import chat services
from .ai_services_lib.summary_services import (
    get_or_generate_summary,
    generate_summary,
    generate_note_diff_summary,
)  # Import summary services
from .ai_services_lib.tool_definitions import (
    WEB_SEARCH_TOOL,
    WEB_SCRAPE_TOOL,
)  # Import tool definitions

import logging

# Configure logging - Removed basicConfig and setLevel here
logger = logging.getLogger(__name__)
