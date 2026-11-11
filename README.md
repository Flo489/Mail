# 🩺 Assistant Automatique de Rappel Dermatologue

Assistant automatisé qui gère les échanges par email avec votre maman pour la prise de votre rendez-vous chez le dermatologue.

Le système s'exécute **100% en ligne et gratuitement** grâce à **GitHub Actions** : vous n'avez pas besoin de laisser votre ordinateur allumé.

---

## ✨ Fonctionnalités

1. **Premier contact programmé** : Envoie un email bienveillant et affectueux à votre maman (par défaut programmé pour demain matin à 8h00, ou déclenchable immédiatement).
2. **Gestion du délai de 24h** : Si elle ne répond pas sous 24 heures, le système lui renvoie automatiquement un email de relance doux et attentionné.
3. **Analyse intelligente (Google Gemini)** :
   - Si elle pose une question (par exemple sur vos disponibilités), l'IA formule une réponse adaptée et souple.
   - Si elle indique qu'elle n'a pas encore eu le temps, l'IA la rassure chaleureusement.
   - Si elle confirme que **le rendez-vous est pris et fixé** : l'agent s'arrête immédiatement, lui envoie un email de remerciement, et vous notifie par email !
4. **Conservation du fil de discussion** : Tous les échanges restent regroupés dans la même conversation dans Gmail (`Re: Rendez-vous dermatologue pour Florent`).
5. **Heures de tranquillité** : Aucun email n'est envoyé la nuit (entre 21h00 et 08h00).

---

## 🚀 Mise en service en 3 minutes

Pour que GitHub Actions puisse envoyer les emails et utiliser Gemini, vous devez enregistrer **4 secrets** dans les paramètres de votre dépôt GitHub.

### Étape 1 : Obtenir un mot de passe d'application Gmail
1. Rendez-vous sur votre compte Google : [Sécurité Google](https://myaccount.google.com/security).
2. Vérifiez que la **validation en deux étapes** est activée.
3. Recherchez **"Mots de passe d'application"** (ou allez directement sur [Mots de passe des applications](https://myaccount.google.com/apppasswords)).
4. Donnez un nom (ex: `GitHub Mail Bot`) et cliquez sur **Créer**.
5. Copiez le code de 16 lettres généré (ex: `abcd efgh ijkl mnop`).

### Étape 2 : Obtenir une clé d'API Gemini gratuite
1. Rendez-vous sur [Google AI Studio](https://aistudio.google.com/).
2. Connectez-vous avec votre compte Google et cliquez sur **"Get API key"**.
3. Créez une nouvelle clé (gratuite) et copiez-la.

### Étape 3 : Ajouter les secrets dans GitHub
Dans ce dépôt GitHub :
1. Allez dans **Settings** (Paramètres) > **Secrets and variables** > **Actions**.
2. Cliquez sur **New repository secret** et ajoutez ces 4 variables :

| Nom du secret | Valeur |
| :--- | :--- |
| `GMAIL_USER` | Votre adresse Gmail (ex: `votre.nom@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Le mot de passe d'application de 16 lettres (sans espaces) |
| `MOTHER_EMAIL` | L'adresse email de votre maman |
| `GEMINI_API_KEY` | Votre clé API Google AI Studio |

*(Optionnel)* Vous pouvez aussi ajouter une variable `USER_NAME` dans l'onglet **Variables** si vous souhaitez personnaliser la signature (par défaut : `Florent`).

---

## ⏰ Comment ça tourne ?

- **Automatiquement** : Le workflow GitHub Actions s'exécute automatiquement toutes les heures entre 07h00 et 21h00.
- **Manuellement** :
  1. Allez dans l'onglet **Actions** de votre dépôt GitHub.
  2. Sélectionnez **"Rappel Dermatologue Maman"** dans la colonne de gauche.
  3. Cliquez sur **Run workflow**.
  4. Vous pouvez cocher *Envoyer le premier email immédiatement* pour ne pas attendre demain 8h, ou tester en *Mode simulation*.

---

## 🛠️ Exécution en local (optionnel)

Si vous souhaitez exécuter ou tester le script directement sur votre machine :

```bash
# 1. Cloner et installer les dépendances
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configurer le fichier .env
cp .env.example .env
# Renseigner vos valeurs dans .env

# 3. Voir le statut actuel
python main.py --status

# 4. Tester en mode simulation (dry-run)
python main.py --dry-run

# 5. Lancer un test immédiat
python main.py --immediate
```

---

## 📁 Architecture du projet

- `main.py` : Orchestrateur principal (gestion du calendrier, du délai de 24h et des transitions).
- `gemini_client.py` : Analyse sémantique des réponses de votre maman et génération des messages personnalisés.
- `email_service.py` : Gestion des envois (SMTP) et de la lecture des réponses (IMAP) via Gmail.
- `state_manager.py` : Persistance de l'état dans `data/state.json`.
- `.github/workflows/reminder.yml` : Automatisation cloud planifiée.
- `tests/test_mail_bot.py` : Tests unitaires automatisés.
