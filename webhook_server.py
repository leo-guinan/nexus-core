from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
import logging
import json
import asyncio
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Store active WebSocket connections
active_connections = []

@app.websocket("/ws/transcription")
async def transcription_websocket(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Receive transcription data
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Log transcription
            timestamp = datetime.fromtimestamp(message["timestamp"] / 1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            status = "FINAL" if message["is_final"] else "PARTIAL"
            logger.info(f"[{timestamp}] [{status}] {message['text']}")
            
            # Write to log file
            with open("transcriptions.log", "a") as f:
                f.write(f"[{timestamp}] [{status}] {message['text']}\n")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        active_connections.remove(websocket)
        await websocket.close()

@app.post("/webhook")
async def webhook(data: dict):
    if data.get("event_type") == "stream_start":
        logger.info(f"Stream started: {data.get('stream_key')}")
        logger.info(f"Metadata: {data.get('metadata')}")
    return JSONResponse(content={"status": "ok"})

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 