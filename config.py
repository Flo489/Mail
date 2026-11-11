import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GMAIL_USER = os.getenv("GMAIL_USER", "").strip()
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    MOTHER_EMAIL = os.getenv("MOTHER_EMAIL", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    
    USER_NAME = os.getenv("USER_NAME", "Florent").strip()
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris").strip()
    
    # 24 hours between reminders if no answer
    REMINDER_INTERVAL_HOURS = int(os.getenv("REMINDER_INTERVAL_HOURS", "24"))
    
    # Preferred sending hour (e.g. 8h in morning)
    START_HOUR = int(os.getenv("START_HOUR", "8"))
    
    # Quiet hours: avoid sending between 21:00 and 08:00 (Paris time)
    QUIET_HOURS_START = int(os.getenv("QUIET_HOURS_START", "21"))
    QUIET_HOURS_END = int(os.getenv("QUIET_HOURS_END", "8"))
    
    EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", f"Rendez-vous dermatologue pour {USER_NAME}").strip()
    
    # Availability info Florent can provide if mom asks
    USER_AVAILABILITY = os.getenv(
        "USER_AVAILABILITY", 
        "Assez flexible selon la date, de préférence les après-midis ou vendredis, mais je peux m'adapter."
    ).strip()
    
    STATE_FILE = os.getenv("STATE_FILE", "data/state.json")
    
    DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

    @classmethod
    def validate(cls, check_gemini=True, check_email=True):
        errors = []
        if check_email and not cls.GMAIL_USER:
            errors.append("GMAIL_USER est manquant (votre adresse Gmail).")
        if check_email and not cls.GMAIL_APP_PASSWORD:
            errors.append("GMAIL_APP_PASSWORD est manquant (mot de passe d'application Google de 16 caractères).")
        if check_email and not cls.MOTHER_EMAIL:
            errors.append("MOTHER_EMAIL est manquant (l'adresse email de votre maman).")
        if check_gemini and not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY est manquant (clé d'API Google AI Studio).")
        return errors
