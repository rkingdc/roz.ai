# app/plugins/google_calendar.py
import datetime
import os.path
import pickle # Used by older google auth flows, might not be needed with json token

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import current_app

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TOKEN_PATH = 'token.json' # Expects token.json in the root directory
CREDS_PATH = 'credentials.json' # Expects credentials.json in the root directory

def get_calendar_service():
    """
    Authenticates and builds the Google Calendar service object.
    Uses existing token.json or initiates flow if run interactively (not suitable for web server).
    In a web app context, token.json MUST exist and be valid or refreshed.
    Returns: googleapiclient.discovery.Resource object or None if error.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            print(f"Error loading credentials from {TOKEN_PATH}: {e}")
            # Could be ValueError if file is corrupted, handle appropriately

    # If there are no (valid) credentials available, log in the user.
    # This part is tricky in a web server context. The flow below is for CLI.
    # For a web app, you'd redirect the user through an OAuth web flow.
    # We are ASSUMING token.json is valid or refreshable for this simplified version.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Refreshing expired Google Calendar credentials...")
                creds.refresh(Request())
                print("Credentials refreshed.")
                # Save the refreshed credentials
                with open(TOKEN_PATH, 'w') as token:
                    token.write(creds.to_json())
                print(f"Refreshed token saved to {TOKEN_PATH}")
            except Exception as e:
                print(f"An error occurred during credential refresh: {e}")
                # Potentially delete token.json so user has to re-auth next time?
                # os.remove(TOKEN_PATH) ?
                return None # Cannot proceed without valid credentials
        else:
            # This path should ideally not be hit in a deployed web app.
            # It requires manual intervention (running the auth flow).
            print(f"ERROR: Missing or invalid {TOKEN_PATH}. Please run the Google auth flow manually first.")
            # Example CLI flow (won't work in standard web server process):
            # flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            # creds = flow.run_local_server(port=0)
            # # Save the credentials for the next run
            # with open(TOKEN_PATH, 'w') as token:
            #     token.write(creds.to_json())
            return None # Cannot proceed

    try:
        service = build('calendar', 'v3', credentials=creds)
        print("Google Calendar service created successfully.")
        return service
    except HttpError as error:
        print(f'An API error occurred building Calendar service: {error}')
        return None
    except Exception as e:
        print(f'An unexpected error occurred building Calendar service: {e}')
        return None


def fetch_upcoming_events(service, months=3):
    """
    Fetches upcoming events from the user's primary calendar for the next few months.
    Args:
        service: Authorized googleapiclient.discovery.Resource object.
        months: Number of months ahead to fetch events for.
    Returns:
        A formatted string listing events, or an error message string.
    """
    if not service:
        return "[Error: Google Calendar service not available]"

    try:
        # 'Z' indicates UTC time
        now = datetime.datetime.utcnow()
        time_min = now.isoformat() + 'Z'
        # Calculate time_max (e.g., 3 months from now)
        # A simple approximation:
        time_max_dt = now + datetime.timedelta(days=months * 30)
        time_max = time_max_dt.isoformat() + 'Z'

        print(f'Getting upcoming events for the next {months} months...')
        events_result = service.events().list(
            calendarId='primary', timeMin=time_min, timeMax=time_max,
            maxResults=50, singleEvents=True, # Limit results
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            print('No upcoming events found.')
            return "No upcoming events found in the next {months} months."

        # Format events into a string
        event_list_str = f"Upcoming Google Calendar Events (Next {months} Months):\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            # Format start time/date nicely
            try:
                # Try parsing as datetime first
                start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                # Convert to local time? Or keep UTC? Let's keep UTC for simplicity
                # Or format nicely:
                start_formatted = start_dt.strftime('%Y-%m-%d %H:%M') # Adjust format as needed
            except ValueError:
                # If parsing as datetime fails, it's likely just a date
                start_formatted = start # Keep as YYYY-MM-DD
            except Exception:
                 start_formatted = start # Fallback

            summary = event.get('summary', '(No Title)')
            event_list_str += f"- {start_formatted}: {summary}\n"

        print(f"Fetched {len(events)} events.")
        return event_list_str.strip()

    except HttpError as error:
        print(f'An API error occurred fetching events: {error}')
        return f"[Error fetching Calendar events: API Error {error.resp.status}]"
    except Exception as e:
        print(f'An unexpected error occurred fetching events: {e}')
        return f"[Error fetching Calendar events: {e}]"

