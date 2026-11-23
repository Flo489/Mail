import json
import urllib.request
import urllib.error
import re
from config import Config

CLIM_PRODUCT_CONTEXT = """
Produit souhaité : Climatiseur mobile VALBERG 9000 BTU pour pièce de 20m² (chez Electro Dépôt)
- Prix : 219,98 € (dont 9,23 € d'éco-part)
- Paiement possible en 3x sans frais (73,34 € + 2 x 73,32 €)
- Note client : 4,2 / 5 (472 avis)
- Classe énergétique : A
- Disponibilité : Disponible en drive sous 1h à Electro Dépôt Hénin-Beaumont, ou en livraison
- Pourquoi Florent en a besoin : pour survivre en été car il fait plus de 30°C dans sa chambre pendant de nombreux jours.
- Une capture d'écran de la fiche produit Electro Dépôt est jointe au premier email.
""".strip()

DENTISTE_CONTEXT = """
Motif du rendez-vous chez le dentiste pour Florent :
- Des traces brunâtres à grisâtres sont apparues récemment en surface sur le bord inférieur des deux incisives du haut (et plus discrètement sur celles du bas).
- Ce type de marque correspond très probablement à une coloration superficielle bénigne — causée par des pigments alimentaires, un produit d'hygiène dentaire ou un assèchement passager de l'émail — et non à une atteinte profonde de la dent.
- Ce phénomène est réversible : il convient de conserver un brossage doux normal pendant deux à trois semaines en évitant absolument les produits abrasifs (bicarbonate, citron, dentifrice blancheur) qui risqueraient de rayer l'émail.
- Si les taches ne s'estompent pas d'elles-mêmes d'ici là, ou si une sensibilité apparaît, une consultation classique chez le dentiste permettra de les éliminer rapidement par un simple polissage.
- Choix du dentiste : pas de dentiste précis imposé, une consultation classique chez un dentiste disponible conviendra très bien.
""".strip()

ACCESSOIRES_CLIM_CONTEXT = """
Les 2 accessoires complémentaires pour installer le climatiseur mobile (chez Amazon) :
1) Tuyau d'échappement de climatiseur universel (marque equlup, filet CCW) :
   - Dimensions : 3 mètres de long (3.28 yd), 150 mm de diamètre
   - Prix : 24,03 € (livraison et retours gratuits, expédié par Amazon)
   - Lien Amazon : https://www.amazon.fr/dp/B0GYZ1RZSF?th=1
2) Tissu d'isolation pour fenêtre à pivot central HOOMEE (kit calfeutrage fenêtre) :
   - Dimensions : périmètre de 381 cm à 460 cm (taille sélectionnée : 2x 230 cm), adapté à toutes les unités mobiles de climatisation
   - Note client : 4,2 / 5 (1 641 avis)
   - Prix : 33,99 € (livraison et retours gratuits, expédié par Amazon)
   - Lien Amazon : https://www.amazon.fr/HOOMEE-dIsolation-P%C3%A9rim%C3%A8tre-Climatiseur-S%C3%A8che-Linge/dp/B08336NZKX?th=1
Total des 2 articles : 58,02 €.
Pourquoi : indispensables pour évacuer l'air chaud dehors par la fenêtre sans laisser rentrer la chaleur l'été (plus de 30°C dans la chambre).
Les deux captures d'écran Amazon sont jointes au premier email.
""".strip()

class GeminiClient:
    def __init__(self, api_key=None, campaign=None):
        self.api_key = api_key or Config.GEMINI_API_KEY
        self.campaign = (campaign or Config.CAMPAIGN or "dermato").strip().lower()
        self.models = [
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash"
        ]

    def _call_gemini(self, prompt, system_instruction=None, json_mode=False):
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY n'est pas configuré.")

        for model_name in self.models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            
            payload = {
                "contents": [
                    {
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "maxOutputTokens": 8192,
                }
            }
            
            if json_mode:
                payload["generationConfig"]["responseMimeType"] = "application/json"

            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    candidate = data["candidates"][0]
                    finish_reason = candidate.get("finishReason", "STOP")
                    if finish_reason == "MAX_TOKENS":
                        print(f"[GeminiClient] Modèle {model_name} tronqué (MAX_TOKENS). Passage au suivant.")
                        continue
                    parts = candidate.get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                    if not text.strip():
                        print(f"[GeminiClient] Modèle {model_name} a renvoyé un texte vide (finishReason={finish_reason}).")
                        continue
                    return text
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                print(f"[GeminiClient] Modèle {model_name} HTTP {e.code}: {err_body}")
                continue
            except Exception as e:
                print(f"[GeminiClient] Erreur avec {model_name}: {e}")
                continue

        raise RuntimeError("Impossible de joindre l'API Gemini avec les modèles configurés.")

    def clean_json_response(self, raw_text):
        """Cleans and extracts JSON from response."""
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())

    def analyze_mother_reply(self, history, new_reply_text, sender_role="mother"):
        """
        Analyzes mother's (or sister's) reply.
        Returns a dict:
        {
            "appointment_booked": bool,
            "appointment_details": str or None,
            "summary": str,
            "needs_reply": bool,
            "suggested_reply": str,
            "notify_other_message": str or None
        }
        """
        history_formatted = "\n".join([
            f"- [{h.get('role', 'inconnu').upper()} à {h.get('timestamp', '')}]: {h.get('content', '')}"
            for h in history[-8:]
        ])

        if self.campaign == "clim":
            system_instruction = (
                f"Tu es un assistant personnel qui aide {Config.USER_NAME} à échanger par email avec sa maman ('Maman') "
                "pour l'achat d'un climatiseur mobile pour sa chambre afin de survivre aux fortes chaleurs d'été (+30°C pendant de nombreux jours).\n"
                "Le ton est bienveillant, affectueux, naturel et poli (Florent tutoie sa mère et l'appelle 'Maman').\n"
                "Tu dois analyser la réponse de sa mère avec précision."
            )
            prompt = f"""
Voici l'historique des derniers échanges :
{history_formatted}

Voici le NOUVEAU message reçu de Maman :
\"\"\"{new_reply_text}\"\"\"

Contexte du produit souhaité :
{CLIM_PRODUCT_CONTEXT}

Consignes strictes :
1. "appointment_booked" : mets TRUE UNIQUEMENT si la maman affirme clairement que la clim a été achetée, commandée ou réservée (ex: "c'est bon je l'ai commandée", "je l'ai achetée", "on va la chercher demain c'est payé"). Si elle dit qu'elle va regarder, qu'elle hésite, qu'elle trouve ça cher, qu'elle verra plus tard, ou qu'elle pose une question, mets FALSE.
2. "appointment_details" : si l'achat/commande est confirmé, extrais les infos (magasin, date de retrait/livraison, etc.). Sinon null.
3. "summary" : résumé court en 1 phrase de ce qu'elle dit.
4. "needs_reply" : true si sa réponse appelle une réponse de Florent (question sur le prix, la taille, l'évacuation, le magasin, hésitation, ou confirmation pour la remercier).
5. "suggested_reply" : rédige un email complet en français, naturel, affectueux, poli, tutoyant sa maman ('tu', 'Maman'), signé '{Config.USER_NAME}'.
   - Si elle a acheté/commandé la clim : remercie-la chaleureusement ("Merci mille fois Maman ! Tu me sauves la vie pour cet été...").
   - Si elle pose une question (prix, magasin, livraison, modèle, 3x sans frais) : réponds précisément avec les infos du contexte (Valberg 9000 BTU 20m² chez Electro Dépôt à 219,98 €, 3x sans frais dispo, classe A, drive 1h à Hénin-Beaumont ou livraison).
   - Si elle hésite ou dit qu'on a le temps : rassure-la gentiment tout en rappelant qu'il fait plus de 30°C dans la chambre pendant de nombreux jours l'été et qu'à 219,98 € (ou 3x sans frais) c'est super avant les ruptures de stock estivales.
   - Si elle n'a pas eu le temps : rassure-la gentiment ("Pas de souci maman, prends ton temps...").

Réponds STRICTEMENT sous ce format JSON :
{{
  "appointment_booked": false,
  "appointment_details": null,
  "summary": "...",
  "needs_reply": true,
  "suggested_reply": "..."
}}
"""
        elif self.campaign == "accessoires_clim":
            sister_name = Config.SISTER_NAME or "Julie"
            sender_label = sister_name if sender_role == "sister" else "Maman"
            other_label = "Maman" if sender_role == "sister" else sister_name
            system_instruction = (
                f"Tu es un assistant personnel qui aide {Config.USER_NAME} à échanger par email séparément avec sa maman ('Maman') "
                f"et sa sœur ('{sister_name}', qui fait les commandes sur internet) pour l'achat des 2 accessoires de la clim sur Amazon.\n"
                "Les messages doivent être TRÈS NATURELS, chaleureux, spontanés et familiaux (pas du tout robotiques). "
                f"Florent tutoie sa maman ('Maman') et sa sœur ('{sister_name}')."
            )
            prompt = f"""
Voici l'historique des derniers échanges (avec Maman et {sister_name}) :
{history_formatted}

Voici le NOUVEAU message reçu de **{sender_label}** :
\"\"\"{new_reply_text}\"\"\"

Contexte des 2 articles souhaités :
{ACCESSOIRES_CLIM_CONTEXT}

Consignes strictes :
1. "appointment_booked" : mets TRUE UNIQUEMENT si {sender_label} affirme clairement que les 2 articles ont été achetés/commandés (ex: "c'est bon je les ai commandés", "j'ai acheté les deux sur Amazon"). Si elle dit qu'elle va regarder, qu'elle attend l'accord de Maman, qu'elle hésite, ou qu'elle pose une question, mets FALSE.
2. "appointment_details" : si l'achat est confirmé, extrais les infos (date de livraison, etc.). Sinon null.
3. "summary" : résumé court en 1 phrase de ce que dit {sender_label}.
4. "needs_reply" : true si sa réponse appelle une réponse de Florent.
5. "suggested_reply" : rédige un email complet en français, naturel, spontané et chaleureux adressé directement à {sender_label}, signé '{Config.USER_NAME}'.
   - Si {sender_label} a commandé les 2 articles : remercie-la chaleureusement ("Merci mille fois {sender_label} ! Avec ça la clim sera au top cet été...").
   - Si {sender_label} pose une question (taille, diamètre, prix, liens, fenêtre) : réponds précisément et simplement avec les infos + liens du contexte.
   - Si {sender_label} dit qu'elle va le faire plus tard : rassure-la gentiment ("Pas de souci {sender_label}, prends ton temps...").
6. "notify_other_message" : un message naturel et court adressé à **{other_label}** pour la tenir au courant en parallèle, UNIQUEMENT si c'est utile :
   - Si "appointment_booked" est TRUE (par ex. {sister_name} vient de commander) : OBLIGATOIRE, écris un message naturel à {other_label} pour lui dire que c'est tout bon et que {sender_label} vient de commander les 2 accessoires (ex: "Coucou {other_label}, juste pour te dire que c'est bon, {sender_label} vient de commander le tuyau et le kit fenêtre sur Amazon ! Gros bisous, {Config.USER_NAME}").
   - Si Maman donne son feu vert pour que {sister_name} commande (ex: "c'est bon dis à Julie de commander") ou si {sister_name} dit qu'elle attend la validation de Maman : écris un petit message naturel à {other_label} pour faire le lien !
   - Sinon (simple question technique) : mets null.

Réponds STRICTEMENT sous ce format JSON :
{{
  "appointment_booked": false,
  "appointment_details": null,
  "summary": "...",
  "needs_reply": true,
  "suggested_reply": "...",
  "notify_other_message": null
}}
"""
        elif self.campaign == "dentiste":
            system_instruction = (
                f"Tu es un assistant personnel qui aide {Config.USER_NAME} à gérer la prise d'un rendez-vous chez le dentiste "
                "par sa maman ('Maman'). Le ton est bienveillant, affectueux, rassurant et naturel (Florent tutoie sa mère et l'appelle 'Maman').\n"
                "Tu dois analyser la réponse de sa mère avec précision."
            )
            prompt = f"""
Voici l'historique des derniers échanges :
{history_formatted}

Voici le NOUVEAU message reçu de Maman :
\"\"\"{new_reply_text}\"\"\"

Informations disponibles sur Florent :
- Prénom : {Config.USER_NAME}
- Disponibilités si demandées : {Config.USER_AVAILABILITY}
{DENTISTE_CONTEXT}

Consignes strictes :
1. "appointment_booked" : mets TRUE UNIQUEMENT si la maman affirme clairement que le rendez-vous chez le dentiste a été pris ou réservé (ex: "c'est bon le rdv est pris", "j'ai pris rdv le 12 mai à 14h"). Si elle dit qu'elle va appeler, qu'elle essaiera plus tard, ou qu'elle pose une question, mets FALSE.
2. "appointment_details" : si le rdv est pris, extrais la date, heure et lieu mentionnés. Sinon null.
3. "summary" : résumé court en 1 phrase de ce qu'elle dit.
4. "needs_reply" : true si sa réponse appelle une réponse de Florent (ex: elle s'inquiète des taches, pose une question sur ses disponibilités ou sur ce que c'est, ou confirme le rdv pour la remercier).
5. "suggested_reply" : rédige un email complet en français, naturel, affectueux, rassurant, tutoyant sa maman ('tu', 'Maman'), signé '{Config.USER_NAME}'.
   - Si le rdv est pris : remercie-la chaleureusement ("Merci mille fois maman ! Tu gères...").
   - Si elle s'inquiète ou demande des précisions sur les taches : rassure-la en utilisant les infos du contexte (coloration superficielle bénigne et réversible, probablement pigments alimentaires / produit d'hygiène / assèchement passager de l'émail, pas une atteinte profonde, brossage doux sans produits abrasifs et un simple polissage chez le dentiste suffira si besoin).
   - Si elle demande des disponibilités : donne gentiment ses disponibilités ({Config.USER_AVAILABILITY}) en restant très souple.
   - Si elle n'a pas eu le temps : rassure-la gentiment ("Pas de souci maman, prends ton temps...").

Réponds STRICTEMENT sous ce format JSON :
{{
  "appointment_booked": false,
  "appointment_details": null,
  "summary": "...",
  "needs_reply": true,
  "suggested_reply": "..."
}}
"""
        else:
            system_instruction = (
                "Tu es un assistant personnel qui aide Florent à gérer la prise d'un rendez-vous chez le dermatologue "
                "par sa maman. L'adresse est bienveillante, affectueuse et naturelle (Florent appelle sa mère 'Maman').\n"
                "Tu dois analyser la réponse de sa mère avec précision."
            )
            prompt = f"""
Voici l'historique des derniers échanges :
{history_formatted}

Voici le NOUVEAU message reçu de Maman :
\"\"\"{new_reply_text}\"\"\"

Informations disponibles sur Florent :
- Prénom : {Config.USER_NAME}
- Disponibilités si demandées : {Config.USER_AVAILABILITY}
- Choix du dermatologue : Florent n'a pas de dermatologue précis en tête, celui/celle que sa maman trouve conviendra parfaitement.

Consignes strictes :
1. "appointment_booked" : mets TRUE UNIQUEMENT si la maman affirme clairement que le rendez-vous a été pris ou réservé (ex: "c'est bon le rdv est pris", "j'ai pris rdv le 12 mai à 14h"). Si elle dit qu'elle va appeler, qu'elle essaiera plus tard, ou qu'elle n'a pas eu le temps, mets FALSE.
2. "appointment_details" : si le rdv est pris, extrais la date, heure et lieu mentionnés. Sinon null.
3. "summary" : résumé court en 1 phrase de ce qu'elle dit.
4. "needs_reply" : true si sa réponse appelle une réponse de Florent (ex: elle pose une question sur ses disponibilités, ou demande une précision, ou confirme le rdv pour le remercier).
5. "suggested_reply" : rédige un email complet en français, naturel, affectueux, poli, tutoyant sa maman ('tu', 'Maman'), signé '{Config.USER_NAME}'. 
   - Si le rdv est pris : remercie-la chaleureusement ("Merci beaucoup maman ! Tu assures...").
   - Si elle demande des disponibilités : donne gentiment ses disponibilités ({Config.USER_AVAILABILITY}) en restant très souple.
   - Si elle s'excuse ou n'a pas eu le temps : rassure-la ("Pas de souci maman, prends ton temps, pas de stress...").

Réponds STRICTEMENT sous ce format JSON :
{{
  "appointment_booked": false,
  "appointment_details": null,
  "summary": "...",
  "needs_reply": true,
  "suggested_reply": "..."
}}
"""
        if not self.api_key:
            return self._fallback_analyze(new_reply_text, sender_role=sender_role)

        try:
            raw = self._call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
            return self.clean_json_response(raw)
        except Exception as e:
            print(f"[GeminiClient] Erreur pendant l'analyse Gemini: {e}. Utilisation du fallback heuristique.")
            return self._fallback_analyze(new_reply_text, sender_role=sender_role)

    def generate_reminder_email(self, history, reminder_count, recipient_role="mother"):
        """Generates a gentle follow-up reminder email when recipient hasn't answered for 24h."""
        if self.campaign == "clim":
            system_instruction = (
                f"Tu rédiges un email de relance de la part de {Config.USER_NAME} à sa maman ('Maman').\n"
                "Le ton doit être doux, affectueux, naturel, sans pression mais efficace. C'est pour lui rappeler "
                "l'achat du climatiseur mobile VALBERG 9000 BTU chez Electro Dépôt (219,98 €, dispo drive 1h à Hénin-Beaumont ou livraison) "
                "pour que Florent puisse survivre dans sa chambre qui dépasse les 30°C l'été."
            )
            prompt = f"""
C'est la relance numéro {reminder_count + 1} (environ {(reminder_count + 1) * 24}h se sont écoulées sans réponse).
Contexte produit :
{CLIM_PRODUCT_CONTEXT}

Écris un message court, affectueux et naturel en français, signé '{Config.USER_NAME}'.
- Relance 1 : simple rappel doux et gentil ("Coucou maman, juste un petit mot pour savoir si tu as pu jeter un œil à la clim chez Electro Dépôt...").
- Relance 2 : tendre, compréhension de son emploi du temps chargé, petit clin d'œil aux +30°C dans la chambre en été.
- Relance 3+ : avec un brin d'humour bienveillant (ex: "c'est encore moi et ma survie face aux 30°C dans ma chambre haha ! Promis dès que c'est commandé je te laisse tranquille...").

Réponds uniquement avec le texte complet du message (pas de JSON, pas de balises markdown).
"""
        elif self.campaign == "accessoires_clim":
            sister_name = Config.SISTER_NAME or "Julie"
            dest_label = sister_name if recipient_role == "sister" else "Maman"
            rel_desc = f"sa sœur ('{sister_name}')" if recipient_role == "sister" else "sa maman ('Maman')"
            system_instruction = (
                f"Tu rédiges un email de relance très naturel, spontané et chaleureux de la part de {Config.USER_NAME} à {rel_desc}.\n"
                "C'est pour lui rappeler gentiment l'achat des 2 accessoires de la clim sur Amazon (tuyau 3m 150mm à 24,03 € + kit isolation fenêtre HOOMEE 2x230cm à 33,99 €)."
            )
            prompt = f"""
C'est la relance numéro {reminder_count + 1} adressée à {dest_label}.
Contexte des 2 articles :
{ACCESSOIRES_CLIM_CONTEXT}

Écris un message court, très naturel et familier en français (pas robotique), tutoyant {dest_label}, signé '{Config.USER_NAME}'.
- Si c'est pour {sister_name} : rappelle-lui gentiment les deux liens Amazon si elle a deux minutes pour commander (avec l'accord de Maman).
- Si c'est pour Maman : demande-lui gentiment si elle a pu voir avec {sister_name} pour les deux accessoires sur Amazon.
- Relance 1 : simple rappel doux.
- Relance 2 : compréhension de son emploi du temps.
- Relance 3+ : petite touche d'humour bienveillante ("c'est encore moi et mon kit anti-canicule haha...").

Réponds uniquement avec le texte complet du message (pas de JSON, pas de balises markdown).
"""
        elif self.campaign == "dentiste":
            system_instruction = (
                f"Tu rédiges un email de relance de la part de {Config.USER_NAME} à sa maman ('Maman').\n"
                "Le ton doit être doux, affectueux, rassurant, sans pression mais efficace. C'est pour lui rappeler "
                "de prendre un rendez-vous classique chez le dentiste POUR FLORENT (pour vérifier/polir les petites traces superficielles sur ses incisives)."
            )
            prompt = f"""
C'est la relance numéro {reminder_count + 1} (environ {(reminder_count + 1) * 24}h se sont écoulées sans réponse).
Écris un message court, affectueux et naturel en français, signé '{Config.USER_NAME}'.
IMPORTANT : Le rendez-vous est POUR FLORENT (écris bien "mon rendez-vous" ou "un rendez-vous pour moi", JAMAIS "ton rendez-vous").
- Relance 1 : simple rappel doux et gentil ("Coucou maman, juste un petit mot pour savoir si tu as pu regarder pour mon rendez-vous chez le dentiste...").
- Relance 2 : tendre, compréhension de son emploi du temps chargé, en rappelant que ce n'est rien de grave mais qu'il vaut mieux caler un créneau si besoin d'un polissage.
- Relance 3+ : avec un brin d'humour bienveillant ("Coucou maman, c'est encore moi et mon histoire de dentiste haha ! Promis dès que le rendez-vous est pris je te laisse tranquille...").

Réponds uniquement avec le texte complet du message (pas de JSON, pas de balises markdown).
"""
        else:
            system_instruction = (
                f"Tu rédiges un email de relance de la part de {Config.USER_NAME} à sa maman ('Maman').\n"
                "Le ton doit être doux, affectueux, sans pression mais efficace. C'est pour lui rappeler de prendre "
                "un rendez-vous chez le dermatologue pour lui."
            )
            prompt = f"""
C'est la relance numéro {reminder_count + 1} (environ {(reminder_count + 1) * 24}h se sont écoulées sans réponse).
Écris un message court, affectueux et naturel en français, signé '{Config.USER_NAME}'.
- Relance 1 : simple rappel doux et gentil ("Coucou maman, juste un petit mot pour savoir si tu as pu regarder pour le dermato...").
- Relance 2 : tendre, compréhension de son emploi du temps chargé ("Coucou maman, petit mémo pour le dermato si tu as deux minutes dans ta journée...").
- Relance 3+ : avec un brin d'humour bienveillant ("Coucou maman, c'est encore moi et mon dermato haha ! Promis dès que c'est calé je te laisse tranquille...").

Réponds uniquement avec le texte du message (pas de JSON, pas de balises markdown).
"""
        if not self.api_key:
            return self._fallback_reminder(reminder_count, recipient_role=recipient_role)

        try:
            text = self._call_gemini(prompt, system_instruction=system_instruction, json_mode=False)
            return text.strip()
        except Exception as e:
            print(f"[GeminiClient] Erreur génération relance Gemini: {e}. Utilisation du fallback.")
            return self._fallback_reminder(reminder_count, recipient_role=recipient_role)

    def generate_initial_email(self, is_test=False, recipient_role="mother"):
        """Generates the very first email sent to mom (or sister)."""
        if is_test:
            recipient_label = "Florent" if "sauvageflorent.pro" in Config.TARGET_EMAIL else "Maman"
            return (
                f"Coucou {recipient_label},\n\n"
                f"Ceci est un message de TEST automatique envoyé à {Config.TARGET_EMAIL} pour tester le système de rappel et l'IA Gemini :)\n\n"
                f"Peux-tu répondre à cet email ?\n\n"
                f"Le robot va analyser ta réponse avec Gemini et t'envoyer automatiquement une réponse adaptée en retour !\n\n"
                f"{Config.USER_NAME}"
            )

        if self.campaign == "clim":
            fallback_clim = (
                f"Coucou Maman,\n\n"
                f"J'espère que tu vas bien ! Je voulais te parler d'un truc pour cet été : comme tu le sais, il fait souvent plus de 30°C "
                f"dans ma chambre pendant de nombreux jours et c'est vraiment dur de dormir et de tenir le coup.\n\n"
                f"J'ai repéré un climatiseur mobile qui a l'air super bien chez Electro Dépôt (je te mets la capture d'écran juste en dessous) :\n"
                f"- Climatiseur mobile VALBERG 9000 BTU pour pièce de 20m² (classe A, noté 4,2/5 sur 472 avis)\n"
                f"- Prix : 219,98 € (avec paiement en 3x sans frais possible : 73,34 € + 2 x 73,32 €)\n"
                f"- Disponible en drive sous 1h à Hénin-Beaumont ou en livraison.\n\n"
                f"Est-ce que tu penses qu'on pourrait l'acheter pour que je puisse survivre cet été ? Dis-moi ce que tu en penses !\n\n"
                f"Gros bisous,\n"
                f"{Config.USER_NAME}"
            )
            if not self.api_key:
                return fallback_clim

            prompt = f"""
Rédige le tout premier email de la part de {Config.USER_NAME} à sa maman ('Maman') pour lui demander d'acheter ce climatiseur mobile afin de survivre en été (il fait plus de 30°C dans sa chambre pendant de nombreux jours).

Voici toutes les infos exactes sur la clim (une capture d'écran de la fiche Electro Dépôt est jointe à l'email) :
{CLIM_PRODUCT_CONTEXT}

Consignes :
- Ton très naturel, affectueux, attentionné, tutoyant sa maman ('Maman').
- Mentionne clairement le modèle (Climatiseur mobile VALBERG 9000 BTU pour 20m² chez Electro Dépôt), le prix (219,98 €, 3x sans frais possible), la classe A / bonne note (4,2/5), et qu'il est dispo en drive sous 1h à Hénin-Beaumont ou en livraison.
- Mentionne qu'une capture d'écran du produit est jointe dans le mail.
- Explique bien la raison (plus de 30°C dans la chambre pendant de nombreux jours l'été, indispensable pour survivre et dormir).
- Signé '{Config.USER_NAME}'.
- Réponds uniquement avec le texte du message (pas d'objet, pas de balises markdown).
"""
            try:
                text = self._call_gemini(prompt, json_mode=False)
                return text.strip()
            except Exception:
                return fallback_clim

        if self.campaign == "accessoires_clim":
            sister_name = Config.SISTER_NAME or "Julie"
            tuyau_url = "https://www.amazon.fr/dp/B0GYZ1RZSF?th=1"
            kit_url = "https://www.amazon.fr/HOOMEE-dIsolation-P%C3%A9rim%C3%A8tre-Climatiseur-S%C3%A8che-Linge/dp/B08336NZKX?th=1"
            if recipient_role == "sister":
                fallback_acc = (
                    f"Coucou {sister_name},\n\n"
                    f"J'espère que tu vas bien et que tu as passé de bonnes fêtes ! Je voulais attendre que Noël soit passé pour ne pas vous embêter avec ça avant.\n\n"
                    f"Comme c'est toi qui gères les commandes sur internet, est-ce que tu pourrais commander (avec Maman) les deux petits accessoires sur Amazon pour que je puisse installer ma clim dans ma chambre ?\n\n"
                    f"1) Le tuyau d'échappement equlup (3m, 150 mm de diamètre, filet CCW) — 24,03 € :\n{tuyau_url}\n\n"
                    f"2) Le tissu d'isolation pour fenêtre à pivot central HOOMEE (périmètre 381-460 cm, taille 2x 230 cm) — 33,99 € :\n{kit_url}\n\n"
                    f"Ça fait 58,02 € au total (livraison et retours gratuits). Je te mets aussi les captures en dessous pour que tu voies bien les options sélectionnées. J'ai aussi envoyé un mail à Maman pour la mettre au courant.\n\n"
                    f"Merci d'avance ! Dis-moi quand c'est bon ou si tu as un doute,\n"
                    f"{Config.USER_NAME}"
                )
            else:
                fallback_acc = (
                    f"Coucou Maman,\n\n"
                    f"J'espère que tu vas bien et que tu as passé de bonnes fêtes ! Je voulais attendre après Noël pour ne pas te déranger avec ça avant.\n\n"
                    f"Pour que le climatiseur mobile fonctionne bien dans ma chambre cet été (et éviter les +30°C), il faudrait deux petits accessoires complémentaires sur Amazon (je les ai aussi envoyés à {sister_name} comme c'est elle qui commande sur internet) :\n"
                    f"1) Tuyau d'échappement equlup (3m, 150 mm de diamètre) à 24,03 € :\n{tuyau_url}\n\n"
                    f"2) Tissu d'isolation pour fenêtre à pivot central HOOMEE (taille 2x 230 cm) à 33,99 € :\n{kit_url}\n\n"
                    f"Soit 58,02 € au total avec livraison et retours gratuits sur Amazon (je te mets les deux captures juste en dessous).\n\n"
                    f"Dis-moi ce que tu en penses quand tu auras un moment !\n\n"
                    f"Gros bisous,\n"
                    f"{Config.USER_NAME}"
                )
            if not self.api_key:
                return fallback_acc

            if recipient_role == "sister":
                prompt = f"""
Rédige un email TRÈS NATUREL, chaleureux et fraternel de la part de {Config.USER_NAME} à sa sœur {sister_name} pour lui demander de commander (comme c'est elle qui fait les achats sur internet) 2 accessoires pour la clim sur Amazon (envoyé fin janvier après les fêtes de Noël).

Voici les infos exactes et les liens à inclure OBLIGATOIREMENT tels quels dans le message :
{ACCESSOIRES_CLIM_CONTEXT}

Consignes :
- Ton naturel, simple, pas robotique, comme un vrai message de frère à sa sœur ('Coucou {sister_name}').
- Explique que tu as attendu après Noël pour ne pas déranger avec ça avant, et que tu as aussi prévenu Maman par mail.
- Inclus les DEUX liens Amazon exacts ({tuyau_url} et {kit_url}) avec les noms et prix (24,03 € et 33,99 €, total 58,02 €).
- Mentionne que les 2 captures d'écran sont jointes pour bien voir les options sélectionnées (150mm et 2x 230cm).
- Signé '{Config.USER_NAME}'.
- Réponds uniquement avec le texte du message.
"""
            else:
                prompt = f"""
Rédige un email TRÈS NATUREL, affectueux et attentionné de la part de {Config.USER_NAME} à sa maman ('Maman') pour lui parler des 2 accessoires à acheter sur Amazon pour la clim (envoyé fin janvier après les fêtes de Noël).

Voici les infos exactes et les liens à inclure OBLIGATOIREMENT tels quels dans le message :
{ACCESSOIRES_CLIM_CONTEXT}

Consignes :
- Ton naturel, affectueux, pas robotique, tutoyant sa maman ('Coucou Maman').
- Dis-lui que tu as attendu après Noël pour ne pas la déranger avec ça avant.
- Précise que tu as aussi envoyé les liens à {sister_name} comme c'est elle qui gère les commandes sur internet.
- Inclus les DEUX liens Amazon exacts ({tuyau_url} et {kit_url}) avec les prix (24,03 € et 33,99 €, total 58,02 €).
- Mentionne que les 2 captures d'écran sont jointes dans le mail.
- Signé '{Config.USER_NAME}'.
- Réponds uniquement avec le texte du message.
"""
            try:
                text = self._call_gemini(prompt, json_mode=False)
                return text.strip()
            except Exception:
                return fallback_acc

        if self.campaign == "dentiste":
            fallback_dentiste = (
                f"Coucou Maman,\n\n"
                f"J'espère que tu vas bien ! Je voulais te demander si tu pouvais me prendre un rendez-vous chez le dentiste quand tu auras un petit moment.\n\n"
                f"Rien d'urgent ni de grave, ne t'inquiète pas : j'ai juste remarqué récemment de petites traces brunâtres à grisâtres en surface sur le bord inférieur "
                f"des deux incisives du haut (et plus discrètement sur celles du bas). D'après ce que j'ai regardé, ça correspond très probablement à une coloration "
                f"superficielle bénigne (due à des pigments alimentaires, un produit d'hygiène ou un assèchement passager de l'émail), et non à une atteinte profonde.\n\n"
                f"Je vais garder un brossage doux normal pendant 2 à 3 semaines en évitant les produits abrasifs (bicarbonate, citron, dentifrice blancheur), "
                f"mais si ça ne s'estompe pas d'ici là ou si une sensibilité apparaît, une consultation classique permettra de les enlever facilement avec un simple polissage.\n\n"
                f"Tiens-moi au courant quand tu as pu voir pour le rendez-vous ou si tu as besoin de mes disponibilités !\n\n"
                f"Gros bisous,\n"
                f"{Config.USER_NAME}"
            )
            if not self.api_key:
                return fallback_dentiste

            prompt = f"""
Rédige le tout premier email de la part de {Config.USER_NAME} à sa maman ('Maman') pour lui demander de lui prendre un rendez-vous chez le dentiste.

Voici les détails précis de la situation :
{DENTISTE_CONTEXT}

Consignes :
- Ton très naturel, affectueux, rassurant et attentionné, tutoyant sa maman ('Maman').
- Explique clairement et rassure-la : des traces brunâtres à grisâtres sont apparues récemment en surface sur le bord inférieur des deux incisives du haut (et plus discrètement sur celles du bas), mais c'est très probablement une coloration superficielle bénigne et réversible (pigments alimentaires, produit d'hygiène ou assèchement passager de l'émail), pas une atteinte profonde.
- Précise qu'il garde un brossage doux pendant 2 à 3 semaines sans produits abrasifs (bicarbonate, citron, dentifrice blancheur), et qu'une consultation classique chez le dentiste permettra de les éliminer rapidement par un simple polissage si ça ne part pas ou si une sensibilité apparaît.
- Signé '{Config.USER_NAME}'.
- Réponds uniquement avec le texte du message (pas d'objet, pas de balises markdown).
"""
            try:
                text = self._call_gemini(prompt, json_mode=False)
                return text.strip()
            except Exception:
                return fallback_dentiste

        if not self.api_key:
            return (
                f"Coucou Maman,\n\n"
                f"J'espère que tu vas bien !\n\n"
                f"Je voulais te demander si tu pouvais me prendre un rendez-vous chez le dermatologue dès que tu as un petit moment ? "
                f"Je n'ai pas de dermato particulier en tête, celui ou celle qui a de la place ou chez qui tu as l'habitude d'aller me conviendra très bien.\n\n"
                f"Tiens-moi au courant quand c'est fait ou si tu as besoin de mes disponibilités !\n\n"
                f"Gros bisous,\n"
                f"{Config.USER_NAME}"
            )

        prompt = f"""
Rédige le tout premier email de la part de {Config.USER_NAME} à sa maman ('Maman') pour lui demander de lui prendre un rendez-vous chez le dermatologue.
Florent n'a pas de dermato particulier en tête (celui de son choix ira très bien).
Le ton doit être très naturel, affectueux, attentionné et signé '{Config.USER_NAME}'.
Réponds uniquement avec le texte du message.
"""
        try:
            text = self._call_gemini(prompt, json_mode=False)
            return text.strip()
        except Exception:
            return (
                f"Coucou Maman,\n\n"
                f"J'espère que tu vas bien !\n\n"
                f"Je voulais te demander si tu pouvais me prendre un rendez-vous chez le dermatologue dès que tu as un petit moment ? "
                f"Je n'ai pas de dermato particulier en tête, celui ou celle qui a de la place me conviendra très bien.\n\n"
                f"Tiens-moi au courant quand c'est fait ou si tu as besoin de mes disponibilités !\n\n"
                f"Gros bisous,\n"
                f"{Config.USER_NAME}"
            )

    def _fallback_analyze(self, text, sender_role="mother"):
        """Heuristic analysis if Gemini is unreachable or no key provided."""
        t = text.lower()
        if self.campaign == "accessoires_clim":
            sister_name = Config.SISTER_NAME or "Julie"
            sender_label = sister_name if sender_role == "sister" else "Maman"
            other_label = "Maman" if sender_role == "sister" else sister_name

            is_bought = any(phrase in t for phrase in [
                "c'est commandé", "je les ai commandé", "je les ai commandés",
                "j'ai commandé", "je les ai acheté", "je les ai achetés", "j'ai acheté",
                "c'est acheté", "c'est pris", "c'est bon", "c'est fait"
            ]) and not any(neg in t for neg in ["pas encore", "pas eu le temps", "j'ai pas", "peux pas", "trop cher"])

            if is_bought:
                return {
                    "appointment_booked": True,
                    "appointment_details": text.strip(),
                    "summary": f"{sender_label} confirme l'achat/commande des accessoires clim.",
                    "needs_reply": True,
                    "suggested_reply": f"Merci mille fois {sender_label} ! Avec ça la clim sera vraiment au top pour cet été.\n\nGros bisous,\n{Config.USER_NAME}",
                    "notify_other_message": (
                        f"Coucou {other_label},\n\n"
                        f"Juste pour te prévenir que c'est tout bon : {sender_label} vient de commander les deux accessoires pour la clim sur Amazon !\n\n"
                        f"Gros bisous,\n{Config.USER_NAME}"
                    )
                }

            if any(w in t for w in ["prix", "combien", "taille", "diamètre", "diametre", "fenêtre", "fenetre", "tuyau"]):
                return {
                    "appointment_booked": False,
                    "appointment_details": None,
                    "summary": f"{sender_label} demande des précisions sur les accessoires clim.",
                    "needs_reply": True,
                    "suggested_reply": (
                        f"Coucou {sender_label},\n\n"
                        f"Les deux articles sont sur Amazon (58,02 € au total, retours gratuits) :\n"
                        f"- Tuyau d'échappement equlup 3m (150 mm de diamètre, filet CCW) : 24,03 €\n"
                        f"- Tissu d'isolation fenêtre HOOMEE (périmètre 381-460 cm, taille 2x 230 cm) : 33,99 €\n\n"
                        f"Gros bisous,\n{Config.USER_NAME}"
                    ),
                    "notify_other_message": None
                }

            return {
                "appointment_booked": False,
                "appointment_details": None,
                "summary": f"{sender_label} a répondu sans confirmer l'achat des accessoires clim.",
                "needs_reply": True,
                "suggested_reply": f"Merci {sender_label} ! Pas de souci, tiens-moi au courant quand tu auras pu regarder pour le tuyau et le kit fenêtre.\n\nGros bisous,\n{Config.USER_NAME}",
                "notify_other_message": None
            }

        if self.campaign == "clim":
            is_bought = any(phrase in t for phrase in [
                "c'est commandé", "je l'ai commandé", "je l'ai commandée",
                "j'ai commandé", "je l'ai acheté", "je l'ai achetée", "j'ai acheté",
                "c'est acheté", "c'est pris", "c'est bon", "c'est fait"
            ]) and not any(neg in t for neg in ["pas encore", "pas eu le temps", "j'ai pas", "peux pas", "trop cher"])

            if is_bought:
                return {
                    "appointment_booked": True,
                    "appointment_details": text.strip(),
                    "summary": "Maman confirme l'achat/commande de la clim.",
                    "needs_reply": True,
                    "suggested_reply": f"Merci mille fois Maman ! Tu me sauves la vie pour cet été, c'est vraiment super gentil.\n\nGros bisous,\n{Config.USER_NAME}"
                }

            if any(w in t for w in ["prix", "combien", "magasin", "où", "ou ", "livraison", "drive"]):
                return {
                    "appointment_booked": False,
                    "appointment_details": None,
                    "summary": "Maman demande des précisions sur la clim.",
                    "needs_reply": True,
                    "suggested_reply": (
                        f"Coucou Maman,\n\n"
                        f"C'est le climatiseur mobile VALBERG 9000 BTU (pour 20m², classe A) chez Electro Dépôt à 219,98 € "
                        f"(avec paiement en 3x sans frais possible). Il est dispo en drive sous 1h à Hénin-Beaumont ou en livraison.\n\n"
                        f"Gros bisous,\n{Config.USER_NAME}"
                    )
                }

            return {
                "appointment_booked": False,
                "appointment_details": None,
                "summary": "Maman a répondu sans confirmer l'achat de la clim.",
                "needs_reply": True,
                "suggested_reply": f"Merci Maman ! Pas de souci, tiens-moi au courant quand tu auras pu regarder pour la clim.\n\nGros bisous,\n{Config.USER_NAME}"
            }

        is_booked = any(phrase in t for phrase in [
            "c'est bon", "rendez-vous pris", "rdv pris", "rdv est pris", 
            "c'est pris", "c'est fait", "j'ai pris", "j'ai reservé", "j'ai réservé"
        ]) and not any(neg in t for neg in ["pas encore", "pas eu le temps", "j'ai pas pris", "peux pas"])

        if is_booked:
            return {
                "appointment_booked": True,
                "appointment_details": text.strip(),
                "summary": "Maman indique avoir pris le rendez-vous.",
                "needs_reply": True,
                "suggested_reply": f"Super, merci mille fois Maman ! C'est vraiment gentil, tu assures. Gros bisous,\n{Config.USER_NAME}"
            }
        
        # Check if asking for availability
        if any(w in t for w in ["dispo", "disponibilité", "quand", "quel jour", "quelle heure"]):
            specialist = "le dentiste" if self.campaign == "dentiste" else "le dermato"
            return {
                "appointment_booked": False,
                "appointment_details": None,
                "summary": "Maman demande les disponibilités.",
                "needs_reply": True,
                "suggested_reply": f"Coucou Maman,\n\nPour mes disponibilités : {Config.USER_AVAILABILITY}\nPrends ce qui arrange {specialist}, je ferai en sorte de m'adapter.\n\nMerci beaucoup, gros bisous !\n{Config.USER_NAME}"
            }

        return {
            "appointment_booked": False,
            "appointment_details": None,
            "summary": "Maman a répondu sans confirmer de rendez-vous définitif.",
            "needs_reply": True,
            "suggested_reply": f"Merci Maman ! Pas de souci, tiens-moi au courant quand tu as un moment.\n\nGros bisous,\n{Config.USER_NAME}"
        }

    def _fallback_reminder(self, count, recipient_role="mother"):
        if self.campaign == "accessoires_clim":
            sister_name = Config.SISTER_NAME or "Julie"
            dest_label = sister_name if recipient_role == "sister" else "Maman"
            if count == 0:
                return (
                    f"Coucou {dest_label},\n\n"
                    f"J'espère que tu passes une bonne journée ! Petit rappel tout doux pour savoir si tu as eu le temps de regarder "
                    f"les 2 accessoires pour la clim sur Amazon (le tuyau 3m 150mm à 24,03 € et le kit fenêtre HOOMEE à 33,99 €) ?\n\n"
                    f"Gros bisous,\n"
                    f"{Config.USER_NAME}"
                )
            elif count == 1:
                return (
                    f"Coucou {dest_label},\n\n"
                    f"Je sais que tes journées sont bien remplies ! Juste un petit mémo pour le tuyau et le tissu d'isolation fenêtre sur Amazon "
                    f"quand tu auras deux minutes, histoire d'être prêt pour la clim cet été.\n\n"
                    f"Bonne journée, gros bisous !\n"
                    f"{Config.USER_NAME}"
                )
            else:
                return (
                    f"Coucou {dest_label},\n\n"
                    f"C'est encore moi et mon kit de survie anti-canicule haha ! Promis, dès que le tuyau et le kit fenêtre sont commandés je ne t'embête plus avec ça :)\n\n"
                    f"Bon courage pour ta journée, bisous !\n"
                    f"{Config.USER_NAME}"
                )

        if self.campaign == "clim":
            if count == 0:
                return (
                    f"Coucou Maman,\n\n"
                    f"J'espère que tu passes une bonne journée ! Petit rappel tout doux pour savoir si tu as eu le temps de jeter un œil "
                    f"au climatiseur mobile VALBERG chez Electro Dépôt (219,98 €) ?\n\n"
                    f"Gros bisous,\n"
                    f"{Config.USER_NAME}"
                )
            elif count == 1:
                return (
                    f"Coucou Maman,\n\n"
                    f"Je sais que tes journées sont bien remplies ! Juste un petit mémo pour la clim Electro Dépôt quand tu auras deux minutes, "
                    f"histoire d'éviter les +30°C dans ma chambre cet été.\n\n"
                    f"Bonne journée, gros bisous !\n"
                    f"{Config.USER_NAME}"
                )
            else:
                return (
                    f"Coucou Maman,\n\n"
                    f"C'est encore moi et ma survie face aux +30°C dans ma chambre haha ! Promis, dès que la clim est commandée je ne t'embête plus avec ça :)\n\n"
                    f"Bon courage pour ta journée, bisous !\n"
                    f"{Config.USER_NAME}"
                )

        if self.campaign == "dentiste":
            if count == 0:
                return (
                    f"Coucou Maman,\n\n"
                    f"J'espère que tu as passé une bonne journée ! Petit rappel tout doux pour savoir si tu as eu l'occasion d'appeler le dentiste "
                    f"pour les petites traces sur mes incisives ? Pas de panique si tu n'as pas eu le temps, dis-moi juste dès que tu peux.\n\n"
                    f"Gros bisous,\n"
                    f"{Config.USER_NAME}"
                )
            elif count == 1:
                return (
                    f"Coucou Maman,\n\n"
                    f"Je sais que tes journées sont bien remplies ! Juste un petit mémo pour le rendez-vous dentiste (pour un éventuel polissage) quand tu auras deux minutes.\n\n"
                    f"Bonne journée, gros bisous !\n"
                    f"{Config.USER_NAME}"
                )
            else:
                return (
                    f"Coucou Maman,\n\n"
                    f"C'est encore moi avec mon histoire de dentiste haha ! Promis, dès que le rendez-vous est calé je ne t'embête plus avec ça :)\n\n"
                    f"Bon courage pour ta journée, bisous !\n"
                    f"{Config.USER_NAME}"
                )

        if count == 0:
            return (
                f"Coucou Maman,\n\n"
                f"J'espère que tu as passé une bonne journée ! Petit rappel tout doux pour savoir si tu as eu l'occasion d'appeler le dermatologue ? "
                f"Pas de panique si tu n'as pas eu le temps, dis-moi juste dès que tu peux.\n\n"
                f"Gros bisous,\n"
                f"{Config.USER_NAME}"
            )
        elif count == 1:
            return (
                f"Coucou Maman,\n\n"
                f"Je sais que tes journées sont bien remplies ! Juste un petit mémo pour le dermato quand tu auras deux minutes de libre.\n\n"
                f"Bonne journée, gros bisous !\n"
                f"{Config.USER_NAME}"
            )
        else:
            return (
                f"Coucou Maman,\n\n"
                f"C'est encore moi avec mon histoire de dermato haha ! Promis, dès que la date est calée je ne t'embête plus avec ça :)\n\n"
                f"Bon courage pour ta journée, bisous !\n"
                f"{Config.USER_NAME}"
            )
