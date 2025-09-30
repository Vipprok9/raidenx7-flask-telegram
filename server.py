import os, time, json, queue, threading
from collections import deque
import requests
from flask import Flask, request, jsonify, Response

# ==== Env ====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()  # chat test mặc định
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==== App, state ====
app = Flask(__name__)
inbox: "queue.Queue[dict]" = queue.Queue(maxsize=1000)   # luồng sự kiện đẩy ra SSE
history: list[dict] = []                                 # lưu nhẹ vài trăm bản ghi

# chống trùng update_id
_seen = set()
_seen_order = deque(maxlen=2000)

def mark_seen(uid: str) -> bool:
    """True nếu là update mới, False nếu trùng"""
    if not uid:
        return True
    if uid in _seen:
        return False
    _seen.add(uid)
    _seen_order.append(uid)
    if len(_seen) > 8000:        # dọn RAM an toàn
        while _seen_order:
            _seen.discard(_seen_order.popleft())
    return True

# ==== headers: CORS + no-cache + không buffer SSE ====
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["X-Accel-Buffering"] = "no"  # tránh proxy buffer SSE
    return resp

# ==== routes cơ bản ====
@app.get("/")
def home():
    return "<h2>⚡ RaidenX7 Bot Backend</h2><p>Service is running.</p>"

@app.get("/health")
def health():
    return "OK", 200

# Web → Telegram
@app.post("/send")
def send():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    to   = str(data.get("chat_id") or CHAT_ID)
    if not text:
        return jsonify(ok=False, error="missing text"), 400
    if not to:
        return jsonify(ok=False, error="missing chat_id"), 400
    try:
        r = requests.post(f"{API}/sendMessage",
                          json={"chat_id": to, "text": text},
                          timeout=10)
        body = r.json() if r.headers.get("content-type","").startswith("application/json") else {"raw": r.text}
        ok = bool(r.ok and body.get("ok", True))
        msg = {"id": int(time.time()*1000), "text": text, "from": "web", "chat_id": to}
        history.append(msg)
        if len(history) > 500: history[:] = history[-500:]
        # đẩy ra SSE
        try: inbox.put_nowait(msg)
        except queue.Full:
            try: _ = inbox.get_nowait()
            except Exception: pass
            inbox.put_nowait(msg)
        return jsonify(ok=ok, tg=body), (200 if ok else 502)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# Telegram → Web (webhook)
@app.post("/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    uid = str(update.get("update_id"))
    if not mark_seen(uid):  # tránh nhân đôi do retry/multi-worker
        return "OK", 200

    msg = (update.get("message") or update.get("edited_message")
           or update.get("channel_post") or update.get("edited_channel_post") or {})
    text = (msg.get("text") or msg.get("caption") or "").strip() or "[non-text]"
    mid  = msg.get("message_id") or int(time.time()*1000)
    chat = (msg.get("chat") or {})
    chat_id = chat.get("id")

    item = {"id": mid, "text": text, "from": "tg", "chat_id": chat_id}
    # đẩy ra SSE + lưu history, trả OK ngay để giảm retry
    try: inbox.put_nowait(item)
    except queue.Full:
        try: _ = inbox.get_nowait()
        except Exception: pass
        inbox.put_nowait(item)
    history.append(item)
    if len(history) > 500: history[:] = history[-500:]
    return "OK", 200

# SSE realtime cho frontend
def sse_stream():
    # gửi snapshot vài tin gần nhất
    for it in history[-10:]:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
    # chờ tin mới hoặc ping giữ kết nối
    while True:
        try:
            item = inbox.get(timeout=15)
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except queue.Empty:
            yield ": ping\n\n"

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    # chạy dev (Render dùng gunicorn từ Procfile)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
