import os, json, queue, time
from flask import Flask, request, jsonify, Response

# ==== ENV ====
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")   # chat id cá nhân hoặc group (âm)
if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==== APP ====
app = Flask(__name__)

# Hàng đợi sự kiện đẩy ra web (SSE)
events: "queue.Queue[dict]" = queue.Queue(maxsize=1000)

# Chống trùng lặp khi Telegram retry webhook (giữ 100 id gần nhất)
recent_update_ids: list[int] = []

def dedup_update(update_id: int) -> bool:
    """Trả về True nếu đã thấy id này (bỏ qua), False nếu mới (và ghi nhớ)."""
    if update_id in recent_update_ids:
        return True
    recent_update_ids.append(update_id)
    if len(recent_update_ids) > 100:
        del recent_update_ids[: len(recent_update_ids) - 100]
    return False

# ====== Helpers ======
import requests
def tg_send_text(text: str) -> bool:
    try:
        r = requests.post(f"{TG_API}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": text
        }, timeout=10)
        return r.ok and r.json().get("ok", False)
    except Exception:
        return False

def push_event(data: dict):
    """Đưa 1 event ra hàng đợi cho web; nếu đầy thì bỏ bớt đầu để không treo."""
    try:
        events.put_nowait(data)
    except queue.Full:
        try:
            events.get_nowait()
        except queue.Empty:
            pass
        events.put_nowait(data)

# ====== Middlewares ======
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    # CORS đơn giản cho frontend tĩnh (Cloudflare Pages)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

# ====== Health / Home ======
@app.get("/")
def home():
    return "<h2>⚡ RaidenX7 Bot Backend</h2><p>/health · /send · /webhook · /stream</p>"

@app.get("/health")
def health():
    return "OK", 200

# ====== Web -> Telegram ======
@app.post("/send")
def send_from_web():
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or data.get("text") or "").strip()
    if not text:
        return jsonify(ok=False, error="missing text"), 400

    ok = tg_send_text(text)
    # đẩy echo lên khung chat web ngay
    push_event({"from": "web", "text": text, "ts": int(time.time()*1000)})
    return jsonify(ok=bool(ok)), (200 if ok else 502)

# ====== Telegram -> Web (Webhook) ======
@app.post("/webhook")
def webhook():
    upd = request.get_json(silent=True) or {}
    # chống retry gây lặp
    upd_id = upd.get("update_id")
    if isinstance(upd_id, int) and dedup_update(upd_id):
        return jsonify(ok=True)

    msg = upd.get("message") or upd.get("edited_message") or {}
    text = (msg.get("text") or "").strip()
    if text:
        push_event({"from": "telegram", "text": text, "ts": int(time.time()*1000)})
    return jsonify(ok=True)

# ====== SSE realtime cho frontend ======
@app.get("/stream")
def stream():
    def gen():
        # Gửi vài keep-alive đầu tiên để proxy không đóng kết nối
        yield ": connected\n\n"
        # nếu có lịch sử tạm thì có thể phát ở đây (nhẹ nhàng)
        last_keepalive = time.time()
        while True:
            try:
                item = events.get(timeout=30)  # block tới khi có event hoặc 30s
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except queue.Empty:
                # keep-alive mỗi ~30s để giữ connection
                now = time.time()
                if now - last_keepalive >= 25:
                    yield ": keepalive\n\n"
                    last_keepalive = now
            # nhả CPU 1 chút
            time.sleep(0.01)

    return Response(gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"   # chống nginx proxy buffer
        })

if __name__ == "__main__":
    # chạy dev: python server.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
