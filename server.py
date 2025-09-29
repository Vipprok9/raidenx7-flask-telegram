import os, time, queue, threading, requests, json
from flask import Flask, request, jsonify, Response

# ---- Env ----
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)

inbox = queue.Queue(maxsize=1000)
history = []

# ---- Home ----
@app.get("/")
def home():
    return "<h2>⚡ RaidenX7 Bot Backend ⚡</h2><p>Server OK - check <a href='/health'>/health</a></p>"

# ---- Health ----
@app.get("/health")
def health():
    return "OK", 200

# ---- Web -> Telegram ----
@app.post("/send")
def send():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "missing text"}, 400
    try:
        r = requests.post(f"{API}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text},
                          timeout=10)
        body = r.json()
        ok = bool(r.ok and body.get("ok"))
        msg = {"id": int(time.time()*1000), "text": text, "from": "me"}
        history.append(msg)
        if len(history) > 500: history[:] = history[-500:]
        print("SEND:", body)
        return {"ok": ok, "tg": body}, (200 if ok else 502)
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# ---- Events (fallback polling) ----
@app.get("/events")
def events():
    items = []
    try:
        while True:
            item = inbox.get_nowait()
            items.append(item)
            history.append(item)
    except queue.Empty:
        pass
    if len(history) > 500: history[:] = history[-500:]
    return jsonify(items), 200

# ---- SSE realtime ----
def sse_stream():
    snapshot = history[-20:]
    for it in snapshot:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
    while True:
        try:
            item = inbox.get(timeout=30)
            history.append(item)
            if len(history) > 500: history[:] = history[-500:]
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except queue.Empty:
            yield ":keep-alive\n\n"

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

# ---- Telegram -> Web ----
@app.post("/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or
           update.get("edited_message") or
           update.get("channel_post") or
           update.get("edited_channel_post") or {})
    text = (msg.get("text") or msg.get("caption") or "").strip()
    mid = msg.get("message_id") or int(time.time()*1000)
    chat_id = (msg.get("chat") or {}).get("id")

    item = {"id": mid, "text": text or "[non-text]", "from": "tg", "chat_id": chat_id}
    try:
        inbox.put_nowait(item)
    except queue.Full:
        _ = inbox.get_nowait()
        inbox.put_nowait(item)
    history.append(item)
    if len(history) > 500: history[:] = history[-500:]

    print("WEBHOOK update:", update)  # log để debug trên Render
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
