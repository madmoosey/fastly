import os
import json
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from openai import OpenAI

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/contentdb",
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class ContentIdea(Base):
    __tablename__ = "content_ideas"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(255), nullable=False, index=True)
    audience = Column(String(255), nullable=True)
    tone = Column(String(100), nullable=True)
    ideas_json = Column(Text, nullable=False)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


client = OpenAI()


def parse_ideas_response(text: str) -> list[str]:
    try:
        parsed = json.loads(text)
        ideas = parsed.get("ideas", [])
        if not isinstance(ideas, list) or not all(isinstance(i, str) for i in ideas):
            raise ValueError("Invalid ideas format")
        return ideas
    except Exception as exc:
        raise RuntimeError(f"Failed to parse model output as JSON. Raw output: {text}") from exc


def generate_content_ideas(topic: str, audience: Optional[str], tone: Optional[str]) -> list[str]:
    audience_text = audience or "a general audience"
    tone_text = tone or "clear and engaging"

    prompt = f"""
Generate 10 strong content ideas.

Topic: {topic}
Target audience: {audience_text}
Tone: {tone_text}

Return valid JSON only in this exact shape:
{{
  "ideas": [
    "idea 1",
    "idea 2"
  ]
}}

Rules:
- Each idea should be specific enough to be immediately useful.
- Avoid duplicates.
- Keep each idea to one sentence.
- No markdown.
""".strip()

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    return parse_ideas_response(response.output_text.strip())


def refine_content_ideas(
    topic: str,
    audience: Optional[str],
    tone: Optional[str],
    existing_ideas: list[str],
    refinement_request: str,
) -> list[str]:
    audience_text = audience or "a general audience"
    tone_text = tone or "clear and engaging"
    existing_ideas_text = "\n".join(f"- {idea}" for idea in existing_ideas)

    prompt = f"""
Refine an existing set of content ideas.

Topic: {topic}
Target audience: {audience_text}
Tone: {tone_text}

Existing ideas:
{existing_ideas_text}

Refinement request:
{refinement_request}

Return valid JSON only in this exact shape:
{{
  "ideas": [
    "refined idea 1",
    "refined idea 2"
  ]
}}

Rules:
- Return 10 refined ideas.
- Preserve the original topic and audience alignment.
- Apply the refinement request directly.
- Avoid duplicates.
- Keep each idea to one sentence.
- No markdown.
""".strip()

    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )

    return parse_ideas_response(response.output_text.strip())


class IdeaRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=255)
    audience: Optional[str] = Field(default=None, max_length=255)
    tone: Optional[str] = Field(default=None, max_length=100)


class RefineIdeaRequest(BaseModel):
    refinement_request: str = Field(..., min_length=3, max_length=1000)


class IdeaResponse(BaseModel):
    id: int
    topic: str
    audience: Optional[str]
    tone: Optional[str]
    ideas: list[str]


app = FastAPI(title="Content Idea API")


@app.on_event("startup")
def on_startup():
    create_tables()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ideas", response_model=IdeaResponse)
def create_ideas(payload: IdeaRequest, db: Session = Depends(get_db)):
    try:
        ideas = generate_content_ideas(
            topic=payload.topic,
            audience=payload.audience,
            tone=payload.tone,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    record = ContentIdea(
        topic=payload.topic,
        audience=payload.audience,
        tone=payload.tone,
        ideas_json=json.dumps(ideas),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return IdeaResponse(
        id=record.id,
        topic=record.topic,
        audience=record.audience,
        tone=record.tone,
        ideas=ideas,
    )


@app.post("/ideas/{idea_id}/refine", response_model=IdeaResponse)
def refine_ideas(idea_id: int, payload: RefineIdeaRequest, db: Session = Depends(get_db)):
    record = db.query(ContentIdea).filter(ContentIdea.id == idea_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Idea set not found")

    existing_ideas = json.loads(record.ideas_json)

    try:
        refined_ideas = refine_content_ideas(
            topic=record.topic,
            audience=record.audience,
            tone=record.tone,
            existing_ideas=existing_ideas,
            refinement_request=payload.refinement_request,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    record.ideas_json = json.dumps(refined_ideas)
    db.commit()
    db.refresh(record)

    return IdeaResponse(
        id=record.id,
        topic=record.topic,
        audience=record.audience,
        tone=record.tone,
        ideas=refined_ideas,
    )


@app.get("/ideas/{idea_id}", response_model=IdeaResponse)
def get_ideas(idea_id: int, db: Session = Depends(get_db)):
    record = db.query(ContentIdea).filter(ContentIdea.id == idea_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Idea set not found")

    return IdeaResponse(
        id=record.id,
        topic=record.topic,
        audience=record.audience,
        tone=record.tone,
        ideas=json.loads(record.ideas_json),
    )


@app.get("/ideas", response_model=list[IdeaResponse])
def list_ideas(db: Session = Depends(get_db)):
    records = db.query(ContentIdea).order_by(ContentIdea.id.desc()).all()
    return [
        IdeaResponse(
            id=r.id,
            topic=r.topic,
            audience=r.audience,
            tone=r.tone,
            ideas=json.loads(r.ideas_json),
        )
        for r in records
    ]