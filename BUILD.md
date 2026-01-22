# ToolkitRAG - Build Specification

## Project Overview

ToolkitRAG is a production-ready web application that transforms an AI Toolkit document into an interactive learning and decision-support platform with multi-user support, RAG-powered Q&A, and strategy planning capabilities.

## Core Requirements

### Non-Negotiables

1. **Real Content Only**: Ingest actual content from `/mnt/data/DONE2.docx` - NO dummy data or placeholders
2. **End-to-End Functionality**: Every feature must be fully wired and runnable locally via Docker Compose
3. **Multi-User Support**: Complete user authentication with admin role and admin-only routes
4. **Clean UI**: Minimal, server-rendered interface that works well (Jinja2 + HTMX + Tailwind CDN)
5. **Production Deployment**: AWS Lightsail deployment with Docker Compose + HTTPS reverse proxy
6. **Testing**: Comprehensive tests for critical paths with clear definition of done

### Technology Stack

**Backend & Framework**
- Python 3.11+
- FastAPI (API + server-rendered HTML)
- Jinja2 templates
- HTMX for interactivity
- Tailwind CSS via CDN (no JS build step)

**Database & Storage**
- PostgreSQL
- pgvector extension for embeddings
- Alembic for migrations

**Authentication & Security**
- JWT access + refresh tokens
- httpOnly cookies for token storage
- Argon2 password hashing (bcrypt fallback)

**Infrastructure**
- Docker + Docker Compose
- Local/prod parity
- Pytest for testing

## Application Screens

### Public/User Screens
- `/` - Home page
- `/register` - User registration
- `/login` - User login
- `/logout` - Logout handler
- `/toolkit` - Chat UI with RAG, citations panel, rating/feedback controls
- `/browse` - Browse toolkit by cluster/section with keyword filtering
- `/strategy` - Strategy plan wizard
- `/strategy/{id}` - View/export saved strategy plan as markdown

### Admin Screens
- `/admin` - Admin dashboard (users, documents, analytics)
- `/admin/ingest` - Upload DOCX, set version tag, trigger reindex

## API Endpoints

### Health & Status
- `GET /health` - Basic health check
- `GET /ready` - Readiness check (DB + embeddings)

### Authentication
- `POST /api/auth/register` - New user registration
- `POST /api/auth/login` - User login (returns JWT in httpOnly cookie)
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Current user info
- `POST /api/auth/logout` - Logout (clear cookies)

### RAG & Search
- `POST /api/rag/search` - Semantic search over toolkit chunks
- `POST /api/rag/answer` - Generate grounded answer with citations

### Strategy Planning
- `POST /api/strategy/create` - Create new strategy plan
- `GET /api/strategy/{id}` - Retrieve strategy plan
- `GET /api/strategy/{id}/export` - Export as markdown

### Admin (Admin-Only)
- `GET /api/admin/users` - List all users
- `POST /api/admin/users/{id}/toggle-admin` - Toggle admin status
- `GET /api/admin/documents` - List toolkit document versions
- `POST /api/admin/ingest` - Upload and process DOCX
- `POST /api/admin/reindex` - Trigger reindexing
- `GET /api/admin/analytics` - Feedback and usage analytics

## Data Model

### Core Tables

**users**
- `id` (PK, UUID)
- `email` (unique, indexed)
- `password_hash` (Argon2/bcrypt)
- `is_admin` (boolean, default false)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**toolkit_documents**
- `id` (PK, UUID)
- `version_tag` (string, unique)
- `source_filename` (string)
- `uploaded_by` (FK → users.id)
- `upload_date` (timestamp)
- `chunk_count` (integer)
- `is_active` (boolean)

**toolkit_chunks**
- `id` (PK, UUID)
- `document_id` (FK → toolkit_documents.id)
- `chunk_text` (text)
- `chunk_index` (integer)
- `cluster` (string, nullable)
- `section` (string, nullable)
- `tool_name` (string, nullable)
- `tags` (jsonb, nullable)
- `embedding` (vector(1536) or appropriate dimension)
- `created_at` (timestamp)

**chat_logs**
- `id` (PK, UUID)
- `user_id` (FK → users.id)
- `question` (text)
- `answer` (text)
- `citations` (jsonb) - array of {chunk_id, section, cluster, snippet}
- `retrieval_confidence` (float)
- `created_at` (timestamp)

**feedback**
- `id` (PK, UUID)
- `user_id` (FK → users.id)
- `chat_log_id` (FK → chat_logs.id)
- `rating` (integer 1-5)
- `issue_type` (string, nullable) - e.g., "inaccurate", "incomplete", "unclear"
- `comment` (text, nullable)
- `created_at` (timestamp)

**strategy_plans**
- `id` (PK, UUID)
- `user_id` (FK → users.id)
- `title` (string)
- `inputs` (jsonb) - wizard answers/selections
- `outputs` (jsonb) - generated recommendations with citations
- `created_at` (timestamp)
- `updated_at` (timestamp)

## Document Ingestion Requirements

### DOCX Processing
- Use `python-docx` library to parse `/mnt/data/DONE2.docx`
- Preserve heading hierarchy (H1, H2, H3, etc.)
- Extract metadata: cluster, section, tool_name when identifiable
- Maintain document structure and context

### Chunking Strategy
- Target chunk size: 800–1200 characters
- Overlap: ~150 characters between consecutive chunks
- Respect paragraph boundaries (don't split mid-sentence)
- Include metadata from parent sections in each chunk

### Embedding Generation
- Create embeddings during ingestion (not on-the-fly)
- Store in pgvector column alongside chunk text
- Use OpenAI text-embedding-3-small or similar model
- Ensure embedding dimension matches pgvector column definition

### Reindexing
- Admin can trigger full reindex
- Marks old chunks as inactive (soft delete)
- Creates new document version
- Updates chunk counts and statistics

## RAG Implementation Requirements

### Retrieval Phase
1. Convert user question to embedding
2. Query pgvector for top_k most similar chunks (k=5-10)
3. Calculate similarity scores/confidence
4. Filter by minimum similarity threshold

### Answer Generation
1. Construct prompt with ONLY retrieved chunks
2. Explicitly instruct LLM to use only provided context
3. Request citations in response
4. If retrieval confidence < threshold, return "Not found in toolkit" - NO hallucination

### Citation Format
Each citation must include:
- `chunk_id` - Reference to source chunk
- `section` - Section/heading from document
- `cluster` - Cluster/category if available
- `snippet` - 50-100 char excerpt showing relevance
- `tool_name` - Specific tool if applicable

### Confidence Handling
- Log retrieval confidence score
- Refuse to answer if top similarity < 0.6 (tune threshold)
- Provide feedback to user: "I couldn't find relevant information in the toolkit"

## Development Workflow

### Implementation Principles
1. **Small Steps**: Implement one feature at a time
2. **Continuous Validation**: After each step, `docker compose up --build` must succeed
3. **Migration Consistency**: Keep Alembic migrations in sync
4. **Test as You Go**: Add tests alongside features - no broken tests
5. **No Sweeping Refactors**: Only refactor when fixing design flaws
6. **Clarity Over Cleverness**: Prefer readable, maintainable code

### Git Workflow
- Commit after each working milestone
- Clear commit messages describing what works
- Tag major milestones (v0.1-auth, v0.2-ingestion, etc.)

## Definition of Done

### Local Development
- [ ] `docker compose up --build` brings up app + PostgreSQL
- [ ] All Alembic migrations apply cleanly
- [ ] App is accessible and functional at http://localhost:8000
- [ ] No errors in container logs during normal operation

### Core Functionality
- [ ] Admin can upload `/mnt/data/DONE2.docx` via `/admin/ingest`
- [ ] Chunk counts increase and display correctly after ingestion
- [ ] `/toolkit` chat returns grounded answers with citations
- [ ] Citations reference actual chunk IDs and include snippets
- [ ] Feedback ratings save to database and display in analytics
- [ ] Strategy builder produces saved plan with toolkit citations
- [ ] Multi-user separation works (users can't see others' data)

### Testing
- [ ] Auth tests: registration, login, JWT validation, admin gating
- [ ] Ingestion tests: DOCX parsing, chunking, embedding creation
- [ ] Retrieval tests: similarity search, top-k results
- [ ] RAG tests: answer generation with citations, confidence thresholds
- [ ] Admin gating tests: non-admin users rejected from admin routes
- [ ] All tests pass: `docker compose run --rm app pytest`

### Documentation
- [ ] `BUILD.md` - This document (complete)
- [ ] `LIGHTSAIL_DEPLOY.md` - Exact deployment commands for AWS Lightsail
  - Docker installation
  - Docker Compose setup
  - Reverse proxy configuration (nginx/Caddy)
  - HTTPS/SSL setup (Let's Encrypt)
  - Systemd service configuration
  - Environment variable management
  - Backup procedures
- [ ] `VALIDATION.md` - Manual validation checklist
  - Step-by-step smoke tests
  - 10 example questions with expected citation types
  - Expected behavior for edge cases
- [ ] `README.md` - Quick start and overview
- [ ] Inline code comments for complex logic

## Repository File Structure

```
toolkitrag/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── README.md
├── BUILD.md
├── LIGHTSAIL_DEPLOY.md (to be created)
├── VALIDATION.md (to be created)
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── (migration files)
│
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entrypoint
│   ├── config.py                  # Settings (env vars)
│   ├── database.py                # DB session, pgvector setup
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── toolkit.py
│   │   ├── chat.py
│   │   └── strategy.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── auth.py
│   │   ├── toolkit.py
│   │   ├── chat.py
│   │   └── strategy.py
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt.py                 # JWT creation/validation
│   │   ├── password.py            # Argon2 hashing
│   │   └── dependencies.py        # get_current_user, require_admin
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ingestion.py           # DOCX parsing, chunking
│   │   ├── embeddings.py          # OpenAI embeddings API
│   │   ├── rag.py                 # Retrieval + answer generation
│   │   └── strategy.py            # Strategy plan generation
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py                # /api/auth/*
│   │   ├── rag.py                 # /api/rag/*
│   │   ├── strategy.py            # /api/strategy/*
│   │   ├── admin.py               # /api/admin/*
│   │   └── pages.py               # HTML page routes
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── toolkit.html           # Chat UI
│   │   ├── browse.html
│   │   ├── strategy.html          # Wizard
│   │   ├── strategy_view.html     # View saved plan
│   │   ├── admin/
│   │   │   ├── dashboard.html
│   │   │   └── ingest.html
│   │   └── components/
│   │       ├── citation.html
│   │       └── feedback.html
│   │
│   └── static/
│       └── (optional: custom CSS if needed)
│
└── tests/
    ├── __init__.py
    ├── conftest.py                # Fixtures (test DB, client)
    ├── test_auth.py
    ├── test_ingestion.py
    ├── test_rag.py
    ├── test_strategy.py
    └── test_admin.py
```

## Implementation Milestones

### Milestone 0: Project Setup (Current)
- [x] Create BUILD.md
- [ ] Create repository structure
- [ ] Docker + Docker Compose setup
- [ ] Database configuration with pgvector
- [ ] Alembic migrations init

### Milestone 1: Authentication & User Management
- [ ] User model + migration
- [ ] JWT auth with httpOnly cookies
- [ ] Argon2 password hashing
- [ ] Register/login/logout pages + API
- [ ] Admin role enforcement
- [ ] Auth tests

### Milestone 2: Document Ingestion
- [ ] toolkit_documents + toolkit_chunks models
- [ ] DOCX parsing service (python-docx)
- [ ] Chunking algorithm (800-1200 chars, 150 overlap)
- [ ] OpenAI embeddings integration
- [ ] pgvector storage
- [ ] Admin ingest page + API
- [ ] Ingestion tests

### Milestone 3: RAG Implementation
- [ ] chat_logs + feedback models
- [ ] Semantic search service (pgvector similarity)
- [ ] Answer generation with LLM
- [ ] Citation extraction and formatting
- [ ] Confidence threshold enforcement
- [ ] /toolkit chat UI
- [ ] RAG tests

### Milestone 4: Browse & Strategy
- [ ] Browse page with cluster/section filtering
- [ ] strategy_plans model
- [ ] Strategy wizard UI
- [ ] Strategy generation service with citations
- [ ] Strategy view/export
- [ ] Strategy tests

### Milestone 5: Admin & Analytics
- [ ] Admin dashboard
- [ ] User management interface
- [ ] Document version management
- [ ] Feedback analytics
- [ ] Usage statistics
- [ ] Admin tests

### Milestone 6: Production Readiness
- [ ] Health/ready endpoints
- [ ] Error handling and logging
- [ ] Rate limiting (optional but recommended)
- [ ] LIGHTSAIL_DEPLOY.md
- [ ] VALIDATION.md
- [ ] Final integration tests
- [ ] Performance validation

## Environment Variables

Required environment variables (`.env.example`):

```bash
# Database
DATABASE_URL=postgresql://user:password@db:5432/toolkitrag
POSTGRES_USER=toolkitrag
POSTGRES_PASSWORD=changeme
POSTGRES_DB=toolkitrag

# Auth
JWT_SECRET_KEY=generate-secure-random-key-here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# OpenAI
OPENAI_API_KEY=sk-...

# App
APP_ENV=development
APP_DEBUG=true
CORS_ORIGINS=["http://localhost:8000"]

# Admin (first user)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=changeme
```

## Success Criteria

The project is considered complete when:

1. A non-technical user can register, log in, and ask questions about the toolkit
2. An admin can upload the real DOCX and see it indexed
3. All answers include citations that trace back to the source document
4. Users can create and save strategy plans
5. The app runs reliably in Docker Compose locally
6. Deployment instructions work on a fresh AWS Lightsail instance
7. All tests pass
8. Validation checklist can be executed successfully

## Next Steps

After BUILD.md approval:
1. Create repository structure and Docker setup
2. Initialize database with pgvector
3. Set up Alembic migrations
4. Begin Milestone 1 (Authentication)
