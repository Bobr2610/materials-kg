---
name: docker-workflow
description: Docker commands and rules for materials-kg. Use when running the app, testing in containers, or rebuilding after code changes.
---

# Docker Workflow

## Quick Start

```bash
# Start everything (Neo4j + API)
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f materials-api

# Stop
docker compose down
```

## Rebuild After Code Changes

```bash
docker compose up -d --build
```

## Services

| Service | URL | Container |
|---------|-----|-----------|
| API | http://localhost:8090 | materials-kg-api |
| Neo4j Browser | http://localhost:7474 | materials-kg-neo4j |

## One-Off Commands

```bash
# Run tests in container
docker compose exec materials-api python -m pytest kg_engine/tests/ -v

# Run linter in container
docker compose exec materials-api ruff check kg_engine/

# Open Python shell
docker compose exec materials-api python
```

## Environment Setup

```bash
# Copy and edit .env
cp .env.example .env

# Required vars:
# NEO4J_USER=neo4j
# NEO4J_PASSWORD=changeme
# OPENROUTER_API_KEY=your_key
```

## Rules

1. **ALWAYS prefer Docker** over running Python directly
2. **NEVER hardcode** Neo4j credentials — use .env
3. **After code changes** → `docker compose up -d --build`
4. **Check logs** before claiming something works or doesn't
5. **Never commit .env** — only .env.example
