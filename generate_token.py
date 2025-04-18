# generate_token.py
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scope required by the application (must match the one in google_calendar.py)
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TOKEN_PATH = 'token.json'
CREDS_PATH = 'credentials.json' # Make sure this file exists in the same directory

def main():
    """Runs the authorization flow to generate token.json."""
    creds = None
    # Check if token already exists
    if os.path.exists(TOKEN_PATH):
        # Try loading existing credentials
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            print(f"'{TOKEN_PATH}' already exists.")
            # Check if valid or refreshable
            if creds and creds.valid:
                print("Credentials are valid.")
                return # No need to run flow again
            elif creds and creds.expired and creds.refresh_token:
                print("Credentials expired, attempting refresh...")
                try:
                    creds.refresh(Request())
                    # Save refreshed credentials
                    with open(TOKEN_PATH, 'w') as token:
                        token.write(creds.to_json())
                    print(f"Credentials refreshed and saved to '{TOKEN_PATH}'.")
                    return # Refreshed successfully
                except Exception as e:
                    print(f"Could not refresh token: {e}. Proceeding with re-authentication.")
                    creds = None # Force re-authentication
            else:
                 print("Existing token is invalid or cannot be refreshed. Re-authenticating.")
                 creds = None # Force re-authentication

        except Exception as e:
            print(f"Error loading existing token file: {e}. Proceeding with authentication.")
            creds = None


    if not creds:
        if not os.path.exists(CREDS_PATH):
            print(f"ERROR: '{CREDS_PATH}' not found. Please download it from Google Cloud Console.")
            return

        print(f"'{TOKEN_PATH}' not found or invalid. Starting authentication flow...")
        # Use InstalledAppFlow for desktop/local script authorization
        flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
        # run_local_server will open a browser window for user consent
        creds = flow.run_local_server(port=0) # Use port=0 to find a free port

        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
        print(f"Authentication successful. Credentials saved to '{TOKEN_PATH}'.")

if __name__ == '__main__':
    main()
