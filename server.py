import os, time, json, queue
from collections import deque

import requests
from flask import Flask, request, Response, jsonify

# ==== ENV ====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")  # DM là số dương; group là -100...
if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==== APP ====
app = Flask(__name__)
inbox: "queue.Queue[dict]" = queue.Queue(maxsize=400)
history: list[dict] = []

# ==== HEADERS: CORS + no-cache + SSE no-buffer ====
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["X-Accel-Buffering"] = "no"  # giúp SSE qua proxy
    return resp

# ---- Home / Health ----
@app.get("/")
def home():
    return "<h2>⚡ RaidenX7 Bot Backend</h2><p>OK</p>"

@app.get("/health")
def health():
    return "OK", 200

# ---- Web -> Telegram ----
@app.post("/send")
def send():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    to   = data.get("chat_id") or CHAT_ID
    if not text:
        return jsonify(ok=False, error="missing text"), 400
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={"chat_id": to, "text": text},
            timeout=10,
        )
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}

        ok = bool(r.ok and body.get("ok", True))

        # echo sang UI ngay (không chờ webhook)
        history.append({"id": int(time.time()*1000), "text": text, "from": "web"})
        if len(history) > 500:
            history[:] = history[-500:]

        return jsonify(ok=ok, tg=body), (200 if ok else 502)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# ---- Chống trùng update_id trong webhook ----
_seen = set()
_seen_order = deque(maxlen=2000)

def _mark_seen(uid: str) -> bool:
    """True nếu mới, False nếu đã thấy -> bỏ qua bản trùng."""
    if not uid:
        return True
    if uid in _seen:
        return False
    _seen.add(uid)
    _seen_order.append(uid)
    # thu gọn nếu quá lớn
    if len(_seen) > 8000:
        while _seen_order:
            _seen.discard(_seen_order.popleft())
    return True

# ---- Telegram -> Web (webhook) ----
@app.post("/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}

    # lọc trùng
    uid = str(update.get("update_id"))
    if not _mark_seen(uid):
        return "OK", 200

    msg = (update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
        or {})

    text    = (msg.get("text") or msg.get("caption") or "").strip() or "[non-text]"
    mid     = msg.get("message_id") or int(time.time()*1000)
    chat_id = (msg.get("chat") or {}).get("id")

    item = {"id": mid, "text": text, "from": "tg", "chat_id": chat_id}

    # đẩy vào stream queue (nếu đầy thì drop đầu)
    try:
        inbox.put_nowait(item)
    except queue.Full:
        try:
            _ = inbox.get_nowait()
        except Exception:
            pass
        inbox.put_nowait(item)

    # lưu lịch sử để client mới vào có snapshot
    history.append(item)
    if len(history) > 500:
        history[:] = history[-500:]

    return "OK", 200

# ---- SSE stream (không nhân đôi history) ----
def sse_stream():
    # snapshot vài bản gần nhất
    for it in history[-10:]:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
    # live
    while True:
        try:
            item = inbox.get(timeout=15)
            # không append lại vào history -> tránh nhân đôi
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except queue.Empty:
            # heartbeat giữ kết nối sống
            yield ": ping\n\n"

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    # chạy dev; Render sẽ dùng gunicorn theo Procfile
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
