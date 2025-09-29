import os, time, json, requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Env vars
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_URL = f"https://api.telegram.org/bot{TOKEN}"

# Bộ nhớ tạm
events = []

def push_event(msg):
    events.append({"text": msg, "ts": time.time()})
    if len(events) > 100:
        events.pop(0)

@app.route("/health")
def health():
    return "OK", 200

# Web gửi tin → Telegram
@app.route("/send", methods=["POST"])
def send():
    data = request.json
    text = data.get("text", "")
    if not text:
        return "no text", 400
    try:
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": CHAT_ID, "text": text})
        push_event(f"Me: {text}")
        return "ok"
    except Exception as e:
        return str(e), 500

# Polling lấy sự kiện
@app.route("/events")
def get_events():
    return jsonify(events)

# SSE realtime
@app.route("/stream")
def stream():
    def event_stream():
        last = 0
        while True:
            if events and events[-1]["ts"] > last:
                last = events[-1]["ts"]
                yield f"data: {json.dumps(events[-1], ensure_ascii=False)}\n\n"
            time.sleep(1)
    return Response(event_stream(), mimetype="text/event-stream")

# Telegram webhook → web
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if "message" in data and "text" in data["message"]:
        text = data["message"]["text"]
        push_event(f"Bot: {text}")
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
