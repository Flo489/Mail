import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GMAIL_USER = os.getenv("GMAIL_USER", "").strip()
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    TARGET_EMAIL = os.getenv("TARGET_EMAIL", "").strip() or os.getenv("MOTHER_EMAIL", "").strip()
    MOTHER_EMAIL = os.getenv("MOTHER_EMAIL", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    
    USER_NAME = os.getenv("USER_NAME", "Florent").strip()
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris").strip()
    CAMPAIGN = os.getenv("CAMPAIGN", "dermato").strip().lower()
    
    # 24 hours between reminders if no answer
    REMINDER_INTERVAL_HOURS = int(os.getenv("REMINDER_INTERVAL_HOURS", "24"))
    
    # Preferred sending hour (e.g. 8h in morning)
    START_HOUR = int(os.getenv("START_HOUR", "8"))
    
    # Quiet hours: avoid sending between 21:00 and 08:00 (Paris time)
    QUIET_HOURS_START = int(os.getenv("QUIET_HOURS_START", "21"))
    QUIET_HOURS_END = int(os.getenv("QUIET_HOURS_END", "8"))
    
    _DEFAULT_SUBJECT = (
        "Climatiseur mobile pour ma chambre cet été"
        if CAMPAIGN == "clim"
        else f"Rendez-vous dermatologue pour {USER_NAME}"
    )
    EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", _DEFAULT_SUBJECT).strip()
    
    # Availability info Florent can provide if mom asks
    USER_AVAILABILITY = os.getenv(
        "USER_AVAILABILITY", 
        "Assez flexible selon la date, de préférence les après-midis ou vendredis, mais je peux m'adapter."
    ).strip()
    
    _DEFAULT_STATE_FILE = "data/clim_state.json" if CAMPAIGN == "clim" else "data/state.json"
    STATE_FILE = os.getenv("STATE_FILE", _DEFAULT_STATE_FILE)
    
    _DEFAULT_ATTACHMENT = "assets/clim_valberg.png" if CAMPAIGN == "clim" else ""
    ATTACHMENT_PATH = os.getenv("ATTACHMENT_PATH", _DEFAULT_ATTACHMENT).strip()
    
    DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
    IS_TEST = os.getenv("IS_TEST", "false").lower() in ("true", "1", "yes")

    @classmethod
    def validate(cls, check_gemini=True, check_email=True):
        errors = []
        if check_email and not cls.GMAIL_USER:
            errors.append("GMAIL_USER est manquant (votre adresse Gmail).")
        if check_email and not cls.GMAIL_APP_PASSWORD:
            errors.append("GMAIL_APP_PASSWORD est manquant (mot de passe d'application Google de 16 caractères).")
        if check_email and not cls.TARGET_EMAIL:
            errors.append("TARGET_EMAIL ou MOTHER_EMAIL est manquant.")
        if check_gemini and not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY est manquant (clé d'API Google AI Studio).")
        return errors
