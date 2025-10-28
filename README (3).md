# AI Calling Agent (Cloudonix Version)

An AI-powered calling agent built with **Cloudonix** and **FastAPI**.  
It integrates **OpenAI**, **Deepgram**, **ElevenLabs**, and **Gemini** to handle speech recognition, text generation, and natural-sounding voice synthesis.

---

## Installation

### 1. Create a Virtual Environment
It’s recommended to create a Python virtual environment to avoid dependency conflicts.

```bash
python -m venv venv
source venv/bin/activate      # For Linux/Mac
venv\Scripts\activate         # For Windows
```

---

### 2. Install Dependencies
After activating the environment, install all required packages:

```bash
pip install -r requirements.txt
```

---

### 3. Configure the `.env` File
Copy `.env.example` to `.env` and set up all required environment variables.

Example configuration:

```env
# Server Configuration
SERVER=callapi.vetaai.com
PORT=3000

# =========================================
# 🌩️ Cloudonix Configuration
# =========================================
CLOUDONIX_API_KEY=sk-your_cloudonix_api_key_here
CLOUDONIX_API_BASE=https://api.cloudonix.io
CLOUDONIX_DOMAIN_ID=your_domain_id_here
CLOUDONIX_TRUNK_NAME=your_trunk_name_here


# =========================================
# 🤖 AI / API Keys
# =========================================
# Google Gemini
GEMINI_API_KEY=AIza-your_gemini_api_key_here

# OpenAI
OPENAI_API_KEY=sk-your_openai_api_key_here

# Anthropic Claude
ANTHROPIC_API_KEY=sk-your_anthropic_api_key_here

# Deepgram (Speech-to-Text)
DEEPGRAM_API_KEY=dg-your_deepgram_api_key_here

# ElevenLabs (Text-to-Speech)
ELEVENLABS_API_KEY=el-your_elevenlabs_api_key_here
ELEVENLABS_MODEL_ID=eleven_turbo_v2
ELEVENLABS_VOICE_ID=your_voice_id_here

# Service Configuration
TTS_SERVICE=deepgram
LLM_SERVICE=openai

# Phone Numbers
APP_NUMBER=+12396675040
YOUR_NUMBER=+17542168196
TRANSFER_NUMBER=+19173974948

# Agent Configuration
AGENT_API_URL=https://68a050d56e38a02c58185916.mockapi.io/agents/vici_agents
AGENT_ID=5

# AI Configuration
SYSTEM_MESSAGE="You are Rebecca, a warm, professional, and empathetic representative from the wellness team. Your role is to guide approved individuals through a no-cost wellness test with clarity and empathy..."
INITIAL_MESSAGE="Hi, Mohim this is Rebecca calling from Wellness Team."
RECORD_CALLS=false

# Deepgram Configuration
DEEPGRAM_MODEL=aura-2-asteria-en
```

> ⚠️ **Important:** Replace all placeholder values with your actual credentials.

---

### 4. Run the FastAPI Server
Start the backend server:

```bash
python app.py
```

The app will run at:
```
http://localhost:3000
```

---

### 5. Running Locally (External Access)
If you’re running the app locally, **Cloudonix requires a public URL** to connect audio streams.  
To make your local server accessible, use **ngrok** or any other tunneling service.

Example with ngrok:
```bash
ngrok http 3000
```

Copy the generated public URL (e.g., `https://1234abcd.ngrok-free.app`) and use it as your `SERVER` value in the `.env` file.

---

## Contribution
Contributions are welcome.  
Fork the repository and submit a pull request for improvements or new features.

---

## Acknowledgement
This project was adapted for **Cloudonix Streaming Integration**.  
Special thanks to **Claude Sonnet 3.5**, **GPT-4o**, and **Aider** for their help in development 🦾.
