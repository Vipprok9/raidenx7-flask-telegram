import os, time, requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

AUTO_REPLY = {
    "hello": "Xin chào 👋, mình là bot demo!",
    "ai": "AI đang là xu hướng: GenAI, RAG, Agent…",
    "defi": "DeFi là tài chính phi tập trung.",
    "node": "Node chạy 24/7 giúp xác thực mạng.",
    "airdrop": "Kiểm tra dự án uy tín trước khi tham gia airdrop.",
}

def match_auto(text:str):
    t = (text or "").lower().strip()
    for k,v in AUTO_REPLY.items():
        if k in t:
            return v
    return None

@app.get("/")
def home():
    return jsonify(ok=True, service="raidenx7-bot", time=int(time.time()))

@app.post("/api/send")
def api_send():
    data = request.get_json(silent=True) or {}
    text = data.get("text","").strip()
    if not text:
        return jsonify(error="missing text"), 400

    # Send to Telegram if config available
    sent = False
    tg_error = None
    if TELEGRAM_TOKEN and TARGET_CHAT_ID:
        try:
            r = requests.post(f"{TG_API}/sendMessage", json={
                "chat_id": TARGET_CHAT_ID,
                "text": text
            }, timeout=10)
            sent = r.ok
            if not sent:
                tg_error = f"telegram status {r.status_code}"
        except Exception as e:
            tg_error = str(e)

    reply = match_auto(text) or "Mình đã chuyển câu hỏi cho chủ bot, sẽ trả lời sớm!"
    return jsonify(ok=True, sent_to_telegram=sent, reply=reply, tg_error=tg_error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
