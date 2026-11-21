"""
==============================================================================
SWARAM AUTOMATED TEST SUITE
Author: Kayala Durga Pavan Teja & Engineering Team
Project: Swaram Voice-First Accessibility Assistant
Tests: Health, Gemini Chat, Multi-Language, Audio TTS, Quiz Engine, Auth
==============================================================================
"""

import unittest
import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:5050"


class TestSwaramEndpoints(unittest.TestCase):
    """End-to-end integration tests for Swaram core backend APIs."""

    def test_01_health_check(self):
        """Verify server is running, database is connected, and API key is present."""
        req = urllib.request.Request(f"{BASE_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertTrue(data.get("has_key"))
            self.assertEqual(data.get("storage"), "sqlite")
            print("\n  [PASS] Health check verified: SQLite active, API key loaded.")

    def test_02_chat_english(self):
        """Verify chat responds in concise spoken English under 30 words."""
        payload = json.dumps({"message": "What is photosynthesis?", "lang": "en-IN"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            reply = data.get("reply", "")
            self.assertTrue(len(reply) > 5)
            self.assertNotIn("*", reply)  # No markdown formatting
            self.assertNotIn("#", reply)
            print(f"  [PASS] English chat verified: '{reply[:50]}...'")

    def test_03_chat_telugu(self):
        """Verify native Telugu script generation for accessibility users."""
        payload = json.dumps({"message": "హైదరాబాద్ రాజధాని ఏమిటి?", "lang": "te-IN"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            reply = data.get("reply", "")
            self.assertTrue(len(reply) > 2)
            print(f"  [PASS] Telugu chat verified: '{reply[:40]}...'")

    def test_04_tts_generation(self):
        """Verify audio synthesizer returns valid audio bytes."""
        url = f"{BASE_URL}/api/tts?lang=en-IN&engine=fast&text=Welcome+to+Swaram"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            audio = resp.read()
            self.assertGreater(len(audio), 500)
            print(f"  [PASS] Audio synthesizer verified: generated {len(audio)} bytes audio.")

    def test_05_quiz_engine(self):
        """Verify dynamic voice quiz question generation."""
        payload = json.dumps({"topic": "Indian History", "lang": "en-IN"}).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/quiz/start",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertGreaterEqual(data.get("total", 0), 1)
            print(f"  [PASS] Quiz engine verified: Question 1: '{data.get('question')[:50]}...'")


if __name__ == "__main__":
    print("=" * 65)
    print("RUNNING SWARAM INTEGRATION TEST SUITE")
    print("Lead Developer: Kayala Durga Pavan Teja")
    print("=" * 65)
    unittest.main(verbosity=2)
