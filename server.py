from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Test server
@app.route("/")
def home():
    return jsonify(status="ok")

# Đặt webhook
@app.route("/set-webhook")
def set_webhook():
    webhook_url = f"{request.host_url}webhook"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    r = requests.get(url)
    return r.json()

# Nhận dữ liệu từ Telegram
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Forward về chat mặc định (nếu muốn lưu)
        if CHAT_ID:
            send_message(CHAT_ID, f"User {chat_id}: {text}")

        # Trả lời trực tiếp cho user
        send_message(chat_id, f"Mình đã nhận: {text}")
    return "ok"

@app.route("/send", methods=["POST"])
def send():
    data = request.json
    text = data.get("text", "")
    if CHAT_ID and text:
        send_message(CHAT_ID, f"Web gửi: {text}")
        return jsonify(success=True, sent=text)
    return jsonify(success=False, error="No text or CHAT_ID")

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
