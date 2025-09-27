from flask import Flask, render_template, request, jsonify
import requests, os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__, static_folder='static', template_folder='templates')

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/send", methods=["POST"])
def send():
    data = request.json or {}
    msg = (data.get("message") or "").strip()
    if msg and BOT_TOKEN and CHAT_ID:
        requests.post(f"{TG_API}/sendMessage", json={"chat_id": CHAT_ID, "text": msg})
    return jsonify({"ok": True})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    if "message" in data:
        text = (data["message"].get("text") or "").strip()
        chat_id = data["message"]["chat"]["id"]
        if text.lower() in ("hi","hello","xin chao","xin chào","/start"):
            requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": chat_id, "text": "Xin chào 👋 Bot RaidenX7 đã kết nối!"})
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
