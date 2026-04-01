from flask import Flask, request, jsonify, send_file
from config.settings import settings
from agent.deduplicator import deduplicator
from integrations.google_sheets import google_sheets
from integrations.gemini_client import gemini_client
from datetime import datetime
import logging
import io
from ellipticcurve.ecdsa import Ecdsa
from ellipticcurve.publicKey import PublicKey
from ellipticcurve.signature import Signature

app = Flask(__name__)
logger = logging.getLogger(__name__)

# 1x1 Transparent Pixel for tracking
PIXEL_DATA = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'

@app.route("/track/open")
def track_open():
    author_id = request.args.get("author_id")
    source = request.args.get("source", "main")
    
    if author_id:
        logger.info(f"Custom tracking: Open detected for author {author_id} (Source: {source})")
        
        # Update Main or Gmail channel based on source
        if source == "gmail":
            from gmail_channel.gmail_dedup import gmail_dedup
            gmail_dedup.mark_gmail_open_detected(author_id)
            gmail_dedup.log_event("INFO", "TRACKING", f"Email opened by author {author_id} (Gmail)")
            gmail_dedup.update_lead_score(author_id, 1)
        else:
            deduplicator.mark_open_detected(author_id)
            google_sheets.update_open_detected(author_id, datetime.utcnow())
            deduplicator.log_event("INFO", "TRACKING", f"Email opened by author {author_id}")
            deduplicator.update_lead_score(author_id, 1)

    return send_file(io.BytesIO(PIXEL_DATA), mimetype='image/gif')

@app.route("/track/click")
def track_click():
    author_id = request.args.get("author_id")
    source = request.args.get("source", "main")
    redirect_url = request.args.get("url", "https://rejoicebookclub.com")
    
    if author_id:
        logger.info(f"Custom tracking: Click detected for author {author_id} (Source: {source})")
        if source == "gmail":
            from gmail_channel.gmail_dedup import gmail_dedup
            gmail_dedup.log_event("INFO", "TRACKING", f"Link clicked by author {author_id} (Gmail)")
            gmail_dedup.update_lead_score(author_id, 5)
        else:
            deduplicator.log_event("INFO", "TRACKING", f"Link clicked by author {author_id}")
            deduplicator.update_lead_score(author_id, 5)

    return f"<html><script>window.location.href='{redirect_url}';</script></html>"

def verify_signature(payload, signature, timestamp):
    if not settings.SENDGRID_WEBHOOK_PUBLIC_KEY:
        # If no key is configured, we skip verification (not recommended for production)
        logger.warning("No SENDGRID_WEBHOOK_PUBLIC_KEY configured. Skipping verification.")
        return True
    
    try:
        public_key = PublicKey.fromString(settings.SENDGRID_WEBHOOK_PUBLIC_KEY)
        # Signature is base64 encoded
        decoded_signature = Signature.fromBase64(signature)
        # Payload to verify is timestamp + body
        event_payload = timestamp.encode('utf-8') + payload
        return Ecdsa.verify(event_payload.decode('utf-8'), decoded_signature, public_key)
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False

@app.route("/webhook/sendgrid-events", methods=["POST"])
def sendgrid_events():
    signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature")
    timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp")
    
    if not verify_signature(request.data, signature, timestamp):
        return jsonify({"error": "Invalid signature"}), 403

    data = request.json
    for event in data:
        author_id = event.get("author_id")
        event_type = event.get("event")
        email = event.get("email")
        
        if event_type == "open":
            logger.info(f"Open detected for author {author_id} ({email})")
            if author_id:
                deduplicator.mark_open_detected(author_id)
                google_sheets.update_open_detected(author_id, datetime.utcnow())
                deduplicator.log_event("INFO", "WEBHOOK", f"Email opened by author {author_id}")
                deduplicator.update_lead_score(author_id, 1) # +1 point for opening
            elif email:
                pass
        elif event_type == "click":
            logger.info(f"Click detected for author {author_id} ({email})")
            if author_id:
                deduplicator.log_event("INFO", "WEBHOOK", f"Link clicked by author {author_id}")
                deduplicator.update_lead_score(author_id, 5) # +5 points for clicking
        elif event_type in ["bounce", "dropped"]:
            logger.warning(f"Email {event_type} for author {author_id} ({email})")
            deduplicator.log_event("WARNING", "WEBHOOK", f"Email {event_type} for {email or author_id}")
            
    return jsonify({"status": "ok"}), 200

@app.route("/webhook/inbound", methods=["POST"])
def inbound_replies():
    # Handle incoming replies (e.g., from SendGrid Inbound Parse)
    data = request.form
    sender = data.get("from")
    text_body = data.get("text", "")
    
    if sender:
        email = sender.split("<")[-1].replace(">", "").strip().lower()
        logger.info(f"Reply received from {email}")
        sentiment = gemini_client.classify_reply(text_body)
        deduplicator.mark_replied(email, sentiment)
        google_sheets.update_reply_detected_by_email(email)
        deduplicator.log_event("SUCCESS", "REPLY", f"Reply received via webhook from: {email} (Sentiment: {sentiment})")
        
        # Log to conversations
        deduplicator.log_conversation(
            author_id=None,
            email=email,
            direction="incoming",
            subject="Re: Invitation (Webhook)",
            body=text_body
        )
        
    return jsonify({"status": "ok"}), 200

def run():
    app.run(host="0.0.0.0", port=settings.WEBHOOK_PORT)

if __name__ == "__main__":
    run()
