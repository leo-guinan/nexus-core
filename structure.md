# RTMP Transcription Platform

## Project Overview
Monorepo containing three interconnected applications for live streaming with real-time transcription.

## Architecture

```
rtmp_host/
├── apps/
│   ├── rtmp-server/        # Python RTMP server for receiving live streams
│   ├── websocket-server/   # Python FastAPI server handling webhooks and API
│   └── webapp/             # Next.js frontend application
├── pyproject.toml          # Python dependencies and project config
└── structure.md            # This file
```

## Tech Stack

### Backend Services
- **RTMP Server**: Python-based RTMP server for receiving live streams
- **WebSocket Server**: FastAPI application handling:
  - Webhook endpoints for RTMP events
  - WebSocket connections for real-time updates
  - REST API endpoints
- **Database**: PostgreSQL with SQLAlchemy ORM

### Frontend
- **Web Application**: Next.js
  - Real-time transcription display
  - Stream management interface
  - WebSocket client for live updates

## Communication Flow
1. Live stream → RTMP Server
2. RTMP Server → WebSocket Server (via webhooks)
3. WebSocket Server → Web Application (via WebSocket)
4. Web Application → WebSocket Server (via REST API)

## Development Setup
- Python services use `uv` for dependency management
- Frontend uses standard Next.js tooling
- All services are containerized for consistent deployment 