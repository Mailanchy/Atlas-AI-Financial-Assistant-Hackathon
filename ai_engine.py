# ai_engine.py
import json
import os
from dotenv import load_dotenv
from groq import Groq
from PIL import Image
from google import genai
import database

load_dotenv()
client = Groq()

# AI setup for normal conversations
def get_ai_response(user_id, user_message, live_data=None):
    print(f"\n---> [AI ENGINE] get_ai_response triggered for User {user_id}")
    
    # 1. Fetch User Profile & Chat History
    profile = database.get_user_profile(user_id)
    history = database.get_recent_chat_history(user_id, limit=10)
    
    print(f"---> [AI ENGINE] Retrieved Profile: {profile}")
    print(f"---> [AI ENGINE] Retrieved Chat History: {len(history)} previous messages")
    
    # 2. Dynamically build the profile text
    profile_lines = []
    for key, value in profile.items():
        clean_key = key.replace('_', ' ').title()
        
        if isinstance(value, list):
            clean_value = ', '.join(value) if value else 'None specified'
        else:
            clean_value = value if value else 'None specified'
            
        profile_lines.append(f"- {clean_key}: {clean_value}")
        
    dynamic_profile_text = "\n    ".join(profile_lines)
    
    # 3. Build the System Prompt (Now enforcing JSON)
    data_context = live_data if live_data else "{}"
    print(f"---> [AI ENGINE] Live Data Context length: {len(data_context)} characters")
    
    system_prompt = f"""You are Atlas, an elite, highly analytical financial analyst and executive assistant built for finance professionals. 

    USER PROFILE & INTERESTS:
    {dynamic_profile_text}

    LIVE FINANCIAL DATA PROVIDED FOR THIS TURN: 
    {data_context}
    
    CRITICAL BEHAVIORAL INSTRUCTIONS:
    1. ANALYTICAL DEPTH: Never just forward news headlines or raw data stats. Always synthesize the information, connect it subtly to the user's background when relevant, and explain *why* it matters from an investment or strategic perspective.
    2. STRICT FACTUAL ACCURACY: Rely ONLY on the provided LIVE FINANCIAL DATA or your verified local knowledge. If data or company metrics cannot be verified from the provided payload, clearly communicate uncertainty. DO NOT hallucinate.
    3. SCOPE & LIMITATIONS: Your capabilities are strictly limited to financial research, reading uploaded documents, scheduling Google Calendar meetings, and searching Gmail. You CANNOT execute live trades, move money, book travel, or control external applications. If a user asks for an unsupported action, politely and concisely decline, explaining what you can do instead.
    4. NATURAL CONVERSATION & PROFILE USAGE: Speak naturally, concisely, and professionally inside Telegram. DO NOT explicitly recite or state the user's profile information back to them (e.g., avoid starting sentences with "As a student..." or "Since you follow AAPL...") unless it is strictly necessary to contextualize a complex financial answer. Keep it fluid.
    5. SETTINGS UPDATES: If the user's message is simply asking to change their settings or briefing time, ONLY confirm that the change was made cleanly and concisely. Do not inject unprompted market analysis.
    6. HISTORY AWARENESS: You have access to the last 10 messages in this chat. Use them to maintain context, but do not repeat or summarize or respond to them unless explicitly asked.
    CRITICAL JSON FORMAT INSTRUCTION:
    You MUST respond ONLY with valid JSON. No markdown formatting outside the JSON, no explanations.
    Use this exact schema:
    {{
        "chat_reply": "Your natural, expert financial response to the user.",
        "is_silent": false
    }}
    
    Rules for the JSON:
    - "chat_reply": The conversational response formatted in Markdown.
    - "is_silent": Set to true ONLY if you are writing a scheduled daily brief and the market news is completely mundane or non-market-moving. Also if the market news has no relevence for the user's profile, this MUST be true. For all direct user questions, this MUST be false.
    """
    
    # 4. Construct the exact message array for Llama 3
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    
    print("---> [AI ENGINE] Sending payload to Groq (Llama 3.3 70B)...")
    
    # 5. Generate the response
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        response_format={"type": "json_object"} # Forces the model to output strict JSON
    )
    
    raw_text = response.choices[0].message.content.strip()
    print(f"---> [AI ENGINE] Raw Response from Groq:\n{raw_text}\n")
    
    # 6. Parse the JSON and Save this interaction
    try:
        ai_data = json.loads(raw_text)
        
        # Only save to chat history if the bot is actually speaking to the user
        if not ai_data.get("is_silent", False):
            print("---> [AI ENGINE] Saving Assistant reply to database chat history.")
            database.save_chat_message(user_id, "user", user_message)
            # Notice we only save the "chat_reply" text, not the whole JSON dictionary
            database.save_chat_message(user_id, "assistant", ai_data["chat_reply"])
        else:
            print("---> [AI ENGINE] 'is_silent' is TRUE. Skipping database history save.")
            
        return ai_data
        
    except json.JSONDecodeError:
        print(f"---> [AI ERROR] Failed to parse JSON. Raw output: {raw_text}")
        # Graceful fallback so the bot doesn't crash on the user's end
        return {
            "chat_reply": "I'm sorry, I ran into a formatting error while thinking about that.", 
            "is_silent": False
        }

# AI setup for structured data extraction
def extract_json_data(user_message, extraction_prompt):    
    print(f"\n---> [AI ENGINE] extract_json_data triggered for message: '{user_message[:50]}...'")
    strict_prompt = extraction_prompt + "\n\nYou MUST respond ONLY with valid JSON. No markdown formatting, no explanations."
    
    print("---> [AI ENGINE] Sending extraction prompt to Groq...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": strict_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.0,
        response_format={"type": "json_object"}
    )
    raw_text = response.choices[0].message.content.strip()
    print(f"---> [AI ENGINE] Raw Extraction Output:\n{raw_text}\n")
    
    try:
        # Convert the LLM's text response into a real Python dictionary
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print(f"---> [AI ERROR] Failed to parse JSON extraction. Raw output: {raw_text}")
        return {}

# AI setup for image analysis using Gemini
gemini_client1 = genai.Client(api_key=os.getenv("GEMINI_API_KEY1"))

def analyze_image(image_path, prompt="Describe what is in this image"):
    print(f"\n---> [AI ENGINE] analyze_image triggered for: '{image_path}'")
    img = Image.open(image_path)
    
    print("---> [AI ENGINE] Sending image to Gemini 3.5 Flash...")
    response = gemini_client1.models.generate_content(
        model='gemini-3.5-flash', 
        contents=[prompt, img]
    )
    print(f"---> [AI ENGINE] Gemini Flash Response length: {len(response.text)} characters")
    return response.text

# AI setup for document analysis using Gemini
gemini_client2 = genai.Client(api_key=os.getenv("GEMINI_API_KEY2"))

def upload_document_to_gemini(file_path):
    """Uploads a file to Google's servers and returns the unique ID."""
    print(f"\n---> [AI ENGINE] Uploading '{file_path}' to Google Gemini Servers...")
    uploaded_file = gemini_client2.files.upload(file=file_path)
    print(f"---> [AI ENGINE] Upload Success. Google File Name: {uploaded_file.name}")
    # Return the unique ID (e.g., 'files/abc123xyz') so we can save it to the DB
    return uploaded_file.name 

def chat_with_document(user_prompt, gemini_file_id):
    """Answers a question using a previously uploaded file."""
    print(f"\n---> [AI ENGINE] chat_with_document triggered for File ID: {gemini_file_id}")
    
    # 1. Fetch the file reference from Google's servers using the ID
    print("---> [AI ENGINE] Retrieving file reference from Google...")
    file_info = gemini_client2.files.get(name=gemini_file_id)
    
    # 2. Pass the file reference and the user's question to the LLM
    print("---> [AI ENGINE] Sending prompt and document reference to Gemini 2.5 Pro...")
    response = gemini_client2.models.generate_content(
        model='gemini-2.5-pro',
        contents=[file_info, user_prompt]
    )
    print(f"---> [AI ENGINE] Gemini Pro Response length: {len(response.text)} characters")
    return response.text

def transcribe_telegram_voice(file_path):
    print(f"\n---> [AI ENGINE] transcribe_telegram_voice triggered for: '{file_path}'")
    print("---> [AI ENGINE] Sending audio to Groq Whisper...")
    with open(file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(file_path, audio_file.read()),
            model="whisper-large-v3-turbo",  # Ultra-fast & highly accurate
            response_format="text"
        )
        print(f"---> [AI ENGINE] Whisper Transcription Output: '{transcription}'")
        return transcription