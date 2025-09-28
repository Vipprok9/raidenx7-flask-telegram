import os, time, json
from collections import deque
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ===== Config từ biến môi trường =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # chat id đích để gửi từ web
BASE_TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ===== Bộ đệm tin nhắn cho trang web =====
# Lưu ~200 tin gần nhất từ cả web & telegram để web poll /messages
BUF = deque(maxlen=200)

def push_item(source, text):
    BUF.append({"source": source, "text": text, "ts": time.time()})

# ===== CORS đơn giản cho Pages =====
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

# ===== Healthcheck =====
@app.get("/health")
def health():
    return jsonify(ok=True)

# ===== API web gửi → Telegram =====
@app.post("/send")
def send_from_web():
    try:
        data = request.get_json(force=True) or {}
        text = (data.get("message") or "").strip()
        if not text:
            return jsonify(ok=False, error="No message"), 400
        if not (TELEGRAM_TOKEN and CHAT_ID):
            return jsonify(ok=False, error="Server missing TELEGRAM_TOKEN/CHAT_ID"), 500

        r = requests.post(
            f"{BASE_TG}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=15,
        )
        ok = r.ok and r.json().get("ok")
        if ok:
            push_item("web", text)
            return jsonify(ok=True)
        return jsonify(ok=False, error=r.text), 502
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# ===== Telegram → webhook (nhớ setWebhook tới /webhook) =====
@app.post("/webhook")
def webhook():
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message") or {})
    text = (msg.get("text") or "").strip()
    if text:
        push_item("telegram", text)
    return jsonify(ok=True)

# ===== Web poll tin nhắn mới để hiển thị =====
@app.get("/messages")
def messages():
    # Trả về tất cả (đơn giản) – web tự lọc theo thời gian nếu muốn
    return jsonify(items=list(BUF), now=time.time())

# ===== Trang gốc: chỉ thông báo đang chạy =====
@app.get("/")
def root():
    return "App đang chạy ✅ — dùng /health, /send, /messages, /webhook"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
