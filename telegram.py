import json
import os
import telebot
from dotenv import load_dotenv
import database
import ai_engine as ai
import time
import threading
from datetime import datetime, timedelta
import finance
import google_service 

print("=======================================")
print("🤖 ATLAS AI BOT IS STARTING UP...")
print("=======================================")
print("Please check with the telegram app and start the bot by sending /start")

load_dotenv()

TeleToken = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TeleToken)


# Handle Text Messages
@bot.message_handler(content_types=['text', '/start', 'voice'])
def reply(message):
    bot.send_chat_action(message.chat.id, 'typing')
    user_id = message.from_user.id
    
    print(f"\n\n---> [NEW MESSAGE] Received from User ID: {user_id}")

    if message.content_type == 'voice':
        print("---> [AUDIO] Voice message detected. Downloading and transcribing...")
        try:
            # 1. Get file information from Telegram
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            # 2. Save it locally as a temporary .ogg file
            temp_ogg_path = f"temp_voice_{user_id}_{message.message_id}.ogg"
            with open(temp_ogg_path, 'wb') as new_file:
                new_file.write(downloaded_file)
            
            # 3. Transcribe using your function inside ai.py
            user_message = ai.transcribe_telegram_voice(temp_ogg_path)
            print(f"---> [AUDIO] Transcription successful: '{user_message}'")
            
            # 4. Clean up the temporary local file
            if os.path.exists(temp_ogg_path):
                os.remove(temp_ogg_path)
                
        except Exception as e:
            print(f"---> [ERROR] Voice Processing Error: {e}")
            if 'temp_ogg_path' in locals() and os.path.exists(temp_ogg_path):
                os.remove(temp_ogg_path)
            bot.reply_to(message, f"Sorry, I had trouble processing your voice note. Could you try sending it as text instead? {e}")
            return
    else:
        user_message = message.text
        print(f"---> [TEXT] User said: '{user_message}'")

    stage = database.get_user_stage(user_id)
    print(f"---> [ROUTING] User {user_id} is currently at onboarding stage: '{stage}'")
    
    def get_onboarding_prompt(bot_question):
        return f"""
        The bot just asked the user this exact question: "{bot_question}"
        
        Based on the user's reply to that question, extract the following information. Use the bot's question to understand the context of short, partial, or casual answers.
        
        1. role (string) - e.g., Investor, Analyst, Founder, Student.
        2. sectors (array of strings) - Companies, sectors, or markets they follow.
        3. watchlist (array of strings) - CRITICAL: If the user mentions a specific company, convert it to its official uppercase stock ticker symbol (e.g., 'AAPL'). If they mention a general topic, keep it as plain text.
        4. insight_types (array of strings) - CRITICAL: ONLY use these exact keywords: ["news", "earnings", "sec_filings", "macro"]. Map whatever they say to the closest option(s).
        5. briefing_time (string) - CRITICAL: Format strictly in 24-hour 'HH:MM' format. Default to '08:00' for morning, '17:00' for evening.
        6. memory_updates (array of objects) - Extract any personal facts, preferences, or contextual details the user shares about themselves. Each object MUST contain "fact_type" and "fact_content". Return [] if none.
        7. intent_to_skip (boolean) - CRITICAL: Set to true ONLY if the user explicitly wants to ABORT the entire setup process or show disinterest (e.g., "stop onboarding", "cancel setup", "exit", "i dont want to continue", etc). If the user simply declines the specific feature being asked about (e.g., "I don't want a briefing", "skip this question", "none", "I don't know", "No"), this is a PARTIAL skip. You MUST set this to false and just return null/empty for the specific fields.
        
        If any specific piece of information is missing from this particular message, return null (for strings) or an empty array [] (for arrays).
        """
    
    # Inject current time and EXPLICITLY specify the timezone (IST)
    current_time_str = datetime.now().strftime("%A, %B %d, %Y %H:%M:%S")
    
    chat_extraction_prompt = f"""
    Current Date and Time: {current_time_str} IST (Indian Standard Time, UTC+05:30)
    
    Analyze the user's message and extract the following parameters in JSON format. 
    Pay close attention to whether the user is referring to a recently uploaded document, asking for live market data, or sharing personal facts/preferences to remember.

    1. needs_document_read (boolean): Set to true ONLY if explicitly asking about an uploaded document, PDF, file, or report.
     --- FINANCIAL RESEARCH TOOLS ---
    2. requires_data (boolean): Set to true ONLY if the message requires live market context, stock prices, financial news, earnings, or SEC filings.
    3. watchlist (array of strings): Extract official uppercase stock tickers mentioned (e.g., ["AAPL", "TSLA"]). Return [] if none.
    4. sectors (array of strings): Extract lower-case industry sectors mentioned. Return [] if none.
    5. insight_types (array of strings): Map intent using ONLY these terms: ["news", "earnings", "sec_filings", "macro"]. Default to ["news"].
    6. start_date (string): If the user asks about a specific past timeframe (e.g., "last month", "Q3 2023", "last week"), calculate the exact start date based on the Current Date above. Format strictly as 'YYYY-MM-DD'. Null if none mentioned.
    7. end_date (string): The end date of the timeframe requested. Format strictly as 'YYYY-MM-DD'. Null if none mentioned.

    8. memory_updates (array of objects): Extract personal facts, portfolio details, or financial goals shared by the user.
       - CRITICAL: DO NOT include 'role', 'watchlist', 'sectors', 'insight_types', or 'briefing_time' here! (Those belong in preference_updates).
       - Allowed 'fact_type' values MUST be one of: ["portfolio", "risk_tolerance", "goal", "investment_style", "general"].
       - Each object MUST contain "fact_type" and "fact_content". Return [] if none.    
    9. preference_updates (object): Extract updates ONLY if the user explicitly asks to change their core settings (e.g., "Change my briefing time to 09:00", "Add TSLA to my watchlist", "I'm a founder now"). Allowed keys: "briefing_time" (HH:MM format), "role", "sectors", "watchlist", "insight_types". Return null if no explicit changes are requested.
    
    --- GOOGLE WORKSPACE TOOLS ---
    10. needs_gmail_search (boolean): True if the user explicitly asks to search, check, or summarize emails.
    11. gmail_query (string): The search query for Gmail (e.g., "Apple", "team meeting"). Null if none.
    12. needs_calendar_schedule (boolean): True if the user asks to schedule a meeting, event, or reminder.
    13. meeting_title (string): The title of the event to schedule. Null if none.
    14. meeting_time (string): The exact ISO-8601 start time WITH TIMEZONE OFFSET for the meeting (e.g., YYYY-MM-DDTHH:MM:SS+05:30). Calculate this using the Current Date and Time provided above, assuming the user is in IST! Null if none.
    
    """
    
    if stage == 'new':
        welcome_text = (
            "Hi, I'm your personal AI financial assistant! 👋\n\n"
            "To make this experience perfectly personalized for you, I'd love to ask a few quick questions about your interests. "
            "Can we proceed with that?"
        )
        bot.reply_to(message, welcome_text)
        database.update_user_stage(user_id, 'awaiting_permission')
        print(f"---> [ONBOARDING] Advanced user to 'awaiting_permission'")

    elif stage == 'awaiting_permission':
        print("---> [ONBOARDING] Extracting permission intent...")
        extracted_data = ai.extract_json_data(user_message, """
        intent_to_skip (boolean) - Set to true ONLY if the user wants to ABORT the entire setup process. If the user provides ANY valid data (like a stock, role, or sector) but says "none" or "no" to a different part of your question, this MUST be false.
        intent_to_proceed (boolean) - Set to true ONLY if the user agrees to proceed with the onboarding questions.
        """)
        print(f"---> [DATA] Extracted Permission Data: {json.dumps(extracted_data, indent=2)}")
        
        if extracted_data.get('intent_to_skip'):
            database.update_user_stage(user_id, 'completed')
            bot.reply_to(message, "No problem at all! We can set that up later. How can I help you right now?")
        else:
            bot.reply_to(message, "Awesome! First up: What best describes your role (e.g., Investor, Student, Founder), and what type of financial insights are most valuable to you (news, earnings, macro, etc.)?")
            database.update_user_stage(user_id, 'awaiting_data1')

    elif stage == 'awaiting_data1':
        bot_question = "What best describes your role (e.g., Investor, Student, Founder), and what type of financial insights are most valuable to you (news, earnings, macro, etc.)?"
        print("---> [ONBOARDING] Extracting data1 (Role & Insights)...")
        
        # Notice we pass the function with the question here!
        extracted_data = ai.extract_json_data(user_message, get_onboarding_prompt(bot_question))
        print(f"---> [DATA] Extracted Data 1: {json.dumps(extracted_data, indent=2)}")
        
        if extracted_data.get('intent_to_skip'):
            database.update_user_stage(user_id, 'completed')
            bot.reply_to(message, "Skipped! We can dive straight into the markets. What do you need help with?")
        else:
            database.save_user_preferences(user_id, extracted_data)
            bot.reply_to(message, "Got it! Next: Which companies, sectors, or markets do you actively follow, and are there any specific stocks you'd like me to monitor?")
            database.update_user_stage(user_id, 'awaiting_data2')

    elif stage == 'awaiting_data2':
        bot_question = "Which companies, sectors, or markets do you actively follow, and are there any specific stocks you'd like me to monitor?"
        print("---> [ONBOARDING] Extracting data2 (Watchlist & Sectors)...")
        
        extracted_data = ai.extract_json_data(user_message, get_onboarding_prompt(bot_question))
        print(f"---> [DATA] Extracted Data 2: {json.dumps(extracted_data, indent=2)}")
        
        if extracted_data.get('intent_to_skip'):
            database.update_user_stage(user_id, 'completed')
            bot.reply_to(message, "Skipping the rest! What can I help you with today?")
        else:
            database.save_user_preferences(user_id, extracted_data)
            bot.reply_to(message, "Noted! Finally: When would you like to receive your daily briefing?")
            database.update_user_stage(user_id, 'awaiting_data3')

    elif stage == 'awaiting_data3':
        bot_question = "When would you like to receive your daily briefing?"
        print("---> [ONBOARDING] Extracting data3 (Briefing Time)...")
        
        extracted_data = ai.extract_json_data(user_message, get_onboarding_prompt(bot_question))
        print(f"---> [DATA] Extracted Data 3: {json.dumps(extracted_data, indent=2)}")
        
        if extracted_data.get('intent_to_skip'):
            database.update_user_stage(user_id, 'completed')
            bot.reply_to(message, "You're all set! What would you like to look at today?")
        else:
            database.save_user_preferences(user_id, extracted_data)
            bot.reply_to(message, "Perfect. Is there absolutely anything else you'd like to add to your profile? If not, just say 'no' or 'all good'!")
            database.update_user_stage(user_id, 'awaiting_extra')

    elif stage == 'awaiting_extra':
        print("---> [ONBOARDING] Extracting extra memory items...")
        bot_question = "Is there absolutely anything else you'd like to add to your profile? If not, just say 'no' or 'all good'!"
        
        extracted_data = ai.extract_json_data(user_message, get_onboarding_prompt(bot_question))
        print(f"---> [DATA] Extracted Extra: {json.dumps(extracted_data, indent=2)}")
        
        if not extracted_data.get('intent_to_skip'):
            database.save_user_preferences(user_id, extracted_data)
            database.save_memory_updates(user_id, extracted_data.get('memory_updates', []))
            
        database.update_user_stage(user_id, 'awaiting_google_auth')
        BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
        login_url = f"{BASE_URL}/auth/login?telegram_id={user_id}"
        
        bot.reply_to(
            message, 
            f"Ok\n\n"
            f"To help you prepare for meetings and manage your schedule, I can connect securely to your Google Calendar and Gmail.\n\n"
            f"🔗 Copy and paste this link into your browser:\n{login_url}\n\n"
            f"Once you've connected it in your browser, just say 'done'. Or, if you'd rather do this later, just tell me to skip!"
            f"Note: Because this is a hackathon prototype, the Google App is unverified. When logging in, please click Advanced -> Go to Atlas (unsafe) to proceed."
        )

    elif stage == 'awaiting_google_auth':
        print("---> [ONBOARDING] Checking Google Auth completion intent...")
        extracted_data = ai.extract_json_data(user_message, """
            Extract intent from the user's message:
            1. intent_to_skip (boolean) - True if the user says skip, no, later, etc.
            2. intent_to_proceed (boolean) - True if the user says done, finished, yes, connected, etc.
        """)
        print(f"---> [DATA] Google Auth Intent: {json.dumps(extracted_data, indent=2)}")
        
        database.update_user_stage(user_id, 'completed')
        
        if extracted_data.get('intent_to_skip'):
            bot.reply_to(message, "No worries, we can connect it later! Your profile is completely set up. 🎉 How can I help you today?")
        else:
            bot.reply_to(message, "Awesome, your Google account is linked! Your profile is completely set up. 🎉 How can I help you today?")

    elif stage == 'completed':
        print("---> [ROUTER] Asking Llama 3 to analyze intent & extract parameters...")
        extracted_intent = ai.extract_json_data(user_message, chat_extraction_prompt)
        print(f"---> [ROUTER] Extracted JSON Plan:\n{json.dumps(extracted_intent, indent=2)}")

        preference_updates = extracted_intent.get('preference_updates')
        if preference_updates:
            print(f"---> [PREFERENCES] Updating user settings: {preference_updates}")
            database.save_user_preferences(user_id, preference_updates)

        memory_updates = extracted_intent.get('memory_updates', [])
        if memory_updates:
            print(f"---> [MEMORY] Saving new background memories: {memory_updates}")
            database.save_memory_updates(user_id, memory_updates)
        
        # ==========================================
        # ROUTE A: The user is talking about a Document
        # ==========================================
        if extracted_intent.get("needs_document_read", False):
            print("---> [TOOL FLAG] 'needs_document_read' is TRUE.")
            latest_doc = database.get_latest_document(user_id)
            
            if latest_doc:
                gemini_file_id = latest_doc["gemini_file_id"]
                print(f"---> [TOOL EXECUTION] Asking Gemini to read doc ID: {gemini_file_id}")
                ai_response = ai.chat_with_document(user_message, gemini_file_id)
                bot.reply_to(message, ai_response)
            else:
                print("---> [TOOL ERROR] User asked about a doc, but no doc exists in DB.")
                bot.reply_to(message, "You asked about a document, but I don't see one uploaded recently. Try sending the file again!")
                
            print("---> [END] Document processing finished. Returning early.")
            return 
        
        # ==========================================
        # ROUTE B, C, D: Standard Chat, Market Data, & Google
        # ==========================================
        live_context = {} 
        
        # ROUTE B: Fetch live financial data if required
        if extracted_intent.get("requires_data", False):
            print("---> [TOOL FLAG] 'requires_data' is TRUE. Preparing to fetch market intel.")
            saved_profile = database.get_user_profile(user_id)
            temp_profile = {
                'watchlist': extracted_intent.get('watchlist') or saved_profile.get('watchlist', []),
                'sectors': extracted_intent.get('sectors') or saved_profile.get('sectors', []),
                'insight_types': extracted_intent.get('insight_types') or saved_profile.get('insight_types', []),
                'start_date': extracted_intent.get('start_date'),
                'end_date': extracted_intent.get('end_date')
            }
            print(f"---> [TOOL EXECUTION] Fetching finance data with params: {temp_profile}")
            live_context["financial_data"] = finance.get_daily_brief_data(temp_profile)
            print(f"---> [DATA FETCHED] Finance Data successfully added to context.")
            
        # ROUTE C: Gmail Search
        if extracted_intent.get("needs_gmail_search", False):
            print("---> [TOOL FLAG] 'needs_gmail_search' is TRUE.")
            if not database.get_integration_token(user_id, 'google'):
                print("---> [TOOL BLOCK] User needs to auth Google. Sending link.")
                BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
                login_url = f"{BASE_URL}/auth/login?telegram_id={user_id}"
                bot.reply_to(message, f"I need access to your Google Workspace to do that!\n🔗 Connect here (   ):\n{login_url} \n\nNote: Because this is a hackathon prototype, the Google App is unverified. When logging in, please click Advanced -> Go to Atlas (unsafe) to proceed.\n\nOnce you've connected, please repeat your requirement")
                return 
                
            query = extracted_intent.get("gmail_query", "")
            print(f"---> [TOOL EXECUTION] Searching Gmail for query: '{query}'")
            live_context["recent_emails"] = google_service.search_emails(user_id, query)
            print(f"---> [DATA FETCHED] Gmail data successfully added to context.")
            
        # ROUTE D: Calendar Scheduling
        if extracted_intent.get("needs_calendar_schedule", False):
            print("---> [TOOL FLAG] 'needs_calendar_schedule' is TRUE.")
            if not database.get_integration_token(user_id, 'google'):
                print("---> [TOOL BLOCK] User needs to auth Google. Sending link.")
                BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
                login_url = f"{BASE_URL}/auth/login?telegram_id={user_id}"
                bot.reply_to(message, f"I need access to your Google Workspace to do that!\n🔗 Connect here (Copy and paste the below link into your web browser):\n{login_url} \n\nNote: Because this is a hackathon prototype, the Google App is unverified. When logging in, please click Advanced -> Go to Atlas (unsafe) to proceed.\n\nOnce you've connected, please repeat your requirement")
                return 
                
            title = extracted_intent.get("meeting_title", "Meeting")
            start_time = extracted_intent.get("meeting_time")
            print(f"---> [TOOL EXECUTION] Scheduling Calendar Event: '{title}' at {start_time}")
            live_context["calendar_status"] = google_service.schedule_event(user_id, title, start_time)
            print(f"---> [DATA FETCHED] Calendar status added to context.")

        print("---> [FINAL LLM CALL] Constructing final payload for conversational reply.")
        live_data_str = json.dumps(live_context) if live_context else "{}"
        
        # Check how big the payload is just so you know!
        if live_context:
            print(f"---> [PAYLOAD PREVIEW] Sending the following live data to LLM: {live_context.keys()}")
        else:
            print(f"---> [PAYLOAD PREVIEW] No live tools triggered. Replying natively via LLM memory.")
            
        ai_response = ai.get_ai_response(user_id, user_message, live_data=live_data_str)
        print(f"---> [LLM RESPONSE] Chat Reply generated successfully.")
        
        bot.reply_to(message, ai_response['chat_reply'])

# Handle Image Messages
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    print(f"\n\n---> [NEW IMAGE] Received from User ID: {message.from_user.id}")
    bot.send_chat_action(message.chat.id, 'typing')
    
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        temp_image_path = "temp_image.jpg"
        with open(temp_image_path, 'wb') as temp_file:
            temp_file.write(downloaded_file)
            
        user_prompt = message.caption if message.caption else "Analyze this image for me."
        print(f"---> [IMAGE PROCESSING] Sending to Gemini Flash with prompt: '{user_prompt}'")
        
        ai_response = ai.analyze_image(temp_image_path, user_prompt)
        print("---> [IMAGE PROCESSING] Gemini Flash response received successfully.")
        bot.reply_to(message, ai_response)
        
    except Exception as e:
        print(f"---> [ERROR] Image Processing Error: {e}")
        bot.reply_to(message, f"Sorry, I ran into an error analyzing that image: {e}")
        
    finally:
        if os.path.exists("temp_image.jpg"):
            os.remove("temp_image.jpg")

# Handle Document Messages
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    file_name = message.document.file_name 
    print(f"\n\n---> [NEW DOCUMENT] '{file_name}' received from User ID: {user_id}")
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    try:
        # 1. Download from Telegram
        print("---> [DOC UPLOAD] Downloading from Telegram...")
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(file_name, 'wb') as temp_file:
            temp_file.write(downloaded_file)
            
        bot.send_chat_action(message.chat.id, 'upload_document')
        
        # 2. Upload to Gemini 
        print("---> [DOC UPLOAD] Uploading to Google Gemini Servers...")
        gemini_file_id = ai.upload_document_to_gemini(file_name)
        print(f"---> [DOC UPLOAD] Success! Gemini File ID: {gemini_file_id}")
        
        # 3. Save to Database
        database.save_document(
            user_id=user_id,
            file_name=file_name,
            telegram_file_id=file_id,
            gemini_file_id=gemini_file_id,
            file_type="document",
        )
        print("---> [DOC DB] Document metadata saved to database.")
        
        # 4. Handle Caption vs. No Caption
        if message.caption:
            print(f"---> [DOC ANALYSIS] Caption found: '{message.caption}'. Processing immediately via Gemini Pro.")
            bot.reply_to(message, f"Got your document ({file_name})! 📄 Processing your request...")
            ai_response = ai.chat_with_document(message.caption, gemini_file_id)
            
            database.save_chat_message(user_id, "user", f"(Uploaded Document: {file_name}) {message.caption}")
            database.save_chat_message(user_id, "assistant", ai_response)
            
            bot.reply_to(message, ai_response)
            print("---> [DOC ANALYSIS] Complete. Response sent.")
        else:
            print("---> [DOC ANALYSIS] No caption found. Prompting user for instructions.")
            bot.reply_to(message, f"Got your document ({file_name})! ✅\n\nWhat would you like me to do with it? (e.g., summarize it, look for risks, or check specific financial metrics)")
        
    except Exception as e:
        print(f"---> [ERROR] Document Processing Error: {e}")
        bot.reply_to(message, f"Sorry, I ran into an error reading that document: {e}")
        
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)

def check_and_send_briefs():
    """Runs continuously in the background, checking the time every 60 seconds."""
    while True:
        current_time = datetime.now().strftime("%H:%M")
        
        users_to_brief = database.get_users_for_briefing(current_time)
        
        if users_to_brief:
            print(f"\n---> [SCHEDULER] Time is {current_time}. Found {len(users_to_brief)} user(s) scheduled for a briefing.")
            
        for user_id in users_to_brief:
            print(f"---> [SCHEDULER] Starting brief generation for User {user_id}...")
            try:
                profile = database.get_user_profile(user_id)
                profile['start_date'] = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                profile['end_date'] = datetime.now().strftime('%Y-%m-%d')
                
                print(f"---> [SCHEDULER] Fetching finance data for Brief...")
                live_data_dict = finance.get_daily_brief_data(profile)
                live_data_str = json.dumps(live_data_dict)
                
                trigger_message = "Please generate my daily morning brief based on the provided live data."
                print(f"---> [SCHEDULER] Sending data to LLM for formatting...")
                brief = ai.get_ai_response(user_id, trigger_message, live_data=live_data_str)
                
                if not brief.get('is_silent', False):
                    print(f"---> [SCHEDULER] Success! Sending brief to user {user_id}.")
                    bot.send_message(user_id, f"🌅 **Your Daily Market Brief**\n\n{brief['chat_reply']}", parse_mode="Markdown")
                else:
                    print(f"---> [SCHEDULER] LLM triggered 'is_silent'. No major news to report. Skipping message to user.")
                    
            except Exception as e:
                print(f"---> [ERROR] Failed to send brief to {user_id}: {e}")
                
        time.sleep(60)

if __name__ == "__main__":
    import uvicorn
    from google_service import app

    # ---> ADD THIS EXACT LINE <---
    # This guarantees your tables are created on Render before the bot starts!
    database.init_db()

    # 1. Start background scheduler
    scheduler_thread = threading.Thread(target=check_and_send_briefs, daemon=True)
    scheduler_thread.start()

    # 2. Start Telegram bot in background thread
    bot_thread = threading.Thread(target=bot.infinity_polling, daemon=True)
    bot_thread.start()

    # 3. Start FastAPI server on main thread
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)