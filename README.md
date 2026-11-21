# Swaram (స్వరం)

> A voice-first accessibility assistant and skill coach for visually impaired and hands-free users across 11 Indian regional languages.

**Live Application:** [https://swaram-app.onrender.com/](https://swaram-app.onrender.com/)  
**Lead Developer:** Kayala Durga Pavan Teja & team

---

## Overview

Existing mobile screen readers (such as TalkBack or NVDA) focus on reading screen elements line-by-line, which can be tedious for educational content and everyday tasks, especially in regional Indian languages. 

**Swaram** is built from the ground up as a conversational, voice-first companion that operates 100% eyes-free. Users can talk to Swaram in Telugu, Hindi, Tamil, Kannada, and 7 other Indian languages to study notes, practice voice quizzes, make phone calls, get voice directions, or read printed text and medicine labels using their camera.

---

## Core Features

- **11 Indian Regional Languages:** Native voice support in Telugu, Hindi, English, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, and Urdu.
- **Hands-Free Wake Word:** Listens for *"Hey Swaram"* in the background using Screen Wake Lock to stay active without turning off the microphone.
- **Voice Phone Calling:** Say *"Call Mom"* or *"Call 9876543210"* in English, Telugu, or Hindi. Integrates with the modern Contact Picker API (`navigator.contacts`), voice contact saving (*"Save Mom 9848012345"*), and provides tap-anywhere mobile dialing.
- **Medicine & Expiry Date Scanner:** Say *"check medicine"* or *"expiry date"* to scan medicine strips, syrup bottles, or ointment labels. Identifies the medicine name, use, expiry date, and announces clear warnings if expired or unreadable.
- **Indian Currency & Bill Reader:** Say *"which note"* or *"read bill"* to recognize Indian Rupee notes (₹10 to ₹500) and announce totals on shopping receipts.
- **Color & Light Detector:** Say *"what color is this"* or *"is the light on"* to identify clothing/object colors and room illumination.
- **Hands-Free Device Status:** Zero-latency spoken responses for battery percentage & charging state via `navigator.getBattery()`, current time, and day/date.
- **Spoken Voice Reminders:** Natural voice scheduling (*"remind me to take medicine in 5 minutes"*), audio bell chime, haptic feedback, spoken alert, and persistent storage.
- **Voice Maps & Compass Navigation:** Provides distance and 8-point compass directions (e.g. *"Charminar is 4.9 km away. Head South-West, about 7 minutes"*) using OpenStreetMap and OSRM routing.
- **Audio Study Coach (PDF Notes):** Upload textbook chapters or study notes in PDF format and ask questions aloud.
- **Voice Biometric Lock:** Client-side speaker verification using Web Audio API FFT frequency analysis to prevent background voices from triggering commands.
- **Emergency SOS:** Announces the user's current GPS coordinates aloud and opens an immediate dialer link to call emergency services (112 / 100).

---

## Architecture & How It Works

Swaram uses a lightweight, client-focused architecture:

```
[ Client (Browser) ]
  ├── Web Speech API (Continuous SpeechRecognition & Synthesizer)
  ├── Web Audio API (Real-time FFT audio spectrum & voiceprint check)
  ├── Geolocation & Screen Wake Lock API
  └── Contact Picker API (Phone dialing integration)
         │
         ▼ HTTP / SSE (Fast sentence streaming)
[ Backend (Flask / Python) ]
  ├── SQLite Database (WAL mode - user notes, sessions, progress)
  ├── Spatial Math (Haversine distance & forward azimuth bearing)
  ├── Audio Synthesizer (Edge-TTS neural voices + Google TTS fallback)
  └── Conversational Model (Google Gemini Flash for spoken explanations)
```

---

## Project Structure

```text
swaram/
├── app.py                # Flask server, routes, SQLite helpers, TTS & Gemini APIs
├── requirements.txt      # Python dependencies (Flask, edge-tts, pypdf, requests)
├── Procfile              # Production deployment command (Gunicorn)
├── static/
│   ├── index.html        # Single-row zero-scroll voice interface & PWA client
│   └── 404.html          # Fallback error page
└── tests/
    └── test_suite.py     # Automated test suite (health, chat, TTS, directions, vision)
```

---

## Getting Started Locally

### Prerequisites
- Python 3.10+
- Modern Chromium browser (Chrome or Edge) for Web Speech API support

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/pavantejkayala/swaram-app..git
   cd swaram-app.
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set your Gemini API key:**
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

4. **Start the application:**
   ```bash
   python app.py
   ```
   Open `http://localhost:5050` in Chrome.

5. **Run test suite:**
   ```bash
   python tests/test_suite.py
   ```

---

## Team & Credits

- **Kayala Durga Pavan Teja** — Lead Developer & Systems Architect
- Developed for the National Accessibility Hackathon.

## License

This project is licensed under the MIT License.
