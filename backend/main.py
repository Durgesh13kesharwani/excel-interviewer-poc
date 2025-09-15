import os
import re
import uuid
import json
import time
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv

# Load env
load_dotenv()

# FastAPI and OpenAI
app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

# CORS (open during local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------ Config ------------
INTERVIEWER_REQUIRED_SKILLS = [
    "excel", "formulas", "functions", "pivot tables", "charts",
    "data cleaning", "power query", "lookup", "index-match",
    "dynamic arrays", "vba", "macros", "goal seek", "solver"
]
MAX_QUESTIONS = 10
SKILL_MATCH_THRESHOLD = 7.0
QUESTION_TIME_LIMIT_SEC = 120
CHEATING_THRESHOLD = 0.75
CONFIDENCE_MIN = 0.4
REQUIRED_SKILL_PASS_MIN = 6.5
SOFT_SKILL_PASS_MIN = 5.5

# ------------ State ------------
interview_sessions: Dict[str, Dict[str, Any]] = {}

# ------------ Models ------------
class StartRequest(BaseModel):
    candidate_name: str = Field(..., example="Jane Doe")
    resume_text: str = Field(
        "Excel resume unavailable (demo). Skills: Excel, Pivot Tables, LOOKUP, Power Query, Charts, SUMIFS.",
        description="Plain-text resume pasted by candidate"
    )
    role: str = Field("Analyst")
    level: str = Field("Intermediate")

class SubmitRequest(BaseModel):
    session_id: str
    answer: str

# Show validation detail in dev
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body}),
    )

# ------------ Utils ------------
def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s\-\+\./]", " ", text.lower())

def extract_resume_skills(resume_text: str) -> List[str]:
    text = normalize(resume_text)
    known = [
        "excel","microsoft excel","vlookup","xlookup","index match","index-match",
        "pivot","pivot table","pivot tables","power query","powerpivot","power pivot",
        "charts","charting","dashboards","macros","vba","solver","goal seek",
        "dynamic arrays","filter","unique","sort","sumifs","countifs","iferror",
        "data cleaning","data validation","conditional formatting","what-if analysis"
    ]
    detected = set()
    for k in known:
        k_norm = normalize(k)
        if k_norm in text:
            if k in ["vlookup","xlookup","index match","index-match"]:
                detected.add("lookup")
            elif k in ["pivot","pivot table","pivot tables"]:
                detected.add("pivot tables")
            elif k in ["powerpivot","power pivot"]:
                detected.add("power query")
            else:
                detected.add(k_norm.strip())
    if "excel" in text or "microsoft excel" in text:
        detected.add("excel")
    return sorted(detected)

def top_required_overlap(resume_skills: List[str], required: List[str], top_n: int = 10) -> Dict[str, Any]:
    required_lower = [normalize(x).strip() for x in required]
    resume_lower = [normalize(x).strip() for x in resume_skills]
    matched = list(set(required_lower).intersection(set(resume_lower)))
    overlap = len(matched)
    denom = min(top_n, len(required_lower))
    score_10 = (overlap / max(1, denom)) * 10.0
    return {"overlap": overlap, "score_10": round(score_10, 2), "matched": matched}

# ------------ LLM helpers ------------
def call_llm_json(messages: List[Dict[str, str]], model: str = "gpt-4o-mini", temperature: float = 0.0) -> Dict[str, Any]:
    if not client.api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    sys = {"role": "system", "content": "Return only a single valid JSON object. No extra text."}
    resp = client.chat.completions.create(
        model=model,
        messages=[sys] + messages,
        temperature=temperature,
        response_format={"type": "json_object"}
    )
    content = resp.choices[0].message.content
    return json.loads(content)

def generate_questions_from_resume(resume_text: str, role: str, level: str, matched_skills: List[str]) -> List[Dict[str, Any]]:
    try:
        sys = (
            f"Generate concise Excel interview questions for a {role} at {level} level. "
            "Include both multiple_choice and open_ended. MCQs must have one correct_answer and 3-4 options. "
            "Open-ended must include a rubric {criteria[], weights[], exemplar?}. "
            "Focus first on the matched skills; also ask about projects/experience with measurable impact. "
            "Every question MUST have a non-empty 'text' field describing the question clearly. "
            'Return JSON as {"questions":[{...}]}' 
        )
        user = (
            f"Resume text:\n{resume_text}\n\n"
            f"Matched resume skills: {', '.join(matched_skills)}\n"
            f"Create up to {MAX_QUESTIONS} questions."
        )
        obj = call_llm_json(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            model="gpt-4o-mini",
            temperature=0.1
        )
        questions = obj.get("questions", [])
        out = []
        for i, q in enumerate(questions, start=1):
            text = q.get("text", "").strip()
            if not text:  # Skip invalid questions without text
                continue
            qt = q.get("type", "open_ended")
            item = {
                "id": i,
                "type": qt,
                "text": text,
                "skill": q.get("skill", "general"),
            }
            if qt == "multiple_choice":
                item["options"] = q.get("options", [])
                item["correct_answer"] = q.get("correct_answer", "").strip()
            else:
                item["rubric"] = q.get(
                    "rubric",
                    {"criteria": ["correctness","clarity","best practices"], "weights": [0.5,0.3,0.2], "exemplar": ""}
                )
            out.append(item)
            if len(out) >= MAX_QUESTIONS:
                break
        if out:
            return out
    except Exception as e:
        print(f"LLM question generation error: {e}")
        pass
    # Fallback static bank (if LLM fails or no valid questions)
    return [
        {
            "id": 1,
            "type": "multiple_choice",
            "text": "What is the main advantage of XLOOKUP over VLOOKUP?",
            "options": [
                "A) Only vertical lookups",
                "B) Requires sorted data",
                "C) Looks left/right and resists column insertions",
                "D) Always approximate"
            ],
            "correct_answer": "C",
            "skill": "lookup"
        },
        {
            "id": 2,
            "type": "open_ended",
            "text": "Describe the steps to build a Pivot Table for total sales by Category and Region.",
            "rubric": {"criteria": ["data_selection","insert_pivot","field_assignment"], "weights": [0.3,0.3,0.4], "exemplar": ""},
            "skill": "pivot tables"
        }
    ]

def grade_open_answer_rubric(question_text: str, candidate_answer: str, rubric: Dict[str, Any]) -> Dict[str, Any]:
    try:
        obj = call_llm_json(
            messages=[
                {"role": "system", "content": "Score strictly against the rubric. Return only JSON."},
                {"role": "user", "content":
                 f"Question: {question_text}\nRubric criteria: {rubric.get('criteria')}\n"
                 f"Rubric weights: {rubric.get('weights')}\nExemplar: {rubric.get('exemplar','')}\n"
                 f"Candidate answer: {candidate_answer}\n"
                 'Return JSON: {"scores":[..0-1..],"total":0-1,"comments":"brief","confidence":0-1}'}
            ],
            model="gpt-4o-mini",
            temperature=0.0
        )
        if "scores" in obj and "total" in obj:
            return obj
    except Exception as e:
        print(f"LLM grading error: {e}")
        pass
    return {"scores": [0.0]*len(rubric.get("criteria", [])), "total": 0.0, "comments": "Grader unavailable.", "confidence": 0.5}

# ------------ API ------------
@app.get("/")
def read_root():
    return {"message": "AI Excel Interviewer API is running."}

@app.post("/start")
def start_interview(request: StartRequest):
    session_id = str(uuid.uuid4())
    resume_skills = extract_resume_skills(request.resume_text)
    overlap = top_required_overlap(resume_skills, INTERVIEWER_REQUIRED_SKILLS, top_n=10)

    if overlap["score_10"] < SKILL_MATCH_THRESHOLD:
        reason = f"Insufficient skill overlap for {request.role}. Matched {overlap['overlap']} skills; need >= {int(SKILL_MATCH_THRESHOLD)} out of 10."
        interview_sessions[session_id] = {
            "candidate_name": request.candidate_name,
            "role": request.role,
            "level": request.level,
            "resume_text": request.resume_text,
            "resume_skills": resume_skills,
            "required_overlap": overlap,
            "questions": [],
            "current_question_index": -1,
            "answers": [],
            "blocked": True,
            "greeting": f"Hello {request.candidate_name}, thanks for sharing the resume. {reason}",
            "cheating_signals": [],
            "soft_skill_observations": [],
            "question_start_time": None
        }
        return {"session_id": session_id, "greeting": interview_sessions[session_id]["greeting"], "blocked": True, "reason": reason}

    questions = generate_questions_from_resume(request.resume_text, request.role, request.level, overlap["matched"])
    if not questions or len(questions) == 0:
        questions = [
            {
                "id": 1,
                "type": "multiple_choice",
                "text": "What is the main advantage of XLOOKUP over VLOOKUP?",
                "options": [
                    "A) Only vertical lookups",
                    "B) Requires sorted data",
                    "C) Looks left/right and resists column insertions",
                    "D) Always approximate"
                ],
                "correct_answer": "C",
                "skill": "lookup"
            }
        ]

    # Ensure at least one question
    if not questions:
        questions = [{
            "id": 1,
            "type": "multiple_choice",
            "text": "What is the main advantage of XLOOKUP over VLOOKUP?",
            "options": [
                "A) Only vertical lookups",
                "B) Requires sorted data",
                "C) Looks left/right and resists column insertions",
                "D) Always approximate"
            ],
            "correct_answer": "C",
            "skill": "lookup"
        }]

    interview_sessions[session_id] = {
        "candidate_name": request.candidate_name,
        "role": request.role,
        "level": request.level,
        "resume_text": request.resume_text,
        "resume_skills": resume_skills,
        "required_overlap": overlap,
        "questions": questions,
        "current_question_index": 0,
        "answers": [],
        "blocked": False,
        "cheating_signals": [],
        "soft_skill_observations": [],
        "question_start_time": time.time()
    }

    greeting = (
        f"Hello {request.candidate_name}! This is an Excel interview for the {request.role} role "
        f"({request.level}). You'll answer up to {len(questions)} questions tailored to the resume. "
        f"Each question has a {QUESTION_TIME_LIMIT_SEC//60} minute time limit."
    )
    first_question = questions[0]
    return {"session_id": session_id, "greeting": greeting, "question": first_question, "time_limit_sec": QUESTION_TIME_LIMIT_SEC}

@app.post("/submit")
def submit_answer(request: SubmitRequest):
    if request.session_id not in interview_sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    session = interview_sessions[request.session_id]
    if session.get("blocked"):
        return {"feedback": "Interview gated due to low skill overlap. Session ended.", "summary": generate_summary(session)}

    idx = session["current_question_index"]
    if idx < 0 or idx >= len(session["questions"]):
        return {"feedback": "Interview already completed.", "summary": generate_summary(session)}

    q = session["questions"][idx]
    answer_text = request.answer.strip()

    # Timer
    started_at = session.get("question_start_time")
    timed_out = started_at is not None and (time.time() - started_at) > QUESTION_TIME_LIMIT_SEC

    feedback = ""
    is_correct = False
    per_question_score = 0.0
    confidence = 0.6
    cheating_score = 0.0

    if timed_out:
        feedback = "Skipped due to time limit."
        confidence = 0.5
    else:
        if len(answer_text) > 1200:
            cheating_score += 0.2
        if "http://" in answer_text or "https://" in answer_text:
            cheating_score += 0.2
        if answer_text.count("\n") > 30:
            cheating_score += 0.1

        if q["type"] == "multiple_choice":
            correct = q.get("correct_answer", "").strip().upper()
            candidate = answer_text[:1].upper()
            is_correct = candidate == correct[:1]
            per_question_score = 1.0 if is_correct else 0.0
            feedback = "Correct." if is_correct else f"Incorrect. Correct answer is {correct}."
            if len(answer_text) < 6:
                session["soft_skill_observations"].append("Concise on MCQ.")
            else:
                session["soft_skill_observations"].append("Verbose on MCQ.")
        else:
            rubric = q.get("rubric", {"criteria": ["correctness","clarity","best_practices"], "weights": [0.5,0.3,0.2], "exemplar": ""})
            res = grade_open_answer_rubric(q["text"], answer_text, rubric)
            per_question_score = float(res.get("total", 0.0))
            feedback = f"{res.get('comments','')}"

            confidence = float(res.get("confidence", 0.6))
            is_correct = per_question_score >= 0.6
            if len(answer_text.split(".")) >= 3:
                session["soft_skill_observations"].append("Structured explanation.")
            else:
                session["soft_skill_observations"].append("Brief explanation.")
            if confidence < 0.4 and len(answer_text) > 800:
                cheating_score += 0.2

    session["answers"].append({
        "question_id": q["id"],
        "type": q["type"],
        "skill": q.get("skill", "general"),
        "answer": "" if timed_out else answer_text,
        "is_correct": is_correct,
        "score": per_question_score,
        "feedback": feedback,
        "confidence": confidence,
        "cheating_delta": cheating_score,
        "timed_out": timed_out
    })

    # advance
    next_index = idx + 1
    if next_index < len(session["questions"]):
        session["current_question_index"] = next_index
        session["cheating_signals"].append(cheating_score)
        session["question_start_time"] = time.time()
        return {"feedback": feedback, "next_question": session["questions"][next_index], "time_limit_sec": QUESTION_TIME_LIMIT_SEC}
    else:
        session["cheating_signals"].append(cheating_score)
        session["question_start_time"] = None
        summary = generate_summary(session)
        return {"feedback": feedback, "summary": summary}

# ------------ Evaluation ------------
def evaluation(session: Dict[str, Any]) -> Dict[str, Any]:
    answers = session.get("answers", [])
    skill_scores: Dict[str, List[float]] = {}
    for a in answers:
        skill_scores.setdefault(a.get("skill","general"), []).append(float(a.get("score",0.0)))

    required_norm = []
    for skill, scores in skill_scores.items():
        val = sum(scores) / max(1, len(scores))
        if skill in [normalize(s) for s in INTERVIEWER_REQUIRED_SKILLS] or skill in (
            "lookup","pivot tables","dynamic arrays","power query","vba","solver","data cleaning","formulas","functions","charts"
        ):
            required_norm.append(val)
    required_avg = (sum(required_norm)/max(1,len(required_norm))) if required_norm else 0.0
    required_skill_score_10 = round(required_avg*10.0,2)

    obs = session.get("soft_skill_observations", [])
    soft_points = 0.0
    for o in obs:
        if "Structured" in o or "Concise" in o:
            soft_points += 1.0
        elif "Verbose" in o or "Brief" in o:
            soft_points += 0.5
    soft_skills_score_10 = round(min(10.0, (soft_points / max(1,len(obs))) * 10.0), 2) if obs else 6.0

    confidences = [float(a.get("confidence",0.6)) for a in answers]
    avg_conf = sum(confidences)/max(1,len(confidences)) if confidences else 0.6
    confidence_score_10 = round(avg_conf*10.0,2)

    ch = session.get("cheating_signals", [])
    cheating = min(1.0, sum(ch)) if ch else 0.0

    passed = (
        (required_skill_score_10 >= REQUIRED_SKILL_PASS_MIN) and
        (soft_skills_score_10 >= SOFT_SKILL_PASS_MIN) and
        (avg_conf >= CONFIDENCE_MIN) and
        (cheating <= CHEATING_THRESHOLD)
    )

    return {
        "required_skill_score_10": required_skill_score_10,
        "soft_skills_score_10": soft_skills_score_10,
        "confidence_score_10": confidence_score_10,
        "cheating_score_0_1": round(cheating, 2),
        "passed": bool(passed)
    }

def generate_summary(session: Dict[str, Any]) -> str:
    total_q = len(session.get("questions", []))
    correct_like = sum(1 for a in session.get("answers", []) if a.get("score",0.0) >= 0.6)
    eval_res = evaluation(session)

    lines = []
    lines.append(f"Interview Summary for {session.get('candidate_name','Candidate')}")
    lines.append("")
    lines.append(f"Questions answered: {len(session.get('answers',[]))}/{total_q}")
    lines.append(f"Approx. correct/strong answers: {correct_like}/{total_q}")
    lines.append("")
    lines.append("Per-question feedback:")
    for a in session.get("answers", []):
        to_flag = " (timeout)" if a.get("timed_out") else ""
        lines.append(f"- Q{a['question_id']} [{a.get('skill','general')}]: score={round(a.get('score',0.0),2)}{to_flag} | {a.get('feedback','')}")
    lines.append("")
    lines.append("Aggregate ratings (out of 10 unless noted):")
    lines.append(f"- Required skills: {eval_res['required_skill_score_10']}")
    lines.append(f"- Soft skills: {eval_res['soft_skills_score_10']}")
    lines.append(f"- Confidence: {eval_res['confidence_score_10']}")
    lines.append(f"- Cheating indicator (0..1, lower is better): {eval_res['cheating_score_0_1']}")
    lines.append("")
    lines.append(f"Final decision: {'PASS' if eval_res['passed'] else 'FAIL'}")
    lines.append("")
    if not eval_res["passed"]:
        lines.append("Recommendation: Focus on interviewer-required areas and provide clearer, structured reasoning on open-ended tasks. Reduce reliance on external references and keep answers concise.")
    else:
        lines.append("Recommendation: Candidate meets requirements; proceed to next stage.")
    return "\n".join(lines)