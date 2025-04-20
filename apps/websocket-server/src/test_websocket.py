import asyncio
import websockets
import json
import time

async def test_named_entity():
    # Connect to the WebSocket server
    uri = "ws://localhost:8000/ws/transcription"
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket server")

        # Example named entity data
        test_data = {
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

        # Send the test data
        print("Sending test data:", test_data)
        await websocket.send(json.dumps(test_data))

        # Wait for response
        try:
            while True:
                response = await websocket.recv()
                print("Received response:", response)
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")

if __name__ == "__main__":
    asyncio.run(test_named_entity()) 