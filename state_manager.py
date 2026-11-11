import json
import os
from datetime import datetime
import pytz

class StateManager:
    def __init__(self, state_file_path, timezone_name="Europe/Paris"):
        self.state_file_path = state_file_path
        self.tz = pytz.timezone(timezone_name)
        self.state = self._load()

    def _default_state(self):
        return {
            "status": "ACTIVE",  # ACTIVE, COMPLETED
            "appointment_booked": False,
            "appointment_details": None,
            "scheduled_start_at": None,
            "last_email_sent_at": None,
            "last_email_received_at": None,
            "last_sent_message_id": None,
            "last_seen_imap_uid": None,
            "reminder_count": 0,
            "conversation_history": []
        }

    def _load(self):
        if not os.path.exists(self.state_file_path):
            state = self._default_state()
            self._save_state(state)
            return state
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[StateManager] Erreur de lecture de {self.state_file_path}: {e}. Réinitialisation.")
            state = self._default_state()
            self._save_state(state)
            return state

    def save(self):
        self._save_state(self.state)

    def _save_state(self, state):
        os.makedirs(os.path.dirname(os.path.abspath(self.state_file_path)), exist_ok=True)
        with open(self.state_file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def get_current_time(self):
        return datetime.now(self.tz)

    def parse_iso(self, iso_string):
        if not iso_string:
            return None
        try:
            dt = datetime.fromisoformat(iso_string)
            if dt.tzinfo is None:
                dt = self.tz.localize(dt)
            return dt.astimezone(self.tz)
        except Exception:
            return None

    def is_completed(self):
        return self.state.get("appointment_booked", False) or self.state.get("status") == "COMPLETED"

    def mark_appointment_booked(self, details=None):
        self.state["appointment_booked"] = True
        self.state["status"] = "COMPLETED"
        if details:
            self.state["appointment_details"] = details
        self.save()

    def record_sent_email(self, subject, content, message_id=None):
        now_iso = self.get_current_time().isoformat()
        self.state["last_email_sent_at"] = now_iso
        if message_id:
            self.state["last_sent_message_id"] = message_id
        
        # If this is a reminder (not the initial email and not a direct reply)
        # Note: caller will increment reminder_count as appropriate
        self.state["conversation_history"].append({
            "role": "user",
            "timestamp": now_iso,
            "subject": subject,
            "content": content
        })
        self.save()

    def record_received_email(self, uid, content, date_iso=None):
        if not date_iso:
            date_iso = self.get_current_time().isoformat()
        self.state["last_email_received_at"] = date_iso
        if uid:
            self.state["last_seen_imap_uid"] = str(uid)
        self.state["conversation_history"].append({
            "role": "mother",
            "timestamp": date_iso,
            "content": content
        })
        self.save()

    def get_hours_since_last_sent(self):
        last_sent_iso = self.state.get("last_email_sent_at")
        if not last_sent_iso:
            return None
        last_sent_dt = self.parse_iso(last_sent_iso)
        if not last_sent_dt:
            return None
        diff = self.get_current_time() - last_sent_dt
        return diff.total_seconds() / 3600.0

    def has_unreplied_mother_message(self):
        """Returns True if mom's last message is more recent than our last sent message."""
        last_sent = self.parse_iso(self.state.get("last_email_sent_at"))
        last_recv = self.parse_iso(self.state.get("last_email_received_at"))
        if not last_recv:
            return False
        if not last_sent:
            return True
        return last_recv > last_sent

    def can_send_reminder(self, reminder_interval_hours=24):
        hours = self.get_hours_since_last_sent()
        if hours is None:
            return False
        return hours >= reminder_interval_hours
