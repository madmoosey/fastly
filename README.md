# Content Idea API

A minimal FastAPI service backed by PostgreSQL that generates and refines content ideas with the OpenAI API.

The app supports:

- creating a new set of ideas for a topic
- retrieving a saved idea set by `idea_id`
- listing all saved idea sets
- refining an existing idea set in place using `idea_id`

The OpenAI integration in this project uses the Python SDK with the Responses API pattern, which is the current primary interface in OpenAI’s API docs. :contentReference[oaicite:0]{index=0}

## Requirements

- Python 3.10+
- PostgreSQL
- An OpenAI API key

## Project file

This version assumes a single-file app:

- `main.py`

## Environment variables

Set these before starting the server:

```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/contentdb"
export OPENAI_API_KEY="your_api_key"
export OPENAI_MODEL="gpt-5.2"