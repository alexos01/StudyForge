"""
main.py
FastAPI backend for StudyForge.

Run locally:
  pip install -r requirements.txt
  cp .env.example .env   # then add your OLLAMA_API_KEY (and ideally JWT_SECRET)
  uvicorn main:app --reload --port 8000
"""

import io
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader

import auth
import db
import jobs
import pipeline

load_dotenv()
db.init_db()

app = FastAPI(title="StudyForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Identity: a request is either an authenticated user or an anonymous guest.
# Guests get full history/recovery too, keyed by a client-generated UUID -
# login is only needed to make that history follow you across devices.
# =============================================================================

def get_identity(
    authorization: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None),
):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = auth.decode_token(token)
        if payload:
            return {"owner_type": "user", "owner_id": payload["sub"], "email": payload.get("email")}

    if x_guest_id:
        return {"owner_type": "guest", "owner_id": x_guest_id, "email": None}

    raise HTTPException(400, "Missing identity: send an Authorization bearer token or X-Guest-Id header.")


def require_ollama_key():
    if not os.environ.get("OLLAMA_API_KEY"):
        raise HTTPException(500, "OLLAMA_API_KEY is not configured on the server.")


# =============================================================================
# Schemas
# =============================================================================

class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ProcessTextRequest(BaseModel):
    text: str


class ExplainRequest(BaseModel):
    kit_id: int
    concept_id: Optional[str] = None
    concept_title: str
    concept_description: str
    question: str
    student_answer: str
    correct_answer: str


class AskRequest(BaseModel):
    question: str


class GradeRequest(BaseModel):
    question_index: int
    student_answer: str


# =============================================================================
# Health
# =============================================================================

@app.get("/")
def health() -> dict:
    return {"message": "StudyForge API is healthy."}


# =============================================================================
# Auth (optional — only needed for cross-device history recovery)
# =============================================================================

@app.post("/api/auth/signup")
def signup(req: SignupRequest, x_guest_id: Optional[str] = Header(None)) -> dict:
    email = req.email.strip().lower()
    if "@" not in email or len(req.password) < 8:
        raise HTTPException(400, "Enter a valid email and a password of at least 8 characters.")
    if db.get_user_by_email(email):
        raise HTTPException(409, "An account with that email already exists.")

    user_id = db.create_user(email, auth.hash_password(req.password))

    if x_guest_id:
        db.migrate_guest_kits(x_guest_id, user_id)

    token = auth.create_token(user_id, email)
    return {"token": token, "email": email}


@app.post("/api/auth/login")
def login(req: LoginRequest, x_guest_id: Optional[str] = Header(None)) -> dict:
    email = req.email.strip().lower()
    user = db.get_user_by_email(email)
    if not user or not auth.verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")

    if x_guest_id:
        db.migrate_guest_kits(x_guest_id, user["id"])

    token = auth.create_token(user["id"], email)
    return {"token": token, "email": email}


@app.get("/api/auth/me")
def me(identity: dict = Depends(get_identity)) -> dict:
    if identity["owner_type"] != "user":
        raise HTTPException(401, "Not logged in.")
    return {"email": identity["email"]}


# =============================================================================
# Study kit generation (job-based, so progress reflects real work)
# =============================================================================

async def _run_build_job(job_id: str, source_text: str, owner_type: str, owner_id: str) -> None:
    import asyncio

    try:
        if len(source_text.strip()) < 40:
            raise ValueError("That's not quite enough material to build a study kit from — paste a bit more.")

        chunks = pipeline.chunk_text(source_text)
        total = len(chunks)

        jobs.update_job(
            job_id,
            stage="extracting",
            label=f"Extracting core concepts (part 1 of {total})\u2026" if total > 1 else "Extracting core concepts\u2026",
        )

        chunk_results = []
        for i, chunk in enumerate(chunks):
            if total > 1:
                jobs.update_job(job_id, label=f"Extracting core concepts (part {i + 1} of {total})\u2026")
            result = await asyncio.to_thread(pipeline.extract_chunk_concepts, chunk, i, total)
            chunk_results.append(result.get("concepts", []))

        jobs.update_job(job_id, stage="synthesizing", label="Making sure nothing was missed\u2026")
        kit = await asyncio.to_thread(pipeline.synthesize_kit, chunk_results, source_text[:6000])

        jobs.update_job(job_id, stage="flashcards", label="Building flashcards\u2026")
        flash_result = await asyncio.to_thread(
            pipeline.generate_flashcards, kit["concepts"], kit["summary"]
        )
        kit["flashcards"] = flash_result.get("flashcards", [])

        jobs.update_job(job_id, stage="quiz", label="Writing the quiz\u2026")
        quiz_result = await asyncio.to_thread(pipeline.generate_quiz, kit["concepts"], kit["summary"])
        kit["quiz"] = quiz_result.get("quiz", [])

        jobs.update_job(job_id, stage="short_answer", label="Writing short-answer questions\u2026")
        sa_result = await asyncio.to_thread(
            pipeline.generate_short_answer_questions, kit["concepts"], kit["summary"]
        )
        kit["short_answer"] = sa_result.get("short_answer", [])

        jobs.update_job(job_id, stage="saving", label="Saving your study kit\u2026")
        kit_id = await asyncio.to_thread(
            db.create_kit, owner_type, owner_id, kit.get("title", "Untitled study kit"), source_text, kit
        )
        kit["id"] = kit_id

        jobs.update_job(job_id, stage="done", label="Done", done=True, result=kit)

    except ValueError as e:
        jobs.update_job(job_id, stage="error", label="Error", done=True, error=str(e))
    except Exception as e:
        jobs.update_job(
            job_id,
            stage="error",
            label="Error",
            done=True,
            error=f"Something went wrong forging the study kit: {e}",
        )


@app.post("/api/process")
async def process_text(req: ProcessTextRequest, identity: dict = Depends(get_identity)) -> dict:
    require_ollama_key()
    import asyncio

    job_id = jobs.create_job()
    asyncio.create_task(_run_build_job(job_id, req.text, identity["owner_type"], identity["owner_id"]))
    return {"job_id": job_id}


@app.post("/api/process-file")
async def process_file(
    file: UploadFile = File(...), identity: dict = Depends(get_identity)
) -> dict:
    require_ollama_key()
    import asyncio

    raw = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(400, f"Could not read PDF: {e}")
    else:
        text = raw.decode("utf-8", errors="ignore")

    job_id = jobs.create_job()
    asyncio.create_task(_run_build_job(job_id, text, identity["owner_type"], identity["owner_id"]))
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found (it may have expired).")
    return job


# =============================================================================
# Kit history
# =============================================================================

@app.get("/api/kits")
def list_kits(identity: dict = Depends(get_identity)) -> dict:
    return {"kits": db.list_kits(identity["owner_type"], identity["owner_id"])}


@app.get("/api/kits/{kit_id}")
def get_kit_detail(kit_id: int, identity: dict = Depends(get_identity)) -> dict:
    row = db.get_kit(kit_id)
    if not row or row["owner_type"] != identity["owner_type"] or row["owner_id"] != identity["owner_id"]:
        raise HTTPException(404, "Study kit not found.")
    kit = row["kit"]
    kit["id"] = row["id"]
    kit["source_text"] = row["source_text"]
    return {"kit": kit, "qa_history": db.list_qa(kit_id)}


@app.delete("/api/kits/{kit_id}")
def remove_kit(kit_id: int, identity: dict = Depends(get_identity)) -> dict:
    row = db.get_kit(kit_id)
    if not row or row["owner_type"] != identity["owner_type"] or row["owner_id"] != identity["owner_id"]:
        raise HTTPException(404, "Study kit not found.")
    db.delete_kit(kit_id)
    return {"deleted": True}


# =============================================================================
# Follow-up Q&A ("Ask" tab)
# =============================================================================

@app.post("/api/kits/{kit_id}/ask")
def ask_followup(kit_id: int, req: AskRequest, identity: dict = Depends(get_identity)) -> dict:
    require_ollama_key()
    row = db.get_kit(kit_id)
    if not row or row["owner_type"] != identity["owner_type"] or row["owner_id"] != identity["owner_id"]:
        raise HTTPException(404, "Study kit not found.")

    kit = row["kit"]
    prior_qa = db.list_qa(kit_id)

    try:
        answer = pipeline.answer_followup_question(
            source_text=row["source_text"], summary=kit.get("summary", ""), question=req.question, prior_qa=prior_qa
        )
    except Exception as e:
        raise HTTPException(502, f"Couldn't get an answer: {e}")

    db.add_qa(kit_id, req.question, answer)
    return {"answer": answer}


# =============================================================================
# Short-answer grading
# =============================================================================

@app.post("/api/kits/{kit_id}/grade-short-answer")
def grade_short_answer(kit_id: int, req: GradeRequest, identity: dict = Depends(get_identity)) -> dict:
    require_ollama_key()
    row = db.get_kit(kit_id)
    if not row or row["owner_type"] != identity["owner_type"] or row["owner_id"] != identity["owner_id"]:
        raise HTTPException(404, "Study kit not found.")

    short_answer = row["kit"].get("short_answer", [])
    if req.question_index < 0 or req.question_index >= len(short_answer):
        raise HTTPException(400, "Invalid question index.")

    q = short_answer[req.question_index]
    try:
        result = pipeline.grade_short_answer(q["question"], q["model_answer"], req.student_answer)
    except Exception as e:
        raise HTTPException(502, f"Couldn't grade that answer: {e}")
    return result


# =============================================================================
# Targeted re-explanation (used by the MCQ quiz on a wrong answer)
# =============================================================================

@app.post("/api/explain")
def explain(req: ExplainRequest, identity: dict = Depends(get_identity)) -> dict:
    require_ollama_key()
    row = db.get_kit(req.kit_id)
    if not row or row["owner_type"] != identity["owner_type"] or row["owner_id"] != identity["owner_id"]:
        raise HTTPException(404, "Study kit not found.")

    try:
        return pipeline.generate_targeted_explanation(
            source_text=row["source_text"],
            concept_title=req.concept_title,
            concept_description=req.concept_description,
            question=req.question,
            student_answer=req.student_answer,
            correct_answer=req.correct_answer,
        )
    except Exception as e:
        raise HTTPException(502, f"Failed to generate explanation: {e}")