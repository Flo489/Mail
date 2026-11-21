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

    def test_clim_fallback_bought_detection(self):
        gemini = GeminiClient(api_key="", campaign="clim")
        result = gemini._fallback_analyze("C'est bon mon minou, je l'ai commandée chez Electro Dépôt !")
        self.assertTrue(result["appointment_booked"])
        self.assertIn("Electro Dépôt", result["appointment_details"])

    def test_clim_fallback_price_question(self):
        gemini = GeminiClient(api_key="", campaign="clim")
        result = gemini._fallback_analyze("Elle coûte combien et c'est dans quel magasin ?")
        self.assertFalse(result["appointment_booked"])
        self.assertTrue(result["needs_reply"])
        self.assertIn("219,98", result["suggested_reply"])
        self.assertIn("Electro Dépôt", result["suggested_reply"])

    def test_clim_fallback_initial_and_reminders(self):
        gemini = GeminiClient(campaign="clim")
        gemini.api_key = ""
        initial = gemini.generate_initial_email(is_test=False)
        self.assertIn("VALBERG 9000 BTU", initial)
        self.assertIn("219,98", initial)
        self.assertIn("30°C", initial)
        self.assertIn("Hénin-Beaumont", initial)

        rem0 = gemini._fallback_reminder(0)
        rem1 = gemini._fallback_reminder(1)
        rem2 = gemini._fallback_reminder(2)
        self.assertIn("VALBERG", rem0)
        self.assertIn("30°C", rem1)
        self.assertIn("haha", rem2)

    def test_dentiste_fallback_initial_and_reminders(self):
        gemini = GeminiClient(campaign="dentiste")
        gemini.api_key = ""
        initial = gemini.generate_initial_email(is_test=False)
        self.assertIn("dentiste", initial.lower())
        self.assertIn("incisives", initial.lower())
        self.assertIn("polissage", initial.lower())
        self.assertIn("bicarbonate", initial.lower())

        rem0 = gemini._fallback_reminder(0)
        rem1 = gemini._fallback_reminder(1)
        rem2 = gemini._fallback_reminder(2)
        self.assertIn("dentiste", rem0.lower())
        self.assertIn("polissage", rem1.lower())
        self.assertIn("haha", rem2.lower())

        dispo = gemini._fallback_analyze("Tu es dispo quel jour ?")
        self.assertFalse(dispo["appointment_booked"])
        self.assertIn("dentiste", dispo["suggested_reply"].lower())

        booked = gemini._fallback_analyze("C'est bon, le rdv est pris pour le 10 décembre à 15h !")
        self.assertTrue(booked["appointment_booked"])

    def test_email_service_campaign_matching(self):
        svc = EmailService()
        self.assertTrue(svc._matches_campaign("Re: Rendez-vous dentiste pour Florent", "", "", campaign="dentiste"))
        self.assertFalse(svc._matches_campaign("Re: Climatiseur mobile pour ma chambre cet été", "", "", campaign="dentiste"))
        self.assertTrue(svc._matches_campaign("Re: Climatiseur mobile pour ma chambre cet été", "", "", campaign="clim"))
        self.assertFalse(svc._matches_campaign("Re: Rendez-vous dentiste pour Florent", "", "", campaign="clim"))
        self.assertTrue(svc._matches_campaign("Nouveau message", "<msg-123@gmail.com>", "", campaign="dentiste", expected_message_id="<msg-123@gmail.com>"))

if __name__ == "__main__":
    unittest.main()
