import os, requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ==== Flask & CORS (phục vụ index.html ở root) ====
app = Flask(__name__, static_url_path="", static_folder=".", template_folder=".")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ==== ENV trên Render ====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID   = os.environ.get("CHAT_ID", "")
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==== fallback auto-reply ngắn (nếu chủ bot chưa rep) ====
AUTO_REPLY = {
    "hello": "Xin chào 👋, mình là bot demo!",
    "ai": "AI là trí tuệ nhân tạo giúp tự động hoá xử lý thông tin.",
    "token": "Token là đơn vị giá trị của dự án (coin).",
    "defi": "DeFi là tài chính phi tập trung trên blockchain.",
    "airdrop": "Airdrop: dự án tặng token cho người dùng.",
    "node": "Node là máy/chương trình vận hành mạng.",
    "depin": "DePIN là mạng lưới hạ tầng phi tập trung (ví dụ: Helium).",
}
def match_auto(text: str):
    t = (text or "").lower().strip()
    for k, v in AUTO_REPLY.items():
        if k in t:
            return v
    return "Mình đã chuyển câu hỏi cho chủ bot, sẽ trả lời sớm!"

# ==== Trang test (mở tại /) ====
@app.get("/")
def home():
    return send_file("index.html")

# ==== API: Web → Telegram ====
@app.post("/api/send")
def api_send():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "EMPTY_TEXT"}), 400

        # Gửi sang Telegram
        if BOT_TOKEN and CHAT_ID:
            requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": f"[Web] {text}"},
                          timeout=10)

        # Trả về câu auto-reply tạm thời để web hiển thị
        reply = match_auto(text)
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ==== Healthcheck ====
@app.get("/health")
def health():
    return {"ok": True}

# ==== cho Render (gunicorn sẽ dùng 'server:app') ====
app = app
