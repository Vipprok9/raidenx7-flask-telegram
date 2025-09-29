import os
import json
import requests
from flask import Flask, request, Response, stream_with_context
from flask_cors import CORS
from queue import Queue

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Hàng đợi lưu tin nhắn để stream
event_queue = Queue()

def send_message(text):
    """Gửi tin nhắn sang Telegram"""
    url = f"{TELEGRAM_URL}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, json=payload)

@app.route("/send", methods=["POST"])
def send():
    """Nhận tin nhắn từ Web gửi sang Telegram"""
    data = request.json
    msg = data.get("message", "")
    if msg:
        send_message(msg)
        return {"status": "ok", "sent": msg}
    return {"status": "error", "message": "no content"}, 400

@app.route("/webhook", methods=["POST"])
def webhook():
    """Telegram gửi tin nhắn về Webhook"""
    update = request.json
    if "message" in update:
        text = update["message"].get("text", "")
        user = update["message"]["from"]["first_name"]
        content = f"{user}: {text}"
        event_queue.put(content)  # Đẩy vào hàng chờ cho SSE
    return {"ok": True}

@app.route("/stream")
def stream():
    """Realtime SSE cho frontend"""
    def event_stream():
        while True:
            msg = event_queue.get()
            yield f"data: {msg}\n\n"
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

@app.route("/events")
def events():
    """Fallback polling: trả về 1 tin mới"""
    if not event_queue.empty():
        return {"events": [event_queue.get()]}
    return {"events": []}

@app.route("/set-webhook")
def set_webhook():
    """Đăng webhook Telegram"""
    url = f"{TELEGRAM_URL}/setWebhook"
    webhook_url = os.getenv("RENDER_EXTERNAL_URL", "") + "/webhook"
    r = requests.get(url, params={"url": webhook_url})
    return r.json()

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
