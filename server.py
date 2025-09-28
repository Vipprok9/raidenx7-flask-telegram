# server.py
import os, requests
from time import time
from collections import deque
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ==== Flask & CORS ====
app = Flask(__name__, static_url_path="", static_folder=".")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ==== ENV ====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID   = os.environ.get("CHAT_ID", "").strip()  # optional cho chiều Web→TG
TG_API    = "https://api.telegram.org/bot" + BOT_TOKEN

# ==== Bộ nhớ tạm để demo (prod nên dùng Redis/DB) ====
MESSAGES = deque(maxlen=200)  # lưu 200 tin gần nhất

def push_msg(source, text):
    MESSAGES.append({"ts": time(), "source": source, "text": text or ""})

# ==== Auto-reply ngắn ====
AUTO_REPLY = {
    "hello": "Xin chào 👋, mình là bot raidenx7!",
    "ai": "AI là trí tuệ nhân tạo giúp tự động hóa và phân tích.",
    "token": "Token là đơn vị giá trị trên blockchain.",
    "defi": "DeFi là tài chính phi tập trung (decentralized finance).",
    "airdrop": "Airdrop: dự án tặng token cho người dùng.",
    "node": "Node là máy/chương trình tham gia mạng blockchain.",
    "depin": "DePIN là mạng lưới hạ tầng vật lý phi tập trung."
}
def match_auto(text: str) -> str:
    t = (text or "").lower().strip()
    for k, v in AUTO_REPLY.items():
        if k in t:
            return v
    return "Mình đã chuyển câu hỏi cho hệ thống, cảm ơn bạn!"

# ==== Trang test ====
@app.get("/")
def home():
    return send_file("index.html")

# ==== Web → Telegram ====
@app.post("/api/send")
def api_send():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        chat_id = str(data.get("chat_id") or CHAT_ID).strip()

        if not text:
            return jsonify({"ok": False, "error": "missing text"}), 400
        if not BOT_TOKEN:
            return jsonify({"ok": False, "error": "missing BOT_TOKEN env"}), 500
        if not chat_id:
            return jsonify({"ok": False, "error": "missing chat_id (pass in body or set CHAT_ID env)"}), 400

        # lưu tin của web để UI hiển thị ngay
        push_msg("web", text)

        r = requests.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
        ok = r.ok and r.json().get("ok", False)
        return jsonify({"ok": bool(ok), "tg": r.json() if r.ok else r.text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ==== Telegram → Web (Webhook) ====
@app.post("/webhook")
def telegram_webhook():
    try:
        data = request.get_json(silent=True) or {}
        msg = data.get("message") or data.get("edited_message") or data.get("channel_post") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        text = msg.get("text") or ""

        print("INCOMING:", {"chat_id": chat_id, "text": text}, flush=True)

        # lưu tin của Telegram để web kéo về
        if text:
            push_msg("telegram", text)

        reply = match_auto(text)
        if BOT_TOKEN and chat_id and reply:
            requests.post(
                f"{TG_API}/sendMessage",
                json={"chat_id": chat_id, "text": reply},
                timeout=10
            )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200

# ==== API cho front-end kéo tin ====
@app.get("/api/messages")
def api_messages():
    try:
        since = request.args.get("since", type=float)  # epoch seconds
        items = list(MESSAGES)
        if since:
            items = [m for m in items if m["ts"] > since]
        return jsonify({"ok": True, "items": items, "now": time()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ==== Healthcheck ====
@app.get("/health")
def health():
    return {"ok": True}

# ==== cho gunicorn ====
app = app
