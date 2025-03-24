import asyncio
import os
import logging
import websockets
import json
import requests
from io import BytesIO
import wave
import audioop
import ffmpeg
import tempfile

from pyrtmp import StreamClosedException
from pyrtmp.flv import FLVFileWriter, FLVMediaType
from pyrtmp.session_manager import SessionManager
from pyrtmp.rtmp import SimpleRTMPController, RTMPProtocol, SimpleRTMPServer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class GladiaTranscriber:
    def __init__(self, api_key):
        self.api_key = api_key
        self.ws = None
        self.session_id = None
        self.temp_dir = tempfile.mkdtemp()
        self.chunk_counter = 0
        self.audio_buffer = []
        self.buffer_size = 0
        self.max_buffer_size = 4096  # Buffer up to 4KB of audio before processing
        
    async def start_session(self):
        url = "https://api.gladia.io/v2/live"
        headers = {
            "x-gladia-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "encoding": "wav/pcm",
            "bit_depth": 16,
            "sample_rate": 16000,
            "channels": 1,
            "model": "accurate",
            "messages_config": {
                "receive_partial_transcripts": True,
                "receive_final_transcripts": True
            }
        }
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 201:
            raise Exception(f"Failed to start Gladia session: {response.text}")
            
        data = response.json()
        self.session_id = data["id"]
        self.ws = await websockets.connect(data["url"])
        
    async def process_audio(self, audio_data):
        if not self.ws:
            await self.start_session()
        
        # Add to buffer
        self.audio_buffer.append(audio_data)
        self.buffer_size += len(audio_data)
        
        # Process if buffer is full
        if self.buffer_size >= self.max_buffer_size:
            # Concatenate all buffered audio
            combined_audio = b''.join(self.audio_buffer)
            pcm_data = await self._convert_to_pcm(combined_audio)
            
            # Clear buffer
            self.audio_buffer = []
            self.buffer_size = 0
            
            if pcm_data:
                await self.ws.send(pcm_data)
                response = await self.ws.recv()
                transcript = json.loads(response)
                if "transcription" in transcript:
                    logger.info(f"Transcription: {transcript['transcription']}")
            
            # Add a small delay to avoid overwhelming the system
            await asyncio.sleep(0.01)  # 10ms delay
            
    async def _convert_to_pcm(self, audio_data):
        try:
            # Write AAC data to temporary file
            self.chunk_counter += 1
            aac_path = os.path.join(self.temp_dir, f"chunk_{self.chunk_counter}.aac")
            pcm_path = os.path.join(self.temp_dir, f"chunk_{self.chunk_counter}.pcm")
            
            # Write AAC data with ADTS header
            # AAC-LC, 44.1kHz, stereo
            adts_header = bytes([
                0xFF, 0xF1,  # Sync word + MPEG-4 + Layer + Protection absent
                0x50,        # AAC-LC + 44.1kHz + Private bit
                0x80,        # Channel config (stereo) + Original + Home + Copyright ID bit + Copyright ID start
                0x00,        # Frame length will be updated
                0xFC, 0x00   # Buffer fullness + Number of AAC frames - 1
            ])
            
            frame_length = len(audio_data) + len(adts_header)
            adts_header = bytearray(adts_header)
            adts_header[3] |= (frame_length >> 11) & 0x03
            adts_header[4] = (frame_length >> 3) & 0xFF
            adts_header[5] = ((frame_length & 0x07) << 5) | 0x1F
            
            with open(aac_path, 'wb') as f:
                f.write(bytes(adts_header))
                f.write(audio_data)
            
            # Convert AAC to PCM using ffmpeg with explicit format
            process = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-f', 'aac',  # Force AAC format
                '-i', aac_path,
                '-f', 's16le',
                '-acodec', 'pcm_s16le',
                '-ac', '1',
                '-ar', '16000',
                '-y',  # Overwrite output file
                pcm_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for the conversion to complete
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg conversion failed: {stderr.decode()}")
                return None
                
            # Read PCM data
            with open(pcm_path, 'rb') as f:
                pcm_data = f.read()
            
            # Cleanup temporary files
            try:
                os.remove(aac_path)
                os.remove(pcm_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp files: {e}")
            
            return pcm_data
        except Exception as e:
            logger.error(f"Failed to convert audio: {e}")
            return None
        
    async def close(self):
        # Process any remaining buffered audio
        if self.audio_buffer:
            combined_audio = b''.join(self.audio_buffer)
            pcm_data = await self._convert_to_pcm(combined_audio)
            if pcm_data and self.ws:
                await self.ws.send(pcm_data)
                response = await self.ws.recv()
                transcript = json.loads(response)
                if "transcription" in transcript:
                    logger.info(f"Final transcription: {transcript['transcription']}")
        
        if self.ws:
            await self.ws.close()
        try:
            os.rmdir(self.temp_dir)
        except:
            pass

class RTMP2FLVController(SimpleRTMPController):

    def __init__(self, output_directory: str, gladia_api_key: str, webhook_url: str = "http://localhost:8000/webhook"):
        self.output_directory = output_directory
        self.transcriber = GladiaTranscriber(gladia_api_key)
        self.webhook_url = webhook_url
        super().__init__()

    async def on_ns_publish(self, session, message) -> None:
        publishing_name = message.publishing_name
        file_path = os.path.join(self.output_directory, f"{publishing_name}.flv")
        session.state = FLVFileWriter(output=file_path)
        
        # Call webhook
        try:
            webhook_data = {
                "event_type": "stream_start",
                "stream_key": publishing_name,
                "metadata": {
                    "file_path": file_path,
                    "timestamp": message.timestamp if hasattr(message, 'timestamp') else None
                }
            }
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(self.webhook_url, json=webhook_data)
            )
            if response.status_code != 200:
                logger.error(f"Failed to call webhook: {response.text}")
        except Exception as e:
            logger.error(f"Failed to call webhook: {e}")
        
        await super().on_ns_publish(session, message)

    async def on_metadata(self, session, message) -> None:
        session.state.write(0, message.to_raw_meta(), FLVMediaType.OBJECT)
        await super().on_metadata(session, message)

    async def on_video_message(self, session, message) -> None:
        session.state.write(message.timestamp, message.payload, FLVMediaType.VIDEO)
        await super().on_video_message(session, message)

    async def on_audio_message(self, session, message) -> None:
        session.state.write(message.timestamp, message.payload, FLVMediaType.AUDIO)
        # Send audio to Gladia for transcription
        try:
            await self.transcriber.process_audio(message.payload)
        except Exception as e:
            logger.error(f"Failed to transcribe audio: {e}")
        await super().on_audio_message(session, message)

    async def on_stream_closed(self, session: SessionManager, exception: StreamClosedException) -> None:
        session.state.close()
        await self.transcriber.close()
        await super().on_stream_closed(session, exception)


class SimpleServer(SimpleRTMPServer):

    def __init__(self, output_directory: str, gladia_api_key: str, webhook_url: str = "http://localhost:8000/webhook"):
        self.output_directory = output_directory
        self.gladia_api_key = gladia_api_key
        self.webhook_url = webhook_url
        super().__init__()

    async def create(self, host: str, port: int):
        loop = asyncio.get_event_loop()
        self.server = await loop.create_server(
            lambda: RTMPProtocol(controller=RTMP2FLVController(
                self.output_directory,
                self.gladia_api_key,
                self.webhook_url
            )),
            host=host,
            port=port,
        )


async def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    gladia_api_key = os.getenv("GLADIA_API_KEY")
    webhook_url = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhook")
    
    if not gladia_api_key:
        raise ValueError("GLADIA_API_KEY environment variable is required")
        
    server = SimpleServer(
        output_directory=current_dir,
        gladia_api_key=gladia_api_key,
        webhook_url=webhook_url
    )
    await server.create(host='0.0.0.0', port=1935)
    await server.start()
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())