import os, time, json, queue, requests
from flask import Flask, request, jsonify, Response

# ========= ENV =========
BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_CID = os.getenv("TELEGRAM_CHAT_ID", "").strip()   # optional (chat riêng của bạn)
ALLOW_ORIGIN= os.getenv("ALLOW_ORIGIN", "*").strip()      # ví dụ: https://raidenx7.pages.dev
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()  # nên đặt, dùng để xác thực webhook

if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ========= APP & STATE =========
app = Flask(__name__)
inbox   = queue.Queue(maxsize=1000)
history = []                             # tin gần đây để client nối vào là có ngay
seen_updates = set()                     # chống xử lý lại update_id
seen_msg_ids = set()                     # chống hiển thị trùng trên UI

# ========= CORS & NO-CACHE =========
@app.after_request
def add_headers(resp):
    resp.headers["Access-Control-Allow-Origin"]  = ALLOW_ORIGIN or "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@app.route("/", methods=["GET"])
def home():
    return "<h2>⚡ RaidenX7 Bot Backend</h2><p>Server is running.</p>"

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# ========= HELPERS =========
def _push(item: dict):
    """đưa message vào history + stream queue, cắt history còn 500"""
    try:
        history.append(item)
        if len(history) > 500:
            del history[:-200]
        try:
            inbox.put_nowait(item)
        except queue.Full:
            try: inbox.get_nowait()
            except queue.Empty: pass
            inbox.put_nowait(item)
    except Exception:
        pass

def tg_post(path: str, payload: dict, timeout=10):
    return requests.post(f"{API}/{path}", json=payload, timeout=timeout)

# ========= SEND (Web -> Telegram) =========
@app.route("/send", methods=["POST", "OPTIONS"])
def send():
    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    chat_id = str(data.get("chat_id") or DEFAULT_CID or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "empty text"}), 400
    if not chat_id:
        # fallback: cho phép client truyền chat_id; nếu không có thì báo lỗi
        return jsonify({"ok": False, "error": "missing chat_id"}), 400

    r = tg_post("sendMessage", {"chat_id": chat_id, "text": text})
    ok = r.ok and (r.json().get("ok") is True)

    # ghi chính mình vào stream (id = từ telegram nếu có, tránh trùng)
    msg_id = None
    try:
        if ok:
            msg_id = r.json()["result"]["message_id"]
    except Exception:
        pass

    item = {
        "id": f"tg:{msg_id}" if msg_id else f"me:{int(time.time()*1000)}",
        "from": "me",
        "text": text,
        "ts": int(time.time()*1000),
    }
    _push(item)

    return jsonify({"ok": bool(ok), "tg": r.json() if r.ok else {"status": r.status_code}}), (200 if ok else 502)

# ========= WEBHOOK (Telegram -> Web) =========
@app.route("/webhook", methods=["POST"])
def webhook():
    # Xác thực header secret của Telegram (nên bật)
    if WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            return jsonify({"ok": False, "error": "invalid secret"}), 401

    update = request.get_json(silent=True) or {}
    up_id = update.get("update_id")

    # Chống xử lý trùng update
    if up_id is not None:
        if up_id in seen_updates:
            return jsonify({"ok": True})
        seen_updates.add(up_id)
        if len(seen_updates) > 2000:
            # dọn bớt cho nhẹ
            seen_updates.clear()
            seen_updates.add(up_id)

    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return jsonify({"ok": True})  # bỏ qua các loại update khác

    m_id   = msg.get("message_id")
    chat   = msg.get("chat") or {}
    c_id   = str(chat.get("id", ""))  # có thể dùng để điền TELEGRAM_CHAT_ID
    text   = (msg.get("text") or "").strip()

    # Gắn chat_id tự động nếu chưa cấu hình
    global DEFAULT_CID
    if not DEFAULT_CID and c_id:
        DEFAULT_CID = c_id

    # Chống hiển thị trùng
    if m_id and f"tg:{m_id}" in seen_msg_ids:
        return jsonify({"ok": True})
    if m_id:
        seen_msg_ids.add(f"tg:{m_id}")
        if len(seen_msg_ids) > 4000:
            seen_msg_ids.clear()
            seen_msg_ids.add(f"tg:{m_id}")

    item = {
        "id": f"tg:{m_id}" if m_id else f"tg:{int(time.time()*1000)}",
        "from": "tg",
        "text": text,
        "ts": int(time.time()*1000),
    }
    _push(item)
    return jsonify({"ok": True})

# ========= SSE STREAM =========
def sse_stream():
    # phát lại vài tin gần nhất cho client mới vào
    for it in history[-20:]:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"

    # rồi giữ kết nối, đẩy tin mới
    while True:
        try:
            it = inbox.get(timeout=30)
            yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
        except queue.Empty:
            # keep-alive để proxy/load balancer không đóng kết nối
            yield ":\n\n"

@app.route("/stream", methods=["GET"])
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

# ========= MAIN =========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
