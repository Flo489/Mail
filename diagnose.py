import os
import imaplib
import email
from email.utils import parsedate_to_datetime
import re

def diagnose():
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    mother_email = os.getenv("MOTHER_EMAIL")

    print(f"=== DIAGNOSTIC GMAIL ===")
    print(f"User: {user}")
    print(f"Mother target: {mother_email}")

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
    mail.login(user, password)
    
    # 1. Check INBOX
    status, count = mail.select("INBOX", readonly=True)
    total_msgs = int(count[0].decode())
    print(f"\n📁 Dossier INBOX : {total_msgs} messages au total.")

    # Get last 10 message UIDs in INBOX
    start = max(1, total_msgs - 9)
    res, data = mail.fetch(f"{start}:{total_msgs}", "(UID FLAGS RFC822.HEADER)")
    if res == "OK":
        print(f"\n--- 10 Derniers messages dans INBOX ---")
        for item in data:
            if isinstance(item, tuple):
                header_text = item[1]
                msg = email.message_from_bytes(header_text)
                from_hdr = msg.get("From", "")
                subject_hdr = msg.get("Subject", "")
                date_hdr = msg.get("Date", "")
                
                uid_match = re.search(rb"UID\s+(\d+)", item[0])
                uid = uid_match.group(1).decode() if uid_match else "N/A"
                print(f"UID: {uid} | De: {from_hdr} | Date: {date_hdr} | Sujet: {subject_hdr}")

    # 2. Check search for mother
    status, search_data = mail.search(None, f'(FROM "{mother_email}")')
    print(f"\n--- Recherche FROM {mother_email} ---")
    if search_data and search_data[0]:
        msg_ids = search_data[0].split()
        print(f"Messages trouvés : {len(msg_ids)}")
        for mid in msg_ids[-5:]:
            r, mdata = mail.fetch(mid, "(UID RFC822.HEADER)")
            if r == "OK":
                for item in mdata:
                    if isinstance(item, tuple):
                        msg = email.message_from_bytes(item[1])
                        uid_match = re.search(rb"UID\s+(\d+)", item[0])
                        uid = uid_match.group(1).decode() if uid_match else "N/A"
                        print(f"  -> UID: {uid} | Date: {msg.get('Date')} | Sujet: {msg.get('Subject')}")
    else:
        print("Aucun message trouvé pour cette adresse.")

    # 3. Check Sent folder
    # List mailboxes to find Sent folder name
    r, mailboxes = mail.list()
    sent_folder = None
    for mb in mailboxes:
        decoded = mb.decode()
        if "\\Sent" in decoded:
            # extract folder name
            match = re.search(r'"([^"]+)"$', decoded) or re.search(r'([^\s]+)$', decoded)
            if match:
                sent_folder = match.group(1)
                break
    
    if sent_folder:
        print(f"\n📁 Dossier Envoyés détecté : {sent_folder}")
        s, scount = mail.select(sent_folder, readonly=True)
        stotal = int(scount[0].decode())
        print(f"Total envoyés : {stotal}")
        sstart = max(1, stotal - 4)
        r, sdata = mail.fetch(f"{sstart}:{stotal}", "(UID RFC822.HEADER)")
        if r == "OK":
            print(f"--- 5 Derniers messages envoyés ---")
            for item in sdata:
                if isinstance(item, tuple):
                    msg = email.message_from_bytes(item[1])
                    print(f"  -> À: {msg.get('To')} | Date: {msg.get('Date')} | Sujet: {msg.get('Subject')}")

    mail.logout()
    print("\nDiagnostic terminé.")

if __name__ == "__main__":
    diagnose()
