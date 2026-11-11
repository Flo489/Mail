import sys
import os
import argparse
from datetime import datetime, timedelta
import pytz

from config import Config
from state_manager import StateManager
from gemini_client import GeminiClient
from email_service import EmailService

def parse_args():
    parser = argparse.ArgumentParser(description="Automatisation d'emails pour rendez-vous dermatologue")
    parser.add_argument("--dry-run", action="store_true", help="Exécute sans envoyer d'emails réels")
    parser.add_argument("--immediate", action="store_true", help="Envoie le 1er email immédiatement sans attendre demain 8h")
    parser.add_argument("--test", action="store_true", help="Envoie un message de test explicite")
    parser.add_argument("--status", action="store_true", help="Affiche le statut actuel et quitte")
    parser.add_argument("--reset", action="store_true", help="Réinitialise l'état local")
    return parser.parse_args()

def display_status(state_mgr):
    st = state_mgr.state
    print("=" * 60)
    print("📋 STATUT DE L'AUTOMATISATION DERMATOLOGUE")
    print("=" * 60)
    print(f"Statut : {st.get('status', 'INCONNU')}")
    print(f"Rendez-vous pris : {'OUI 🎉' if st.get('appointment_booked') else 'NON (en cours)'}")
    if st.get('appointment_details'):
        print(f"Détails du RDV : {st.get('appointment_details')}")
    print(f"Démarrage programmé : {st.get('scheduled_start_at')}")
    print(f"Dernier email envoyé : {st.get('last_email_sent_at')}")
    print(f"Dernier message reçu : {st.get('last_email_received_at')}")
    print(f"Nombre de relances : {st.get('reminder_count', 0)}")
    hours = state_mgr.get_hours_since_last_sent()
    if hours is not None:
        print(f"Temps écoulé depuis le dernier envoi : {hours:.1f} heures")
    print(f"Échanges enregistrés : {len(st.get('conversation_history', []))}")
    for idx, msg in enumerate(st.get("conversation_history", []), 1):
        role = "FLORENT" if msg.get("role") == "user" else "MAMAN"
        print(f"  [{idx}] {role} ({msg.get('timestamp')}) : {msg.get('content')[:80]}...")
    print("=" * 60)

def main():
    args = parse_args()

    if args.dry_run:
        Config.DRY_RUN = True

    state_mgr = StateManager(Config.STATE_FILE, Config.TIMEZONE)

    if args.reset:
        state_mgr.state = state_mgr._default_state()
        state_mgr.save()
        print("✅ État réinitialisé avec succès.")
        return 0

    if args.status:
        display_status(state_mgr)
        return 0

    tz = pytz.timezone(Config.TIMEZONE)
    now = datetime.now(tz)
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] Lancement de la vérification...")

    # 1. Validation de la configuration
    errors = Config.validate(check_gemini=bool(Config.GEMINI_API_KEY), check_email=not Config.DRY_RUN)
    if errors:
        for err in errors:
            print(f"⚠️  Configuration : {err}")
        if not Config.DRY_RUN:
            print("Arrêt : Veuillez renseigner les variables d'environnement requises.")
            return 1

    # 2. Vérification si déjà terminé
    if state_mgr.is_completed():
        print(f"🎉 Le rendez-vous chez le dermatologue a déjà été confirmé !")
        if state_mgr.state.get("appointment_details"):
            print(f"Détails : {state_mgr.state.get('appointment_details')}")
        print("Aucune action requise. Fin du processus.")
        return 0

    gemini = GeminiClient()
    email_svc = EmailService()

    is_test_mode = args.test or Config.IS_TEST

    # Initialisation de la date de démarrage si pas encore définie
    scheduled_start_iso = state_mgr.state.get("scheduled_start_at")
    if not scheduled_start_iso or is_test_mode or args.immediate or os.getenv("FORCE_START_NOW", "false").lower() in ("true", "1"):
        if args.immediate or is_test_mode or os.getenv("FORCE_START_NOW", "false").lower() in ("true", "1"):
            scheduled_start_dt = now
        else:
            # Demain matin à 8h heure locale
            tomorrow = now.date() + timedelta(days=1)
            scheduled_start_dt = tz.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, Config.START_HOUR, 0, 0))
        
        state_mgr.state["scheduled_start_at"] = scheduled_start_dt.isoformat()
        state_mgr.save()
        print(f"📅 Date de premier envoi programmée : {scheduled_start_dt.strftime('%d/%m/%Y à %H:%M')}")

    scheduled_start_dt = state_mgr.parse_iso(state_mgr.state.get("scheduled_start_at"))

    # 3. Vérification des réponses de Maman (IMAP)
    # Seulement si un premier email a déjà été envoyé
    if state_mgr.state.get("last_email_sent_at"):
        print("🔍 Recherche de nouvelles réponses de Maman...")
        last_uid = state_mgr.state.get("last_seen_imap_uid")
        new_replies = email_svc.fetch_new_replies(last_seen_uid=last_uid)

        if new_replies:
            print(f"📩 {len(new_replies)} nouvelle(s) réponse(s) détectée(s) !")
            for reply in new_replies:
                print(f"De Maman ({reply.get('date')}) : \"{reply.get('body')}\"")
                
                # Analyse intelligente par Gemini
                analysis = gemini.analyze_mother_reply(
                    state_mgr.state.get("conversation_history", []),
                    reply.get("body", "")
                )
                print(f"💡 Analyse Gemini : {analysis.get('summary')}")

                # Enregistrement du message de maman
                state_mgr.record_received_email(
                    uid=reply.get("uid"),
                    content=reply.get("body"),
                    date_iso=reply.get("date")
                )

                # Cas 1 : Rendez-vous pris !
                if analysis.get("appointment_booked"):
                    print("🎯 RDV CONFIRMÉ PAR MAMAN !")
                    details = analysis.get("appointment_details") or reply.get("body")
                    state_mgr.mark_appointment_booked(details)

                    # Envoi d'un mot de remerciement à maman
                    thank_you_body = analysis.get("suggested_reply") or (
                        f"Merci mille fois Maman ! Tu gères, c'est super gentil.\n\n"
                        f"Gros bisous,\n{Config.USER_NAME}"
                    )
                    parent_id = reply.get("message_id") or state_mgr.state.get("last_sent_message_id")
                    email_svc.send_email(
                        to_addr=Config.MOTHER_EMAIL,
                        subject=f"Re: {Config.EMAIL_SUBJECT}",
                        body_text=thank_you_body,
                        reply_to_message_id=parent_id
                    )

                    # Notification pour Florent
                    email_svc.notify_user_appointment_booked(details)
                    print("✅ Remerciements envoyés à maman et notification transmise à Florent.")
                    return 0

                # Cas 2 : Maman a posé une question ou répondu
                if analysis.get("needs_reply", True):
                    reply_text = analysis.get("suggested_reply")
                    if reply_text:
                        print(f"✉️  Envoi de la réponse adaptée à Maman...")
                        parent_id = reply.get("message_id") or state_mgr.state.get("last_sent_message_id")
                        msg_id = email_svc.send_email(
                            to_addr=Config.MOTHER_EMAIL,
                            subject=f"Re: {Config.EMAIL_SUBJECT}",
                            body_text=reply_text,
                            reply_to_message_id=parent_id
                        )
                        state_mgr.record_sent_email(
                            subject=f"Re: {Config.EMAIL_SUBJECT}",
                            content=reply_text,
                            message_id=msg_id
                        )

            # Fin du traitement des nouvelles réponses
            return 0

    # 4. Si aucune nouvelle réponse de Maman :
    # A) Premier email pas encore envoyé
    if not state_mgr.state.get("last_email_sent_at"):
        if now < scheduled_start_dt and not (args.immediate or is_test_mode or os.getenv("FORCE_START_NOW", "false").lower() in ("true", "1")):
            print(f"⏳ Le premier email est programmé pour le {scheduled_start_dt.strftime('%d/%m/%Y à %H:%M')}. Heure actuelle : {now.strftime('%H:%M')}. En attente.")
            return 0

        email_subject = f"[TEST] {Config.EMAIL_SUBJECT}" if is_test_mode else Config.EMAIL_SUBJECT
        print(f"🚀 Envoi du premier email à Maman{' (MODE TEST)' if is_test_mode else ''}...")
        initial_text = gemini.generate_initial_email(is_test=is_test_mode)
        msg_id = email_svc.send_email(
            to_addr=Config.MOTHER_EMAIL,
            subject=email_subject,
            body_text=initial_text
        )
        state_mgr.record_sent_email(
            subject=email_subject,
            content=initial_text,
            message_id=msg_id
        )
        print("✅ Premier email envoyé avec succès.")
        return 0

    # B) Premier email déjà envoyé : vérifier si 24h sans réponse
    hours_since_sent = state_mgr.get_hours_since_last_sent()
    reminder_interval = Config.REMINDER_INTERVAL_HOURS

    if hours_since_sent is None or hours_since_sent < reminder_interval:
        remaining = reminder_interval - (hours_since_sent or 0)
        print(f"⏳ Dernier email envoyé il y a {hours_since_sent:.1f}h. Pas de relance nécessaire pour le moment (prochaine relance possible dans {remaining:.1f}h).")
        return 0

    # C) 24h écoulées sans réponse : envoyer une relance !
    # Vérification des heures de tranquillité (ne pas envoyer entre 21h et 8h)
    if now.hour < Config.QUIET_HOURS_END or now.hour >= Config.QUIET_HOURS_START:
        print(f"🌙 Il est {now.strftime('%H:%M')}. Relance reportée à demain matin (à partir de 8h) pour ne pas déranger Maman en pleine nuit.")
        return 0

    count = state_mgr.state.get("reminder_count", 0)
    print(f"🔔 24h sans réponse écoulées. Préparation de la relance n°{count + 1}...")

    reminder_text = gemini.generate_reminder_email(
        state_mgr.state.get("conversation_history", []),
        count
    )

    parent_id = state_mgr.state.get("last_sent_message_id")
    msg_id = email_svc.send_email(
        to_addr=Config.MOTHER_EMAIL,
        subject=f"Re: {Config.EMAIL_SUBJECT}",
        body_text=reminder_text,
        reply_to_message_id=parent_id
    )

    state_mgr.state["reminder_count"] = count + 1
    state_mgr.record_sent_email(
        subject=f"Re: {Config.EMAIL_SUBJECT}",
        content=reminder_text,
        message_id=msg_id
    )
    print(f"✅ Relance n°{count + 1} envoyée à Maman.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
