import smtplib
import imaplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid, parsedate_to_datetime
import re
from config import Config

class EmailService:
    def __init__(self, user=None, password=None, mother_email=None):
        self.user = user or Config.GMAIL_USER
        self.password = password or Config.GMAIL_APP_PASSWORD
        self.mother_email = mother_email or Config.MOTHER_EMAIL
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 465
        self.imap_host = "imap.gmail.com"
        self.imap_port = 993

    def send_email(self, to_addr, subject, body_text, reply_to_message_id=None):
        """
        Sends an email via Gmail SMTP.
        Returns the generated Message-ID.
        """
        if Config.DRY_RUN:
            fake_id = f"<dry-run-{make_msgid().strip('<>')}>"
            print(f"[DRY-RUN] Envoi simulé à {to_addr}")
            print(f"[DRY-RUN] Sujet: {subject}")
            print(f"[DRY-RUN] Message:\n{body_text}\n")
            return fake_id

        msg = MIMEMultipart("alternative")
        msg["From"] = formataddr((Config.USER_NAME, self.user))
        msg["To"] = to_addr
        msg["Subject"] = subject
        
        msg_id = make_msgid(domain="gmail.com")
        msg["Message-ID"] = msg_id

        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        # Plain text
        part_text = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part_text)

        # HTML formatted text
        html_paragraphs = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in body_text.split("\n\n") if p.strip())
        html_content = f"""
        <html>
          <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #222;">
            {html_paragraphs}
          </body>
        </html>
        """
        part_html = MIMEText(html_content, "html", "utf-8")
        msg.attach(part_html)

        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30) as server:
            server.login(self.user, self.password)
            server.sendmail(self.user, [to_addr], msg.as_string())

        print(f"[EmailService] Email envoyé avec succès à {to_addr} (Message-ID: {msg_id})")
        return msg_id

    def notify_user_appointment_booked(self, details):
        """Sends notification to Florent that mom booked the appointment."""
        subject = f"🎉 RDV dermatologue confirmé par Maman !"
        body = (
            f"Salut {Config.USER_NAME},\n\n"
            f"Bonne nouvelle ! Ta maman a confirmé la prise du rendez-vous chez le dermatologue.\n\n"
            f"Détails enregistrés :\n{details or 'Rendez-vous confirmé'}\n\n"
            f"Le script s'est arrêté automatiquement et n'enverra plus aucune relance.\n\n"
            f"— Ton assistant automatique"
        )
        try:
            self.send_email(self.user, subject, body)
        except Exception as e:
            print(f"[EmailService] Impossible d'envoyer l'email de notification utilisateur: {e}")

    def fetch_new_replies(self, last_seen_uid=None):
        """
        Fetches unread / recent replies from mother's email address via IMAP.
        Returns a list of dicts:
        [
            {
                "uid": int,
                "message_id": str,
                "date": iso_string,
                "subject": str,
                "body": str (clean, stripped of quotes)
            }
        ]
        """
        if Config.DRY_RUN:
            print("[DRY-RUN] Recherche de réponses IMAP simulée (aucune nouvelle réponse).")
            return []

        replies = []
        try:
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=30) as mail:
                mail.login(self.user, self.password)
                mail.select("INBOX", readonly=True)

                # Search for messages from mother
                search_query = f'(FROM "{self.mother_email}")'
                status, data = mail.search(None, search_query)
                if status != "OK" or not data or not data[0]:
                    return []

                message_ids = data[0].split()
                # Process messages
                for num in message_ids:
                    # Fetch UID
                    status_uid, uid_data = mail.fetch(num, "(UID)")
                    uid = None
                    if status_uid == "OK" and uid_data:
                        match = re.search(rb"UID\s+(\d+)", uid_data[0])
                        if match:
                            uid = int(match.group(1))

                    if uid and last_seen_uid and uid <= int(last_seen_uid):
                        continue

                    # Fetch message content
                    status_msg, msg_data = mail.fetch(num, "(RFC822)")
                    if status_msg != "OK" or not msg_data:
                        continue

                    raw_email = msg_data[0][1]
                    parsed_email = email.message_from_bytes(raw_email)

                    msg_id = parsed_email.get("Message-ID", "")
                    subject = self._decode_header(parsed_email.get("Subject", ""))
                    date_header = parsed_email.get("Date", "")
                    
                    try:
                        date_dt = parsedate_to_datetime(date_header)
                        date_iso = date_dt.isoformat()
                    except Exception:
                        date_iso = None

                    body = self._extract_body(parsed_email)
                    clean_body = self._clean_reply_text(body)

                    if clean_body.strip():
                        replies.append({
                            "uid": uid,
                            "message_id": msg_id,
                            "date": date_iso,
                            "subject": subject,
                            "body": clean_body
                        })

        except Exception as e:
            print(f"[EmailService] Erreur lors de la lecture IMAP: {e}")

        return replies

    def _decode_header(self, raw_header):
        if not raw_header:
            return ""
        decoded_parts = email.header.decode_header(raw_header)
        result = []
        for text, encoding in decoded_parts:
            if isinstance(text, bytes):
                encoding = encoding or "utf-8"
                try:
                    result.append(text.decode(encoding, errors="ignore"))
                except Exception:
                    result.append(text.decode("latin-1", errors="ignore"))
            else:
                result.append(str(text))
        return "".join(result)

    def _extract_body(self, msg):
        """Extracts text content from email message, preferring text/plain."""
        text_content = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(charset, errors="ignore")
                elif content_type == "text/html" and not text_content:
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_text = payload.decode(charset, errors="ignore")
                        # Basic HTML tag stripping
                        text_content = re.sub(r"<[^>]+>", " ", html_text)
            return text_content
        else:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(charset, errors="ignore")
        return ""

    def _clean_reply_text(self, text):
        """Strips quotes, previous message trails, and typical email signatures."""
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Stop if we hit a standard reply header
            if re.match(r"^(Le\s.+a\sécrit\s?:|On\s.+wrote\s?:|De\s?:|From\s?:|-----Original Message-----)", stripped, re.IGNORECASE):
                break
            # Skip quoted lines
            if stripped.startswith(">"):
                continue
            # Skip signature markers like "Envoyé de mon iPhone"
            if re.search(r"Envoyé (de mon|depuis mon)|Sent from my", stripped, re.IGNORECASE):
                continue
            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()
