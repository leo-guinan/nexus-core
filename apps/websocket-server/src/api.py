import aiohttp
import os
import json
import logging
from typing import Dict, Any, List
from fastapi import UploadFile, HTTPException
from google.cloud import storage
from google.oauth2 import service_account
import chromadb
from chromadb.config import Settings
import docx
from PyPDF2 import PdfReader
from pylatexenc.latex2text import LatexNodes2Text
import uuid
import tempfile
import re

logger = logging.getLogger(__name__)

def split_text_into_chunks(text: str, max_chunk_size: int = 4000) -> List[str]:
    """Split text into chunks of approximately max_chunk_size bytes."""
    # First split by paragraphs
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para_size = len(para.encode('utf-8'))
        if current_size + para_size > max_chunk_size and current_chunk:
            # Join current chunk and add to chunks
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size
    
    # Add the last chunk if it exists
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks

class DocumentProcessor:
    def __init__(self):
        # Initialize GCS client with credentials
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/credentials/service-account.json")
        credentials_json = os.getenv("GOOGLE_CREDENTIALS")
        
        logger.info(f"Initializing DocumentProcessor with credentials_path: {credentials_path}")
        
        if credentials_json:
            # Use credentials from environment variable
            logger.info("Using credentials from GOOGLE_CREDENTIALS env var")
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(credentials_json)
            )
        elif credentials_path:
            # Use credentials from file
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"Credentials file not found at {credentials_path}")
            logger.info(f"Using credentials from file: {credentials_path}")
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
        else:
            raise ValueError("Neither GOOGLE_APPLICATION_CREDENTIALS nor GOOGLE_CREDENTIALS environment variable is set")
            
        self.gcs_client = storage.Client(credentials=credentials)
        self.bucket_name = os.getenv("GOOGLE_CLOUD_BUCKET_NAME")
        
        # Create bucket if it doesn't exist
        try:
            self.bucket = self.gcs_client.get_bucket(self.bucket_name)
            logger.info(f"Using existing bucket: {self.bucket_name}")
        except Exception as e:
            logger.info(f"Bucket {self.bucket_name} does not exist, creating it...")
            self.bucket = self.gcs_client.create_bucket(self.bucket_name)
            logger.info(f"Created bucket: {self.bucket_name}")
        
        # Initialize ChromaDB client (optional)
        self.collection = None
        try:
            logger.info("Initializing ChromaDB client...")
            try:
                self.chroma_client = chromadb.HttpClient(
                    host='api.trychroma.com',
                    port=8000,
                    ssl=True,
                    tenant=os.getenv("CHROMA_TENANT"),
                    database=os.getenv("CHROMA_DATABASE"),
                    headers={
                        'x-chroma-token': os.getenv("CHROMA_API_KEY")
                    }
                )
                logger.info("ChromaDB client initialized successfully")
                
                logger.info("Getting or creating 'documents' collection...")
                self.collection = self.chroma_client.get_or_create_collection("documents")
                logger.info("Collection initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing ChromaDB: {str(e)}", exc_info=True)
                logger.warning("Continuing without ChromaDB functionality")
                self.chroma_client = None
                self.collection = None
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {str(e)}", exc_info=True)
            logger.warning("Continuing without ChromaDB functionality")

    async def process_document(self, file: UploadFile) -> Dict[str, Any]:
        file_id = str(uuid.uuid4())
        file_ext = file.filename.split('.')[-1].lower()
        
        # Validate file type
        if file_ext not in ['pdf', 'docx', 'tex']:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        # Save file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            # Upload to GCS
            blob_name = f"documents/{file_id}/{file.filename}"
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(temp_file.name)
            
            # Extract text based on file type
            text = self._extract_text(temp_file.name, file_ext)
            
            # Store in ChromaDB if available
            chroma_status = "skipped"
            chunks_processed = 0
            total_chunks = 0
            
            if self.collection:
                # Split text into chunks
                chunks = split_text_into_chunks(text)
                total_chunks = len(chunks)
                logger.info(f"Split document into {total_chunks} chunks")
                
                # Store each chunk with metadata
                chunk_ids = []
                for i, chunk in enumerate(chunks):
                    chunk_id = f"{file_id}_chunk_{i}"
                    chunk_ids.append(chunk_id)
                    
                    metadata = {
                        "filename": file.filename,
                        "type": file_ext,
                        "document_id": file_id,
                        "chunk_id": chunk_id,
                        "chunk_index": i,
                        "total_chunks": total_chunks
                    }
                    
                    try:
                        self.collection.add(
                            documents=[chunk],
                            ids=[chunk_id],
                            metadatas=[metadata]
                        )
                        chunks_processed += 1
                        logger.info(f"Successfully stored chunk {i+1}/{total_chunks}")
                    except Exception as e:
                        error_msg = str(e)
                        if "Quota exceeded" in error_msg or "429" in error_msg:
                            logger.warning(f"ChromaDB quota exceeded for chunk {chunk_id}. Stopping chunk processing.")
                            break
                        else:
                            logger.error(f"Error storing chunk in ChromaDB: {error_msg}", exc_info=True)
                            continue
                
                if chunks_processed == total_chunks:
                    chroma_status = "processed"
                elif chunks_processed > 0:
                    chroma_status = "partially_processed"
                else:
                    chroma_status = "quota_exceeded"
            
            return {
                "id": file_id,
                "filename": file.filename,
                "gcs_path": blob_name,
                "status": "processed",
                "chroma_status": chroma_status,
                "chunks_processed": chunks_processed,
                "total_chunks": total_chunks
            }

    def _extract_text(self, file_path: str, file_type: str) -> str:
        if file_type == 'pdf':
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
        elif file_type == 'docx':
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        else:  # tex
            with open(file_path, 'r', encoding='utf-8') as f:
                latex_content = f.read()
                text = LatexNodes2Text().latex_to_text(latex_content)
        return text

class MastraAPI:
    def __init__(self):
        self.base_url = os.getenv("MASTRA_API_URL", "http://localhost:3001")
        self.session = None
        logger.info(f"Initialized MastraAPI with base URL: {self.base_url}")

    async def ensure_session(self):
        if not self.session:
            logger.info("Creating new aiohttp session")
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session:
            logger.info("Closing aiohttp session")
            await self.session.close()
            self.session = None

    async def send_message(self, message): 
        session = await self.ensure_session()
        url = f"{self.base_url}/api/agents/memeticMarketingAgent/generate"
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ]
        }
        logger.info(f"Sending message to {url}")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with session.post(url, json=payload) as response:
                response_data = await response.json()
                logger.info(f"Response status: {response.status}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
                return response_data
        except Exception as e:
            logger.error(f"Error in send_message: {e}", exc_info=True)
            raise

    async def trigger_transcript_workflow(self, text: str, timestamp: int, stream_key: str):
        session = await self.ensure_session()
        url = f"{self.base_url}/api/workflows/transcript"
        payload = {
            "text": text,
            "timestamp": timestamp,
            "stream_key": stream_key
        }
        logger.info(f"Triggering transcript workflow at {url}")
        logger.debug(f"Workflow payload: {json.dumps(payload, indent=2)}")
        
        try:
            async with session.post(url, json=payload) as response:
                response_data = await response.json()
                logger.info(f"Workflow response status: {response.status}")
                logger.debug(f"Workflow response: {json.dumps(response_data, indent=2)}")
                return response_data
        except Exception as e:
            logger.error(f"Error in trigger_transcript_workflow: {e}", exc_info=True)
            raise

