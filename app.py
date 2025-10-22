import asyncio
import base64
import json
import os
from collections import deque
from typing import Dict

import dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.websockets import WebSocketState

from logger_config import get_logger
from services.call_context import CallContext
from services.llm_service import LLMFactory
from services.stream_service import StreamService
from services.transcription_service import TranscriptionService
from services.tts_service import TTSFactory
import requests
from datetime import datetime
from pydantic import BaseModel
import psutil

dotenv.load_dotenv()
app = FastAPI()
logger = get_logger("App")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecretkey"))

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

call_contexts = {}
stream_status_data = {}

AGENT_API_URL = "https://68a050d56e38a02c58185916.mockapi.io/agents/vici_agents"

AURA2_VOICES = [
    {"model": "aura-2-thalia-en", "name": "Thalia", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-thalia.wav"},
    {"model": "aura-2-andromeda-en", "name": "Andromeda", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-andromeda.wav"},
    {"model": "aura-2-helena-en", "name": "Helena", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-helena.wav"},
    {"model": "aura-2-apollo-en", "name": "Apollo", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-apollo.wav"},
    {"model": "aura-2-arcas-en", "name": "Arcas", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-arcas.wav"},
    {"model": "aura-2-aries-en", "name": "Aries", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-aries.wav"},
    {"model": "aura-2-amalthea-en", "name": "Amalthea", "gender": "feminine", "language": "en-ph", "accent": "Filipino", "preview_url": "https://static.deepgram.com/examples/Aura-2-amalthea.wav"},
    {"model": "aura-2-asteria-en", "name": "Asteria", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-asteria.wav"},
    {"model": "aura-2-athena-en", "name": "Athena", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-athena.wav"},
    {"model": "aura-2-atlas-en", "name": "Atlas", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-atlas.wav"},
    {"model": "aura-2-aurora-en", "name": "Aurora", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-aurora.wav"},
    {"model": "aura-2-callista-en", "name": "Callista", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-callista.wav"},
    {"model": "aura-2-cora-en", "name": "Cora", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-cora.wav"},
    {"model": "aura-2-cordelia-en", "name": "Cordelia", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-cordelia.wav"},
    {"model": "aura-2-delia-en", "name": "Delia", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-delia.wav"},
    {"model": "aura-2-draco-en", "name": "Draco", "gender": "masculine", "language": "en-gb", "accent": "British", "preview_url": "https://static.deepgram.com/examples/Aura-2-draco.wav"},
    {"model": "aura-2-electra-en", "name": "Electra", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-electra.wav"},
    {"model": "aura-2-harmonia-en", "name": "Harmonia", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-harmonia.wav"},
    {"model": "aura-2-hera-en", "name": "Hera", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-hera.wav"},
    {"model": "aura-2-hermes-en", "name": "Hermes", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-hermes.wav"},
    {"model": "aura-2-hyperion-en", "name": "Hyperion", "gender": "masculine", "language": "en-au", "accent": "Australian", "preview_url": "https://static.deepgram.com/examples/Aura-2-hyperion.wav"},
    {"model": "aura-2-iris-en", "name": "Iris", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-iris.wav"},
    {"model": "aura-2-janus-en", "name": "Janus", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-janus.wav"},
    {"model": "aura-2-juno-en", "name": "Juno", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-juno.wav"},
    {"model": "aura-2-jupiter-en", "name": "Jupiter", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-jupiter.wav"},
    {"model": "aura-2-luna-en", "name": "Luna", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-luna.wav"},
    {"model": "aura-2-mars-en", "name": "Mars", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-mars.wav"},
    {"model": "aura-2-minerva-en", "name": "Minerva", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-minerva.wav"},
    {"model": "aura-2-neptune-en", "name": "Neptune", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-neptune.wav"},
    {"model": "aura-2-odysseus-en", "name": "Odysseus", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-odysseus.wav"},
    {"model": "aura-2-ophelia-en", "name": "Ophelia", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-ophelia.wav"},
    {"model": "aura-2-orion-en", "name": "Orion", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-orion.wav"},
    {"model": "aura-2-orpheus-en", "name": "Orpheus", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-orpheus.wav"},
    {"model": "aura-2-pandora-en", "name": "Pandora", "gender": "feminine", "language": "en-gb", "accent": "British", "preview_url": "https://static.deepgram.com/examples/Aura-2-pandora.wav"},
    {"model": "aura-2-phoebe-en", "name": "Phoebe", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-phoebe.wav"},
    {"model": "aura-2-pluto-en", "name": "Pluto", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-pluto.wav"},
    {"model": "aura-2-saturn-en", "name": "Saturn", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-saturn.wav"},
    {"model": "aura-2-selene-en", "name": "Selene", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-selene.wav"},
    {"model": "aura-2-theia-en", "name": "Theia", "gender": "feminine", "language": "en-au", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-theia.wav"},
    {"model": "aura-2-vesta-en", "name": "Vesta", "gender": "feminine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-vesta.wav"},
    {"model": "aura-2-zeus-en", "name": "Zeus", "gender": "masculine", "language": "en-us", "accent": "American", "preview_url": "https://static.deepgram.com/examples/Aura-2-zeus.wav"},
    {"model": "aura-2-celeste-es", "name": "Celeste", "gender": "feminine", "language": "es-co", "accent": "Colombian", "preview_url": "https://static.deepgram.com/examples/Celeste.wav"},
    {"model": "aura-2-estrella-es", "name": "Estrella", "gender": "feminine", "language": "es-mx", "accent": "Mexican", "preview_url": "https://static.deepgram.com/examples/Estrella.wav"},
    {"model": "aura-2-nestor-es", "name": "Nestor", "gender": "masculine", "language": "es-es", "accent": "Peninsular", "preview_url": "https://static.deepgram.com/examples/Nestor.wav"},
    {"model": "aura-2-sirio-es", "name": "Sirio", "gender": "masculine", "language": "es-mx", "accent": "Mexican", "preview_url": "https://static.deepgram.com/examples/Sirio.wav"},
    {"model": "aura-2-carina-es", "name": "Carina", "gender": "feminine", "language": "es-es", "accent": "Peninsular", "preview_url": "https://static.deepgram.com/examples/Carina.wav"},
    {"model": "aura-2-alvaro-es", "name": "Alvaro", "gender": "masculine", "language": "es-es", "accent": "Peninsular", "preview_url": "https://static.deepgram.com/examples/Alvaro.wav"},
    {"model": "aura-2-diana-es", "name": "Diana", "gender": "feminine", "language": "es-es", "accent": "Peninsular", "preview_url": "https://static.deepgram.com/examples/Diana.wav"},
    {"model": "aura-2-aquila-es", "name": "Aquila", "gender": "masculine", "language": "es-419", "accent": "Latin American", "preview_url": "https://static.deepgram.com/examples/Aquila.wav"},
    {"model": "aura-2-selena-es", "name": "Selena", "gender": "feminine", "language": "es-419", "accent": "Latin American", "preview_url": "https://static.deepgram.com/examples/Selena.wav"},
    {"model": "aura-2-javier-es", "name": "Javier", "gender": "masculine", "language": "es-mx", "accent": "Latin American", "preview_url": "https://static.deepgram.com/examples/Javier.wav"}
]

class AgentCreate(BaseModel):
    name: str
    system_message: str
    initial_message: str
    voice_model: str

def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def update_env_file(updates: dict, env_file_path: str = ".env"):
    try:
        if os.path.exists(env_file_path):
            with open(env_file_path, 'r') as file:
                lines = file.readlines()
        else:
            lines = []
        existing_keys = {}
        for line in lines:
            if line.strip() and not line.strip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                existing_keys[key.strip()] = value.strip()
        for key, value in updates.items():
            existing_keys[key] = value
        with open(env_file_path, 'w') as file:
            for key, value in existing_keys.items():
                file.write(f"{key}={value}\n")
        for key, value in updates.items():
            os.environ[key] = value
        return True
    except Exception as e:
        logger.error(f"Failed to update .env file: {str(e)}", exc_info=True)
        return False



@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "password":
        request.session["user"] = username
        return RedirectResponse(url="/agents", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout", response_class=RedirectResponse)
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request, current_user: str = Depends(get_current_user)):
    try:
        response = requests.get(AGENT_API_URL, timeout=5)
        response.raise_for_status()
        agents = response.json()
        return templates.TemplateResponse("agents.html", {"request": request, "agents": agents, "success": request.session.pop("success", None)})
    except requests.RequestException as e:
        return templates.TemplateResponse("agents.html", {"request": request, "agents": [], "error": f"Failed to fetch agents: {str(e)}"})

@app.get("/create-agent", response_class=HTMLResponse)
async def create_agent_page(request: Request, current_user: str = Depends(get_current_user)):
    return templates.TemplateResponse("create_agent.html", {
        "request": request, "error": None, "edit": request.query_params.get("edit") == "true",
        "id": request.query_params.get("id"), "name": request.query_params.get("name"),
        "system": request.query_params.get("system"), "initial": request.query_params.get("initial"),
        "voice_model": request.query_params.get("voice_model", "aura-2-asteria-en"), "voices": AURA2_VOICES
    })

@app.post("/create-agent", response_class=JSONResponse)
async def create_agent(name: str = Form(...), system_message: str = Form(...), initial_message: str = Form(...), voice_model: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        agent_data = AgentCreate(name=name, system_message=system_message, initial_message=initial_message, voice_model=voice_model)
        response = requests.post(AGENT_API_URL, json=agent_data.dict(), timeout=5)
        response.raise_for_status()
        return {"status": "success", "message": "Agent created successfully"}
    except requests.RequestException as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to create agent: {str(e)}"})

@app.post("/update-agent/{agent_id}", response_class=JSONResponse)
async def update_agent(agent_id: str, name: str = Form(...), system_message: str = Form(...), initial_message: str = Form(...), voice_model: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        agent_data = AgentCreate(name=name, system_message=system_message, initial_message=initial_message, voice_model=voice_model)
        response = requests.put(f"{AGENT_API_URL}/{agent_id}", json=agent_data.dict(), timeout=5)
        response.raise_for_status()
        return {"status": "success", "message": "Agent updated successfully"}
    except requests.RequestException as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to update agent: {str(e)}"})

@app.post("/delete-agent/{agent_id}", response_class=JSONResponse)
async def delete_agent(agent_id: str, current_user: str = Depends(get_current_user)):
    try:
        response = requests.delete(f"{AGENT_API_URL}/{agent_id}", timeout=5)
        response.raise_for_status()
        return {"status": "success", "message": "Agent deleted successfully"}
    except requests.RequestException as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to delete agent: {str(e)}"})

@app.get("/assign-agent", response_class=HTMLResponse)
async def assign_agent_page(request: Request, current_user: str = Depends(get_current_user)):
    try:
        response = requests.get(AGENT_API_URL, timeout=5)
        response.raise_for_status()
        agents = response.json()
        current_agent_id = os.getenv("AGENT_ID", "1")
        return templates.TemplateResponse("assign_agent.html", {"request": request, "agents": agents, "error": None, "current_agent_id": current_agent_id})
    except requests.RequestException as e:
        return templates.TemplateResponse("assign_agent.html", {"request": request, "agents": [], "error": f"Failed to fetch agents: {str(e)}", "current_agent_id": os.getenv("AGENT_ID", "1")})

@app.post("/assign-agent", response_class=JSONResponse)
async def assign_agent(request: Request, agent_id: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        agent_url = f"{AGENT_API_URL}/{agent_id}"
        agent_res = requests.get(agent_url, timeout=3)
        agent_res.raise_for_status()
        agent_data = agent_res.json()
        system_message = agent_data.get("system_message")
        initial_message = agent_data.get("initial_message")  # Allow empty or None
        agent_name = agent_data.get("name", f"Agent {agent_id}")
        voice_model = agent_data.get("voice_model")  # No default
        if not system_message or not voice_model:
            return JSONResponse(status_code=400, content={"status": "error", "message": f"Agent {agent_id} configuration is incomplete: system_message and voice_model are required"})
        env_updated = update_env_file({"AGENT_ID": agent_id, "DEEPGRAM_MODEL": voice_model})
        if not env_updated:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to update configuration file"})
        request.session["assigned_agent"] = agent_id
        logger.info(f"Agent {agent_id} ({agent_name}) assigned by user {current_user}")
        return JSONResponse({
            "status": "success", 
            "message": f"Agent '{agent_name}' assigned successfully",
            "agent_id": agent_id, 
            "agent_name": agent_name, 
            "system_message": system_message,
            "initial_message": initial_message, 
            "voice_model": voice_model, 
            "env_updated": True, 
            "restart_required": True
        })
    except requests.RequestException as e:
        logger.error(f"Failed to fetch agent {agent_id}: {str(e)}", exc_info=True)
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to assign agent: {str(e)}"})
    except Exception as e:
        logger.error(f"Unexpected error in assign_agent for agent {agent_id}: {str(e)}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})

@app.get("/current-agent")
async def get_current_agent():
    try:
        agent_id = os.getenv("AGENT_ID", "1")
        agent_url = f"{AGENT_API_URL}/{agent_id}"
        agent_res = requests.get(agent_url, timeout=3)
        agent_res.raise_for_status()
        agent_data = agent_res.json()
        return {
            "agent_id": agent_id, "agent_name": agent_data.get("name", f"Agent {agent_id}"),
            "system_message": agent_data.get("system_message"), "initial_message": agent_data.get("initial_message"),
            "voice_model": agent_data.get("voice_model", "aura-2-asteria-en")
        }
    except Exception as e:
        return {"error": f"Failed to get current agent: {str(e)}", "agent_id": os.getenv("AGENT_ID", "1")}

@app.get("/voices", response_class=JSONResponse)
async def get_voices():
    return {"voices": AURA2_VOICES}

@app.get("/")
async def root():
    return {"message": "API is running"}

@app.post("/incoming")
async def incoming_call(request: Request) -> HTMLResponse:
    try:
        # Capture query parameters
        query_params = dict(request.query_params)
        
        # Capture headers
        headers = dict(request.headers)
        
        # Capture body (if any)
        try:
            body = await request.json()
        except Exception:
            body_text = await request.body()
            body = {"raw_body": body_text.decode("utf-8", errors="ignore")}
        
        # Extract callId, session token, and First-Name
        call_id = None
        session_token = body.get("Session", headers.get("x-cx-session"))
        first_name = None
        try:
            call_id = (body.get("SessionData", {}).get("callIds", [None])[0] or 
                       body.get("SessionData", {}).get("profile", {}).get("callId", [None])[0])
            first_name = body.get("SessionData", {}).get("profile", {}).get("trunk-sip-headers", {}).get("First-Name")
            if not call_id:
                logger.warning("No callId found in SessionData, falling back to Session token")
                call_id = session_token  # Fallback to session token if callId is missing
            logger.info(f"Extracted callId: {call_id}, Session token: {session_token}, First-Name: {first_name}")
        except Exception as e:
            logger.error(f"Error extracting callId or First-Name: {str(e)}", exc_info=True)
        
        # Initialize CallContext
        call_context = CallContext()
        call_context.call_sid = call_id  # Use call_id instead of CallSid
        call_context.session = session_token
        call_context.first_name = first_name
        call_contexts[call_id] = call_context  # Store with call_id as key
        logger.info(f"Stored CallContext: {call_context.to_dict()}")
        
        # Log the request details
        request_data = {
            "query_params": query_params,
            "headers": headers,
            "body": body,
            "timestamp": datetime.now().isoformat()
        }
        logger.info("========== VOICE APPLICATION REQUEST ==========")
        logger.info(json.dumps(request_data, indent=2, ensure_ascii=False))
        logger.info("==============================================")
        
        # Original CXML response
        server = os.environ.get("SERVER", "callapi.vetaai.com")
        cxml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        cxml += '<Response>\n'
        cxml += '    <Connect>\n'
        cxml += f'        <Stream url="wss://{server}/connection" track="both_tracks" name="my-stream" statusCallback="https://{server}/stream-status" statusCallbackMethod="POST" />\n'
        cxml += '    </Connect>\n'
        cxml += '</Response>'
        return HTMLResponse(content=cxml, status_code=200)
    
    except Exception as e:
        logger.error(f"Error processing Voice Application Request: {str(e)}", exc_info=True)
        # Return the CXML response even if logging or context setup fails
        server = os.environ.get("SERVER", "callapi.vetaai.com")
        cxml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        cxml += '<Response>\n'
        cxml += '    <Connect>\n'
        cxml += f'        <Stream url="wss://{server}/connection" track="both_tracks" name="my-stream" statusCallback="https://{server}/stream-status" statusCallbackMethod="POST" />\n'
        cxml += '    </Connect>\n'
        cxml += '</Response>'
        return HTMLResponse(content=cxml, status_code=200)

@app.post("/stream-status")
async def stream_status(request: Request):
    try:
        # Read both JSON and raw text body
        try:
            body = await request.json()
        except Exception:
            body_text = await request.body()
            body = {"raw_body": body_text.decode("utf-8", errors="ignore")}
        
        # Combine query params and body
        query_params = dict(request.query_params)
        headers = dict(request.headers)
        event_data = {
            "query_params": query_params,
            "body": body,
            "headers": headers
        }

        # Log everything in a readable JSON format
        logger.info("========== CLOUDONIX STREAM EVENT ==========")
        logger.info(json.dumps(event_data, indent=2, ensure_ascii=False))
        logger.info("============================================")

        # Store stream_sid if available
        stream_sid = (
            body.get("StreamSid") 
            or query_params.get("StreamSid") 
            or headers.get("StreamSid")
        )
        if stream_sid:
            stream_status_data[stream_sid] = event_data

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing stream status: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

@app.websocket("/connection")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    llm_service_name = os.getenv("LLM_SERVICE", "openai")
    tts_service_name = os.getenv("TTS_SERVICE", "deepgram")
    logger.info(f"Using LLM service: {llm_service_name}")
    logger.info(f"Using TTS service: {tts_service_name}")
    llm_service = LLMFactory.get_llm_service(llm_service_name, CallContext())
    stream_service = StreamService(websocket)
    transcription_service = TranscriptionService()
    tts_service = TTSFactory.get_tts_service(tts_service_name)
   
    marks = deque()
    interaction_count = 0
    await transcription_service.connect()

    def replace_template_variables(text, first_name):
        if not text:
            return text
        if first_name:
            return text.replace("{{First-Name}}", first_name).strip()
        return re.sub(r'\s+', ' ', text.replace("{{First-Name}}", "").strip())

    async def process_media(msg):
        await transcription_service.send(base64.b64decode(msg['media']['payload']))

    async def handle_transcription(text):
        nonlocal interaction_count
        if not text:
            return
        logger.info(f"Interaction {interaction_count} – STT -> LLM: {text}")
        await llm_service.completion(text, interaction_count)
        interaction_count += 1

    async def handle_llm_reply(llm_reply, icount):
        logger.info(f"Interaction {icount}: LLM -> TTS: {llm_reply['partialResponse']}")
        await tts_service.generate(llm_reply, icount)

    async def handle_speech(response_index, audio, label, icount):
        logger.info(f"Interaction {icount}: TTS -> TWILIO: {label}")
        await stream_service.buffer(response_index, audio)

    async def handle_audio_sent(mark_label):
        marks.append(mark_label)

    async def handle_utterance(text, stream_sid):
        try:
            if len(marks) > 0 and text.strip():
                logger.info("Intruption detected, clearing system.")
                await websocket.send_json({
                    "streamSid": stream_sid,
                    "event": "clear"
                })
                stream_service.reset()
                llm_service.reset()
        except Exception as e:
            logger.error(f"Error while handling utterance: {e}")
            e.print_stack()

    transcription_service.on('utterance', handle_utterance)
    transcription_service.on('transcription', handle_transcription)
    llm_service.on('llmreply', handle_llm_reply)
    tts_service.on('speech', handle_speech)
    stream_service.on('audiosent', handle_audio_sent)

    message_queue = asyncio.Queue()

    async def websocket_listener():
        try:
            while True:
                data = await websocket.receive_text()
                await message_queue.put(json.loads(data))
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")

    async def message_processor():
        while True:
            msg = await message_queue.get()
            if msg['event'] == 'start':
                stream_sid = msg['start']['streamSid']
                session_token = msg['start']['callSid']  # This is the session token

                # === FIND CallContext using session_token or call_id ===
                call_context = None
                call_id = None

                # Try to match by session token
                for cid, ctx in call_contexts.items():
                    if ctx.session == session_token:
                        call_context = ctx
                        call_id = cid
                        logger.info(f"Matched CallContext by session token: {session_token} → call_id: {call_id}")
                        break

                # Fallback: try direct match by callSid if it's actually the call_id
                if not call_context and session_token in call_contexts:
                    call_context = call_contexts[session_token]
                    call_id = session_token
                    logger.info(f"Matched CallContext directly by callSid: {session_token}")

                if not call_context:
                    logger.warning(f"No CallContext found for session {session_token}, creating new")
                    call_context = CallContext()
                    call_context.session = session_token
                    call_id = session_token

                # === FIRST-NAME (already in call_context from /incoming) ===
                first_name = getattr(call_context, 'first_name', None) or "Mamoon"
                logger.info(f"Using first_name: {first_name}")

                # === AGENT FETCHING ===
                agent_id = os.getenv("AGENT_ID", "1")
                system_message = os.getenv("SYSTEM_MESSAGE")
                initial_message = os.getenv("INITIAL_MESSAGE")

                try:
                    agent_url = f"{os.getenv('AGENT_API_URL')}/{agent_id}"
                    agent_res = requests.get(agent_url, timeout=3)
                    agent_res.raise_for_status()
                    agent_data = agent_res.json()
                    system_message = agent_data.get("system_message")
                    initial_message = agent_data.get("initial_message")
                    logger.info(f"Using agent {agent_id} from API")
                except Exception as e:
                    logger.warning(f"Failed to fetch agent {agent_id}: {e}")

                # === REPLACE {{First-Name}} ===
                if system_message:
                    system_message = replace_template_variables(system_message, first_name)
                if initial_message:
                    initial_message = replace_template_variables(initial_message, first_name)

                # Update context
                call_context.system_message = system_message
                call_context.initial_message = initial_message
                call_context.call_sid = session_token
                call_context.stream_sid = stream_sid
                call_contexts[call_id] = call_context

                llm_service.set_call_context(call_context)
                stream_service.set_stream_sid(stream_sid)
                transcription_service.set_stream_sid(stream_sid)
                logger.info(f"Twilio -> Starting Media Stream for {stream_sid}")

                await tts_service.generate({
                    "partialResponseIndex": None,
                    "partialResponse": call_context.initial_message or "Hello"
                }, 1)

            elif msg['event'] == 'media':
                asyncio.create_task(process_media(msg))
            elif msg['event'] == 'mark':
                label = msg['mark']['name']
                if label in marks:
                    marks.remove(label)
            elif msg['event'] == 'stop':
                logger.info(f"Twilio -> Media stream {stream_sid} ended.")
                break
            message_queue.task_done()

    try:
        listener_task = asyncio.create_task(websocket_listener())
        processor_task = asyncio.create_task(message_processor())
        await asyncio.gather(listener_task, processor_task)
    except asyncio.CancelledError:
        logger.info("Tasks cancelled")
    finally:
        await transcription_service.disconnect()

@app.get("/transcript/{call_sid}")
async def get_transcript(call_sid: str):
    call_context = call_contexts.get(call_sid)
    if not call_context:
        logger.info(f"[GET] Call not found for call SID: {call_sid}")
        return {"error": "Call not found"}
    return {"transcript": call_context.user_context}

@app.get("/all_transcripts")
async def get_all_transcripts():
    try:
        transcript_list = []
        for call_sid, context in call_contexts.items():
            transcript_list.append({"call_sid": call_sid, "transcript": context.user_context})
        return {"transcripts": transcript_list}
    except Exception as e:
        logger.error(f"Error fetching all transcripts: {str(e)}", exc_info=True)
        return {"error": f"Failed to fetch all transcripts: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    logger.info(f"Backend server address set to: {os.getenv('SERVER')}")
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
