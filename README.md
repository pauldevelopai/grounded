# ToolkitRAG

A production-ready web application that transforms an AI Toolkit document into an interactive learning and decision-support platform with RAG-powered Q&A, strategy planning, and multi-user support.

## Features

- **Multi-User Authentication**: Secure registration/login with JWT tokens and admin roles
- **RAG-Powered Q&A**: Chat with the AI toolkit using retrieval-augmented generation
- **Citations**: Every answer includes traceable citations to source content
- **Browse Toolkit**: Filter by cluster, section, and keywords
- **Strategy Planning**: Generate and save AI tool strategy plans with citations
- **Admin Dashboard**: Manage users, ingest documents, view analytics
- **Feedback Loop**: Rate answers and track outcomes

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OpenAI API key

### Local Development

1. **Clone and setup**:
```bash
cd aitools
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

2. **Start the application**:
```bash
docker compose up --build
```

3. **Access the app**:
- Application: http://localhost:8000
- Admin login: Use credentials from .env (default: admin@example.com / changeme123)

4. **Ingest the toolkit**:
- Login as admin
- Navigate to http://localhost:8000/admin/ingest
- The DOCX at `/mnt/data/DONE2.docx` will be available for ingestion

### Running Tests

```bash
docker compose run --rm app pytest
```

## Tech Stack

- **Backend**: FastAPI, Python 3.11+
- **Database**: PostgreSQL with pgvector
- **Frontend**: Jinja2 templates, HTMX, Tailwind CSS
- **Auth**: JWT with httpOnly cookies, Argon2 password hashing
- **AI**: OpenAI embeddings and chat models
- **Infrastructure**: Docker, Docker Compose

## Documentation

- [BUILD.md](BUILD.md) - Complete build specification and requirements
- [LIGHTSAIL_DEPLOY.md](LIGHTSAIL_DEPLOY.md) - AWS Lightsail deployment guide (coming soon)
- [VALIDATION.md](VALIDATION.md) - Validation checklist and test scenarios (coming soon)

## Project Structure

```
aitools/
├── app/              # Application code
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   ├── routers/      # API and page routes
│   ├── services/     # Business logic
│   ├── auth/         # Authentication
│   └── templates/    # Jinja2 templates
├── alembic/          # Database migrations
├── tests/            # Test suite
└── docker-compose.yml
```

## License

Proprietary
