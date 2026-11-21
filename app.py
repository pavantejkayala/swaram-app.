import asyncio
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import urllib.parse

import edge_tts
import pypdf
import requests
from flask import Flask, jsonify, request, send_from_directory, Response

app = Flask(__name__, static_folder="static", static_url_path="")

DEFAULT_GEMINI_KEY = ""  # Set via GEMINI_API_KEY environment variable
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or DEFAULT_GEMINI_KEY
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
THINKING_BUDGET = int(os.environ.get("GEMINI_THINKING", "0"))

LANG_NAMES = {
    "te-IN": "Telugu",
    "hi-IN": "Hindi",
    "en-IN": "English",
    "ta-IN": "Tamil",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
    "pa-IN": "Punjabi",
    "ur-IN": "Urdu",
}

INTENTS = {
    "none", "open", "play", "call", "add_contact", "list_contacts", "end_call",
    "voice_lock_on", "voice_lock_off", "guest_on", "guest_off", "cancel",
    "start_quiz", "start_story", "start_game", "pronunciation", "start_lesson", "fill_form",
}

UI_CACHE = {}
TTS_CACHE = {}
CHAT_CACHE = {}
HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://translate.google.com/"
})


ACTIVE_QUIZZES = {}    # session_id -> {topic, questions, index, score}
ACTIVE_FORMS = {}      # session_id -> {fields, answers, index, lang, i18n}

# =====================================================================
# PERSISTENT SQLITE DATABASE LAYER
# =====================================================================
DB_PATH = os.path.join(os.path.dirname(__file__), "swaram.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS progress (
            session_id TEXT PRIMARY KEY,
            questions_answered INT DEFAULT 0,
            topics_learned INT DEFAULT 0,
            quiz_score INT DEFAULT 0,
            streak_days INT DEFAULT 1,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS documents (
            session_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            text_content TEXT NOT NULL,
            pages INT DEFAULT 1,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS form_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            form_data TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

init_db()

def db_get_user(username: str):
    with get_db() as conn:
        row = conn.execute("SELECT username, password_hash, name FROM users WHERE username = ?", (username.lower(),)).fetchone()
        return dict(row) if row else None

def db_create_user(username: str, password_hash: str, name: str):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO users (username, password_hash, name) VALUES (?, ?, ?)",
                     (username.lower(), password_hash, name))

def db_get_progress(session_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT questions_answered, topics_learned, quiz_score, streak_days FROM progress WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if row:
            return {
                "questionsAnswered": row["questions_answered"],
                "topicsLearned": row["topics_learned"],
                "quizScore": row["quiz_score"],
                "streakDays": row["streak_days"]
            }
        return {"questionsAnswered": 0, "topicsLearned": 0, "quizScore": 0, "streakDays": 1}

def db_save_progress(session_id: str, p: dict):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO progress (session_id, questions_answered, topics_learned, quiz_score, streak_days, last_updated)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(session_id) DO UPDATE SET
               questions_answered=excluded.questions_answered,
               topics_learned=excluded.topics_learned,
               quiz_score=excluded.quiz_score,
               streak_days=excluded.streak_days,
               last_updated=CURRENT_TIMESTAMP""",
            (
                session_id,
                int(p.get("questionsAnswered", 0)),
                int(p.get("topicsLearned", 0)),
                int(p.get("quizScore", 0)),
                int(p.get("streakDays", 1))
            )
        )

def db_get_doc(session_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT filename, text_content, pages FROM documents WHERE session_id = ?", (session_id,)).fetchone()
        if row:
            return {"filename": row["filename"], "text": row["text_content"], "pages": row["pages"]}
        return None

def db_save_doc(session_id: str, filename: str, text: str, pages: int):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO documents (session_id, filename, text_content, pages, uploaded_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(session_id) DO UPDATE SET
               filename=excluded.filename,
               text_content=excluded.text_content,
               pages=excluded.pages,
               uploaded_at=CURRENT_TIMESTAMP""",
            (session_id, filename, text, pages)
        )

def db_save_form(session_id: str, form_data: dict):
    with get_db() as conn:
        conn.execute("INSERT INTO form_responses (session_id, form_data) VALUES (?, ?)", (session_id, json.dumps(form_data, ensure_ascii=False)))

# =====================================================================
# CURRICULUM & MULTILINGUAL FORM TEMPLATES
# =====================================================================
COURSES = {
    "dsa": {
        "title": "Data Structures and Algorithms",
        "chapters": [
            "Arrays and Strings",
            "Linked Lists",
            "Stacks and Queues",
            "Trees and Graphs",
            "Sorting and Searching",
        ],
    },
    "python": {
        "title": "Python Basics",
        "chapters": [
            "Variables and Data Types",
            "Loops and Conditions",
            "Functions and Modules",
            "File Handling",
        ],
    },
}

FORM_FIELDS_I18N = {
    "te-IN": {
        "fields": ["పూర్తి పేరు", "ఈమెయిల్ చిరునామా", "ఫోన్ నంబర్", "కోర్సు ఆసక్తి"],
        "start": "వాయిస్ ద్వారా మీ ఫారమ్ నింపుదాం. మొదట మీ {field} చెప్పండి.",
        "next": "ధన్యవాదాలు. తరువాత మీ {field} చెప్పండి.",
        "done": "ధన్యవాదాలు! మీ ఫారమ్ విజయవంతంగా పూర్తయింది మరియు భద్రపరచబడింది.",
    },
    "hi-IN": {
        "fields": ["पूरा नाम", "ईमेल पता", "फ़ोन नंबर", "कोर्स में रुचि"],
        "start": "आइए बोलकर आपका फ़ॉर्म भरें। पहले अपना {field} बताइए।",
        "next": "बहुत बढ़िया। अब अपना {field} बताइए।",
        "done": "धन्यवाद! आपका फ़ॉर्म पूरा हो गया है और सुरक्षित सेव कर लिया गया है।",
    },
    "ta-IN": {
        "fields": ["முழு பெயர்", "மின்னஞ்சல் முகவரி", "தொலைபேசி எண்", "பாட ஆர்வம்"],
        "start": "குரல் மூலம் உங்கள் படிவத்தை நிரப்புவோம். முதலில் உங்கள் {field} கூறுங்கள்.",
        "next": "நன்றி. அடுத்து உங்கள் {field} கூறுங்கள்.",
        "done": "நன்றி! உங்கள் படிவம் வெற்றிகரமாக சேமிக்கப்பட்டது.",
    },
    "en-IN": {
        "fields": ["Full Name", "Email Address", "Phone Number", "Course Interest"],
        "start": "Let's fill out your form by voice. First, please say your {field}.",
        "next": "Got it. Next, please say your {field}.",
        "done": "Thank you! Your form is complete and saved.",
    }
}

NEURAL_VOICES = {
    "te-IN": "te-IN-ShrutiNeural",
    "hi-IN": "hi-IN-SwaraNeural",
    "en-IN": "en-IN-NeerjaNeural",
    "ta-IN": "ta-IN-PallaviNeural",
    "kn-IN": "kn-IN-SapnaNeural",
    "ml-IN": "ml-IN-SobhanaNeural",
    "mr-IN": "mr-IN-AarohiNeural",
    "bn-IN": "bn-IN-TanishaaNeural",
    "gu-IN": "gu-IN-DhwaniNeural",
    "pa-IN": "pa-IN-RaaghavNeural",
    "ur-IN": "ur-IN-GulNeural",
}


def build_system_prompt(lang_code: str) -> str:
    lang = LANG_NAMES.get(lang_code, "English")
    return (
        f"You are Swaram, a lightning-fast voice AI assistant like Siri. "
        f"Reply in {lang}. Spoken text only: strictly no markdown, no asterisks, no bullets, no emojis. "
        "Be direct, warm, and concise: answer immediately in 1 short spoken sentence (under 20 words). "
        "Never use lists, preambles, or filler. Give the direct answer immediately. "
        "Native script: Telugu script for Telugu, Devanagari for Hindi/Marathi, Tamil script for Tamil, English for English."
    )


def clean_for_speech(text: str) -> str:
    text = re.sub(r"[*_#`>~|]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def gen_config(**extra):
    cfg = {
        "temperature": 0.3,
        "maxOutputTokens": 60,
    }
    cfg.update(extra)
    return cfg


def call_gemini(body, timeout=12):
    models_to_try = [GEMINI_MODEL, "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    # remove duplicates while preserving order
    models_to_try = list(dict.fromkeys(models_to_try))
    last_err = None
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            resp = HTTP_SESSION.post(
                url,
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=body,
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text"))
                    if text:
                        return text
            last_err = f"{resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")


async def generate_neural_speech(text: str, voice: str) -> bytes:
    comm = edge_tts.Communicate(text, voice)
    data = b""
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return data


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify(error="API endpoint not found", path=request.path), 404
    return send_from_directory(app.static_folder, "404.html"), 404


@app.get("/health")
def health():
    return jsonify(ok=True, has_key=bool(GEMINI_API_KEY), model=GEMINI_MODEL, storage="sqlite", key_prefix=GEMINI_API_KEY[:15] if GEMINI_API_KEY else "")



# =====================================================================
# WINDOWS NATIVE APPLICATION LAUNCHER
# =====================================================================
NATIVE_APPS = {
    # Calculator
    "calculator": "calc.exe", "calc": "calc.exe", "క్యాలిక్యులేటర్": "calc.exe", "कैलकुलेटर": "calc.exe",
    # Notepad
    "notepad": "notepad.exe", "notes": "notepad.exe", "నోట్‌ప్యాడ్": "notepad.exe", "नोटपैड": "notepad.exe",
    # Camera
    "camera": "start microsoft.windows.camera:", "క్యామెరా": "start microsoft.windows.camera:", "कैमरा": "start microsoft.windows.camera:",
    # Settings
    "settings": "start ms-settings:", "సెట్టింగ్స్": "start ms-settings:", "सेटिंग्स": "start ms-settings:",
    # Paint
    "paint": "mspaint.exe", "పెయింట్": "mspaint.exe", "पेंट": "mspaint.exe",
    # File Explorer
    "explorer": "explorer.exe", "file explorer": "explorer.exe", "files": "explorer.exe", "ఫైల్స్": "explorer.exe", "फ़ाइलें": "explorer.exe",
    # Spotify
    "spotify": "start spotify:", "స్పాటిఫై": "start spotify:", "स्पॉटिफाई": "start spotify:",
    # WhatsApp
    "whatsapp": "start whatsapp:", "వాట్సాప్": "start whatsapp:", "व्हाट्सएप": "start whatsapp:",
    # Clock / Timer
    "clock": "start ms-clock:", "timer": "start ms-clock:", "alarm": "start ms-clock:", "గడియారం": "start ms-clock:", "घड़ी": "start ms-clock:",
    # Calendar
    "calendar": "start outlookcal:", "క్యాలెండర్": "start outlookcal:", "कैलेंडर": "start outlookcal:",
    # Chrome / Browser
    "chrome": "start chrome", "browser": "start chrome", "గూగుల్ క్రోమ్": "start chrome",
    # Edge
    "edge": "start msedge",
    # Command Prompt
    "cmd": "start cmd.exe", "command prompt": "start cmd.exe", "terminal": "start wt.exe", "కమాండ్ ప్రాంప్ట్": "start cmd.exe",
    # Task Manager
    "task manager": "taskmgr.exe",
    # Store
    "store": "start ms-windows-store:", "microsoft store": "start ms-windows-store:",
    # Weather
    "weather": "start bingweather:", "వాతావరణం": "start bingweather:", "मौसम": "start bingweather:",
    # Photos
    "photos": "start ms-photos:", "ఫోటోలు": "start ms-photos:", "फ़ोटो": "start ms-photos:",
}

@app.post("/api/open-app")
def open_native_app():
    data = request.get_json(force=True, silent=True) or {}
    app_query = (data.get("app") or "").strip().lower()
    if not app_query:
        return jsonify(ok=False, error="No app name specified"), 400

    cmd = None
    matched_name = app_query
    for key, command in NATIVE_APPS.items():
        if key == app_query or key in app_query or app_query in key:
            cmd = command
            matched_name = key.capitalize()
            break

    if not cmd:
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '', app_query)
        if clean_name:
            cmd = f"start {clean_name}"
            matched_name = clean_name.capitalize()

    if cmd:
        try:
            subprocess.Popen(cmd, shell=True)
            return jsonify(ok=True, app=matched_name, launched=True)
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500

    return jsonify(ok=False, error="App not recognized"), 404

@app.get("/api/tts")
def tts():
    text = (request.args.get("text") or "").strip()
    lang = request.args.get("lang", "en-IN")
    engine = request.args.get("engine", "fast")  # 'fast' (~0.3s) or 'neural' (~1.2s)
    if not text:
        return "empty text", 400

    cache_key = f"{engine}:{lang}:{text}"
    if cache_key in TTS_CACHE:
        return Response(TTS_CACHE[cache_key], mimetype="audio/mpeg")

    # Fast Engine (Google Translate TTS ~0.3s)
    if engine == "fast":
        tl = lang.split("-")[0].lower()
        try:
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl={tl}&client=tw-ob&q={urllib.parse.quote(text[:250])}"
            r = HTTP_SESSION.get(url, timeout=6)
            if r.status_code == 200 and r.content:
                if len(TTS_CACHE) < 500:
                    TTS_CACHE[cache_key] = r.content
                return Response(r.content, mimetype="audio/mpeg")
        except Exception as e:
            app.logger.warning("Fast TTS failed, trying neural: %s", e)

    # Neural Engine (Azure Edge-TTS ~1.2s)
    voice = NEURAL_VOICES.get(lang) or NEURAL_VOICES.get("en-IN")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(generate_neural_speech(text, voice))
        loop.close()
        if audio_bytes:
            if len(TTS_CACHE) < 500:
                TTS_CACHE[cache_key] = audio_bytes
            return Response(audio_bytes, mimetype="audio/mpeg")
    except Exception as exc:
        app.logger.warning("Neural TTS failed, falling back to Google TTS: %s", exc)

    # Fallback to Google TTS
    tl = lang.split("-")[0].lower()
    try:
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl={tl}&client=tw-ob&q={urllib.parse.quote(text[:250])}"
        r = HTTP_SESSION.get(url, timeout=6)
        if r.status_code == 200 and r.content:
            if len(TTS_CACHE) < 500:
                TTS_CACHE[cache_key] = r.content
            return Response(r.content, mimetype="audio/mpeg")
    except Exception as e:
        app.logger.error("TTS fetch error: %s", e)

    return "TTS generation failed", 500


@app.post("/api/upload-pdf")
def upload_pdf():
    if "file" not in request.files:
        return jsonify(error="No file uploaded"), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify(error="Empty file"), 400

    session_id = request.headers.get("X-Session-ID", "default")
    lang = request.form.get("lang", "en-IN")

    try:
        reader = pypdf.PdfReader(file.stream)
        pages_text = []
        for i, page in enumerate(reader.pages[:30]):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"--- Page {i+1} ---\n" + txt.strip())

        full_text = "\n\n".join(pages_text)
        if not full_text.strip():
            return jsonify(error="Could not extract text from this PDF"), 400

        db_save_doc(session_id, file.filename, full_text[:30000], len(reader.pages))

        lang_name = LANG_NAMES.get(lang, "English")
        summary_prompt = (
            f"You are Swaram, a friendly voice skill coach for visually impaired students. "
            f"The learner uploaded study notes from '{file.filename}' ({len(reader.pages)} pages). "
            f"Give a clear, encouraging 2-sentence voice summary in {lang_name} describing what these notes cover, "
            "and invite them to ask questions or ask for a voice quiz on it. "
            "Plain spoken language only, no markdown, under 45 words.\n\n"
            f"Excerpt:\n{full_text[:3000]}"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": summary_prompt}]}],
            "generationConfig": gen_config(temperature=0.5, maxOutputTokens=150),
        }
        summary = clean_for_speech(call_gemini(body))

        curr = db_get_progress(session_id)
        curr["topicsLearned"] = curr.get("topicsLearned", 0) + 1
        db_save_progress(session_id, curr)

        return jsonify(
            ok=True,
            filename=file.filename,
            pages=len(reader.pages),
            summary=summary,
        )
    except Exception as exc:
        app.logger.error("PDF upload error: %s", exc)
        return jsonify(error=f"PDF processing failed: {exc}"), 500


@app.post("/api/pdf-page")
def read_pdf_page():
    session_id = request.headers.get("X-Session-ID", "default")
    data = request.get_json(force=True, silent=True) or {}
    page_num = int(data.get("page", 1))
    lang = data.get("lang", "en-IN")
    doc = db_get_doc(session_id)
    if not doc:
        return jsonify(error="No notes uploaded yet. Please upload a study notes PDF first."), 400

    text = doc["text"]
    pages = [p.strip() for p in text.split("--- Page ") if p.strip()]
    if page_num < 1 or page_num > len(pages):
        return jsonify(error=f"Page {page_num} not found. Available pages: 1 to {len(pages)}"), 404

    page_content = pages[page_num - 1]
    page_lines = page_content.splitlines()
    body_text = "\n".join(page_lines[1:]) if len(page_lines) > 1 and page_lines[0].endswith("---") else page_content

    prompt = (
        f"You are Swaram reading study notes aloud to a visually impaired learner. Reply in {LANG_NAMES.get(lang, 'English')}. "
        f"Summarize page {page_num} of '{doc['filename']}' in 3 to 4 clear, expressive spoken sentences: \n{body_text[:2000]}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.4, maxOutputTokens=250),
    }
    try:
        spoken_text = clean_for_speech(call_gemini(body))
        return jsonify(ok=True, page=page_num, total_pages=doc["pages"], content=spoken_text)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.get("/api/progress")
def get_progress():
    session_id = request.headers.get("X-Session-ID", "default")
    return jsonify(ok=True, progress=db_get_progress(session_id))


@app.post("/api/progress")
def update_progress():
    session_id = request.headers.get("X-Session-ID", "default")
    data = request.get_json(force=True, silent=True) or {}
    curr = db_get_progress(session_id)
    if "questionsAnswered" in data:
        curr["questionsAnswered"] = max(0, int(data["questionsAnswered"]))
    if "topicsLearned" in data:
        curr["topicsLearned"] = max(0, int(data["topicsLearned"]))
    if "quizScore" in data:
        curr["quizScore"] = max(0, int(data["quizScore"]))
    if "streakDays" in data:
        curr["streakDays"] = max(1, int(data["streakDays"]))

    db_save_progress(session_id, curr)
    return jsonify(ok=True, progress=curr)


@app.post("/api/chat")
def chat():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    data = request.get_json(force=True, silent=True) or {}
    message = (data.get("message") or "").strip()
    lang = data.get("lang", "en-IN")
    history = data.get("history", [])[-12:]

    if not message:
        return jsonify(error="empty message"), 400

    session_id = request.headers.get("X-Session-ID", "default")
    doc = db_get_doc(session_id)

    # Fast in-memory cache for common search queries without uploaded PDF notes
    cache_key = f"{lang}:{message.lower()}" if not doc and not history else None
    if cache_key and cache_key in CHAT_CACHE:
        return jsonify(reply=CHAT_CACHE[cache_key])

    doc_prompt = ""
    if doc:
        doc_prompt = (
            f"\n\n[STUDY NOTES / UPLOADED PDF CONTEXT]\n"
            f"File: {doc['filename']} ({doc['pages']} pages)\n"
            f"Notes content:\n'''{doc['text'][:8000]}'''\n"
            "If the learner asks about their notes, questions from the PDF, or asks for a summary or quiz on their notes, "
            "teach and explain accurately based on these notes in simple spoken sentences."
        )

    prog = db_get_progress(session_id)
    prog["questionsAnswered"] = prog.get("questionsAnswered", 0) + 1
    db_save_progress(session_id, prog)

    contents = []
    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": str(turn.get("text", ""))}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    body = {
        "system_instruction": {"parts": [{"text": build_system_prompt(lang) + doc_prompt}]},
        "contents": contents,
        "generationConfig": gen_config(),
    }

    try:
        reply = clean_for_speech(call_gemini(body))
        if not reply:
            raise ValueError("empty reply")
        if cache_key and len(CHAT_CACHE) < 1000:
            CHAT_CACHE[cache_key] = reply
        return jsonify(reply=reply)
    except Exception as exc:
        app.logger.error("Gemini error: %s", exc)
        return jsonify(error=str(exc)), 502


@app.post("/api/ui-strings")
def ui_strings():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    data = request.get_json(force=True, silent=True) or {}
    code = data.get("lang", "")
    strings = data.get("strings")
    lang = LANG_NAMES.get(code)
    if not lang or not isinstance(strings, dict) or not strings or len(strings) > 100:
        return jsonify(error="bad request"), 400
    if code in UI_CACHE:
        return jsonify(strings=UI_CACHE[code])

    prompt = (
        f"Translate these UI strings into {lang}. Return ONLY a JSON object mapping each key to its translation. "
        "Use natural script. Do not add or omit keys.\n"
        f"{json.dumps(strings, ensure_ascii=False)}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.2, responseMimeType="application/json"),
    }
    try:
        raw = call_gemini(body)
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            UI_CACHE[code] = parsed
            return jsonify(strings=parsed)
        raise ValueError("Invalid format")
    except Exception as exc:
        app.logger.error("ui-strings error: %s", exc)
        return jsonify(error=str(exc)), 502


@app.post("/api/intent")
def intent():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text") or "").strip()[:300]
    lang = LANG_NAMES.get(data.get("lang", ""), "an Indian language")
    contacts = [str(c)[:40] for c in (data.get("contacts") or [])][:50]
    if not text:
        return jsonify(intent="none")

    prompt = (
        f"You classify ONE spoken sentence for a voice assistant. The speaker uses {lang}. "
        f"Valid intents: {', '.join(sorted(INTENTS))}. "
        "Reply with JSON only, with fields: intent, site, query, name, number.\n"
        f"Saved contacts: {json.dumps(contacts, ensure_ascii=False)}\n"
        f"Spoken sentence: {json.dumps(text, ensure_ascii=False)}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(
            temperature=0, maxOutputTokens=200, responseMimeType="application/json"
        ),
    }
    try:
        out = json.loads(call_gemini(body, timeout=20))
        if not isinstance(out, dict):
            raise ValueError("not an object")
        kind = out.get("intent") if out.get("intent") in INTENTS else "none"
        field = lambda k: str(out.get(k) or "")[:100]
        return jsonify(
            intent=kind,
            site=field("site"),
            query=field("query"),
            name=field("name"),
            number=field("number"),
        )
    except Exception as exc:
        app.logger.error("intent error: %s", exc)
        return jsonify(intent="none")


# =====================================================================
# AUTH & INTERACTIVE LEARNING ENDPOINTS (SQLITE BACKED)
# =====================================================================

@app.post("/api/auth/register")
def register():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or username).strip()

    if not username or len(password) < 4:
        return jsonify(error="Username and a password of at least 4 characters are required"), 400
    if db_get_user(username):
        return jsonify(error="Username already exists"), 409

    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    db_create_user(username, pw_hash, name)
    token = secrets.token_hex(16)
    return jsonify(ok=True, session_id=username, token=token, name=name)


@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    user = db_get_user(username)
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    if not user or user["password_hash"] != pw_hash:
        return jsonify(error="Invalid username or password"), 401

    token = secrets.token_hex(16)
    return jsonify(ok=True, session_id=username, token=token, name=user["name"])


@app.post("/api/pronunciation")
def pronunciation_guide():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    data = request.get_json(force=True, silent=True) or {}
    word = (data.get("word") or "").strip()
    spoken = (data.get("spoken") or "").strip()
    lang = LANG_NAMES.get(data.get("lang", "en-IN"), "English")

    if not word:
        return jsonify(error="No word provided"), 400

    prompt = (
        f"You are Swaram, a friendly voice pronunciation coach. Reply in {lang}. "
        f"Target word or phrase: '{word}'. "
        + (f"The learner pronounced it as: '{spoken}'. Give gentle feedback and " if spoken else "")
        + "break the target word into simple slow spoken syllables, then use it in one short sentence. "
        "Plain spoken text only, no markdown, under 50 words."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.4, maxOutputTokens=180),
    }
    try:
        guide = clean_for_speech(call_gemini(body))
        return jsonify(ok=True, word=word, guide=guide)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/story")
def storytelling():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    data = request.get_json(force=True, silent=True) or {}
    topic = (data.get("topic") or "a short inspiring moral story").strip()
    choice = (data.get("choice") or "").strip()
    lang = LANG_NAMES.get(data.get("lang", "en-IN"), "English")

    prompt = (
        f"You are Swaram, an expressive audio storyteller. Tell an interactive story in {lang} "
        f"about: {topic}. "
        + (f"Continue the story based on the listener's choice: '{choice}'. " if choice else "Start the story. ")
        + "Keep it to 3 vivid spoken sentences, then end with a simple two-option question so the listener can choose what happens next. "
        "Plain spoken text only, no markdown, under 70 words."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.7, maxOutputTokens=250),
    }
    try:
        story = clean_for_speech(call_gemini(body))
        return jsonify(ok=True, story=story)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/quiz/start")
def quiz_start():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    session_id = request.headers.get("X-Session-ID", "default")
    data = request.get_json(force=True, silent=True) or {}
    topic = (data.get("topic") or "general knowledge").strip()
    lang = LANG_NAMES.get(data.get("lang", "en-IN"), "English")
    use_pdf = bool(data.get("use_pdf", False))

    doc = db_get_doc(session_id)
    context = ""
    if use_pdf and doc:
        context = f"\nBase the questions on these study notes:\n{doc['text'][:5000]}"

    prompt = (
        f"Create 3 short voice-friendly quiz questions in {lang} on '{topic}'.{context}\n"
        "Return JSON only as a list of objects with keys: question, answer, hint. "
        "Keep questions and answers concise for speech."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.4, maxOutputTokens=600, responseMimeType="application/json"),
    }
    try:
        questions = json.loads(call_gemini(body))
        if not isinstance(questions, list) or not questions:
            raise ValueError("Invalid quiz format")
        ACTIVE_QUIZZES[session_id] = {"topic": topic, "questions": questions, "index": 0, "score": 0}
        first_q = clean_for_speech(questions[0]["question"])
        return jsonify(ok=True, total=len(questions), question_number=1, question=first_q)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/quiz/answer")
def quiz_answer():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    session_id = request.headers.get("X-Session-ID", "default")
    quiz = ACTIVE_QUIZZES.get(session_id)
    if not quiz:
        return jsonify(error="No active quiz. Start one first."), 400

    data = request.get_json(force=True, silent=True) or {}
    user_ans = (data.get("answer") or "").strip()
    lang = LANG_NAMES.get(data.get("lang", "en-IN"), "English")
    curr_q = quiz["questions"][quiz["index"]]

    prompt = (
        f"Question: {curr_q['question']}\nExpected Answer: {curr_q['answer']}\n"
        f"Learner's spoken answer: {user_ans}\n"
        f"Return JSON only with keys: correct (boolean), feedback (1 encouraging spoken sentence in {lang}, no markdown)."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.1, maxOutputTokens=200, responseMimeType="application/json"),
    }
    try:
        result = json.loads(call_gemini(body))
        is_correct = bool(result.get("correct"))
        feedback = clean_for_speech(str(result.get("feedback", "")))
        if is_correct:
            quiz["score"] += 1

        quiz["index"] += 1
        finished = quiz["index"] >= len(quiz["questions"])
        if finished:
            prog = db_get_progress(session_id)
            prog["quizScore"] = prog.get("quizScore", 0) + quiz["score"]
            db_save_progress(session_id, prog)
            final_score = quiz["score"]
            total = len(quiz["questions"])
            del ACTIVE_QUIZZES[session_id]
            return jsonify(ok=True, correct=is_correct, feedback=feedback, finished=True, score=final_score, total=total)

        next_q = clean_for_speech(quiz["questions"][quiz["index"]]["question"])
        return jsonify(
            ok=True,
            correct=is_correct,
            feedback=feedback,
            finished=False,
            question_number=quiz["index"] + 1,
            next_question=next_q,
        )
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.get("/api/courses")
def list_courses():
    return jsonify(ok=True, courses=COURSES)


@app.post("/api/lesson")
def get_lesson():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    session_id = request.headers.get("X-Session-ID", "default")
    data = request.get_json(force=True, silent=True) or {}
    course_id = (data.get("course") or "dsa").lower()
    chapter_idx = int(data.get("chapter", 0))
    lang = LANG_NAMES.get(data.get("lang", "en-IN"), "English")

    course = COURSES.get(course_id)
    if not course or chapter_idx < 0 or chapter_idx >= len(course["chapters"]):
        return jsonify(error="Course or chapter not found"), 404

    chapter_name = course["chapters"][chapter_idx]
    prompt = (
        f"You are Swaram, a voice tech tutor for visually impaired learners. "
        f"Teach chapter '{chapter_name}' from '{course['title']}' in {lang}. "
        "Explain the concept with one clear everyday analogy in 3 to 4 simple spoken sentences. "
        "No code blocks, no markdown, plain speech only."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.5, maxOutputTokens=250),
    }
    try:
        lesson = clean_for_speech(call_gemini(body))
        prog = db_get_progress(session_id)
        prog["topicsLearned"] = prog.get("topicsLearned", 0) + 1
        db_save_progress(session_id, prog)
        return jsonify(ok=True, course=course["title"], chapter=chapter_name, lesson=lesson)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/game")
def voice_game():
    if not GEMINI_API_KEY:
        return jsonify(error="GEMINI_API_KEY is not set on the server"), 500

    data = request.get_json(force=True, silent=True) or {}
    game_type = (data.get("type") or "riddle").strip()
    user_input = (data.get("input") or "").strip()
    lang = LANG_NAMES.get(data.get("lang", "en-IN"), "English")

    prompt = (
        f"You are Swaram hosting a fun voice '{game_type}' game in {lang}. "
        + (f"The player said: '{user_input}'. Respond to their move and give the next turn. " if user_input else "Start the game with the first prompt. ")
        + "Keep it energetic, 1 to 2 spoken sentences, no markdown."
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_config(temperature=0.8, maxOutputTokens=150),
    }
    try:
        reply = clean_for_speech(call_gemini(body))
        return jsonify(ok=True, reply=reply)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/form")
def voice_form():
    session_id = request.headers.get("X-Session-ID", "default")
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "answer")
    lang = data.get("lang", "en-IN")

    i18n = FORM_FIELDS_I18N.get(lang) or FORM_FIELDS_I18N.get(lang.split('-')[0]) or FORM_FIELDS_I18N["en-IN"]

    if action == "start" or session_id not in ACTIVE_FORMS:
        fields = data.get("fields") or i18n["fields"]
        ACTIVE_FORMS[session_id] = {"fields": fields, "answers": {}, "index": 0, "lang": lang, "i18n": i18n}
        prompt = i18n["start"].format(field=fields[0])
        return jsonify(
            ok=True,
            completed=False,
            prompt=prompt,
            current_field=fields[0],
        )

    form = ACTIVE_FORMS[session_id]
    i18n = form.get("i18n") or i18n
    spoken_value = (data.get("value") or "").strip()
    curr_field = form["fields"][form["index"]]
    form["answers"][curr_field] = spoken_value
    form["index"] += 1

    if form["index"] >= len(form["fields"]):
        completed_data = form["answers"]
        db_save_form(session_id, completed_data)
        del ACTIVE_FORMS[session_id]
        return jsonify(
            ok=True,
            completed=True,
            prompt=i18n["done"],
            data=completed_data,
        )

    next_field = form["fields"][form["index"]]
    next_prompt = i18n["next"].format(field=next_field)
    return jsonify(
        ok=True,
        completed=False,
        prompt=next_prompt,
        current_field=next_field,
    )


if __name__ == "__main__":
    import socket
    try:
        from werkzeug.serving import BaseWSGIServer
        orig_server_bind = BaseWSGIServer.server_bind
        def dual_stack_server_bind(self):
            if self.address_family == socket.AF_INET6:
                try:
                    self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                except Exception:
                    pass
            return orig_server_bind(self)
        BaseWSGIServer.server_bind = dual_stack_server_bind
    except Exception:
        pass

    port = int(os.environ.get("PORT", 5050))
    host = os.environ.get("HOST", "::")
    try:
        app.run(host=host, port=port, debug=True)
    except Exception:
        app.run(host="0.0.0.0", port=port, debug=True)
