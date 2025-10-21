import asyncio
import os
import requests
import httpx
from logger_config import get_logger
from datetime import datetime

logger = get_logger("EndCallFunction")

active_hangups = set()

async def end_call(context, args):
    call_sid = context.call_sid
    session_id = getattr(context, 'session', None)
    domain_id = os.environ.get('CLOUDONIX_DOMAIN_ID')
    
    if context.call_ended:
        logger.info(f"Call {call_sid} already ended; skipping")
        return "Thank you for your order. Goodbye."
    
    if call_sid in active_hangups:
        logger.info(f"Hangup already in progress for call {call_sid}")
        return "Thank you for your order. Goodbye."
    
    if not domain_id:
        logger.error(f"CLOUDONIX_DOMAIN_ID not set in environment")
        return "Error: Cannot end call without domain ID. Goodbye."
    
    active_hangups.add(call_sid)
    try:
        cloudonix_api_key = os.environ.get('CLOUDONIX_API_KEY')
        if not cloudonix_api_key:
            raise ValueError("CLOUDONIX_API_KEY not set")
        
        # Query session ID if missing or invalid
        if not session_id or session_id == context.call_sid:
            logger.info(f"Querying session ID for call {call_sid}")
            api_url = f"https://api.cloudonix.io/customers/self/domains/{domain_id}/sessions?callSid={call_sid}"
            headers = {
                "Authorization": f"Bearer {cloudonix_api_key}",
                "Accept": "application/json"
            }
            try:
                response = requests.get(api_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    sessions = response.json()
                    if sessions and isinstance(sessions, list):
                        # Find session with matching callSid in profile.callId or profile.CID
                        for session in sessions:
                            profile = session.get('profile', {})
                            call_ids = profile.get('callId', []) if isinstance(profile, dict) else []
                            cid = profile.get('subscriber-sip-headers', {}).get('CID') if isinstance(profile, dict) else None
                            if call_sid in call_ids or session.get('token') == call_sid or cid == call_sid:
                                session_id = str(session['token'])
                                logger.info(f"Found session ID {session_id} for call {call_sid}")
                                context.session = session_id
                                break
                        else:
                            logger.warning(f"No session found for call {call_sid} in API response: {json.dumps(sessions, indent=2)}")
                    else:
                        logger.warning(f"Empty sessions response for call {call_sid}: {response.text}")
                else:
                    logger.warning(f"Session query failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.warning(f"Failed to query session ID: {str(e)}")
        
        # Try DELETE session API
        if session_id:
            api_url = f"https://api.cloudonix.io/customers/self/domains/{domain_id}/sessions/{session_id}"
            headers = {
                "Authorization": f"Bearer {cloudonix_api_key}",
                "Accept": "application/json"
            }
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.delete(api_url, headers=headers, timeout=15)
                    if response.status_code in [200, 204]:
                        logger.info(f"Call {call_sid} (session {session_id}) terminated via Cloudonix DELETE session API")
                        context.call_ended = True
                        context.end_time = datetime.now().isoformat()
                        context.final_status = "ended"
                        return "Thank you for your order. Goodbye."
                    else:
                        logger.warning(f"Session DELETE attempt {attempt + 1} failed for {call_sid}: {response.status_code} - {response.text}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                except requests.RequestException as e:
                    logger.warning(f"Session DELETE attempt {attempt + 1} failed for {call_sid}: {str(e)}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
        
        # Fallback to /stop_stream if no session or API fails
        logger.info(f"Falling back to /stop_stream for {call_sid}")
        server = os.environ.get('SERVER', 'callapi.vetaai.com')
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"https://{server}/stop_stream",
                    json={"call_sid": call_sid, "session": session_id or "unknown"},
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"Fallback: Sent stop_stream for {call_sid}")
                context.call_ended = True
                context.end_time = datetime.now().isoformat()
                context.final_status = "ended_fallback"
                return "Thank you for your order. Goodbye."
            except httpx.HTTPError as e:
                logger.error(f"Fallback /stop_stream failed for {call_sid}: {str(e)}")
                raise
        
    except Exception as e:
        logger.error(f"Failed to end call {call_sid} (session {session_id}): {str(e)}")
        return f"Error ending call. Goodbye."
    finally:
        active_hangups.discard(call_sid)