"""
pipeline.py
Core AI pipeline for StudyForge, split into discrete stages so that:
  (a) the frontend can show real progress ("Extracting concepts" only shows
      while that call is actually in flight), and
  (b) long material gets full coverage instead of being silently truncated.

Stages:
  1. chunk_text + extract_chunk_concepts (map)   -> one call per chunk
  2. synthesize_kit (reduce)                     -> merges chunks into one
                                                     concept map + summary
  3. generate_flashcards
  4. generate_quiz
  5. generate_short_answer_questions

Plus, independent of the build pipeline:
  - answer_followup_question   (the "Ask" tab)
  - grade_short_answer         (the "Short answer" tab)

Talks to Ollama Cloud (https://ollama.com) through its OpenAI-compatible
/v1/chat/completions endpoint via the `openai` SDK.
"""

import json
import os
import re
from typing import Any, Optional

from openai import OpenAI

MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1")

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key=os.environ.get("OLLAMA_API_KEY", ""),
)

# Chunking: keep chunks small enough for reliable extraction, capped so a
# single upload can't blow the time/cost budget in one request. This still
# covers roughly 60k+ characters of source material end to end.
CHUNK_SIZE = 9000
MAX_CHUNKS = 8


def _strip_to_json_start(raw_text: str) -> str:
    """Strip markdown code fences / any preamble before the JSON begins."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned.strip())
    cleaned = re.sub(r"```$", "", cleaned.strip())
    cleaned = cleaned.strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        if start != -1:
            cleaned = cleaned[start:]
    return cleaned


def _extract_json(raw_text: str) -> Any:
    """Parse the first JSON object out of a model response. Uses raw_decode
    (not json.loads) so trailing commentary after the JSON doesn't break
    parsing - only an actually truncated/malformed object raises."""
    cleaned = _strip_to_json_start(raw_text)
    obj, _ = json.JSONDecoder().raw_decode(cleaned)
    return obj


def _repair_truncated_json(raw_text: str) -> str:
    """Best-effort repair for a response that got cut off mid-generation
    (e.g. hit the token limit mid-string or mid-object). Rather than trying
    to guess how to close a half-written field - which can produce
    plausible-looking but wrong JSON - this walks the text and remembers the
    last point where a full element had just been completed (right before a
    top-level comma), then closes brackets from there. Worst case it drops
    the one in-progress item that got cut off; it never fabricates data."""
    text = _strip_to_json_start(raw_text)
    stack: list = []
    in_string = False
    escape = False
    last_safe_cut = None  # (index, stack snapshot at that point)

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
        elif ch == "," and stack:
            last_safe_cut = (i, list(stack))

    closers = {"{": "}", "[": "]"}

    if last_safe_cut is None:
        # Nothing to safely cut back to. If we're still mid-string, terminate
        # it so at least a partial value survives; then close whatever's open.
        cut_text = text + '"' if in_string else text
        cut_text = re.sub(r'[,:]\s*$', "", cut_text)
        remaining = list(stack)
        while remaining:
            cut_text += closers[remaining.pop()]
        return cut_text

    idx, snapshot = last_safe_cut
    cut_text = text[:idx]
    remaining = list(snapshot)
    while remaining:
        cut_text += closers[remaining.pop()]
    return cut_text


def _chat_json(system_prompt: str, user_prompt: str, max_tokens: int) -> dict:
    def call(tokens: int):
        try:
            return client.chat.completions.create(
                model=MODEL,
                max_tokens=tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception:
            return client.chat.completions.create(
                model=MODEL,
                max_tokens=tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

    response = call(max_tokens)
    choice = response.choices[0]
    raw_text = choice.message.content or ""

    try:
        return _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError):
        pass

    # If the model actually ran out of room, retrying with more headroom
    # fixes it properly instead of just salvaging a partial response.
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "length" and max_tokens < 8000:
        bigger = min(max_tokens * 2, 8000)
        response = call(bigger)
        raw_text = response.choices[0].message.content or ""
        try:
            return _extract_json(raw_text)
        except (ValueError, json.JSONDecodeError):
            pass

    # Last resort: repair whatever we got rather than fail the whole stage.
    try:
        return _extract_json(_repair_truncated_json(raw_text))
    except (ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"The model's response wasn't valid JSON and couldn't be repaired: {e}"
        ) from e


def _chat_text(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, max_chunks: int = MAX_CHUNKS) -> list:
    """Split text into paragraph-aware chunks so long material still gets
    fully covered instead of silently cut off at some character limit."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) > chunk_size:
                for i in range(0, len(para), chunk_size):
                    chunks.append(para[i : i + chunk_size])
                current = ""
            else:
                current = para
    if current:
        chunks.append(current)

    if len(chunks) > max_chunks:
        head = chunks[: max_chunks - 1]
        tail = "\n\n".join(chunks[max_chunks - 1 :])
        head.append(tail[: chunk_size * 3])
        chunks = head

    return chunks


# ---------------------------------------------------------------------------
# Stage 1 (map): per-chunk concept extraction
# ---------------------------------------------------------------------------

CHUNK_EXTRACT_SYSTEM_PROMPT = """You are helping build a comprehensive study guide. You will be \
given ONE excerpt (part of a larger document). Extract every distinct concept, term, or idea a \
student would need to know from THIS excerpt to be tested on it — be exhaustive, not just the \
headline ideas. A missed topic here means a student is unprepared for a question on the exam, \
so err on the side of including more, minor concepts rather than fewer.

Respond with ONLY a JSON object of this shape, no markdown fences, no commentary:
{
  "concepts": [
    { "title": "short concept name", "description": "1-2 sentence plain-language explanation" }
  ]
}
"""


def extract_chunk_concepts(chunk: str, chunk_index: int, total_chunks: int) -> dict:
    user_prompt = (
        f"Excerpt {chunk_index + 1} of {total_chunks} from the source material:\n\n{chunk}"
    )
    return _chat_json(CHUNK_EXTRACT_SYSTEM_PROMPT, user_prompt, max_tokens=3000)


# ---------------------------------------------------------------------------
# Stage 2 (reduce): synthesize the final concept map + summary
# ---------------------------------------------------------------------------

SYNTHESIZE_SYSTEM_PROMPT = """You are an expert study-skills tutor building the final version of a \
student's study kit. You are given (a) a raw, possibly-duplicated list of concepts extracted from \
every part of a longer document, and (b) a sample of the original text for tone and grounding.

Your job: merge and deduplicate the raw concept list into a clean, well-organized concept map, and \
write a cheat-sheet summary. CRITICAL: every distinct topic in the raw list must be represented \
somewhere in your final concept map — do not drop minor concepts for the sake of brevity. If two \
entries clearly describe the same idea, merge them into one; if they are genuinely different, keep \
both, even if there end up being many concepts. Comprehensive coverage matters more than a short list \
— a student's grade depends on nothing being missed.

Respond with ONLY a JSON object of this shape, no markdown fences, no commentary:
{
  "title": "short descriptive title for this material",
  "summary": "a 150-300 word cheat-sheet summary a student could review in a few minutes before an exam, covering every major topic",
  "concepts": [
    {
      "id": "c1",
      "title": "short concept name",
      "description": "1-2 sentence plain-language explanation",
      "parent_id": null
    }
  ]
}

Use parent_id to show genuine hierarchy (e.g. a broad theory as the parent of specific mechanisms \
under it). Most concepts can have parent_id: null if the material is fairly flat.
"""


def synthesize_kit(chunk_concept_lists: list, source_sample: str) -> dict:
    raw_dump = json.dumps(
        {"raw_concepts_by_excerpt": chunk_concept_lists}, ensure_ascii=False, indent=1
    )
    user_prompt = (
        f"Raw concepts extracted from every part of the document:\n{raw_dump}\n\n"
        f"Sample of the original source text (for tone/grounding):\n{source_sample}"
    )
    return _chat_json(SYNTHESIZE_SYSTEM_PROMPT, user_prompt, max_tokens=5000)


# ---------------------------------------------------------------------------
# Stage 3: flashcards
# ---------------------------------------------------------------------------

FLASHCARDS_SYSTEM_PROMPT = """You are generating spaced-repetition flashcards from a finalized \
concept map. Every concept listed must be covered by at least one flashcard — more for concepts \
whose description suggests they're complex or have multiple parts. Missing a concept here means a \
student won't get to practice it, so be thorough rather than minimal.

Respond with ONLY a JSON object, no markdown fences, no commentary:
{
  "flashcards": [
    { "question": "a specific, testable question", "answer": "a concise, correct answer", "concept_id": "c1" }
  ]
}
"""


def generate_flashcards(concepts: list, summary: str) -> dict:
    user_prompt = (
        f"Summary:\n{summary}\n\nConcepts (cover every one):\n"
        f"{json.dumps(concepts, ensure_ascii=False, indent=1)}"
    )
    return _chat_json(FLASHCARDS_SYSTEM_PROMPT, user_prompt, max_tokens=3500)


# ---------------------------------------------------------------------------
# Stage 4: multiple-choice quiz
# ---------------------------------------------------------------------------

QUIZ_SYSTEM_PROMPT = """You are generating a multiple-choice quiz from a finalized concept map. \
Every concept listed must be tested by at least one question — this quiz is how a student finds \
out what they don't know yet, so skipping a concept means they go into an exam blind on it. Favor \
questions that require applying or distinguishing ideas over pure recall. Distractors (wrong \
options) should be plausible, not obviously wrong.

Respond with ONLY a JSON object, no markdown fences, no commentary:
{
  "quiz": [
    {
      "question": "...",
      "options": ["option A", "option B", "option C", "option D"],
      "correct_index": 0,
      "concept_id": "c1"
    }
  ]
}
"""


def generate_quiz(concepts: list, summary: str) -> dict:
    user_prompt = (
        f"Summary:\n{summary}\n\nConcepts (test every one):\n"
        f"{json.dumps(concepts, ensure_ascii=False, indent=1)}"
    )
    return _chat_json(QUIZ_SYSTEM_PROMPT, user_prompt, max_tokens=4000)


# ---------------------------------------------------------------------------
# Stage 5: short-answer / free-response questions
# ---------------------------------------------------------------------------

SHORT_ANSWER_SYSTEM_PROMPT = """You are generating short-answer (free-response) study questions \
from a finalized concept map. Unlike multiple choice, these should require the student to explain, \
compare, or apply a concept in their own words — deeper than recall. Aim for 4-8 questions spread \
across the most important concepts (you don't need one per concept here; pick the ones that most \
reward being able to explain them). For each question, include a model answer that will be used to \
grade the student's own response later, covering the key points a correct answer must include.

Respond with ONLY a JSON object, no markdown fences, no commentary:
{
  "short_answer": [
    { "question": "...", "model_answer": "the key points a strong answer should cover", "concept_id": "c1" }
  ]
}
"""


def generate_short_answer_questions(concepts: list, summary: str) -> dict:
    user_prompt = (
        f"Summary:\n{summary}\n\nConcepts:\n{json.dumps(concepts, ensure_ascii=False, indent=1)}"
    )
    return _chat_json(SHORT_ANSWER_SYSTEM_PROMPT, user_prompt, max_tokens=2500)


# ---------------------------------------------------------------------------
# Follow-up Q&A ("Ask" tab)
# ---------------------------------------------------------------------------

ASK_SYSTEM_PROMPT = """You are a patient, encouraging study tutor. A student is asking a follow-up \
question about material they're studying. Answer clearly and directly, grounded ONLY in the source \
material and summary provided. If the material doesn't cover something the student asks about, say \
so honestly rather than inventing an answer. Keep answers focused — a few sentences to a short \
paragraph, not an essay, unless the question genuinely requires more.
"""


def answer_followup_question(
    source_text: str, summary: str, question: str, prior_qa: Optional[list] = None
) -> str:
    trimmed_source = source_text[:40000]
    history_block = ""
    if prior_qa:
        recent = prior_qa[-4:]
        history_block = "\n\nRecent Q&A on this material (for context):\n" + "\n".join(
            f"Q: {qa['question']}\nA: {qa['answer']}" for qa in recent
        )

    user_prompt = (
        f"Source material:\n{trimmed_source}\n\nSummary:\n{summary}{history_block}\n\n"
        f"Student's question: {question}"
    )
    return _chat_text(ASK_SYSTEM_PROMPT, user_prompt, max_tokens=700)


# ---------------------------------------------------------------------------
# Targeted re-explanation (used by the MCQ quiz on a wrong answer)
# ---------------------------------------------------------------------------

EXPLAIN_SYSTEM_PROMPT = """You are a patient, encouraging tutor. A student just answered a \
quiz question incorrectly. Re-explain the specific concept they missed, grounded ONLY in the \
source material provided, addressing their likely misunderstanding — not a generic definition.

Respond with ONLY a JSON object, no markdown fences, no commentary:
{
  "explanation": "a focused, 3-5 sentence re-explanation targeting the misunderstanding",
  "analogy": "one short concrete analogy or example that makes the concept stick"
}
"""


def generate_targeted_explanation(
    source_text: str,
    concept_title: str,
    concept_description: str,
    question: str,
    student_answer: str,
    correct_answer: str,
) -> dict:
    trimmed = source_text[:40000]
    user_prompt = f"""Source material:
{trimmed}

Concept being tested: {concept_title} — {concept_description}
Quiz question: {question}
Student's (incorrect) answer: {student_answer}
Correct answer: {correct_answer}

Re-explain this concept for the student, addressing why their answer likely felt right but wasn't."""
    return _chat_json(EXPLAIN_SYSTEM_PROMPT, user_prompt, max_tokens=600)


# ---------------------------------------------------------------------------
# Short-answer grading ("Short answer" tab)
# ---------------------------------------------------------------------------

GRADE_SYSTEM_PROMPT = """You are a fair, encouraging tutor grading a student's short-answer \
response against a model answer. Judge whether the student's answer captures the key points, not \
whether the wording matches exactly. Be specific about what they got right and what's missing.

Respond with ONLY a JSON object, no markdown fences, no commentary:
{
  "verdict": "correct" | "partial" | "incorrect",
  "feedback": "2-4 sentences: what they got right, what's missing or wrong, and the key point to remember"
}
"""


def grade_short_answer(question: str, model_answer: str, student_answer: str) -> dict:
    user_prompt = (
        f"Question: {question}\n\nModel answer (key points expected): {model_answer}\n\n"
        f"Student's answer: {student_answer}"
    )
    return _chat_json(GRADE_SYSTEM_PROMPT, user_prompt, max_tokens=500)