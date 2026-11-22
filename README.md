# Swaram (స్వరం)

A voice assistant and study companion for visually impaired users across 11 Indian languages.

**Live Site:** [https://swaram-app.onrender.com/](https://swaram-app.onrender.com/)  
**Author:** Kayala Durga Pavan Teja

---

## Why I Built Swaram

Existing screen readers like TalkBack or NVDA read out every button, icon, and div on a webpage. For visually impaired people, having to navigate through dozens of UI elements just to check a medicine expiry date, count currency notes, or study textbook notes is slow and exhausting.

Swaram is built from scratch to be voice-first and eyes-free. You just speak naturally in your mother tongue:
- **Telugu (తెలుగు)**
- **Hindi (हिन्दी)**
- **English**
- **Tamil (தமிழ்)**
- **Kannada (ಕನ್ನಡ)**
- **Malayalam (മലയാളം)**
- **Marathi (मराठी)**
- **Bengali (বাংলা)**
- **Gujarati (ગુજરાતી)**
- **Punjabi (ਪੰਜਾਬੀ)**
- **Urdu (اردو)**

---

## What It Does

1. **Medicine & Expiry Date Scanner:** Say *"check medicine"* or *"expiry date"* and point your rear camera at a medicine strip or syrup bottle. It reads the medicine name, use, expiry date, and warns if it has expired.
2. **Indian Currency & Bill Reader:** Say *"which note"* or *"read bill"* to recognize ₹10 to ₹500 currency notes or hear the final total on a printed store bill.
3. **Color & Light Detector:** Say *"what color is this"* or *"is the light on"* to check shirt colors or room lighting.
4. **Hands-Free Phone Calling:** Say *"Call Mom"* or *"Call 9848012345"*. Tap anywhere on the screen if you need to open the native phone dialer.
5. **Spoken Voice Reminders:** Say *"remind me to take medicine in 5 minutes"*. When the time comes, it plays a chime, vibrates, and speaks the reminder aloud.
6. **Local Status:** Say *"battery"*, *"time"*, or *"date"* for an instant spoken update without waiting for a server round-trip.
7. **Hands-Free Wake Word:** Say *"Hey Swaram"* anytime to activate listening without touching the screen.
8. **Study Notes (PDF):** Upload PDF chapters or notes and ask questions aloud.
9. **Voice Navigation:** Ask for directions to any landmark (e.g. *"take me to Charminar"*), and it announces the distance and 8-point compass heading (e.g. *"South-West, 4.9 km"*).
10. **Voice Lock:** Quick audio-frequency speaker check to make sure background voices don't trigger calls or settings.

---

## Tech Stack

- **Frontend:** Plain HTML5, CSS3, and JavaScript. Uses Web Speech API for recognition and Web Audio API for tone chimes and audio analysis.
- **Backend:** Python with Flask.
- **Storage:** SQLite in WAL mode for user notes, sessions, and contact shortcuts.
- **Speech Synthesis:** Dual approach using native browser synthesis when installed, with Google Translate TTS fallback for all 11 languages.
- **AI Model:** Google Gemini Flash for general conversational queries and camera vision.

---

## Running Locally

### 1. Requirements
- Python 3.10 or higher
- Google Chrome or Microsoft Edge (for Web Speech API)

### 2. Setup
```bash
git clone https://github.com/pavantejkayala/swaram-app..git
cd swaram-app.
pip install -r requirements.txt
```

### 3. Set Gemini API Key
```bash
export GEMINI_API_KEY="your-gemini-api-key"
# On Windows PowerShell:
# $env:GEMINI_API_KEY="your-gemini-api-key"
```

### 4. Start Server
```bash
python app.py
```
Open `http://localhost:5050` in Chrome.

### 5. Run Tests
```bash
python tests/test_suite.py
```

---

## License

MIT License. Free for educational and accessibility use.
