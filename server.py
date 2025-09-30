import os, time, json, threading
from collections import deque
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests

BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()  # có thể bỏ trống; sẽ lấy từ update

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)
CORS(app)

# ── Bộ nhớ tạm cho message (phục vụ SSE/polling)
EVENTS = deque(maxlen=200)
CLIENTS = set()
LOCK = threading.Lock()
PROCESSED_UPDATE_IDS = set()  # chống nhận trùng từ Telegram

def push(kind, text, sender, meta=None):
    """Đưa 1 event vào hàng đợi (và đánh thức SSE)."""
    evt = {
        "id": str(int(time.time() * 1000)),
        "kind": kind,          # 'message' | 'system'
        "text": text,
        "from": sender,        # 'web' | 'telegram' | 'bot'
        "meta": meta or {}
    }
    with LOCK:
        EVENTS.append(evt)
        # đánh thức các client SSE: gửi 1 tín hiệu rỗng
        for q in list(CLIENTS):
            try:
                q.put(evt, timeout=0.01)
            except Exception:
                pass
    return evt

def tg_send_text(chat_id, text):
    if not BOT_TOKEN or not chat_id:
        return None
    try:
        r = requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                          timeout=10)
        return r.json()
    except Exception:
        return None

def auto_reply(text: str) -> str | None:
    """Quy tắc auto-reply đơn giản (bạn có thể bổ sung)."""
    t = (text or "").lower().strip()
    if not t:
        return None
    # chào hỏi
    if t in ("hi", "hello", "xin chào", "chào", "chao", "hey"):
        return "Chào bạn 👋, mình là bot RaidenX7. Mình có thể trả lời vài câu cơ bản như: 'thời tiết', 'giờ', 'help'."
    # thời tiết
    if "thời tiết" in t or "weather" in t:
        return "Hôm nay trời nắng nhẹ, 31°C ☀️. Nhớ mang mũ và uống nước nhé!"
    # giờ
    if "mấy giờ" in t or "giờ" == t or "time" in t:
        return time.strftime("Bây giờ là %H:%M:%S ⏰", time.localtime())
    # help
    if t in ("help", "/help"):
        return "Lệnh nhanh: 'thời tiết', 'giờ', 'hi'. Bạn thử gõ xem!"
    return None

# ── Web gửi tin
@app.route("/send", methods=["POST"])
def send_from_web():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty_text"}), 400

    # phát cho web (hiện ngay)
    push("message", text, "web")

    # gửi qua Telegram (nếu cấu hình)
    chat_id = DEFAULT_CHAT_ID
    tg_send_text(chat_id, text)

    # auto-reply
    reply = auto_reply(text)
    if reply:
        push("message", reply, "bot")
        tg_send_text(chat_id, reply)

    return jsonify({"ok": True})

# ── Telegram webhook
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    upd = request.get_json(force=True, silent=True) or {}

    # chống trùng
    upd_id = upd.get("update_id")
    if upd_id is not None:
        if upd_id in PROCESSED_UPDATE_IDS:
            return jsonify({"ok": True})
        PROCESSED_UPDATE_IDS.add(upd_id)

    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return jsonify({"ok": True})

    chat_id = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()

    # phát lên web
    push("message", text, "telegram", {"chat_id": chat_id})

    # auto-reply
    reply = auto_reply(text)
    if reply:
        push("message", reply, "bot")
        tg_send_text(chat_id, reply)

    return jsonify({"ok": True})

# ── SSE stream
@app.route("/stream")
def stream():
    from queue import Queue
    q = Queue(maxsize=100)
    with LOCK:
        CLIENTS.add(q)

    def gen():
        try:
            # đẩy lịch sử ngắn trước (optional)
            with LOCK:
                snapshot = list(EVENTS)[-30:]
            for e in snapshot:
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"

            while True:
                e = q.get()
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            pass
        finally:
            with LOCK:
                CLIENTS.discard(q)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return Response(gen(), headers=headers)

# ── Polling fallback
@app.route("/messages")
def messages():
    with LOCK:
        return jsonify(list(EVENTS)[-50:])

@app.route("/")
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
