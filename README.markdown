# AI Excel Interviewer (with Proctoring, Voice Input, LLM Grading)

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://example.com/build)  
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)  
[![Version: 1.0.0](https://img.shields.io/badge/version-1.0.0-orange.svg)](https://example.com)

An end-to-end mock interview system for Excel roles that parses resume text, gates candidates on required skill overlap, generates tailored questions with an LLM, grades open-ended answers against a rubric, tracks soft skills, confidence and cheating indicators, and produces a final pass/fail decision. The frontend includes proctoring (camera, mic, screen share), voice transcription for answers, and a clean chat-style UI for the interview flow.

## Why this project
Recruiters and teams need a scalable way to quickly evaluate Excel proficiency aligned with role requirements while minimizing interviewer load and candidate bias. This app automates resume skill matching, adaptive question generation, structured answer evaluation, and summary feedback, with a smooth candidate experience and basic proctoring.

## Key Features
- **Resume-driven interview gating**: Parses resume text, extracts Excel skills, and compares with a required-skill set; blocks if overlap is below threshold.
- **LLM-tailored questions**: Generates up to 10 role/level questions (MCQ + open-ended) via Chat Completions with JSON-mode to return structured question objects reliably.
- **Rubric-based grading**: Open-ended answers are evaluated by rubric criteria and weights with structured scoring; MCQs are auto-scored.
- **Confidence, soft skills, and cheating indicators**: Tracks structured vs verbose answers, grader confidence, length/links/format hints for potential cheating.
- **Timed questions**: Server-side per-question timer (default 120s) with skip on timeout.
- **Proctoring in the browser**: Camera and mic indicators; optional screen sharing (user consent).
- **Voice input**: Speech recognition to capture answers where supported; falls back gracefully when not available.
- **Final summary and decision**: Weighted scores and thresholds yield pass/fail plus constructive feedback and ratings out of 10.

## Tech Stack
- **Backend**: FastAPI + Uvicorn (ASGI), OpenAI Chat Completions API.
- **Frontend**: Vanilla JS + Web APIs (MediaDevices, Screen Capture, Web Speech), Tailwind-like utility classes in CSS.
- **Model I/O**: JSON mode for structured outputs with `response_format={"type":"json_object"}` to ensure valid JSON parsing.

## Architecture Overview
- **Start flow**: Frontend sends `candidate_name`, `role`, `level`, and optional `resume_text` (backend has a safe default). Backend extracts resume skills, computes overlap with required skills, gates or proceeds. Returns `session_id`, `greeting`, and the first question.
- **Iterative Q/A**: For each submitted answer, backend evaluates (MCQ vs rubric), tracks signals, and returns `next_question` or final `summary`; server enforces the per-question timer.
- **LLM integration**: All generation and grading requests enforce JSON-mode for stable parsing, then normalized to a consistent internal schema. If the API fails or key is missing, a small static fallback bank is used to guarantee flow.

## Project Structure
- `backend/main.py`: FastAPI app, endpoints, resume parsing, overlap gating, question generation, grading, timers, evaluation, summary.
- `frontend/index.html`, `style.css`, `script.js`: UI shell, chat box, proctoring panels, speech recognition handlers, screen share toggles, fetch calls to backend.

## Installation and Running Locally

### Prerequisites
- **Python 3.10+**
- **Node/npm** (optional; static frontend runs in a simple server)
- **OpenAI API key** (optional: project falls back to static questions if missing)

### Backend (FastAPI + Uvicorn)
1. Create virtual environment and install dependencies:
   - Windows: `python -m venv .venv && . .venv/Scripts/activate`
   - macOS/Linux: `python -m venv .venv && source .venv/bin/activate`
   - `pip install fastapi uvicorn python-dotenv openai`
2. Set environment variable (PowerShell):
   - `$env:OPENAI_API_KEY="sk-..."`
3. Run:
   - `uvicorn main:app --reload`
4. Open API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to test `/start` and `/submit` interactively.

### Frontend
1. Serve the `frontend` folder via any static server:
   - Python: `python -m http.server 5500` (then open [http://127.0.0.1:5500/frontend/index.html](http://127.0.0.1:5500/frontend/index.html))
   - VS Code Live Server or similar
2. Ensure `API_URL` in `script.js` points to `http://127.0.0.1:8000`.
3. Click “Start Interview”; allow Camera/Mic (and Screen if desired). Use text input or voice input (Chrome/Edge recommended for Web Speech API).

## Configuration
- **Skill gating**:
  - `INTERVIEWER_REQUIRED_SKILLS`: Master list in `backend/main.py`
  - `SKILL_MATCH_THRESHOLD` (default 7/10): Minimum normalized overlap to proceed.
- **Questions and timing**:
  - `MAX_QUESTIONS` (default 10)
  - `QUESTION_TIME_LIMIT_SEC` (default 120)
- **Evaluation thresholds**:
  - `REQUIRED_SKILL_PASS_MIN`, `SOFT_SKILL_PASS_MIN`, `CONFIDENCE_MIN`, `CHEATING_THRESHOLD` in `backend/main.py`
- **JSON mode (LLM)**:
  - Backend calls use `response_format={"type": "json_object"}` and parse `choices.message.content`.

## Notable Implementation Choices
- **JSON-mode for structured outputs**: Using `response_format` constrains the model to valid JSON, reducing runtime parsing errors vs prompt-only enforcement.
- **Defensive fallbacks**: If the OpenAI key is missing or the API errors, a static bank ensures the app stays usable for demos/tests.
- **Proctoring via Web APIs only**: No server-side uploads—browser permissions indicate camera/mic/screen activity; grants a good UX with minimal compliance complexity.
- **Voice input via Web Speech Recognition**: Best supported on Chromium browsers; UI disables or falls back when unsupported or permission denied.

## Usage Flow
- **Start**: Candidate clicks Start; backend gates on resume_skill overlap (default resume text provided for quick demos).
- **Interview**: Mixed MCQ + open-ended questions tailored to resume skills and role/level. Timer enforced per question.
- **Grading and signals**: MCQ exact key match; open-ended rubric returns per-criterion scores, total, comments, and confidence. Length/links/newlines tracked for cheating signal; brief/structured text contributes to soft skills signal.
- **Summary**: Aggregate ratings out of 10 for required skills, soft skills, confidence; cheating score in [0..1]; pass/fail decision with recommendations.

## Troubleshooting
- **“Question undefined” in UI**: This occurs when the backend returns a list for `question` or malformed JSON. Ensure `first_question = questions[0]` (single object), and OpenAI parsing uses `choices[0].message.content`. Add `console.log` of the response in the frontend before rendering.
- **422 Unprocessable Entity on /start**: The backend expects `candidate_name`, `role`, `level`, and `resume_text` (has a default). Ensure JSON body keys match and `content-type` is `application/json` or use Swagger UI to test.
- **500 errors from OpenAI call**: Verify `OPENAI_API_KEY` is set and code uses `choices[0].message.content`; JSON mode requires `response_format={"type":"json_object"}` and a compatible model. The app falls back to static questions if API is missing/unavailable.

## Security and Privacy
- Proctoring uses browser APIs only; no video/audio is uploaded to the server in this reference implementation. Permissions can be revoked per browser session.
- Voice recognition may rely on browser/cloud services; show a prompt/warning and allow text input as fallback.

## Roadmap / Future Scope
- Richer rubric library by skill (pivot tables, dynamic arrays, Power Query, VBA) for more consistent scoring across roles.
- Follow-up question generation based on previous answers to probe depth and confidence per skill domain.
- Multi-round interviews and interviewer review portal with calibration tools and analytics dashboards (time-to-answer, hesitation, topic drift).
- CI/CD with tests, coverage, and auto-generated API docs; badges at README top (build, license, version).
- Pluggable LLMs and on-prem embeddings; fallback to local models where compliance requires.
- Accessibility: extended ARIA roles, keyboard-only flow, and TTS for questions.

## Contributing
- Fork and PRs welcome. Please open issues for bugs or feature requests and follow conventional commit messages. Include steps to reproduce for bug reports.

## License
This project is licensed under the [MIT License](LICENSE).

## Quick Commands
- Backend: `uvicorn main:app --reload`
- Frontend: `python -m http.server 5500` (or any static server)
- Swagger docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### References
- [FastAPI Getting Started](https://fastapi.tiangolo.com/)
- [Uvicorn Quick Start](https://www.uvicorn.org/)
- [OpenAI JSON Mode](https://platform.openai.com/docs/guides/text-generation/json-mode)
- [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [MediaDevices API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices)