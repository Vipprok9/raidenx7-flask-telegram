from flask import Flask, request, jsonify
from flask_cors import CORS
import os, requests

app = Flask(__name__)
CORS(app)

# Đọc biến môi trường đúng với Render
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text):
    url = f"{TELEGRAM_API}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    return r.json()

@app.route("/")
def home():
    return jsonify(status="ok")

@app.route("/set-webhook")
def set_webhook():
    webhook_url = f"{request.host_url}webhook"
    r = requests.get(f"{TELEGRAM_API}/setWebhook", params={"url": webhook_url})
    return r.json()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    msg = data.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text = msg.get("text", "")
    if text:
        # Forward về chat mặc định
        if CHAT_ID:
            send_message(CHAT_ID, f"Forward từ {chat_id}: {text}")
        # Trả lời trực tiếp cho user
        if chat_id:
            send_message(chat_id, f"Mình đã nhận: {text}")
    return "ok"

@app.route("/send", methods=["POST"])
def send_from_web():
    data = request.json or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify(success=False, error="Empty text"), 400
    if not (BOT_TOKEN and CHAT_ID):
        return jsonify(success=False, error="Missing env vars"), 400

    resp = send_message(CHAT_ID, f"Web gửi: {text}")
    return jsonify(success=True, telegram=resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
