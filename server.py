import os
import json
import time
import queue
import requests
from flask import Flask, request, Response, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ===== ENV =====
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ===== EVENT QUEUE (cho SSE/polling) =====
events = queue.Queue()

def push_event(kind, text, sender="system"):
    evt = {"id": int(time.time()*1000), "kind": kind, "text": text, "from": sender}
    try:
        events.put_nowait(evt)
    except queue.Full:
        pass
    return evt

# ===== TELEGRAM SEND =====
def send_to_telegram(text, chat_id=None):
    cid = chat_id or CHAT_ID
    if not BOT_TOKEN or not cid:
        return {"ok": False, "error": "Missing token/chat_id"}
    url = f"{TG_API}/sendMessage"
    r = requests.post(url, json={"chat_id": cid, "text": text}, timeout=10)
    return r.json()

# ===== API: Web → Telegram =====
@app.post("/send")
def send_msg():
    data = request.get_json(force=True)
    text = data.get("text")
    if not text:
        return jsonify({"ok": False, "error": "No text"}), 400
    send_to_telegram(text)
    push_event("message", text, sender="web")
    return jsonify({"ok": True})

# ===== API: SSE stream =====
@app.get("/stream")
def stream():
    def event_stream():
        while True:
            evt = events.get()
            yield f"data: {json.dumps(evt)}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

# ===== TELEGRAM WEBHOOK =====
@app.post("/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message") or {})
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id or not text:
        return jsonify({"ok": True})

    # Đẩy lên web UI
    push_event("message", text, sender="telegram")

    # ===== AUTO-REPLY LOGIC =====
    reply = None
    lower = text.lower()
    if lower in {"/start", "hi", "hello", "chào"}:
        reply = "Xin chào 👋, mình là bot RaidenX7. Bạn có thể hỏi mình vài câu cơ bản."
    elif "ping" in lower or "test" in lower:
        reply = "pong ✅"
    elif "mấy giờ" in lower or "giờ" in lower:
        reply = time.strftime("Bây giờ là %H:%M:%S", time.localtime())
    elif "ngày" in lower or "hôm nay" in lower:
        reply = time.strftime("Hôm nay là %d/%m/%Y", time.localtime())
    elif "thời tiết" in lower:
        reply = "Mình chưa xem được API thời tiết, nhưng nhớ mang áo mưa nếu trời âm u ☔"
    else:
        reply = f"Bạn vừa nhắn: {text}"

    if reply:
        try:
            requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": chat_id, "text": reply},
                          timeout=10)
        except Exception as e:
            print("Send error:", e)

    return jsonify({"ok": True})

# ===== HEALTH =====
@app.get("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
