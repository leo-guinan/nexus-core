from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
import asyncio
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class StreamEvent(BaseModel):
    event_type: str
    stream_key: str
    metadata: Optional[Dict[str, Any]] = None

async def handle_stream_start(event: StreamEvent):
    """
    Handle stream start event. Add your custom logic here.
    For example:
    - Send notifications
    - Start recording
    - Update database
    - Call other services
    """
    logger.info(f"Stream started: {event.stream_key}")
    logger.info(f"Metadata: {event.metadata}")
    # Add your custom logic here

@app.post("/webhook")
async def webhook(event: StreamEvent, background_tasks: BackgroundTasks):
    if event.event_type == "stream_start":
        background_tasks.add_task(handle_stream_start, event)
        return {"status": "processing"}
    else:
        raise HTTPException(status_code=400, detail="Unsupported event type")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 