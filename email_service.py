import os
import smtplib
import imaplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr, make_msgid, parsedate_to_datetime
import re
from config import Config

class EmailService:
    def __init__(self, user=None, password=None, mother_email=None):
        self.user = user or Config.GMAIL_USER
        self.password = password or Config.GMAIL_APP_PASSWORD
        self.mother_email = mother_email or Config.TARGET_EMAIL or Config.MOTHER_EMAIL
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 465
        self.imap_host = "imap.gmail.com"
        self.imap_port = 993

    def send_email(self, to_addr, subject, body_text, reply_to_message_id=None, attachment_path=None):
        """
        Sends an email via Gmail SMTP.
        Supports optional image attachments (single path, comma-separated paths, or list of paths).
        Returns the generated Message-ID.
        """
        if isinstance(attachment_path, (list, tuple)):
            raw_paths = [str(p).strip() for p in attachment_path if str(p).strip()]
        elif isinstance(attachment_path, str) and attachment_path.strip():
            raw_paths = [p.strip() for p in attachment_path.split(",") if p.strip()]
        else:
            raw_paths = []

        valid_paths = [p for p in raw_paths if os.path.exists(p)]

        if Config.DRY_RUN:
            fake_id = f"<dry-run-{make_msgid().strip('<>')}>"
            print(f"[DRY-RUN] Envoi simulé à {to_addr}")
            print(f"[DRY-RUN] Sujet: {subject}")
            if raw_paths:
                print(f"[DRY-RUN] Pièce(s) jointe(s): {', '.join(raw_paths)}")
            print(f"[DRY-RUN] Message:\n{body_text}\n")
            return fake_id

        has_attachment = bool(valid_paths)
        msg = MIMEMultipart("related") if has_attachment else MIMEMultipart("alternative")
        msg["From"] = formataddr((Config.USER_NAME, self.user))
        msg["To"] = to_addr
        msg["Subject"] = subject
        
        msg_id = make_msgid(domain="gmail.com")
        msg["Message-ID"] = msg_id

        if reply_to_message_id:
            msg["In-Reply-To"] = reply_to_message_id
            msg["References"] = reply_to_message_id

        body_container = MIMEMultipart("alternative") if has_attachment else msg

        # Plain text
        part_text = MIMEText(body_text, "plain", "utf-8")
        body_container.attach(part_text)

        # HTML formatted text
        html_paragraphs = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in body_text.split("\n\n") if p.strip())
        inline_img_html = "".join(
            f'<p style="margin-top:16px;"><img src="cid:product_image_{idx}" alt="Produit {idx}" '
            'style="max-width:100%; height:auto; border:1px solid #e5e7eb; border-radius:8px;" /></p>'
            for idx, _ in enumerate(valid_paths, 1)
        )
        html_content = f"""
        <html>
          <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #222;">
            {html_paragraphs}
            {inline_img_html}
          </body>
        </html>
        """
        part_html = MIMEText(html_content, "html", "utf-8")
        body_container.attach(part_html)

        if has_attachment:
            msg.attach(body_container)
            for idx, path in enumerate(valid_paths, 1):
                with open(path, "rb") as img_file:
                    img_data = img_file.read()
                img_part = MIMEImage(img_data)
                filename = os.path.basename(path)
                img_part.add_header("Content-ID", f"<product_image_{idx}>")
                img_part.add_header("Content-Disposition", "inline", filename=filename)
                msg.attach(img_part)

        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30) as server:
            server.login(self.user, self.password)
            server.sendmail(self.user, [to_addr], msg.as_string())

        print(f"[EmailService] Email envoyé avec succès à {to_addr} (Message-ID: {msg_id})")
        return msg_id

    def notify_user_goal_completed(self, details, campaign="dermato"):
        """Sends notification to Florent that mom completed the requested goal."""
        if campaign == "clim":
            subject = "🎉 Achat de la clim confirmé par Maman !"
            body = (
                f"Salut {Config.USER_NAME},\n\n"
                f"Bonne nouvelle ! Ta maman a confirmé l'achat/commande du climatiseur mobile VALBERG 9000 BTU.\n\n"
                f"Détails enregistrés :\n{details or 'Achat confirmé'}\n\n"
                f"Le script clim s'est arrêté automatiquement et n'enverra plus aucune relance.\n\n"
                f"— Ton assistant automatique"
            )
        elif campaign == "accessoires_clim":
            subject = "🎉 Accessoires clim (tuyau + kit fenêtre) confirmés par Maman !"
            body = (
                f"Salut {Config.USER_NAME},\n\n"
                f"Bonne nouvelle ! Ta maman a confirmé l'achat/commande des accessoires clim (tuyau 3m 150mm + tissu d'isolation fenêtre HOOMEE).\n\n"
                f"Détails enregistrés :\n{details or 'Achat confirmé'}\n\n"
                f"Le script accessoires clim s'est arrêté automatiquement et n'enverra plus aucune relance.\n\n"
                f"— Ton assistant automatique"
            )
        elif campaign == "dentiste":
            subject = "🎉 RDV dentiste confirmé par Maman !"
            body = (
                f"Salut {Config.USER_NAME},\n\n"
                f"Bonne nouvelle ! Ta maman a confirmé la prise du rendez-vous chez le dentiste.\n\n"
                f"Détails enregistrés :\n{details or 'Rendez-vous confirmé'}\n\n"
                f"Le script dentiste s'est arrêté automatiquement et n'enverra plus aucune relance.\n\n"
                f"— Ton assistant automatique"
            )
        else:
            subject = "🎉 RDV dermatologue confirmé par Maman !"
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

    def notify_user_appointment_booked(self, details):
        """Backwards-compatible wrapper for dermatologist notification."""
        self.notify_user_goal_completed(details, campaign="dermato")

    def _matches_campaign(self, subject, in_reply_to, references, campaign=None, expected_message_id=None):
        """Checks whether an incoming email belongs to the specified campaign."""
        if not campaign:
            return True

        if expected_message_id:
            if isinstance(expected_message_id, (list, tuple, set)):
                expected_ids = [str(eid).strip() for eid in expected_message_id if str(eid).strip()]
            else:
                expected_ids = [str(expected_message_id).strip()] if str(expected_message_id).strip() else []
            for clean_id in expected_ids:
                if clean_id in (in_reply_to or "") or clean_id in (references or ""):
                    return True

        subj = (subject or "").lower()
        campaign_keywords = {
            "accessoires_clim": ("accessoires", "tuyau", "fenêtre", "fenetre", "hoomee"),
            "clim": ("climatiseur mobile", "valberg", "electro"),
            "dentiste": ("dentiste", "dent", "incisive"),
            "dermato": ("dermato", "dermatologue"),
        }

        own_kws = campaign_keywords.get(campaign, ())
        if any(kw in subj for kw in own_kws):
            return True

        # Reject if the subject explicitly belongs to another campaign
        for other_camp, kws in campaign_keywords.items():
            if other_camp != campaign and any(kw in subj for kw in kws):
                return False

        return True

    def fetch_new_replies(self, last_seen_uid=None, campaign=None, expected_message_id=None, sender_emails=None):
        """
        Fetches unread / recent replies from target email address(es) via IMAP.
        sender_emails: optional dict {email_addr: role} (e.g. {"maman@...": "mother", "julie@...": "sister"}).
        """
        if Config.DRY_RUN:
            print("[DRY-RUN] Recherche de réponses IMAP simulée (aucune nouvelle réponse).")
            return []

        if not sender_emails:
            sender_emails = {self.mother_email: "mother"}

        replies = []
        seen_uids = set()
        try:
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=30) as mail:
                mail.login(self.user, self.password)
                mail.select("INBOX", readonly=True)

                for sender_addr, sender_role in sender_emails.items():
                    if not sender_addr:
                        continue
                    search_query = f'(FROM "{sender_addr}")'
                    status, data = mail.search(None, search_query)
                    if status != "OK" or not data or not data[0]:
                        continue

                    message_ids = data[0].split()
                    for num in message_ids:
                        status_uid, uid_data = mail.fetch(num, "(UID)")
                        uid = None
                        if status_uid == "OK" and uid_data:
                            match = re.search(rb"UID\s+(\d+)", uid_data[0])
                            if match:
                                uid = int(match.group(1))

                        if uid and last_seen_uid and uid <= int(last_seen_uid):
                            continue
                        if uid and uid in seen_uids:
                            continue

                        status_msg, msg_data = mail.fetch(num, "(RFC822)")
                        if status_msg != "OK" or not msg_data:
                            continue

                        raw_email = msg_data[0][1]
                        parsed_email = email.message_from_bytes(raw_email)

                        msg_id = parsed_email.get("Message-ID", "")
                        subject = self._decode_header(parsed_email.get("Subject", ""))
                        in_reply_to = parsed_email.get("In-Reply-To", "")
                        references = parsed_email.get("References", "")

                        if not self._matches_campaign(subject, in_reply_to, references, campaign=campaign, expected_message_id=expected_message_id):
                            continue

                        date_header = parsed_email.get("Date", "")
                        try:
                            date_dt = parsedate_to_datetime(date_header)
                            date_iso = date_dt.isoformat()
                        except Exception:
                            date_iso = None

                        body = self._extract_body(parsed_email)
                        clean_body = self._clean_reply_text(body)

                        if clean_body.strip():
                            if uid:
                                seen_uids.add(uid)
                            replies.append({
                                "uid": uid,
                                "message_id": msg_id,
                                "date": date_iso,
                                "subject": subject,
                                "body": clean_body,
                                "sender_email": sender_addr,
                                "sender_role": sender_role,
                            })

        except Exception as e:
            print(f"[EmailService] Erreur lors de la lecture IMAP: {e}")

        replies.sort(key=lambda r: r.get("uid") or 0)
        return replies

    def get_latest_inbox_uid(self):
        """Returns the highest UID currently in INBOX, or None."""
        if Config.DRY_RUN:
            return None
        try:
            with imaplib.IMAP4_SSL(self.imap_host, self.imap_port, timeout=30) as mail:
                mail.login(self.user, self.password)
                status, count = mail.select("INBOX", readonly=True)
                if status == "OK" and count and count[0]:
                    total = int(count[0].decode())
                    if total > 0:
                        status_uid, uid_data = mail.fetch(str(total), "(UID)")
                        if status_uid == "OK" and uid_data:
                            match = re.search(rb"UID\s+(\d+)", uid_data[0])
                            if match:
                                return int(match.group(1))
        except Exception as e:
            print(f"[EmailService] Erreur lors de la récupération du dernier UID : {e}")
        return None

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
