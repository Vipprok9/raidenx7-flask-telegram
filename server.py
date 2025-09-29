import os, time, json, queue
import requests
from flask import Flask, request, jsonify, Response, make_response

# ==== Env ====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)
inbox: "queue.Queue[dict]" = queue.Queue(maxsize=200)
history: list[dict] = []   # lưu để /events & SSE trả snapshot

# ---- headers: no-cache + CORS ----
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

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
        ok = r.ok and (r.json().get("ok") if r.headers.get("content-type","").startswith("application/json") else True)
        msg = {"id": int(time.time()*1000), "text": text, "from": "web"}
        history.append(msg)
        if len(history) > 500: history[:] = history[-500:]
        return {"ok": bool(ok), "tg": r.json() if r.headers.get("content-type","").startswith("application/json") else {}}, (200 if ok else 502)
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# ---- Fallback: polling qua HTTP của web (trả ngay các item chờ) ----
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
    return make_response(jsonify(items), 200)

# ---- SSE realtime ----
def sse_stream():
    # gửi snapshot 20 tin gần nhất
    for it in history[-20:]:
        yield f"data: {json.dumps(it, ensure_ascii=False)}\n\n"
    # stream các tin mới
    while True:
        try:
            item = inbox.get(timeout=30)
            history.append(item)
            if len(history) > 500: history[:] = history[-500:]
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        except queue.Empty:
            # keep-alive
            yield ":\\n\\n"

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

# ---- Telegram -> Web (WEBHOOK) ----
@app.post("/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    msg = (update.get("message") or update.get("edited_message")) or {}
    text = (msg.get("text") or "").strip()
    mid = msg.get("message_id") or int(time.time()*1000)
    if text:
        item = {"id": mid, "text": text, "from": "tg"}
        try:
            inbox.put_nowait(item)
        except queue.Full:
            _ = inbox.get_nowait()
            inbox.put_nowait(item)
        history.append(item)
        if len(history) > 500: history[:] = history[-500:]
    # MUST: trả 200 ngay
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
