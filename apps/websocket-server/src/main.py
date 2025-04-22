import os
import json
import logging
from typing import List
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, APIRouter, Form
from fastapi.middleware.cors import CORSMiddleware
from .api import MastraAPI, DocumentProcessor

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize document processor
document_processor = None

def get_document_processor():
    global document_processor
    return document_processor

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize document processor
    global document_processor
    try:
        document_processor = DocumentProcessor()
        logger.info("Document processor initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize document processor: {e}", exc_info=True)
        document_processor = None
    yield
    # Cleanup
    document_processor = None

app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create main router
main_router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.mastra_api = MastraAPI()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
        # Close API session when all connections are closed
        if not self.active_connections:
            await self.mastra_api.close()

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
                logger.info(f"Processing entity: {entity_text} ({entity_type})")
                
                if entity_text and entity_type:
                    # Give the agent context about what was mentioned
                    message = f"Someone mentioned {entity_type} '{entity_text}' in their stream. Send a tweet about this."
                    logger.info(f"Sending to agent: {message}")
                    
                    response = await self.mastra_api.send_message(message)
                    logger.info(f"Raw agent response: {json.dumps(response, indent=2)}")
                    
                    if not response:
                        logger.error("Agent returned empty response")
                        continue
                        
                    if isinstance(response, dict):
                        logger.info(f"Agent response structure: {list(response.keys())}")
                    
                    logger.info(f"Processed entity: {entity_text} ({entity_type})")
            except Exception as e:
                logger.error(f"Error handling entity: {e}", exc_info=True)

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

@main_router.post("/webhook")
async def webhook(data: dict):
    """Webhook endpoint for RTMP events"""
    logger.info(f"Received webhook: {data}")
    return {"status": "ok"}

@main_router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    logger.info("Health check requested")
    return {"status": "ok", "service": "websocket-server"}

@main_router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), user_id: str = Form(...)):
    """Upload and process a document (PDF, DOCX, or LaTeX)"""
    logger.info(f"Received upload request for file: {file.filename} from user: {user_id}")
    processor = get_document_processor()
    if not processor:
        logger.error("Document processor not initialized")
        raise HTTPException(status_code=500, detail="Document processor not initialized")
    try:
        logger.info("Processing document...")
        result = await processor.process_document(file, user_id)
        logger.info(f"Document processed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@main_router.get("/documents")
async def get_documents(user_id: str):
    """Get all documents for a user"""
    processor = get_document_processor()
    if not processor:
        raise HTTPException(status_code=500, detail="Document processor not initialized")
    try:
        documents = await processor.get_user_documents(user_id)
        return {"documents": documents}
    except Exception as e:
        logger.error(f"Error retrieving documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@main_router.get("/documents/{document_id}")
async def get_document_status(document_id: str):
    """Get the status and content of a processed document"""
    processor = get_document_processor()
    if not processor:
        raise HTTPException(status_code=500, detail="Document processor not initialized")
    try:
        document = await processor.get_document_by_id(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except Exception as e:
        logger.error(f"Error retrieving document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@main_router.patch("/documents/{document_id}")
async def update_document(document_id: str, updates: dict):
    """Update a document's metadata"""
    processor = get_document_processor()
    if not processor:
        raise HTTPException(status_code=500, detail="Document processor not initialized")
    try:
        document = await processor.update_document(document_id, updates)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except Exception as e:
        logger.error(f"Error updating document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@main_router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document and its associated data"""
    processor = get_document_processor()
    if not processor:
        raise HTTPException(status_code=500, detail="Document processor not initialized")
    try:
        success = await processor.delete_document(document_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"status": "success", "message": "Document deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Include main router
app.include_router(main_router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port) 