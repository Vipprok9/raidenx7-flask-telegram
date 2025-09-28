import os, time, json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # nơi bot sẽ gửi khi web bấm Gửi
PUBLIC_BASE = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

EVENTS = []  # buffer sự kiện nhẹ cho web kéo

def tg_api(method, payload):
    if not BOT_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    return requests.post(url, json=payload, timeout=15)

def push_event(source, text):
    EVENTS.append({"source": source, "text": text, "ts": time.time()})
    if len(EVENTS) > 100:
        del EVENTS[:len(EVENTS)-100]

@app.get("/")
def root():
    return jsonify({"ok": True, "service": "raidenx7-bot"})

@app.get("/health")
def health():
    return jsonify({"ok": True})

# tiện ích set webhook (gọi 1 lần sau deploy)
@app.get("/set-webhook")
def set_webhook():
    if not BOT_TOKEN:
        return jsonify({"ok": False, "error": "BOT_TOKEN missing"}), 500
    base = PUBLIC_BASE or request.host_url.rstrip("/")
    url = f"{base}/webhook"
    r = tg_api("setWebhook", {"url": url})
    try:
        data = r.json()
    except Exception:
        data = {"status_code": r.status_code, "text": r.text}
    return jsonify({"ok": True, "result": data, "webhook": url})

# Telegram gọi vào đây
@app.post("/webhook")
def webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        msg = data.get("message") or data.get("edited_message")
        if not msg:
            return jsonify({"ok": True})

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # log về web
        if text:
            push_event("telegram", text)

        # auto-reply nhẹ (demo)
        if text:
            tg_api("sendMessage", {"chat_id": chat_id, "text": "Mình đã nhận: " + text})

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "err": str(e)})

# Web kéo sự kiện hiển thị
@app.get("/events")
def events():
    return jsonify({"items": EVENTS, "now": time.time()})

# Web gửi sang Telegram (không cần chat_id)
@app.post("/send")
def send_from_web():
    if not BOT_TOKEN:
        return jsonify({"ok": False, "error": "BOT_TOKEN missing"}), 500
    if not DEFAULT_CHAT_ID:
        return jsonify({"ok": False, "error": "TELEGRAM_CHAT_ID missing"}), 500

    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "no message"}), 400

    r = tg_api("sendMessage", {"chat_id": DEFAULT_CHAT_ID, "text": text})
    if r.status_code != 200:
        return jsonify({"ok": False, "error": r.text}), 400

    push_event("web", text)
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
