import os, time, queue, threading, requests
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ==== Env vars ====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else None

# ==== Event queue ====
event_q = queue.Queue(maxsize=2000)
event_id = 0
lock = threading.Lock()

def push_event(kind, text, sender="system"):
    """Đẩy tin nhắn vào hàng đợi cho web"""
    global event_id
    with lock:
        event_id += 1
        eid = event_id
    data = {"id": eid, "kind": kind, "text": text, "sender": sender, "ts": time.time()}
    try:
        event_q.put_nowait(data)
    except queue.Full:
        _ = event_q.get_nowait()
        event_q.put_nowait(data)
    return data

# ==== Routes ====
@app.get("/")
def home():
    return "<h2>⚡ RaidenX7 Bot Backend</h2>"

@app.post("/send")
def send_to_tg():
    """
    Web -> Telegram
    """
    if not TG_API or not CHAT_ID:
        return jsonify({"ok": False, "error": "Missing TELEGRAM_* env"}), 500

    text = (request.json or {}).get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400

    # Push event cho web hiển thị ngay
    push_event("message", text, sender="web")

    # Gửi Telegram async
    def _bg_send():
        try:
            requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text}, timeout=10)
        except Exception:
            pass
    threading.Thread(target=_bg_send, daemon=True).start()

    return jsonify({"ok": True})

@app.post("/webhook")
def telegram_webhook():
    """
    Telegram -> Webhook -> đẩy cho web
    """
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message") or {})
    text = (msg.get("text") or "").strip()

    if text:
        push_event("message", text, sender="telegram")

    return jsonify({"ok": True})

@app.get("/events")
def events_long_poll():
    """
    Long-poll: client gọi /events?since=<lastId>
    Server chờ tối đa 25s nếu chưa có tin mới
    """
    since = int(request.args.get("since", "0") or 0)
    deadline = time.time() + 25
    cached = []

    # Gom nhanh tin mới trong queue
    try:
        while True:
            item = event_q.get_nowait()
            if item["id"] > since:
                cached.append(item)
    except queue.Empty:
        pass
    if cached:
        return jsonify({"ok": True, "events": cached})

    # Nếu chưa có, chờ blocking
    while time.time() < deadline:
        try:
            item = event_q.get(timeout=1.0)
            if item["id"] > since:
                cached.append(item)
                # drain các item kế tiếp
                try:
                    while True:
                        nxt = event_q.get_nowait()
                        if nxt["id"] > since:
                            cached.append(nxt)
                except queue.Empty:
                    pass
                return jsonify({"ok": True, "events": cached})
        except queue.Empty:
            continue

    return jsonify({"ok": True, "events": []})

@app.get("/stream")
def stream():
    """
    SSE stream cho frontend (fallback nếu dùng SSE)
    """
    def event_stream():
        last_sent = 0
        while True:
            try:
                item = event_q.get(timeout=15)
                yield f"data: {item}\n\n"
                last_sent = item["id"]
            except queue.Empty:
                yield ": keepalive\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

@app.get("/health")
def health():
    return jsonify({"ok": True, "time": time.time()})

# ==== Run local ====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
