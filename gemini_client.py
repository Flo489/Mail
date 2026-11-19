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
                    "maxOutputTokens": 2048,
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
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
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

    def analyze_mother_reply(self, history, new_reply_text):
        """
        Analyzes mother's reply.
        Returns a dict:
        {
            "appointment_booked": bool,
            "appointment_details": str or None,
            "summary": str,
            "needs_reply": bool,
            "suggested_reply": str
        }
        """
        history_formatted = "\n".join([
            f"- [{h.get('role', 'inconnu').upper()} à {h.get('timestamp', '')}]: {h.get('content', '')}"
            for h in history[-6:]
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
            return self._fallback_analyze(new_reply_text)

        try:
            raw = self._call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
            return self.clean_json_response(raw)
        except Exception as e:
            print(f"[GeminiClient] Erreur pendant l'analyse Gemini: {e}. Utilisation du fallback heuristique.")
            return self._fallback_analyze(new_reply_text)

    def generate_reminder_email(self, history, reminder_count):
        """Generates a gentle follow-up reminder email when mother hasn't answered for 24h."""
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
            return self._fallback_reminder(reminder_count)

        try:
            text = self._call_gemini(prompt, system_instruction=system_instruction, json_mode=False)
            return text.strip()
        except Exception as e:
            print(f"[GeminiClient] Erreur génération relance Gemini: {e}. Utilisation du fallback.")
            return self._fallback_reminder(reminder_count)

    def generate_initial_email(self, is_test=False):
        """Generates the very first email sent to mom."""
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

    def _fallback_analyze(self, text):
        """Heuristic analysis if Gemini is unreachable or no key provided."""
        t = text.lower()
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
            return {
                "appointment_booked": False,
                "appointment_details": None,
                "summary": "Maman demande les disponibilités.",
                "needs_reply": True,
                "suggested_reply": f"Coucou Maman,\n\nPour mes disponibilités : {Config.USER_AVAILABILITY}\nPrends ce qui arrange le dermato, je ferai en sorte de m'adapter.\n\nMerci beaucoup, gros bisous !\n{Config.USER_NAME}"
            }

        return {
            "appointment_booked": False,
            "appointment_details": None,
            "summary": "Maman a répondu sans confirmer de rendez-vous définitif.",
            "needs_reply": True,
            "suggested_reply": f"Merci Maman ! Pas de souci, tiens-moi au courant quand tu as un moment.\n\nGros bisous,\n{Config.USER_NAME}"
        }

    def _fallback_reminder(self, count):
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
