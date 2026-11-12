import os
import imaplib
import email
from email.utils import parsedate_to_datetime
import re

def parse_box_name(line):
    # Match pattern: (\Flags) "/" "Folder Name" or (\Flags) "/" FolderName
    match = re.search(r'\(([^)]*)\)\s+"([^"]+)"\s+(.+)$', line)
    if match:
        name = match.group(3).strip()
        if name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        return name
    return None

def diagnose():
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    mother_email = os.getenv("MOTHER_EMAIL")

    print(f"=== DIAGNOSTIC GMAIL APPROFONDI ===")
    print(f"User: {user}")
    print(f"Mother: {mother_email}")

    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
    mail.login(user, password)
    
    r, boxes = mail.list()
    box_map = {}
    print("\n--- Liste des dossiers disponibles ---")
    for b in boxes:
        decoded = b.decode("utf-8", errors="replace")
        box_name = parse_box_name(decoded)
        print(f"  {decoded} -> '{box_name}'")
        if "\\All" in decoded:
            box_map["all"] = box_name
        if "\\Sent" in decoded:
            box_map["sent"] = box_name
        if "\\Junk" in decoded or "\\Spam" in decoded:
            box_map["spam"] = box_name

    # 1. Vérification dans "Tous les messages" (All Mail)
    target_all = box_map.get("all")
    if target_all:
        print(f"\n📂 Recherche globale dans '{target_all}'...")
        mail.select(f'"{target_all}"', readonly=True)
        status, data = mail.search(None, f'(FROM "{mother_email}")')
        if status == "OK" and data and data[0]:
            mids = data[0].split()
            print(f"✅ Trouvé {len(mids)} message(s) de Maman dans Tout le compte :")
            for mid in mids:
                res, mdata = mail.fetch(mid, "(UID RFC822.HEADER)")
                if res == "OK":
                    for item in mdata:
                        if isinstance(item, tuple):
                            msg = email.message_from_bytes(item[1])
                            uid_match = re.search(rb"UID\s+(\d+)", item[0])
                            uid = uid_match.group(1).decode() if uid_match else "N/A"
                            print(f"   UID: {uid} | Date: {msg.get('Date')} | Objet: {msg.get('Subject')}")
        else:
            print(f"❌ Aucun message de {mother_email} trouvé dans '{target_all}'.")

    # 2. Vérification dans "Messages envoyés" (Sent)
    target_sent = box_map.get("sent")
    if target_sent:
        print(f"\n📤 Messages dans le dossier Envoyés ('{target_sent}') :")
        mail.select(f'"{target_sent}"', readonly=True)
        status, data = mail.search(None, f'(TO "{mother_email}")')
        if status == "OK" and data and data[0]:
            mids = data[0].split()
            print(f"✅ Trouvé {len(mids)} email(s) envoyé(s) à Maman :")
            for mid in mids[-5:]:
                res, mdata = mail.fetch(mid, "(RFC822.HEADER)")
                if res == "OK":
                    for item in mdata:
                        if isinstance(item, tuple):
                            msg = email.message_from_bytes(item[1])
                            print(f"   Date: {msg.get('Date')} | Objet: {msg.get('Subject')}")
        else:
            print(f"❌ Aucun email trouvé envoyé à {mother_email}.")

    # 3. Vérification dans Spam
    target_spam = box_map.get("spam")
    if target_spam:
        print(f"\n⚠️ Recherche dans le dossier Spam ('{target_spam}')...")
        mail.select(f'"{target_spam}"', readonly=True)
        status, data = mail.search(None, f'(FROM "{mother_email}")')
        if status == "OK" and data and data[0]:
            mids = data[0].split()
            print(f"Trouvé {len(mids)} message(s) dans les SPAMS !")
        else:
            print("Rien dans les spams.")

    mail.logout()
    print("\nFin du diagnostic.")

if __name__ == "__main__":
    diagnose()
