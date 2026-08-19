"""
pipeline.py
Core AI pipeline for StudyForge.

Given raw source material (a lecture transcript, reading, or notes), this
module turns it into a structured study kit:
  1. A concept map (parent/child relationships between the key ideas)
  2. Spaced-repetition-ready flashcards
  3. A multiple-choice quiz, each question tagged to the concept it tests
  4. A short cheat-sheet summary

It also powers the adaptive loop: when a student misses a quiz question,
generate_targeted_explanation() re-explains *that specific concept*,
grounded in the original source text, instead of a generic canned response.

Talks to Ollama Cloud (https://ollama.com) through its OpenAI-compatible
/v1/chat/completions endpoint, using the `openai` Python SDK pointed at
Ollama's base URL.
"""

import json
import os
import re
from typing import Any

from openai import OpenAI

MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1")

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key=os.environ.get("OLLAMA_API_KEY", ""),
)


def _extract_json(raw_text: str) -> Any:
    """Strip markdown code fences / stray prose and parse JSON safely."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned.strip())
    cleaned = re.sub(r"```$", "", cleaned.strip())
    cleaned = cleaned.strip()
    # In case the model adds any preamble, grab the outermost {...} block.
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _chat_json(system_prompt: str, user_prompt: str, max_tokens: int) -> dict:
    """Call the model and parse a JSON object out of its response.

    Uses response_format=json_object where the model supports it (most
    current Ollama Cloud models do); falls back to prompt-only JSON
    extraction if the server rejects the parameter.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception:
        # Some models/hosts don't support response_format - retry without it.
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

    raw_text = response.choices[0].message.content or ""
    return _extract_json(raw_text)


STUDY_KIT_SYSTEM_PROMPT = """You are an expert study-skills tutor and instructional designer \
helping a college student turn raw course material into an effective study kit.

You must respond with ONLY a single JSON object. No preamble, no markdown code fences, \
no commentary before or after. The JSON must match this exact shape:

{
  "title": "short descriptive title for this material",
  "summary": "a 150-250 word cheat-sheet summary a student could review in 2 minutes before an exam",
  "concepts": [
    {
      "id": "c1",
      "title": "short concept name",
      "description": "1-2 sentence plain-language explanation",
      "parent_id": null
    }
  ],
  "flashcards": [
    {
      "question": "a specific, testable question",
      "answer": "a concise, correct answer",
      "concept_id": "c1"
    }
  ],
  "quiz": [
    {
      "question": "a multiple choice question testing understanding, not just recall",
      "options": ["option A", "option B", "option C", "option D"],
      "correct_index": 0,
      "concept_id": "c1"
    }
  ]
}

Rules:
- Identify 5-10 core concepts. Use parent_id to show real hierarchy (e.g. a broad theory \
as the parent of two specific mechanisms) — most concepts can have parent_id: null if the \
material is fairly flat, but nest wherever there is a genuine sub-idea relationship.
- Generate 8-12 flashcards spread across the concepts, not clustered on one.
- Generate 5-8 quiz questions, each tagged with the concept_id it tests. Favor questions \
that require applying or distinguishing ideas over pure memorization.
- Ground every question and flashcard directly in the provided material. Do not invent \
facts that are not supported by the source text.
- Keep language clear and student-facing, not academic jargon for its own sake.
"""


def build_study_kit(source_text: str) -> dict:
    """Call the model once to turn source material into a full study kit."""
    if len(source_text.strip()) < 40:
        raise ValueError("Source text is too short to build a meaningful study kit.")

    # Guard against extremely long uploads blowing the context / cost budget.
    trimmed = source_text[:60000]

    data = _chat_json(
        system_prompt=STUDY_KIT_SYSTEM_PROMPT,
        user_prompt=f"Here is the source material:\n\n{trimmed}",
        max_tokens=4000,
    )
    return data


EXPLAIN_SYSTEM_PROMPT = """You are a patient, encouraging tutor. A student just answered a \
quiz question incorrectly. Your job is to re-explain the specific concept they missed, \
grounded ONLY in the source material provided, in a way that addresses their likely \
misunderstanding — not a generic textbook definition.

Respond with ONLY a JSON object of this shape:
{
  "explanation": "a focused, 3-5 sentence re-explanation targeting the misunderstanding",
  "analogy": "one short concrete analogy or example that makes the concept stick",
  "try_again_question": "a new, simpler question testing the same concept, to check understanding"
}
No markdown fences, no extra commentary.
"""


def generate_targeted_explanation(
    source_text: str,
    concept_title: str,
    concept_description: str,
    question: str,
    student_answer: str,
    correct_answer: str,
) -> dict:
    """Generate a targeted re-explanation for a missed quiz concept."""
    trimmed = source_text[:60000]

    user_prompt = f"""Source material:
{trimmed}

Concept being tested: {concept_title} — {concept_description}
Quiz question: {question}
Student's (incorrect) answer: {student_answer}
Correct answer: {correct_answer}

Re-explain this concept for the student, addressing why their answer likely felt right \
but wasn't."""

    return _chat_json(
        system_prompt=EXPLAIN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=600,
    )