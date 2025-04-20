import asyncio
import websockets
import json
import time
from typing import Dict, Any

class WebSocketTester:
    def __init__(self, uri: str = "ws://localhost:8000/ws/transcription"):
        self.uri = uri
        self.websocket = None

    async def connect(self):
        self.websocket = await websockets.connect(self.uri)
        print("Connected to WebSocket server")

    async def send_message(self, data: Dict[str, Any]):
        if not self.websocket:
            await self.connect()
        print(f"Sending data: {data}")
        await self.websocket.send(json.dumps(data))
        try:
            response = await self.websocket.recv()
            print(f"Received response: {response}")
            return response
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
            return None

    async def test_named_entity(self):
        data = {
            "type": "named_entity_recognition",
            "data": {
                "results": [
                    {
                        "text": "OpenAI",
                        "entity_type": "ORG",
                    },
                    {
                        "text": "San Francisco",
                        "entity_type": "LOC",
                    }
                ]
            },
            "timestamp": int(time.time() * 1000)
        }
        return await self.send_message(data)

    async def test_sentiment(self):
        data = {
            "type": "sentiment",
            "data": {
                "sentiment": {
                    "label": "POSITIVE",
                    "score": 0.95
                }
            },
            "timestamp": int(time.time() * 1000)
        }
        return await self.send_message(data)

    async def test_transcript(self):
        data = {
            "type": "transcript",
            "text": "This is a test transcript",
            "timestamp": int(time.time() * 1000)
        }
        return await self.send_message(data)

    async def test_final_transcript(self):
        data = {
            "type": "post_final_transcript",
            "text": "This is a final test transcript",
            "timestamp": int(time.time() * 1000),
            "stream_key": "test-stream"
        }
        return await self.send_message(data)

    async def run_all_tests(self):
        try:
            print("\n=== Testing Named Entity Recognition ===")
            await self.test_named_entity()
            await asyncio.sleep(1)  # Wait for processing

            print("\n=== Testing Sentiment Analysis ===")
            await self.test_sentiment()
            await asyncio.sleep(1)

            print("\n=== Testing Partial Transcript ===")
            await self.test_transcript()
            await asyncio.sleep(1)

            print("\n=== Testing Final Transcript ===")
            await self.test_final_transcript()
            await asyncio.sleep(1)

        except Exception as e:
            print(f"Error during tests: {e}")
        finally:
            if self.websocket:
                await self.websocket.close()

async def main():
    tester = WebSocketTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 