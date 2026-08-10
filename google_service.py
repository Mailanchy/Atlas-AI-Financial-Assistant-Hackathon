import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Import YOUR database module!
import database

load_dotenv()

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = FastAPI()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

google_client_config = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uris": [f"{BASE_URL}/auth/callback"]
    }
}

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar' 
    ]

# --- NEW: Temporary cache to remember the flow & its secret code verifier ---
flow_cache = {}

@app.get("/auth/login")
async def login(telegram_id: int):
    print(f"\n---> [GOOGLE AUTH] Login initiated for User ID: {telegram_id}")
    flow = Flow.from_client_config(
        google_client_config,
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/auth/callback"
    )
    
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=str(telegram_id)
    )
    
    # Save this exact flow object in memory using the telegram_id
    flow_cache[telegram_id] = flow
    print(f"---> [GOOGLE AUTH] Flow cached. Redirecting user to Google URL...")
    
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def callback(request: Request):
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    
    print(f"\n---> [GOOGLE AUTH] Callback received. State: {state}")

    if not state or not code:
        print("---> [GOOGLE ERROR] Missing state or code from Google.")
        return HTMLResponse("<h1>Error: Missing state or code from Google.</h1>")

    telegram_id = int(state)

    # --- NEW: Retrieve the exact flow object that generated the link ---
    flow = flow_cache.get(telegram_id)
    
    if not flow:
        print(f"---> [GOOGLE ERROR] No matching flow cache found for User {telegram_id}.")
        return HTMLResponse("<h1>Error: Session expired or invalid. Please try logging in again.</h1>")

    print("---> [GOOGLE AUTH] Fetching token using Google code...")
    # Now it remembers the code_verifier and trades the code for tokens!
    flow.fetch_token(code=code)
    credentials = flow.credentials

    # Bundle token details as JSON
    token_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    
    print(f"---> [GOOGLE AUTH] Token successfully fetched. Saving to database for User {telegram_id}...")
    # Use YOUR database architecture to save it
    database.save_integration_token(telegram_id, 'google', json.dumps(token_data))

    # Cleanup the cache now that we are done
    del flow_cache[telegram_id]
    print("---> [GOOGLE AUTH] Flow cache cleared. Auth complete.")

    return HTMLResponse("""
    <html>
        <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 50px;">
            <h1 style="color: #4CAF50;">✅ Google Account Connected!</h1>
            <p>Your Google account has been successfully linked to Atlas.</p>
            <p>You can safely close this tab and return to Telegram.</p>
        </body>
    </html>
    """)


# ==========================================
# GOOGLE WORKSPACE TOOLS (Called by telegram.py)
# ==========================================

def get_google_credentials(telegram_id):
    """Converts the token from the database into a Google Credentials object."""
    print(f"\n---> [GOOGLE WORKSPACE] Retrieving credentials for User {telegram_id}...")
    # Look how clean this is now!
    token_data = database.get_integration_token(telegram_id, 'google')

    if not token_data:
        print("---> [GOOGLE WORKSPACE] No token found in database.")
        return None
    
    print("---> [GOOGLE WORKSPACE] Token found. Building Google Credentials object...")
    # Create the Google Credentials object
    creds = Credentials(
        token=token_data['token'],
        refresh_token=token_data['refresh_token'],
        token_uri=token_data['token_uri'],
        client_id=token_data['client_id'],
        client_secret=token_data['client_secret'],
        scopes=token_data['scopes']
    )
    return creds

def search_emails(telegram_id, query):
    """Searches the user's Gmail and returns the 3 most relevant emails."""
    print(f"\n---> [GMAIL API] search_emails triggered. Query: '{query}'")
    creds = get_google_credentials(telegram_id)
    if not creds:
        return "Error: User has not connected their Google account."

    try:
        print("---> [GMAIL API] Connecting to Gmail service...")
        service = build('gmail', 'v1', credentials=creds)
        
        # Search for messages (Limit to top 3 so we don't overwhelm the Llama prompt)
        print(f"---> [GMAIL API] Executing search for: '{query}'...")
        results = service.users().messages().list(userId='me', q=query, maxResults=3).execute()
        messages = results.get('messages', [])

        if not messages:
            print("---> [GMAIL API] Search complete. 0 emails found.")
            return f"No emails found matching the query: '{query}'"

        print(f"---> [GMAIL API] Found {len(messages)} emails. Fetching metadata...")
        email_summaries = []
        for msg in messages:
            # Fetch the actual email details
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From', 'Date']).execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            snippet = msg_data.get('snippet', '')
            
            email_summaries.append(f"From: {sender} | Subject: {subject} | Snippet: {snippet}")

        print("---> [GMAIL API] Email metadata successfully compiled.")
        return "\n".join(email_summaries)

    except Exception as e:
        print(f"---> [GMAIL ERROR] Exception occurred: {str(e)}")
        return f"Error fetching emails: {str(e)}"

def schedule_event(telegram_id, title, start_time_iso):
    """Creates a 1-hour meeting on the user's Google Calendar."""
    print(f"\n---> [CALENDAR API] schedule_event triggered. Title: '{title}', Time: {start_time_iso}")
    creds = get_google_credentials(telegram_id)
    if not creds:
        return "Error: User has not connected their Google account."

    try:
        print("---> [CALENDAR API] Connecting to Google Calendar service...")
        service = build('calendar', 'v3', credentials=creds)

        # Clean up the timestamp from the LLM and add 1 hour for the end time
        if not start_time_iso.endswith('Z') and '+' not in start_time_iso:
            print("---> [CALENDAR API] Missing timezone offset. Forcing UTC 'Z'.")
            start_time_iso += 'Z' # Force UTC format if missing
            
        start_dt = datetime.datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
        end_dt = start_dt + datetime.timedelta(hours=1)
        
        print(f"---> [CALENDAR API] Parsed Times - Start: {start_dt}, End: {end_dt}")

        event = {
          'summary': title,
          'start': {
            'dateTime': start_dt.isoformat(),
          },
          'end': {
            'dateTime': end_dt.isoformat(),
          },
        }

        # Push the event to Google Calendar
        print("---> [CALENDAR API] Pushing event to Google Calendar...")
        event_result = service.events().insert(calendarId='primary', body=event).execute()
        
        link = event_result.get('htmlLink')
        print(f"---> [CALENDAR API] Success! Event created. Link: {link}")
        
        return f"Success! Event '{title}' scheduled. Google Calendar Link: {link}"

    except Exception as e:
        print(f"---> [CALENDAR ERROR] Exception occurred: {str(e)}")
        return f"Error scheduling calendar event: {str(e)}"

@app.get("/")
async def root():
    return {"status": "Atlas AI Assistant is live!"}