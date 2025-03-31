import aiohttp
import os
from typing import Dict, Any

class MastraAPI:
    def __init__(self):
        self.base_url = os.getenv("MASTRA_API_URL", "http://localhost:3001")
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def send_message(self, message): 
        url = f"{self.base_url}/api/agents/memeticMarketingAgent/generate"
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ]
        }
        async with self.session.post(url, json=payload) as response:
            return await response.json()

    async def tweet_entity(self, entity: str) -> Dict[str, Any]:
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}/api/tweet"
        payload = {
            "text": f"leo has mentioned an entity: {entity}"
        }
        
        async with self.session.post(url, json=payload) as response:
            return await response.json()

    async def trigger_transcript_workflow(self, text: str, timestamp: int, stream_key: str) -> Dict[str, Any]:
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}/api/workflows/transcript-workflow/trigger"
        payload = {
            "text": text,
            "timestamp": timestamp,
            "streamKey": stream_key
        }
        
        async with self.session.post(url, json=payload) as response:
            return await response.json() 