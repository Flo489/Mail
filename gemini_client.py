import json
import urllib.request
import urllib.error
import re
from config import Config

class GeminiClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or Config.GEMINI_API_KEY
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
                    "maxOutputTokens": 1000,
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
        system_instruction = (
            "Tu es un assistant personnel qui aide Florent à gérer la prise d'un rendez-vous chez le dermatologue "
            "par sa maman. L'adresse est bienveillante, affectueuse et naturelle (Florent appelle sa mère 'Maman').\n"
            "Tu dois analyser la réponse de sa mère avec précision."
        )

        history_formatted = "\n".join([
            f"- [{h.get('role', 'inconnu').upper()} à {h.get('timestamp', '')}]: {h.get('content', '')}"
            for h in history[-6:]
        ])

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
            return (
                f"Coucou Maman,\n\n"
                f"Ceci est un petit message de TEST automatique de Florent pour le rendez-vous chez le dermatologue :)\n\n"
                f"Peux-tu répondre à ce mail pour tester le système ? Tu peux me dire par exemple si tu as pris le RDV, ou me poser une question sur mes disponibilités.\n\n"
                f"Le robot va analyser ta réponse et t'envoyer automatiquement une réponse adaptée en retour !\n\n"
                f"Gros bisous,\n"
                f"{Config.USER_NAME}"
            )

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
