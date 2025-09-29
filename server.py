import os, threading, time, queue, json
import requests
from flask import Flask, request, jsonify, make_response, Response

# ---- Env ----
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)
inbox: "queue.Queue[dict]" = queue.Queue(maxsize=2000)  # tin mới từ Telegram
history: list[dict] = []  # lưu nhẹ để /events trả về

# ---- headers: no-cache + CORS ----
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Access-Control-Allow-Origin"] = "*"   # cho web tĩnh call
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

@app.get("/health")
def health(): return "OK", 200

# ---- Web -> Telegram ----
@app.post("/send")
def send():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text: return {"ok": False, "error": "empty"}, 400
    try:
        r = requests.post(f"{API}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text},
                          timeout=10)
        ok = r.ok and r.json().get("ok")
        # ghi vào history như message phía "me"
        msg = {"id": int(time.time()*1000), "text": text, "from": "me"}
        history.append(msg)
        if len(history) > 500: history[:] = history[-500:]
        return {"ok": bool(ok)}, 200 if ok else 500
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# ---- Fallback: poll mỗi lần gọi (trả ngay) ----
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
    # gửi lại vài tin gần nhất cho client mới kết nối
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
            # keep-alive để proxy không đóng kết nối
            yield ":\n\n"

@app.get("/stream")
def stream():
    return Response(sse_stream(), mimetype="text/event-stream")

# ---- Nhiệm vụ nền: lấy tin từ Telegram ----
def poll_telegram():
    offset = None
    while True:
        try:
            r = requests.get(f"{API}/getUpdates",
                             params={"timeout": 1, "offset": offset},
                             timeout=5)
            if not r.ok:
                time.sleep(1); continue
            updates = r.json().get("result", [])
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text = msg.get("text")
                mid  = msg.get("message_id")
                if not text or not mid: continue
                item = {"id": mid, "text": text, "from": "them"}
                try:
                    inbox.put_nowait(item)
                except queue.Full:
                    _ = inbox.get_nowait()
                    inbox.put_nowait(item)
        except Exception:
            time.sleep(1)

threading.Thread(target=poll_telegram, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
