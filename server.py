# server.py
import os, requests
from time import time
from collections import deque
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ==== Flask & CORS ====
app = Flask(__name__, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ==== ENV (đọc linh hoạt) ====
# Hỗ trợ cả 2 kiểu đặt biến ENV để tránh nhầm tên
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_TOKEN") or ""
CHAT_ID   = os.environ.get("CHAT_ID")   or os.environ.get("TARGET_CHAT_ID") or ""
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

# ==== Bộ nhớ tạm hiển thị lên Web (demo) ====
MESSAGES = deque(maxlen=200)  # lưu ~200 tin gần nhất

def push_msg(source: str, text: str):
    MESSAGES.append({"ts": time(), "source": source, "text": text})

# (tuỳ chọn) Trang gốc – không cần index.html trên Render
@app.get("/")
def root():
    return "App đang chạy ✅ — thiếu index.html", 200

# Healthcheck
@app.get("/health")
def health():
    return jsonify({"ok": True})

# ==== API: Web <-> Telegram ====
# GET: web đọc tin | POST: web gửi tin sang Telegram
@app.route("/api/messages", methods=["GET", "POST"])
def api_messages():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "missing text"}), 400

        # Lưu tin người dùng web
        push_msg("web", text)

        # Gửi qua Telegram (nếu có token)
        if TG_API:
            chat_id = (data.get("chat_id") or CHAT_ID or "").strip()
            try:
                requests.post(
                    f"{TG_API}/sendMessage",
                    json={"chat_id": chat_id, "text": f"[Web] {text}"},
                    timeout=10,
                )
            except Exception:
                pass

        return jsonify({"ok": True})

    # GET: trả về danh sách tin nhắn (no-store để tránh cache)
    data = {"items": list(MESSAGES), "now": time()}
    return jsonify(data), 200, {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"
    }

# ==== Webhook Telegram ====
@app.post("/webhook")
def tg_webhook():
    u = request.get_json(silent=True) or {}
    msg = (u.get("message") or u.get("edited_message")) or {}
    text = (msg.get("text") or "").strip()
    if not text:
        return jsonify({"ok": True})

    # Lưu tin người dùng từ Telegram để web nhìn thấy
    push_msg("telegram", text)

    # (tuỳ chọn) gửi ACK và cũng lưu để web nhìn thấy luôn
    ack = "Mình đã chuyển câu hỏi cho hệ thống, cảm ơn bạn!"
    try:
        if TG_API:
            requests.post(
                f"{TG_API}/sendMessage",
                json={"chat_id": CHAT_ID or msg.get("chat", {}).get("id"), "text": ack},
                timeout=10,
            )
        push_msg("telegram", ack)
    except Exception:
        pass

    return jsonify({"ok": True})

# Cho Render (gunicorn dùng biến app)
app = app
