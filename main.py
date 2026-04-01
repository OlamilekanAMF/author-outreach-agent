# Scheduling is handled by GitHub Actions (.github/workflows/)
# Run locally: python main.py --run-now
# Run follow-ups: python main.py --followup-now
# Dry run: set DRY_RUN=true in .env then python main.py --run-now

import sys
import logging
from config.settings import settings
from agent.orchestrator import orchestrator
from agent.followup_manager import followup_manager
import webhook_server

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)

if __name__ == "__main__":
    if "--run-now" in sys.argv:
        orchestrator.run_daily_pipeline()
    elif "--followup-now" in sys.argv:
        followup_manager.run_followup_pipeline()
    elif "--webhook" in sys.argv:
        webhook_server.run()
    elif "--gmail-run-now" in sys.argv:
        from gmail_channel.gmail_orchestrator import run_gmail_pipeline
        run_gmail_pipeline()
    elif "--gmail-followup-now" in sys.argv:
        from gmail_channel.gmail_followup import run_gmail_followup_pipeline
        run_gmail_followup_pipeline()
    elif "--dashboard" in sys.argv:
        from dashboard.routes import start_dashboard
        start_dashboard()
    elif "--detect-replies" in sys.argv:
        from agent.reply_detector import detect_replies
        detect_replies()
    else:
        print("🚀 Rejoicebookclub Author Outreach Agent")
        print("Usage:")
        print("  python main.py --run-now       (Run invitation pipeline)")
        print("  python main.py --followup-now  (Run follow-up pipeline)")
        print("  python main.py --webhook       (Start webhook server)")
        print("\nNote: Automated scheduling is managed via GitHub Actions.")
