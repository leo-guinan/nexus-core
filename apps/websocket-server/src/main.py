import os
import json
import logging
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from .api import MastraAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.mastra_api = MastraAPI()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        # Broadcast to all connected clients
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")

    async def handle_named_entities(self, entities: List[dict]):
        logger.info(f"Handling named entities: {entities}")
        for entity in entities:
            try:
                # Extract entity text and type
                entity_text = entity.get("text", "")
                entity_type = entity.get("entity_type", "")
                print(f"Entity text: {entity_text}, Entity type: {entity_type}")
                if entity_text and entity_type:
                    # Tweet about the entity
                    response = await self.mastra_api.send_message("Leo mentioned an entity")
                    logger.info(f"Tweeted about entity: {entity_text} ({entity_type})")
                    logger.debug(f"Tweet response: {response}")
            except Exception as e:
                logger.error(f"Error tweeting about entity: {e}")

    async def handle_final_transcript(self, text: str, timestamp: int, stream_key: str):
        try:
            # Trigger the transcript workflow
            response = await self.mastra_api.trigger_transcript_workflow(text, timestamp, stream_key)
            logger.info(f"Triggered transcript workflow: {response}")
        except Exception as e:
            logger.error(f"Error triggering transcript workflow: {e}")

manager = ConnectionManager()

@app.websocket("/ws/transcription")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    print("Connected to transcription websocket")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                message_type = message.get("type", "unknown")
                print(f"Received message: {message}")
                if message_type == "transcript":
                    await manager.broadcast(json.dumps({
                        "type": "partial_transcript",
                        "text": message.get("text", ""),
                        "timestamp": message.get("timestamp")
                    }))
                elif message_type == "post_final_transcript":
                    text = message.get("text", "")
                    timestamp = message.get("timestamp")
                    stream_key = message.get("stream_key", "unknown")
                    
                    await manager.handle_final_transcript(text, timestamp, stream_key)
                    await manager.broadcast(json.dumps({
                        "type": "final_transcript",
                        "text": text,
                        "timestamp": timestamp
                    }))
                elif message_type == "named_entity_recognition":
                    entities = message.get("data", {}).get("results", [])
                    await manager.handle_named_entities(entities)
                    await manager.broadcast(json.dumps({
                        "type": "named_entities",
                        "entities": entities,
                        "timestamp": message.get("timestamp")
                    }))
                elif message_type == "sentiment":
                    await manager.broadcast(json.dumps({
                        "type": "sentiment",
                        "sentiment": message.get("data", {}).get("sentiment", {}),
                        "timestamp": message.get("timestamp")
                    }))
                else:
                    await manager.broadcast(data)
            except json.JSONDecodeError:
                await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/webhook")
async def webhook(data: dict):
    """Webhook endpoint for RTMP events"""
    logger.info(f"Received webhook: {data}")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port) 