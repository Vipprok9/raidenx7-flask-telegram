import os, time, json, queue
from flask import Flask, request, jsonify, Response

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}"

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

app = Flask(__name__)
events: "queue.Queue[dict]" = queue.Queue(maxsize=2000)
_seen_updates = set()           # chống nhân bản webhook

# ---------- tiện ích ----------
def push_event(item: dict) -> None:
    item.setdefault("ts", int(time.time()*1000))
    try:
        events.put_nowait(item)
    except queue.Full:
        # rơi bớt phần đầu cho nhẹ
        try: events.get_nowait()
        except queue.Empty: pass
        events.put_nowait(item)

def tg_send_text(text: str) -> bool:
    try:
        import requests
        r = requests.post(
            f"{TG_API}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
        return bool(r.ok and r.json().get("ok"))
    except Exception:
        return False

def dedup_update(update_id: int) -> bool:
    """True nếu đã thấy (bỏ qua), False nếu lần đầu (lưu & xử lý)."""
    if update_id in _seen_updates: 
        return True
    _seen_updates.add(update_id)
    if len(_seen_updates) > 5000:
        # dọn bớt cho nhẹ bộ nhớ
        for _ in range(3000): _seen_updates.pop()
    return False

# ---------- headers chung ----------
@app.after_request
def add_common_headers(resp):
    # CORS
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    # chống cache cứng đầu các tầng
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate, no-transform"
    return resp

@app.route("/", methods=["GET"])
def home():
    return "RaidenX7 Bot Backend", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify(ok=True), 200

# ---------- Web -> Telegram ----------
@app.post("/send")
def send_from_web():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or data.get("text") or "").strip()
    if not text:
        return jsonify(ok=False, error="empty"), 400

    ok = tg_send_text(text)
    # Echo ngay sang web để thấy tức thì (không đợi Telegram)
    push_event({"from": "web", "text": text})
    return jsonify(ok=ok)

# ---------- Telegram -> Web (webhook) ----------
@app.post("/webhook")
def webhook():
    upd = request.get_json(silent=True) or {}
    upd_id = upd.get("update_id")
    if upd_id and dedup_update(upd_id):
        return jsonify(ok=True)  # đã xử lý, trả OK sớm để Telegram khỏi gửi lại

    msg = upd.get("message") or upd.get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    if text:
        push_event({"from": "telegram", "text": text})
    return jsonify(ok=True)

# ---------- SSE realtime ----------
@app.get("/stream")
def stream():
    def gen():
        # mở đầu để ngăn proxy đệm
        yield ": connected\n\n"
        last = time.time()
        while True:
            try:
                item = events.get(timeout=14)   # < 15s để Cloudflare không idle
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except queue.Empty:
                # keep-alive đều đặn để không bị treo & buộc proxy xả buffer
                yield ": ping\n\n"
                # lặp tiếp
    headers = {
        # BẮT BUỘC cho SSE + tắt buffering/caching các tầng
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",   # với proxy kiểu nginx
    }
    return Response(gen(), headers=headers)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
