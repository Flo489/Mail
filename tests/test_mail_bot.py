import os
import unittest
import json
from datetime import datetime, timedelta
import pytz

from state_manager import StateManager
from gemini_client import GeminiClient
from email_service import EmailService

class TestMailBot(unittest.TestCase):
    def setUp(self):
        self.test_state_file = "data/test_state.json"
        if os.path.exists(self.test_state_file):
            os.remove(self.test_state_file)
        self.state_mgr = StateManager(self.test_state_file, "Europe/Paris")

    def tearDown(self):
        if os.path.exists(self.test_state_file):
            os.remove(self.test_state_file)

    def test_default_state(self):
        self.assertEqual(self.state_mgr.state["status"], "ACTIVE")
        self.assertFalse(self.state_mgr.state["appointment_booked"])
        self.assertIsNone(self.state_mgr.state["appointment_details"])
        self.assertEqual(self.state_mgr.state["reminder_count"], 0)
        self.assertFalse(self.state_mgr.is_completed())

    def test_record_sent_email_and_24h_timing(self):
        tz = pytz.timezone("Europe/Paris")
        now = datetime.now(tz)
        
        # 1. Record sent email 10 hours ago
        past_10h = now - timedelta(hours=10)
        self.state_mgr.state["last_email_sent_at"] = past_10h.isoformat()
        self.state_mgr.save()

        hours = self.state_mgr.get_hours_since_last_sent()
        self.assertAlmostEqual(hours, 10.0, places=1)
        self.assertFalse(self.state_mgr.can_send_reminder(24))

        # 2. Sent 25 hours ago
        past_25h = now - timedelta(hours=25)
        self.state_mgr.state["last_email_sent_at"] = past_25h.isoformat()
        self.state_mgr.save()

        self.assertTrue(self.state_mgr.can_send_reminder(24))

    def test_clean_reply_text(self):
        svc = EmailService()
        raw_msg = (
            "C'est bon j'ai pris rdv pour le 22 décembre à 10h chez le Dr Dupont !\n\n"
            "Envoyé de mon iPhone\n\n"
            "Le 11 nov. 2026 à 08:00, Florent a écrit :\n"
            "> Coucou Maman,\n"
            "> Tu as pu regarder pour le dermato ?"
        )
        cleaned = svc._clean_reply_text(raw_msg)
        self.assertEqual(cleaned, "C'est bon j'ai pris rdv pour le 22 décembre à 10h chez le Dr Dupont !")

    def test_gemini_fallback_booked_detection(self):
        gemini = GeminiClient(api_key="")
        result = gemini._fallback_analyze("C'est bon, le rdv est pris pour le 15 décembre à 14h")
        self.assertTrue(result["appointment_booked"])
        self.assertIn("15 décembre", result["appointment_details"])

    def test_gemini_fallback_disponibilities_detection(self):
        gemini = GeminiClient(api_key="")
        result = gemini._fallback_analyze("Tu es dispo quel jour ?")
        self.assertFalse(result["appointment_booked"])
        self.assertTrue(result["needs_reply"])
        self.assertIn("disponibilités", result["suggested_reply"].lower())

    def test_gemini_fallback_reminders(self):
        gemini = GeminiClient(api_key="")
        rem0 = gemini._fallback_reminder(0)
        rem1 = gemini._fallback_reminder(1)
        rem2 = gemini._fallback_reminder(2)
        
        self.assertIn("Maman", rem0)
        self.assertIn("Maman", rem1)
        self.assertIn("haha", rem2)  # Humorous tone for reminder 3+

    def test_mark_appointment_booked(self):
        self.state_mgr.mark_appointment_booked("Rendez-vous le 20 janvier à 15h30")
        self.assertTrue(self.state_mgr.is_completed())
        self.assertEqual(self.state_mgr.state["status"], "COMPLETED")
        self.assertEqual(self.state_mgr.state["appointment_details"], "Rendez-vous le 20 janvier à 15h30")

if __name__ == "__main__":
    unittest.main()
