from flask import Flask, request, jsonify
from flask_cors import CORS
import os, requests

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # BẮT BUỘC để web gọi được

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")   or os.getenv("TARGET_CHAT_ID")

MEMO = []  # lưu ngắn để web đọc /messages

@app.route("/")
def home():
    return jsonify(status="ok")

@app.route("/send", methods=["POST"])
def send():
    try:
        text = (request.get_json() or {}).get("text", "").strip()
        if not text:
            return jsonify(success=False, error="empty_text"), 400

        MEMO.append({"side": "me", "text": text})
        MEMO[:] = MEMO[-50:]

        if BOT_TOKEN and CHAT_ID:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": CHAT_ID, "text": f"Web gửi: {text}"}, timeout=10)

        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500

@app.route("/messages", methods=["GET"])
def messages():
    return jsonify(items=MEMO)

# (tùy chọn) route debug gửi nhanh trên trình duyệt:
@app.route("/debug-send")
def debug_send():
    text = request.args.get("text", "ping")
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": f"Debug: {text}"}, timeout=10)
    return jsonify(ok=True, sent=text)
