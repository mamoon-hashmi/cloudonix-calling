import asyncio
import base64
import json
import os
from collections import deque
from typing import Dict
import uuid

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
from datetime import datetime
from pydantic import BaseModel
import psutil
import re

dotenv.load_dotenv()
app = FastAPI()
logger = get_logger("App")

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "supersecretkey"))

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

call_contexts = {}
stream_status_data = {}

AGENTS_JSON_FILE = "agents.json"

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

def read_agents(file_path: str = AGENTS_JSON_FILE) -> list:
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as file:
                agents = json.load(file)
                if not isinstance(agents, list):
                    logger.warning("Agents JSON file does not contain a list, initializing empty list")
                    return []
                return agents
        return []
    except Exception as e:
        logger.error(f"Failed to read agents from {file_path}: {str(e)}", exc_info=True)
        return []

def write_agents(agents: list, file_path: str = AGENTS_JSON_FILE):
    try:
        with open(file_path, 'w') as file:
            json.dump(agents, file, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to write agents to {file_path}: {str(e)}", exc_info=True)
        return False

def get_agent_by_id(agent_id: str, file_path: str = AGENTS_JSON_FILE) -> dict:
    agents = read_agents(file_path)
    for agent in agents:
        if agent.get("id") == agent_id:
            return agent
    return None

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
        agents = read_agents()
        return templates.TemplateResponse("agents.html", {"request": request, "agents": agents, "success": request.session.pop("success", None)})
    except Exception as e:
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
        agents = read_agents()
        agent_dict = agent_data.dict()
        agent_dict["id"] = str(uuid.uuid4())
        agents.append(agent_dict)
        if write_agents(agents):
            return {"status": "success", "message": "Agent created successfully"}
        else:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to save agent to file"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to create agent: {str(e)}"})

@app.post("/update-agent/{agent_id}", response_class=JSONResponse)
async def update_agent(agent_id: str, name: str = Form(...), system_message: str = Form(...), initial_message: str = Form(...), voice_model: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        agent_data = AgentCreate(name=name, system_message=system_message, initial_message=initial_message, voice_model=voice_model)
        agents = read_agents()
        for agent in agents:
            if agent.get("id") == agent_id:
                agent.update(agent_data.dict())
                agent["id"] = agent_id
                if write_agents(agents):
                    return {"status": "success", "message": "Agent updated successfully"}
                else:
                    return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to save agent to file"})
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Agent {agent_id} not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to update agent: {str(e)}"})

@app.post("/delete-agent/{agent_id}", response_class=JSONResponse)
async def delete_agent(agent_id: str, current_user: str = Depends(get_current_user)):
    try:
        agents = read_agents()
        updated_agents = [agent for agent in agents if agent.get("id") != agent_id]
        if len(updated_agents) == len(agents):
            return JSONResponse(status_code=404, content={"status": "error", "message": f"Agent {agent_id} not found"})
        if write_agents(updated_agents):
            return {"status": "success", "message": "Agent deleted successfully"}
        else:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Failed to delete agent from file"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Failed to delete agent: {str(e)}"})

@app.get("/assign-agent", response_class=HTMLResponse)
async def assign_agent_page(request: Request, current_user: str = Depends(get_current_user)):
    try:
        agents = read_agents()
        current_agent_id = os.getenv("AGENT_ID", "1")
        return templates.TemplateResponse("assign_agent.html", {"request": request, "agents": agents, "error": None, "current_agent_id": current_agent_id})
    except Exception as e:
        return templates.TemplateResponse("assign_agent.html", {"request": request, "agents": [], "error": f"Failed to fetch agents: {str(e)}", "current_agent_id": os.getenv("AGENT_ID", "1")})

@app.post("/assign-agent", response_class=JSONResponse)
async def assign_agent(request: Request, agent_id: str = Form(...), current_user: str = Depends(get_current_user)):
    try:
        agent_data = get_agent_by_id(agent_id)
        if not agent_data:
            return JSONResponse(status_code=404, content={"status": "error", "message": f"Agent {agent_id} not found"})
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
    except Exception as e:
        logger.error(f"Unexpected error in assign_agent for agent {agent_id}: {str(e)}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": "An unexpected error occurred"})

@app.get("/current-agent")
async def get_current_agent():
    try:
        agent_id = os.getenv("AGENT_ID", "1")
        agent_data = get_agent_by_id(agent_id)
        if not agent_data:
            return {"error": f"Agent {agent_id} not found", "agent_id": agent_id}
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
    interaction_count = 1
    start_time = datetime.now()
    tasks = []
    max_reconnect_attempts = 3
    reconnect_attempts = 0

    async def reconnect_transcription_service():
        nonlocal reconnect_attempts
        if not stream_service.active or websocket.application_state == WebSocketState.DISCONNECTED:
            logger.info(f"Skipping Deepgram reconnection for stream {transcription_service.get_stream_sid()}: Stream inactive or WebSocket disconnected")
            return False
        if reconnect_attempts >= max_reconnect_attempts:
            logger.error(f"Max reconnection attempts ({max_reconnect_attempts}) reached for stream {transcription_service.get_stream_sid()}")
            return False
        try:
            logger.info(f"Attempting to reconnect to Deepgram for stream {transcription_service.get_stream_sid()}, attempt {reconnect_attempts + 1}")
            await transcription_service.connect()
            transcription_service.on('utterance', handle_utterance)
            transcription_service.on('transcription', handle_transcription)
            transcription_service.on('error', handle_transcription_error)
            transcription_service.on('close', handle_transcription_close)
            reconnect_attempts = 0
            logger.info(f"Reconnected to Deepgram for stream {transcription_service.get_stream_sid()}")
            return True
        except Exception as e:
            reconnect_attempts += 1
            logger.error(f"Failed to reconnect to Deepgram for stream {transcription_service.get_stream_sid()}: {str(e)}", exc_info=True)
            return False

    async def process_media(msg):
        try:
            stream_sid = msg.get('streamSid', 'unknown')
            if 'media' not in msg or 'payload' not in msg['media']:
                logger.warning(f"Invalid media message format for stream {stream_sid}: {json.dumps(msg, indent=2)}")
                return
            payload = base64.b64decode(msg['media']['payload'])
            if not payload:
                logger.warning(f"Empty media payload received for stream {stream_sid}, chunk: {msg['media'].get('chunk', 'unknown')}")
                return
            logger.debug(f"Received media payload for stream {stream_sid}, length: {len(payload)}, chunk: {msg['media'].get('chunk', 'unknown')}")
            stream_service._last_media_received = asyncio.get_event_loop().time()
            if not transcription_service.is_connected:
                if not await reconnect_transcription_service():
                    logger.error(f"Cannot send audio: Deepgram reconnection failed for stream {stream_sid}")
                    return
            await transcription_service.send(payload)
        except base64.binascii.Error as e:
            logger.error(f"Invalid base64 payload for stream {stream_sid}: {str(e)}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing media for stream {stream_sid}: {str(e)}", exc_info=True)

    async def handle_transcription(text):
        nonlocal interaction_count
        if not text:
            logger.debug(f"Empty transcription received for stream {stream_service.stream_sid}")
            return
        logger.info(f"Interaction {interaction_count} – STT -> LLM: {text}")
        await llm_service.completion(text, interaction_count)
        interaction_count += 1

    async def handle_llm_reply(llm_reply, icount):
        try:
            if not stream_service.active or websocket.application_state == WebSocketState.DISCONNECTED:
                logger.warning(f"Skipping LLM reply for interaction {icount} and stream {stream_service.stream_sid}: Stream inactive or WebSocket disconnected")
                return
            logger.info(f"Interaction {icount}: LLM -> TTS: {llm_reply['partialResponse']}")
            await tts_service.generate(llm_reply, interaction_count)
        except Exception as e:
            logger.error(f"Error in handle_llm_reply for stream {stream_service.stream_sid}: {str(e)}", exc_info=True)

    async def handle_speech(partial_response_index, audio_base64, text, interaction_count):
        logger.debug(f"Handling speech event: index={partial_response_index}, text={text}, interaction={interaction_count}")
        await stream_service.send_audio(audio_base64)

    async def handle_audio_sent(chunk_sequence):
        marks.append(f"chunk-{chunk_sequence}")
        logger.debug(f"Mark chunk-{chunk_sequence} added to queue for stream {stream_service.stream_sid}")

    async def handle_utterance(text, stream_sid):
        try:
            if len(marks) > 0 and text.strip():
                logger.info(f"Interruption detected for stream {stream_sid}, sending clear signal")
                if hasattr(tts_service, "stop"):
                    await tts_service.stop()
                    logger.info("Stopped ongoing TTS due to user interruption")
                await stream_service.send_clear_signal()
                stream_service.reset()
                llm_service.reset()
            else:
                logger.debug(f"No interruption detected for stream {stream_sid}, marks: {len(marks)}, text: '{text}'")
        except Exception as e:
            logger.error(f"Error in handle_utterance: {e}", exc_info=True)

    async def handle_transcription_error(error):
        logger.error(f"Transcription error for stream {transcription_service.get_stream_sid()}: {error}")
        if not stream_service.active or websocket.application_state == WebSocketState.DISCONNECTED:
            logger.info(f"Skipping Deepgram reconnection on error for stream {transcription_service.get_stream_sid()}: Stream inactive or WebSocket disconnected")
            return
        if not await reconnect_transcription_service():
            logger.error(f"Failed to reconnect after transcription error for stream {transcription_service.get_stream_sid()}")
            stream_service.stop()
            await websocket.close()

    async def handle_transcription_close(close):
        logger.info(f"Transcription closed for stream {transcription_service.get_stream_sid()}")
        if not stream_service.active or websocket.application_state == WebSocketState.DISCONNECTED:
            logger.info(f"Skipping Deepgram reconnection on close for stream {transcription_service.get_stream_sid()}: Stream inactive or WebSocket disconnected")
            return
        if not await reconnect_transcription_service():
            logger.error(f"Failed to reconnect after transcription close for stream {transcription_service.get_stream_sid()}")
            stream_service.stop()
            await websocket.close()

    transcription_service.on('utterance', handle_utterance)
    transcription_service.on('transcription', handle_transcription)
    transcription_service.on('error', handle_transcription_error)
    transcription_service.on('close', handle_transcription_close)
    llm_service.on('llmreply', handle_llm_reply)
    tts_service.on('speech', handle_speech)
    stream_service.on('audiosent', handle_audio_sent)
    message_queue = asyncio.Queue()

    async def websocket_listener():
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                await message_queue.put(msg)
                if msg.get('event') == 'pong':
                    logger.debug(f"Received pong for stream {msg.get('streamSid', 'unknown')}")
        except WebSocketDisconnect as e:
            logger.info(f"WebSocket disconnected for stream {stream_service.stream_sid}: code={e.code}, reason={e.reason}")
            stream_service.deactivate()
        except Exception as e:
            logger.error(f"WebSocket listener error for stream {stream_service.stream_sid}: {str(e)}", exc_info=True)
            stream_service.deactivate()

    async def message_processor():
        nonlocal start_time
        while True:
            msg = await message_queue.get()
            logger.debug(f"Processing message for stream {msg.get('streamSid', 'unknown')}: {json.dumps(msg, indent=2)}")
            try:
                if msg['event'] == 'connected':
                    logger.info("Received 'connected' event, sending acknowledgment")
                    await websocket.send_json({
                        "event": "connected",
                        "protocol": "Call",
                        "version": "1.0.0"
                    })
                elif msg['event'] == 'start':
                    start_time = datetime.now()
                    logger.debug(f"WebSocket Start Message: {json.dumps(msg['start'], indent=2)}")
                    logger.info(f"Call started at {start_time.isoformat()}")
                    stream_sid = msg['start']['streamSid']
                    start_call_sid = msg['start']['callSid']
                    logger.info(f"Extracted start callSid: {start_call_sid}")
                    logger.debug(f"Full start message: {json.dumps(msg['start'], indent=2)}")
                    stream_data = stream_status_data.get(stream_sid, {})
                    call_id = None
                    call_context = None
                    max_retries = 5
                    retry_delay = 1.0
                    for attempt in range(max_retries):
                        logger.debug(f"call_contexts state: { {k: v.to_dict() for k, v in call_contexts.items()} }")
                        for cid, ctx in call_contexts.items():
                            if ctx.session == start_call_sid:
                                call_id = cid
                                call_context = ctx
                                logger.info(f"Matched as session token: call_id={call_id}, session={start_call_sid}")
                                break
                        if not call_context and start_call_sid in call_contexts:
                            call_context = call_contexts[start_call_sid]
                            call_id = start_call_sid
                            logger.info(f"Matched as call_id: call_id={call_id}, session={call_context.session}")
                        if call_context:
                            break
                        logger.debug(f"Attempt {attempt + 1}/{max_retries}: No CallContext found for start_call_sid {start_call_sid}, retrying in {retry_delay}s")
                        await asyncio.sleep(retry_delay)
                    
                    if not call_context:
                        logger.warning(f"No CallContext found for start_call_sid {start_call_sid} after {max_retries} retries, creating new CallContext")
                        call_context = CallContext()
                        call_context.session = start_call_sid
                        call_context.call_sid = start_call_sid
                        call_contexts[start_call_sid] = call_context
                        call_id = start_call_sid
                    else:
                        logger.info(f"Found CallContext for call_id: {call_id} with session: {call_context.session}")

                    call_context.stream_sid = stream_sid
                    call_context.start_time = msg['start'].get('Timestamp') or datetime.now().isoformat()
                    
                    current_first_name = getattr(call_context, 'first_name', None)
                    logger.info(f"Current first_name in call_context: {current_first_name}")
                    
                    if not current_first_name:
                        if 'start' in msg and 'customParameters' in msg['start']:
                            custom_params = msg['start']['customParameters']
                            if 'firstName' in custom_params:
                                call_context.first_name = custom_params['firstName']
                                logger.info(f"Set first_name from customParameters: {call_context.first_name}")
                            elif 'First-Name' in custom_params:
                                call_context.first_name = custom_params['First-Name']
                                logger.info(f"Set first_name from customParameters (First-Name): {call_context.first_name}")
                        elif 'start' in msg and 'userData' in msg['start']:
                            user_data = msg['start']['userData']
                            if isinstance(user_data, dict) and 'firstName' in user_data:
                                call_context.first_name = user_data['firstName']
                                logger.info(f"Set first_name from userData: {call_context.first_name}")
                            elif isinstance(user_data, str):
                                try:
                                    parsed_data = json.loads(user_data)
                                    if 'firstName' in parsed_data:
                                        call_context.first_name = parsed_data['firstName']
                                        logger.info(f"Set first_name from parsed userData: {call_context.first_name}")
                                except json.JSONDecodeError:
                                    logger.warning("userData is not valid JSON")
                        if not getattr(call_context, 'first_name', None):
                            call_context.first_name = "Mamoon"
                            logger.warning(f"first_name not available from any source, using fallback: {call_context.first_name}")
                    
                    logger.info(f"Final first_name being used: {call_context.first_name}")
                    
                    agent_id = os.getenv("AGENT_ID", "1")
                    try:
                        agent_data = get_agent_by_id(agent_id)
                        if not agent_data:
                            logger.error(f"Agent {agent_id} not found in JSON file")
                            system_message = None
                            initial_message = None
                        else:
                            system_message = agent_data.get("system_message")
                            initial_message = agent_data.get("initial_message")
                            logger.info(f"Using agent {agent_id} from JSON file")
                    except Exception as e:
                        logger.error(f"Failed to fetch agent data for agent_id {agent_id}: {str(e)}", exc_info=True)
                        system_message = None
                        initial_message = None
                    
                    def replace_template_variables(text, context):
                        if not text:
                            return text
                        logger.debug(f"Before template replacement - text: {text}")
                        if hasattr(context, 'first_name') and context.first_name:
                            replaced_text = text.replace("{{First-Name}}", context.first_name)
                            logger.info(f"Successfully replaced {{First-Name}} with: {context.first_name}")
                            logger.debug(f"After replacement - text: {replaced_text}")
                            return replaced_text
                        else:
                            replaced_text = text.replace("{{First-Name}}", "").strip()
                            replaced_text = re.sub(r'\s+', ' ', replaced_text)
                            replaced_text = re.sub(r' ,', ',', replaced_text)
                            replaced_text = re.sub(r' \.', '.', replaced_text)
                            logger.warning("first_name not available, removed {{First-Name}} template")
                            return replaced_text
                    
                    if system_message:
                        original_system_msg = system_message
                        system_message = replace_template_variables(system_message, call_context)
                        if original_system_msg != system_message:
                            logger.info(f"System message updated with first_name: {system_message}")
                        else:
                            logger.info("No template variables found in system message")
                    
                    if initial_message:
                        original_initial_msg = initial_message
                        initial_message = replace_template_variables(initial_message, call_context)
                        if original_initial_msg != initial_message:
                            logger.info(f"Initial message updated with first_name: {initial_message}")
                        else:
                            logger.info("No template variables found in initial message")
                    
                    call_context.system_message = system_message
                    call_context.initial_message = initial_message
                    call_contexts[call_id] = call_context
                    
                    llm_service.set_call_context(call_context)
                    stream_service.set_stream_sid(stream_sid)
                    transcription_service.set_stream_sid(stream_sid)
                    logger.info(f"Cloudonix -> Starting Media Stream for {stream_sid} (session: {call_context.session}, call_id: {call_id})")
                    
                    if not initial_message or not initial_message.strip():
                        logger.info(f"Empty or missing initial_message for agent {agent_id}")
                        if system_message is None:
                            logger.error(f"No system message defined for agent {agent_id}, cannot proceed")
                            await tts_service.generate({"partialResponseIndex": None, "partialResponse": "Error: No system message defined"}, 1)
                        else:
                            logger.info(f"Triggering LLM with 'Hello' for agent {agent_id}")
                            await llm_service.completion("Hello", interaction_count=1)
                    else:
                        logger.info(f"Sending initial_message to TTS: {initial_message}")
                        await tts_service.generate({"partialResponseIndex": None, "partialResponse": initial_message}, 1)
                elif msg['event'] == 'media':
                    logger.debug(f"Processing media message for stream {msg.get('streamSid', 'unknown')}")
                    asyncio.create_task(process_media(msg))
                elif msg['event'] == 'mark':
                    label = msg['mark']['name']
                    if label in marks:
                        marks.remove(label)
                        logger.debug(f"Mark {label} removed from queue for stream {msg.get('streamSid', 'unknown')}")
                    else:
                        logger.warning(f"Received mark {label} not found in queue for stream {msg.get('streamSid', 'unknown')}")
                elif msg['event'] == 'stop':
                    duration = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Cloudonix -> Media stream {msg.get('streamSid', 'unknown')} ended after {duration} seconds. Stop event received.")
                    call_context.final_status = "stopped"
                    if call_id in call_contexts:
                        del call_contexts[call_id]
                    stream_service.stop()
                    await websocket.close()
                    break
                elif msg['event'] == 'dtmf':
                    logger.info(f"Received DTMF event for stream {msg.get('streamSid', 'unknown')}: {msg['dtmf']['digit']}")
                else:
                    logger.warning(f"Unknown message event: {msg.get('event')} for stream {msg.get('streamSid', 'unknown')}")
            except Exception as e:
                logger.error(f"Error processing message for stream {msg.get('streamSid', 'unknown')}: {str(e)}", exc_info=True)
            message_queue.task_done()

    async def periodic_health_check():
        failure_count = 0
        max_failures = 5
        while stream_service.active:
            try:
                if not await stream_service.health_check():
                    failure_count += 1
                    logger.warning(f"Health check failed for stream {stream_service.stream_sid} ({failure_count}/{max_failures})")
                    if failure_count >= max_failures:
                        logger.error(f"Max health check failures reached for stream {stream_service.stream_sid}, stopping stream")
                        stream_service.stop()
                        await websocket.close()
                        break
                else:
                    failure_count = 0
                if not transcription_service.is_connected and stream_service.active and websocket.application_state != WebSocketState.DISCONNECTED:
                    if not await reconnect_transcription_service():
                        logger.error(f"Max reconnection attempts reached, stopping stream {stream_service.stream_sid}")
                        stream_service.stop()
                        await websocket.close()
                        break
                logger.debug(f"Stream status for {stream_service.stream_sid}: active={stream_service.active}, WebSocket state={websocket.application_state}, Transcription connected={transcription_service.is_connected}")
            except Exception as e:
                logger.error(f"Health check error for stream {stream_service.stream_sid}: {str(e)}", exc_info=True)
                failure_count += 1
                if failure_count >= max_failures:
                    logger.error(f"Max health check errors reached for stream {stream_service.stream_sid}, stopping stream")
                    stream_service.stop()
                    await websocket.close()
                    break
            await asyncio.sleep(5)

    try:
        await transcription_service.connect()
        listener_task = asyncio.create_task(websocket_listener())
        processor_task = asyncio.create_task(message_processor())
        health_check_task = asyncio.create_task(periodic_health_check())
        tasks = [listener_task, processor_task, health_check_task]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"WebSocket error for stream {stream_service.stream_sid}: {str(e)}", exc_info=True)
        stream_service.stop()
        await websocket.close()
    finally:
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Cleaning up WebSocket connection for stream {stream_service.stream_sid}. Duration: {duration} seconds")
        logger.debug(f"Final stream status: active={stream_service.active}, WebSocket state={websocket.application_state}, Active tasks: {len(tasks)}")
        logger.debug(f"Call contexts: {len(call_contexts)}, Marks queue: {len(marks)}")
        await transcription_service.disconnect()
        stream_service.stop()
        tts_service.stop()
        llm_service.reset()
        for task in tasks:
            task.cancel()
        if websocket.application_state != WebSocketState.DISCONNECTED:
            await websocket.close()
        logger.info(f"WebSocket endpoint cleanup completed for stream {stream_service.stream_sid}")

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