# StudyForge

**Raw material in. Tempered mastery out.**

StudyForge turns a lecture transcript, reading, or set of notes into a full,
adaptive study kit: a cheat-sheet summary, a concept map, flashcards, a
multiple-choice quiz, short-answer practice, and a place to ask follow-up
questions — all grounded in your actual source material, with a live
mastery gauge per concept.

Built for the August AI Challenge.

## Why this exists

College students don't lack study material — they're drowning in it.
Turning three hours of lecture into something you can actually study from
takes real work: figuring out what matters, testing yourself on it in more
than one way, and knowing what to review when you get something wrong.
StudyForge automates that pipeline and closes the loop.

## What's in the kit

- **Cheat sheet** — a 150-300 word summary covering every major topic.
- **Concept map** — a hierarchy of every concept in the material, each with
  a live mastery gauge (ember = untested, steel = missed, tempered green =
  mastered) that updates as you answer questions.
- **Flashcards** — at least one per concept.
- **Quiz** — multiple choice, every concept tested at least once. Get a
  question wrong and StudyForge generates a targeted re-explanation on the
  spot, grounded in your source material, plus an analogy — then lets you
  retry just the concepts you missed.
- **Short answer** — free-response questions that ask you to explain ideas
  in your own words, graded against a model answer with specific feedback
  on what's there and what's missing.
- **Ask** — a running Q&A thread for anything the kit didn't cover, answered
  from your actual material rather than a generic response.

## Comprehensive coverage, not a highlight reel

Earlier drafts of tools like this truncate long material and only cover the
first few thousand characters — meaning a real exam could easily test
something the kit never mentioned. StudyForge instead:

1. Splits long material into paragraph-aware chunks and extracts concepts
   from **every** chunk (not just the beginning).
2. Merges those into one deduplicated concept map, explicitly instructed to
   drop nothing — every distinct topic found anywhere in the source shows
   up somewhere in the final map.
3. Generates flashcards, quiz questions, and short-answer questions with an
   explicit instruction to touch every concept, not just the "interesting"
   ones.

## Real progress, not a fake timer

Generating a kit runs as a background job with real stages — "Extracting
core concepts (part 2 of 5)", "Making sure nothing was missed", "Building
flashcards", "Writing the quiz", "Writing short-answer questions" — and the
frontend polls actual job status, so the label on screen always matches
what's actually happening on the server.

## History

Every kit you forge is saved automatically, tied to an anonymous ID stored
in your browser — no signup required. Open "My kits" any time to revisit,
continue asking questions, or delete old ones. History is per-browser; there's
no account system, so it won't follow you to a different device or browser.

## Themes

Four themes, switchable any time from the header, saved per browser:

- **Forge** — the default dark, ember/steel theme.
- **Daylight** — a light academic theme for daytime studying.
- **Midnight Focus** — a low-stimulation, near-grayscale dark theme.
- **High Contrast** — near-black/white with strong accents, for accessibility.

## Architecture

```
studykit/
  backend/
    main.py       API routes: job-based kit generation, history,
                  Ask, short-answer grading, quiz explanations
    pipeline.py    every LLM call, split into discrete stages
    db.py          SQLite persistence (kits, Q&A history)
    jobs.py         in-memory job registry for real progress polling
    requirements.txt
  frontend/        static webpage, no build step required
    index.html
    style.css       theme variables + all component styles
    app.js          identity, polling, history, all tab logic
    config.js       set your backend URL here
```

The frontend is plain HTML/CSS/JS on purpose — it opens directly in a
browser or deploys to any static host with zero build tooling.

## Running it locally

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then add your OLLAMA_API_KEY
uvicorn main:app --reload --port 8000
```

Get an Ollama Cloud API key at
[ollama.com/settings/keys](https://ollama.com/settings/keys). `.env.example`
also sets `OLLAMA_MODEL` (default `gpt-oss:20b` — try `gpt-oss:120b` for
better JSON reliability on longer material).

A SQLite file (`studyforge.db`) is created automatically on first run —
nothing else to set up.

The API is now running at `http://localhost:8000`. Check `/api/health`.

### 2. Frontend

No build step. From the `frontend/` folder:

```bash
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500`. `config.js` points at `http://localhost:8000`
by default — change `API_BASE_URL` there if your backend runs elsewhere.

## What to show in the demo video

1. Paste in a real lecture transcript or reading — ideally a longer one, to
   show the multi-part "Extracting core concepts (part X of Y)" progress.
2. Walk through the generated cheat sheet, concept map, flashcards, quiz,
   short answer, and Ask tabs.
3. Answer a quiz question wrong — show the targeted re-explanation and the
   concept's mastery gauge shift from ember to steel; answer right on a
   retry and show it turn green.
4. Submit a short-answer response and show the graded feedback.
5. Ask a follow-up question in the Ask tab.
6. Open "My kits," show the kit saved in history, and switch a theme.

## Possible stretch goals (if time allows)

- YouTube/lecture-recording transcription as an input source
- Spaced-repetition scheduling for flashcards (SM-2 algorithm)
- Export the cheat sheet as a printable PDF
- Multi-document study kits (combine several readings into one concept map)

## Tech

- **Backend:** FastAPI, `openai` Python SDK (pointed at Ollama Cloud's
  OpenAI-compatible endpoint), SQLite, pypdf
- **Frontend:** vanilla HTML/CSS/JS (Space Grotesk, Source Serif 4,
  JetBrains Mono), four CSS-variable-driven themes
- **Model:** any model available on your Ollama Cloud account
  (default `gpt-oss:20b`)
