# 🏦 Atlas AI Financial Assistant

Atlas is an elite, highly analytical AI financial assistant and executive bot built for finance professionals. It is designed to track markets, analyze documents, and seamlessly integrate into daily workflows through Telegram.

This project was built during a Hackathon to demonstrate the capabilities of multimodal AI agents combined with live financial APIs and productivity tools.

## ✨ Features

- **Conversational Intelligence**: Powered by Groq and Google Gemini, Atlas maintains context, understands user preferences, and adapts to your role (e.g., Founder, Data Analyst, Trader).
- **Live Market Data**: Integrates with Finnhub and Yahoo Finance (`yfinance`) to fetch real-time stock prices, SEC filings, and financial news.
- **Multimodal Capabilities**:
  - 📄 **PDF Summarization**: Upload earnings reports or financial documents and ask Atlas to analyze them.
  - 🖼️ **Image Analysis**: Send stock charts or screenshots and ask for trend analysis using Gemini Vision.
  - 🎙️ **Voice Processing**: Send voice notes, and Atlas will transcribe (via Whisper) and respond seamlessly.
- **Productivity & Google Workspace**: Connect your Google account via OAuth to allow Atlas to schedule Calendar events or search your Gmail for important emails.
- **Automated Daily Briefings**: Atlas uses a background scheduler to send personalized market briefings at your preferred time, avoiding spam by only sending updates when important events occur.

## 🏗️ Architecture

- **Bot Interface**: `pyTelegramBotAPI` with multi-threading to handle multiple users simultaneously.
- **LLM Routing**: `ai_engine.py` orchestrates prompts between Groq (for fast chat) and Gemini (for document/image processing).
- **Database**: SQLite (`database.py`) with strict foreign keys to manage user profiles, long-term memory (preferences), and OAuth integration tokens.
- **Web Server / OAuth**: FastAPI (`google_service.py`) handles Google OAuth 2.0 flow and redirects.

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Telegram Bot Token (from [BotFather](https://core.telegram.org/bots#botfather))
- API Keys for Groq, Google Gemini, Finnhub, and Google Cloud Console (OAuth credentials)

### 1. Clone the repository
```bash
git clone https://github.com/Mailanchy/Atlas-AI-Financial-Assistant-Hackathon.git
cd Atlas-AI-Financial-Assistant-Hackathon
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory and add the following keys:
```env
TELEGRAM_BOT_TOKEN=your_telegram_token
GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY1=your_gemini_api_key_1
GEMINI_API_KEY2=your_gemini_api_key_2
FINNHUB_API_KEY=your_finnhub_api_key
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
BASE_URL=http://localhost:8000 # Your FastAPI server URL (for OAuth callbacks)
```

### 4. Run the services
The project uses a Telegram polling mechanism and a FastAPI server for OAuth. You will need to start both:
```bash
# Start the Telegram Bot & Background Scheduler
python telegram.py

# In a separate terminal, start the FastAPI OAuth server
uvicorn google_service:app --host 0.0.0.0 --port 8000
```

## 🧪 Testing the Bot

1. Open Telegram and send `/start` to your bot.
2. Complete the onboarding experience to set your role and tracked stocks.
3. **Try commands:**
   - *"What's the live price of NVDA and are there any recent SEC filings?"*
   - Upload a PDF and ask *"Summarize the risks mentioned in this document."*
   - Connect Google, then ask *"Schedule a 1-hour meeting with my team tomorrow at 3 PM to discuss earnings."*
   - Send a voice note asking for a market overview.

## 📝 Notes
- SQLite is used for simplicity and thread safety, utilizing localized database connections inside handlers to avoid threading locks.
- Render deployment ready: The bot can be hosted on platforms like Render by serving FastAPI on the required port.

