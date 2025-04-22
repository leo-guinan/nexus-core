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
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

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
        # Initialize database connection
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
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

    async def process_document(self, file: UploadFile, user_id: str) -> Dict[str, Any]:
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
                        "f": file.filename,  # filename
                        "t": file_ext,       # type
                        "d": file_id,        # document_id
                        "c": chunk_id,       # chunk_id
                        "i": i,              # chunk_index
                        "n": total_chunks,   # total_chunks
                        "u": user_id         # user_id
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
            
            # Store document metadata in database
            with self.SessionLocal() as db:
                db.execute(
                    text("""
                        INSERT INTO documents (
                            id, user_id, filename, file_type, gcs_path, 
                            fulltext_content, chroma_status, chunks_processed, 
                            total_chunks, created_at, updated_at
                        ) VALUES (
                            :id, :user_id, :filename, :file_type, :gcs_path,
                            :fulltext_content, :chroma_status, :chunks_processed,
                            :total_chunks, :created_at, :updated_at
                        )
                    """),
                    {
                        "id": file_id,
                        "user_id": user_id,
                        "filename": file.filename,
                        "file_type": file_ext,
                        "gcs_path": blob_name,
                        "fulltext_content": text,
                        "chroma_status": chroma_status,
                        "chunks_processed": chunks_processed,
                        "total_chunks": total_chunks,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                )
                db.commit()
            
            return {
                "id": file_id,
                "filename": file.filename,
                "gcs_path": blob_name,
                "status": "processed",
                "chroma_status": chroma_status,
                "chunks_processed": chunks_processed,
                "total_chunks": total_chunks
            }

    async def get_user_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all documents for a given user."""
        with self.SessionLocal() as db:
            result = db.execute(
                text("""
                    SELECT 
                        id, filename, file_type, gcs_path, chroma_status,
                        chunks_processed, total_chunks, created_at, updated_at
                    FROM documents
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                """),
                {"user_id": user_id}
            )
            
            documents = []
            for row in result:
                documents.append({
                    "id": row.id,
                    "filename": row.filename,
                    "file_type": row.file_type,
                    "gcs_path": row.gcs_path,
                    "chroma_status": row.chroma_status,
                    "chunks_processed": row.chunks_processed,
                    "total_chunks": row.total_chunks,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat()
                })
            
            return documents

    async def get_document_by_id(self, document_id: str) -> Dict[str, Any]:
        """Get a document by ID."""
        with self.SessionLocal() as db:
            result = db.execute(
                text("""
                    SELECT 
                        id, user_id, filename, file_type, gcs_path, 
                        fulltext_content, chroma_status, chunks_processed, 
                        total_chunks, created_at, updated_at
                    FROM documents
                    WHERE id = :document_id
                """),
                {"document_id": document_id}
            ).first()
            
            if not result:
                return None
                
            # Get chunks from ChromaDB if available
            chunks = []
            if self.collection:
                try:
                    chroma_results = self.collection.get(
                        where={"document_id": document_id},
                        include=["documents", "metadatas"]
                    )
                    if chroma_results and chroma_results['ids']:
                        for i, chunk_id in enumerate(chroma_results['ids']):
                            chunks.append({
                                "id": chunk_id,
                                "content": chroma_results['documents'][i],
                                "metadata": chroma_results['metadatas'][i]
                            })
                except Exception as e:
                    logger.error(f"Error retrieving chunks from ChromaDB: {str(e)}", exc_info=True)
            
            return {
                "id": result.id,
                "user_id": result.user_id,
                "filename": result.filename,
                "file_type": result.file_type,
                "gcs_path": result.gcs_path,
                "fulltext_content": result.fulltext_content,
                "chroma_status": result.chroma_status,
                "chunks_processed": result.chunks_processed,
                "total_chunks": result.total_chunks,
                "created_at": result.created_at.isoformat(),
                "updated_at": result.updated_at.isoformat(),
                "chunks": chunks
            }

    async def update_document(self, document_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update a document's metadata."""
        with self.SessionLocal() as db:
            # First check if document exists
            result = db.execute(
                text("SELECT id FROM documents WHERE id = :document_id"),
                {"document_id": document_id}
            ).first()
            
            if not result:
                return None
            
            # Build update query dynamically based on provided fields
            update_fields = []
            params = {"document_id": document_id}
            
            allowed_fields = {
                "filename": "filename",
                "file_type": "file_type",
                "chroma_status": "chroma_status",
                "chunks_processed": "chunks_processed",
                "total_chunks": "total_chunks"
            }
            
            for field, value in updates.items():
                if field in allowed_fields:
                    update_fields.append(f"{allowed_fields[field]} = :{field}")
                    params[field] = value
            
            if not update_fields:
                return await self.get_document_by_id(document_id)
            
            # Add updated_at timestamp
            update_fields.append("updated_at = now()")
            
            # Execute update
            db.execute(
                text(f"""
                    UPDATE documents 
                    SET {', '.join(update_fields)}
                    WHERE id = :document_id
                """),
                params
            )
            db.commit()
            
            return await self.get_document_by_id(document_id)

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its associated data."""
        with self.SessionLocal() as db:
            # First check if document exists
            result = db.execute(
                text("""
                    SELECT gcs_path, user_id 
                    FROM documents 
                    WHERE id = :document_id
                """),
                {"document_id": document_id}
            ).first()
            
            if not result:
                return False
            
            try:
                # Delete from GCS
                blob = self.bucket.blob(result.gcs_path)
                blob.delete()
                
                # Delete chunks from ChromaDB if available
                if self.collection:
                    try:
                        self.collection.delete(
                            where={"document_id": document_id}
                        )
                    except Exception as e:
                        logger.error(f"Error deleting chunks from ChromaDB: {str(e)}", exc_info=True)
                
                # Delete from database
                db.execute(
                    text("DELETE FROM documents WHERE id = :document_id"),
                    {"document_id": document_id}
                )
                db.commit()
                
                return True
            except Exception as e:
                logger.error(f"Error deleting document: {str(e)}", exc_info=True)
                db.rollback()
                return False

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

