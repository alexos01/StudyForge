"""
main.py
FastAPI backend for StudyForge — an adaptive study kit generator.

Endpoints:
  POST /api/process   -> upload/paste source material, get back a full study kit
  POST /api/explain    -> when a student misses a quiz question, get a targeted re-explanation

Run locally:
  pip install -r requirements.txt
  cp .env.example .env   # then add your OLLAMA_API_KEY
  uvicorn main:app --reload --port 8000
"""

import io
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader

import pipeline

load_dotenv()

app = FastAPI(title="StudyForge API")

# Allow the local Vite dev server (and any deployed frontend) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessTextRequest(BaseModel):
    text: str


class ExplainRequest(BaseModel):
    source_text: str
    concept_title: str
    concept_description: str
    question: str
    student_answer: str
    correct_answer: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/process")
def process_text(req: ProcessTextRequest) -> dict:
    """Build a study kit from pasted text."""
    if not os.environ.get("OLLAMA_API_KEY"):
        raise HTTPException(500, "OLLAMA_API_KEY is not configured on the server.")
    try:
        return pipeline.build_study_kit(req.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Failed to generate study kit: {e}")


@app.post("/api/process-file")
async def process_file(file: UploadFile = File(...)) -> dict:
    """Build a study kit from an uploaded .txt or .pdf file."""
    if not os.environ.get("OLLAMA_API_KEY"):
        raise HTTPException(500, "OLLAMA_API_KEY is not configured on the server.")

    raw = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(400, f"Could not read PDF: {e}")
    else:
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception as e:
            raise HTTPException(400, f"Could not read file: {e}")

    try:
        return pipeline.build_study_kit(text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Failed to generate study kit: {e}")


@app.post("/api/explain")
def explain(req: ExplainRequest) -> dict:
    """Generate a targeted re-explanation for a missed quiz concept."""
    if not os.environ.get("OLLAMA_API_KEY"):
        raise HTTPException(500, "OLLAMA_API_KEY is not configured on the server.")
    try:
        return pipeline.generate_targeted_explanation(
            source_text=req.source_text,
            concept_title=req.concept_title,
            concept_description=req.concept_description,
            question=req.question,
            student_answer=req.student_answer,
            correct_answer=req.correct_answer,
        )
    except Exception as e:
        raise HTTPException(502, f"Failed to generate explanation: {e}")