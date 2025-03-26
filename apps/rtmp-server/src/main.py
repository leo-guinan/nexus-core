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
import time

from pyrtmp import StreamClosedException
from pyrtmp.flv import FLVFileWriter, FLVMediaType
from pyrtmp.session_manager import SessionManager
from pyrtmp.rtmp import SimpleRTMPController, RTMPProtocol, SimpleRTMPServer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class GladiaTranscriber:
    def __init__(self, api_key, transcription_ws_url="ws://websocket:8000/ws/transcription"):
        self.api_key = api_key
        self.ws = None
        self.transcription_ws = None
        self.session_id = None
        self.temp_dir = tempfile.mkdtemp()
        self.chunk_counter = 0
        self.audio_buffer = []
        self.buffer_size = 0
        self.max_buffer_size = 4096  # Buffer up to 4KB of audio before processing
        self.aac_config = None  # Store AAC configuration
        self.transcription_ws_url = transcription_ws_url
        
    def set_aac_config(self, config):
        self.aac_config = config
        
    async def connect_transcription_ws(self):
        if not self.transcription_ws:
            try:
                self.transcription_ws = await websockets.connect(self.transcription_ws_url)
                logger.info("Connected to transcription WebSocket")
            except Exception as e:
                logger.error(f"Failed to connect to transcription WebSocket: {e}")
                
    async def send_transcription(self, text, is_final=False):
        if self.transcription_ws:
            try:
                message = {
                    "text": text,
                    "is_final": is_final,
                    "timestamp": int(time.time() * 1000)
                }
                await self.transcription_ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send transcription: {e}")
                # Try to reconnect
                await self.connect_transcription_ws()
        
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
            "pre_processing": {
                "audio_enhancer": True,
                "speech_threshold": 0.9
            },
            "realtime_processing": {
                "sentiment_analysis": True,
                "named_entity_recognition": True
            },
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
        
        if not self.transcription_ws:
            await self.connect_transcription_ws()
        
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
                
                # Handle different types of messages from Gladia
                if transcript.get("type") == "transcript":
                    text = transcript.get("data", {}).get("text", "")
                    await self.send_transcription(text, is_final=False)
                elif transcript.get("type") == "named_entity_recognition":
                    results = transcript.get("data", {}).get("results", {})
                    logger.info(f"Named entity recognition: {results}")
                    for result in results:
                        logger.info(f"Named entity recognition: {result.get('entity_type')}: {result.get('text')}")
                elif transcript.get("type") == "sentiment":
                    pass       
                elif transcript.get("type") == "post_final_transcript":
                    # final transcription
                    text = transcript.get("data", {}).get("text", "")
                    await self.send_transcription(text, is_final=True)
                    logger.info(f"Final transcription: {text}")

               
            # Add a small delay to avoid overwhelming the system
            await asyncio.sleep(0.01)  # 10ms delay
            
    async def _convert_to_pcm(self, audio_data):
        try:
            self.chunk_counter += 1
            aac_path = os.path.join(self.temp_dir, f"chunk_{self.chunk_counter}.aac")
            pcm_path = os.path.join(self.temp_dir, f"chunk_{self.chunk_counter}.pcm")
            wav_path = os.path.join(self.temp_dir, f"chunk_{self.chunk_counter}.wav")
            
            # Write AAC data with ADTS header for each frame
            with open(aac_path, 'wb') as f:
                # Write AAC config if available
                if self.aac_config:
                    # ADTS header for config
                    config_header = bytearray([0xFF, 0xF1])  # Sync word, MPEG-4, Layer, Protection absent
                    config_header.append(((self.aac_config['profile'] - 1) << 6) | (self.aac_config['sampling_freq_index'] << 2) | ((self.aac_config['channels'] >> 2) & 0x01))
                    config_header.append(((self.aac_config['channels'] & 0x03) << 6) | ((9) >> 11))  # 9 is length of config
                    config_header.append((9 >> 3) & 0xFF)
                    config_header.append(((9 & 0x07) << 5) | 0x1F)
                    config_header.append(0xFC)
                    f.write(config_header)
                    f.write(self.aac_config['config'])
                
                # Write audio frame with ADTS header
                frame_len = len(audio_data) + 7  # ADTS header size
                header = bytearray([0xFF, 0xF1])  # Sync word, MPEG-4, Layer, Protection absent
                if self.aac_config:
                    header.append(((self.aac_config['profile'] - 1) << 6) | (self.aac_config['sampling_freq_index'] << 2) | ((self.aac_config['channels'] >> 2) & 0x01))
                    header.append(((self.aac_config['channels'] & 0x03) << 6) | ((frame_len) >> 11))
                else:
                    header.append(0x40)  # AAC-LC, 44.1kHz
                    header.append(0x20 | ((frame_len) >> 11))  # 2 channels
                header.append((frame_len >> 3) & 0xFF)
                header.append(((frame_len & 0x07) << 5) | 0x1F)
                header.append(0xFC)
                f.write(header)
                f.write(audio_data)
            
            # First convert to WAV to ensure proper format
            process = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-y',
                '-f', 'aac',
                '-acodec', 'aac',
                '-i', aac_path,
                '-acodec', 'pcm_s16le',
                '-f', 'wav',
                '-ac', '1',
                '-ar', '16000',
                wav_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg conversion to WAV failed: {stderr.decode()}")
                return None
            
            # Then convert WAV to raw PCM
            process = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-y',
                '-f', 'wav',
                '-i', wav_path,
                '-f', 's16le',
                '-acodec', 'pcm_s16le',
                pcm_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg conversion to PCM failed: {stderr.decode()}")
                return None
            
            try:
                with open(pcm_path, 'rb') as f:
                    pcm_data = f.read()
                return pcm_data if len(pcm_data) > 0 else None
            except FileNotFoundError:
                logger.error("PCM file not created")
                return None
            finally:
                # Cleanup temporary files
                for path in [aac_path, wav_path, pcm_path]:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp file {path}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to convert audio: {e}", exc_info=True)
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
                    text = transcript["transcription"]
                    await self.send_transcription(text, is_final=True)
                    logger.info(f"Final transcription: {text}")
        
        if self.ws:
            await self.ws.close()
        if self.transcription_ws:
            await self.transcription_ws.close()
        try:
            os.rmdir(self.temp_dir)
        except:
            pass

class RTMP2FLVController(SimpleRTMPController):

    def __init__(self, output_directory: str, gladia_api_key: str, webhook_url: str = "http://websocket:8000/webhook", transcription_ws_url: str = "ws://websocket:8000/ws/transcription"):
        self.output_directory = output_directory
        self.transcriber = None  # Initialize later when we have audio config
        self.gladia_api_key = gladia_api_key
        self.webhook_url = webhook_url
        self.transcription_ws_url = transcription_ws_url
        self.audio_config = None
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
        # Try to get audio configuration from metadata
        try:
            # Parse raw metadata
            meta = message.payload.decode('utf-8')
            logger.debug(f"Raw metadata: {meta}")
            
            # Extract audio configuration if available
            if '@setDataFrame' in meta:
                if 'audiocodecid' in meta:
                    logger.info(f"Audio codec ID found in metadata")
                if 'audiosamplerate' in meta:
                    logger.info(f"Audio sample rate found in metadata")
        except Exception as e:
            logger.error(f"Failed to parse metadata: {e}")
        await super().on_metadata(session, message)

    async def on_video_message(self, session, message) -> None:
        session.state.write(message.timestamp, message.payload, FLVMediaType.VIDEO)
        await super().on_video_message(session, message)

    async def on_audio_message(self, session, message) -> None:
        session.state.write(message.timestamp, message.payload, FLVMediaType.AUDIO)
        
        try:
            # First byte of FLV audio tag contains audio format info
            audio_tag = message.payload[0]
            sound_format = (audio_tag >> 4) & 0x0F  # First 4 bits
            sound_rate = (audio_tag >> 2) & 0x03    # Next 2 bits
            sound_size = (audio_tag >> 1) & 0x01    # Next 1 bit
            sound_type = audio_tag & 0x01           # Last bit
            
            # Log audio format details for debugging
            if not self.audio_config:
                logger.debug(f"Audio format: {sound_format}, rate: {sound_rate}, size: {sound_size}, type: {sound_type}")
            
            # For AAC (sound_format == 10), second byte is AACPacketType
            if sound_format == 10:  # AAC
                aac_packet_type = message.payload[1]
                if aac_packet_type == 0 and not self.audio_config:  # AAC sequence header
                    # Extract AAC configuration
                    aac_config = message.payload[2:]
                    logger.info(f"AAC config received: {aac_config.hex()}")
                    
                    # Parse AAC config
                    aac_profile = (aac_config[0] >> 3) & 0x1F
                    aac_sampling_freq = ((aac_config[0] & 0x07) << 1) | ((aac_config[1] >> 7) & 0x01)
                    aac_channels = (aac_config[1] >> 3) & 0x0F
                    
                    logger.info(f"AAC Profile: {aac_profile}, Sampling Freq Index: {aac_sampling_freq}, Channels: {aac_channels}")
                    
                    self.audio_config = {
                        'format': 'aac',
                        'profile': aac_profile,
                        'sampling_freq_index': aac_sampling_freq,
                        'channels': aac_channels,
                        'rate_idx': sound_rate,
                        'config': aac_config
                    }
                    # Initialize transcriber now that we have config
                    self.transcriber = GladiaTranscriber(self.gladia_api_key, self.transcription_ws_url)
                    self.transcriber.set_aac_config(self.audio_config)
                    return  # Don't process AAC sequence header
                
                # Only process AAC raw packets (type 1)
                if aac_packet_type != 1:
                    return
                
                # Skip AAC packet type byte for raw packets
                audio_data = message.payload[2:]
            else:
                audio_data = message.payload[1:]  # Skip FLV audio tag
                
            # Send audio to Gladia for transcription
            if self.transcriber:
                try:
                    await self.transcriber.process_audio(audio_data)
                except Exception as e:
                    logger.error(f"Failed to transcribe audio: {e}")
            
        except Exception as e:
            logger.error(f"Failed to process audio message: {e}", exc_info=True)
        
        await super().on_audio_message(session, message)

    async def on_stream_closed(self, session: SessionManager, exception: StreamClosedException) -> None:
        session.state.close()
        if self.transcriber:
            await self.transcriber.close()
        await super().on_stream_closed(session, exception)


class SimpleServer(SimpleRTMPServer):

    def __init__(self, output_directory: str, gladia_api_key: str, webhook_url: str = "http://websocket:8000/webhook"):
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
    webhook_url = os.getenv("WEBHOOK_URL", "http://websocket:8000/webhook")
    
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