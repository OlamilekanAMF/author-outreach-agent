# Triumphant Author Outreach Agent

Production-grade, fully automated AI agent for Rejoicebookclub to discover authors, verify contact data, and send personalized spotlight invitations.

## 🚀 Key Features
- **Daily Discovery:** Automatically finds 50 unique authors from Google Books, Goodreads, etc.
- **AI-Personalization:** Uses GPT-4o to fill invitation templates with book-specific details.
- **3-Layer Verification:** Syntax check, MX record lookup, and SMTP probe.
- **Smart Follow-ups:** Automatically follows up with authors who opened the email but didn't reply after 4 days.
- **Full Integration:** Logs everything to Google Sheets and generates daily reports in Google Docs.
- **Error Tolerant:** Robust retry logic and SQLite deduplication.

## 📁 Project Structure
- `agent/`: Core logic (orchestrator, discoverer, collector, verifier, etc.)
- `integrations/`: Third-party APIs (Google, OpenAI)
- `templates/`: Email copy templates
- `config/`: Environment configuration
- `data/`: SQLite database and logs

## 🛠️ Setup Instructions

  ## Web Search Setup (Free)

  ### Option A — DuckDuckGo (zero setup needed)
  Works immediately with no configuration.
  No API key, no account, no limits.
  The agent uses this automatically as the default.

  ### Option B — Google Custom Search (optional, better results)
  Adds 100 higher-quality searches/day on top of DuckDuckGo.

  1. Go to console.cloud.google.com
  2. Create a new project (free)
  3. Enable "Custom Search API" in the API Library
  4. Go to Credentials → Create API Key → copy it
     → paste as GOOGLE_CSE_API_KEY in .env

  5. Go to programmablesearchengine.google.com
  6. Click "Add" → Search the entire web → Create
  7. Copy the "Search engine ID"
     → paste as GOOGLE_CSE_ID in .env

  Both steps take under 5 minutes and cost nothing.
  If you skip this, DuckDuckGo handles all searches automatically.

### 1. Prerequisites
- Python 3.11+
- Google Cloud Service Account (with Sheets & Docs API access)
- OpenAI API Key
- SendGrid API Key (and verified sender identity)

### 2. Installation
```bash
cd rejoicebookclub_agent
pip install -r requirements.txt
playwright install chromium
```

### 3. Configuration
1. Copy `.env.example` to `.env`.
2. Fill in all required API keys and IDs.
3. Place your Google Service Account JSON file in the root or update the path in `.env`.

### 4. Running the Agent
- **Start the Scheduler:**
  ```bash
  python main.py
  ```
- **Run Discovery/Invites Now:**
  ```bash
  python main.py --run-now
  ```
- **Run Follow-ups Now:**
  ```bash
  python main.py --followup-now
  ```
- **Start Webhook Server (for open tracking):**
  ```bash
  python main.py --webhook
  ```

## 🔐 Security
- Zero hardcoded secrets (all in `.env`).
- SQLite tracks contacted authors to ensure no one is emailed twice.
- Banned phrase filter ensures professional communication.
