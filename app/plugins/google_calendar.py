# app/plugins/google_calendar.py
import datetime
import os.path
import pickle  # Used by older google auth flows, might not be needed with json token

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import current_app

# Configure logging
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = "token.json"  # Expects token.json in the root directory
CREDS_PATH = "credentials.json"  # Expects credentials.json in the root directory


def get_calendar_service():
    """
    Authenticates and builds the Google Calendar service object.
    Uses existing token.json or initiates flow if run interactively (not suitable for web server).
    In a web app context, token.json MUST exist and be valid or refreshable.
    Returns: googleapiclient.discovery.Resource object or None if error.
    """
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.info(f"Error loading credentials from {TOKEN_PATH}: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired Google Calendar credentials...")
                creds.refresh(Request())
                logger.info("Credentials refreshed.")
                with open(TOKEN_PATH, "w") as token:
                    token.write(creds.to_json())
                logger.info(f"Refreshed token saved to {TOKEN_PATH}")
            except Exception as e:
                logger.info(f"An error occurred during credential refresh: {e}")
                return None  # Cannot proceed without valid credentials
        else:
            logger.info(
                f"ERROR: Missing or invalid {TOKEN_PATH}. Please run the Google auth flow manually first (e.g., using generate_token.py)."
            )
            return None  # Cannot proceed

    try:
        service = build("calendar", "v3", credentials=creds)
        logger.info("Google Calendar service created successfully.")
        return service
    except HttpError as error:
        logger.info(f"An API error occurred building Calendar service: {error}")
        return None
    except Exception as e:
        logger.info(f"An unexpected error occurred building Calendar service: {e}")
        return None


def fetch_upcoming_events(service, months=3):
    """
    Fetches upcoming events from the user's primary calendar including details.
    Args:
        service: Authorized googleapiclient.discovery.Resource object.
        months: Number of months ahead to fetch events for.
    Returns:
        A formatted string listing events with details, or an error message string.
    """
    if not service:
        return "[Error: Google Calendar service not available]"

    try:
        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max_dt = now + datetime.timedelta(days=months * 30)
        time_max = time_max_dt.isoformat() + "Z"

        logger.info(f"Getting upcoming events for the next {months} months...")
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            logger.info("No upcoming events found.")
            return f"No upcoming events found in the next {months} months."

        # Format events into a string with more details
        event_list_items = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            try:
                start_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                start_formatted = start_dt.strftime(
                    "%Y-%m-%d %H:%M"
                )  # UTC time for consistency
            except ValueError:
                start_formatted = start  # All-day event date
            except Exception:
                start_formatted = start  # Fallback

            summary = event.get("summary", "(No Title)")
            description = event.get("description", "").strip()
            location = event.get("location", "").strip()

            event_str = f"- {start_formatted}: {summary}"
            if location:
                event_str += f"\n    Location: {location}"
            if description:
                # Limit description length for context?
                desc_preview = (
                    (description[:100] + "...")
                    if len(description) > 100
                    else description
                )
                event_str += f"\n    Description: {desc_preview.replace(chr(10), ' ')}"  # Replace newlines in preview

            event_list_items.append(event_str)

        logger.info(f"Fetched {len(events)} events.")
        output_str = (
            f"Upcoming Google Calendar Events (Next {months} Months):\n"
            + "\n".join(event_list_items)
        )
        return output_str

    except HttpError as error:
        logger.info(f"An API error occurred fetching events: {error}")
        # Provide more specific error info if possible
        error_details = error.resp.get("content", b"").decode()
        try:
            error_json = json.loads(error_details)
            message = error_json.get("error", {}).get("message", "Unknown API Error")
            return f"[Error fetching Calendar events: {message}]"
        except json.JSONDecodeError:
            return f"[Error fetching Calendar events: API Error {error.resp.status}]"

    except Exception as e:
        logger.info(f"An unexpected error occurred fetching events: {e}")
        return f"[Error fetching Calendar events: {e}]"
