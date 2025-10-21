import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()
logger = logging.getLogger("uvicorn.error")


async def keep_alive(ws: WebSocket, interval: int = 20):
    """Send periodic ping frames to keep WebSocket alive."""
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.send_text(json.dumps({"type": "ping"}))
                logger.info("Sent ping to client")
            except Exception as e:
                logger.error(f"Ping failed, closing connection: {e}")
                break
    except asyncio.CancelledError:
        logger.info("Keep-alive task cancelled")


@app.websocket("/connection")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket connection opened")

    # Start keep-alive task
    keep_alive_task = asyncio.create_task(keep_alive(ws))

    try:
        while True:
            msg = await ws.receive_text()
            logger.info(f"Received message: {msg}")

            # Example: echo back the message
            await ws.send_text(f"Echo: {msg}")

    except WebSocketDisconnect:
        logger.warning("WebSocket disconnected by client")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")

    finally:
        keep_alive_task.cancel()
        logger.info("WebSocket connection closed")
