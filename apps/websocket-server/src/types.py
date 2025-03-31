from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, Field

class TranscriptionEventType(str, Enum):
    START = "start"
    TRANSCRIPT = "transcript"
    END = "end"

class TranscriptionData(BaseModel):
    text: Optional[str] = None
    confidence: Optional[float] = None
    is_final: Optional[bool] = None

class TranscriptionEvent(BaseModel):
    type: TranscriptionEventType
    stream_id: str = Field(..., alias="streamId")
    timestamp: float
    data: TranscriptionData

class TranscriptionRequest(BaseModel):
    event: TranscriptionEvent

class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

class Sentiment(BaseModel):
    score: float
    label: SentimentLabel

class TranscriptionData(BaseModel):
    transcript: str
    sentiment: Optional[Sentiment] = None

class TranscriptionResponse(BaseModel):
    success: bool
    data: Optional[TranscriptionData] = None
    error: Optional[str] = None

class WebSocketMessageType(str, Enum):
    TRANSCRIPTION_EVENT = "transcription_event"
    ERROR = "error"

class WebSocketMessage(BaseModel):
    type: WebSocketMessageType
    payload: Union[TranscriptionEvent, str] 