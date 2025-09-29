import os, time, json, queue
import requests
from flask import Flask, request, Response

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)
inbox = queue.Queue(maxsize=400)
history = []

@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp

@app.get("/")
def home():
    return "<h2>⚡ RaidenX7 Bot Backend</h2><p>OK</p>"

@app.get("/health")
def health():
    return "OK", 200

@app.post("/send")
def send():
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    to = data.get("chat_id") or CHAT_ID
    if not text:
        return jsonify(ok=False, error="missing text"), 400
    try:
        r = requests.post(f"{API}/sendMessage", json={"chat_id": to, "text": text}, timeout=8)
        body = {}
        try: body = r.json()
        except: body = {"raw": r.text}
        ok = bool(r.ok and body.get("ok", True))
        history.append({"id": int(time.time()*1000), "text": text, "from": "web"})
        if len(history) > 500: history[:] = history[-500:]
        return (json.dumps({"ok": ok, "tg": body}), 200 if ok else 502, {"Content-Type":"application/json"})
    except Exception as e:
        return (json.dumps({"ok": False, "error": str(e)}), 500, {"Content-Type":"application/json"})

@app.post("/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message") or
           update.get("channel_post") or update.get("edited_channel_post") or {})
    text = (msg.get("text") or msg.get("caption") or "").strip()
    mid = msg.get("message_id") or int(time.time()*1000)
    chat_id = (msg.get("chat") or {}).get("id")
    item = {"id": mid, "text": text or "[non-text]", "from": "tg", "chat_id": chat_id}
    try:
        inbox.put_nowait(item)
    except queue.Full:
        _ = inbox.get_nowait(); inbox.put_nowait(item)
    history.append(item)
    if len(history) > 500: history[:] = history[-500:]
    print("WEBHOOK ok for chat:", chat_id)
    return "OK", 200

def sse_stream():
    for it in history[-10:]:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
    while True:
        try:
            item = inbox.get(timeout=15)
            history.append(item)
            if len(history) > 500: history[:] = history[-500:]
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except queue.Empty:
            yield ": ping\n\n"

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","10000")))
