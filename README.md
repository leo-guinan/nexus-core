# RTMP Live Transcription Platform

A monorepo containing a full-stack live streaming platform with real-time transcription capabilities.

## Project Structure

```
.
├── apps/
│   ├── rtmp-server/         # RTMP ingest server with Gladia transcription
│   │   ├── src/
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── websocket-server/    # WebSocket server for transcription events
│   │   ├── src/
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── web/                 # Next.js frontend application
│       ├── src/
│       ├── package.json
│       └── README.md
├── pnpm-workspace.yaml      # PNPM workspace config
├── pyproject.toml          # Root Python project config
└── README.md
```

## Tech Stack

- **RTMP Server**: Python with `pyrtmp` for RTMP ingest
- **WebSocket Server**: Python FastAPI server for real-time transcription events
- **Frontend**: Next.js 14 with TypeScript and Tailwind CSS
- **Package Management**: 
  - Python: `uv` for dependency management
  - Node.js: `pnpm` for workspace management

## Setup

1. Install dependencies:
   ```bash
   # Install Python dependencies using uv
   uv venv
   source .venv/bin/activate
   uv pip install -e apps/rtmp-server
   uv pip install -e apps/websocket-server

   # Install Node.js dependencies
   pnpm install
   ```

2. Set up environment variables:
   ```bash
   # RTMP Server
   export GLADIA_API_KEY=your_key_here
   export WEBHOOK_URL=http://localhost:8000/webhook

   # WebSocket Server
   export PORT=8000

   # Web App
   cp apps/web/.env.example apps/web/.env.local
   ```

3. Start the services:
   ```bash
   # Start RTMP server
   python apps/rtmp-server/src/main.py

   # Start WebSocket server
   python apps/websocket-server/src/main.py

   # Start web app
   cd apps/web && pnpm dev
   ```

## Development

- RTMP server listens on port 1935
- WebSocket server runs on port 8000
- Web app runs on port 3000

## Contributing

1. Create a new branch for your feature
2. Make your changes
3. Submit a pull request

## License

MIT

## Document Processing Feature

### API Documentation

#### Document Upload
```http
POST /api/documents/upload
Content-Type: multipart/form-data

Parameters:
- file: File (PDF, DOCX, or TEX)
- user_id: string
```

Response:
```json
{
  "id": "uuid",
  "filename": "example.pdf",
  "gcs_path": "documents/uuid/example.pdf",
  "status": "processed",
  "chroma_status": "processed",
  "chunks_processed": 5,
  "total_chunks": 5
}
```

#### Get User Documents
```http
GET /api/documents?user_id={user_id}
```

Response:
```json
{
  "documents": [
    {
      "id": "uuid",
      "filename": "example.pdf",
      "file_type": "pdf",
      "gcs_path": "documents/uuid/example.pdf",
      "chroma_status": "processed",
      "chunks_processed": 5,
      "total_chunks": 5,
      "created_at": "2024-04-01T12:00:00",
      "updated_at": "2024-04-01T12:00:00"
    }
  ]
}
```

#### Get Document by ID
```http
GET /api/documents/{document_id}
```

Response:
```json
{
  "id": "uuid",
  "user_id": "user123",
  "filename": "example.pdf",
  "file_type": "pdf",
  "gcs_path": "documents/uuid/example.pdf",
  "fulltext_content": "Full document text...",
  "chroma_status": "processed",
  "chunks_processed": 5,
  "total_chunks": 5,
  "created_at": "2024-04-01T12:00:00",
  "updated_at": "2024-04-01T12:00:00",
  "chunks": [
    {
      "id": "uuid_chunk_0",
      "content": "Chunk text...",
      "metadata": {
        "filename": "example.pdf",
        "type": "pdf",
        "document_id": "uuid",
        "chunk_id": "uuid_chunk_0",
        "chunk_index": 0,
        "total_chunks": 5,
        "user_id": "user123"
      }
    }
  ]
}
```

#### Update Document
```http
PATCH /api/documents/{document_id}
Content-Type: application/json

{
  "filename": "new_name.pdf",
  "chroma_status": "processed",
  "chunks_processed": 6,
  "total_chunks": 6
}
```

Response: Returns the updated document object (same as GET /api/documents/{document_id})

#### Delete Document
```http
DELETE /api/documents/{document_id}
```

Response:
```json
{
  "status": "success",
  "message": "Document deleted successfully"
}
```

### Requirements Checklist
- [ ] Add new dependencies:
  - [ ] `python-docx` for DOCX processing
  - [ ] `PyPDF2` for PDF processing
  - [ ] `pylatexenc` for LaTeX processing
  - [ ] `google-cloud-storage` for GCS integration
  - [ ] `chromadb` for vector storage
- [ ] Environment Variables:
  - [ ] `GOOGLE_CLOUD_PROJECT_ID`
  - [ ] `GOOGLE_CLOUD_BUCKET_NAME`
  - [ ] `GOOGLE_APPLICATION_CREDENTIALS` (path to service account key)
  - [ ] `CHROMA_API_KEY`
  - [ ] `CHROMA_HOST`
- [ ] API Endpoints:
  - [ ] POST `/api/documents/upload` for file upload
  - [ ] GET `/api/documents/{id}` for document status
- [ ] Storage:
  - [ ] Set up GCS bucket for document storage
  - [ ] Configure CORS for GCS bucket
- [ ] Vector Database:
  - [ ] Set up ChromaDB collection for document embeddings
  - [ ] Configure embedding model (e.g., OpenAI's text-embedding-3-small)
- [ ] Document Processing:
  - [ ] Implement file type detection
  - [ ] Add content extraction for each file type
  - [ ] Add text chunking for large documents
  - [ ] Implement embedding generation
  - [ ] Add error handling and validation
- [ ] Testing:
  - [ ] Unit tests for file processing
  - [ ] Integration tests for GCS upload
  - [ ] Integration tests for ChromaDB
  - [ ] Load testing for large documents
