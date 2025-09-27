import os, time, requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
# Cho phép gọi từ web tĩnh (Cloudflare Pages) hoặc cùng domain Render
# Nếu bạn biết domain Pages, thay "*" bằng ["https://<ten>.pages.dev"]
CORS(app, resources={r"/*": {"origins": "*"}})

# ENV cần có trên Render:
# TELEGRAM_TOKEN  : token bot từ BotFather
# TARGET_CHAT_ID  : chat id Telegram của BẠN (nơi nhận tin từ web & forward)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("TARGET_CHAT_ID", "")

if not TOKEN:
    print("[WARN] Missing TELEGRAM_TOKEN")
if not OWNER_CHAT_ID:
    print("[WARN] Missing TARGET_CHAT_ID")

TG_API = f"https://api.telegram.org/bot{TOKEN}"

# ====== AUTO-REPLY TRENDS (có thể mở rộng) ======
AUTO_REPLY = {
    "hello": "Xin chào 👋, mình là bot hỗ trợ cơ bản.",
    "ai": "AI (Trí tuệ nhân tạo) giúp máy tính học và suy nghĩ như con người.",
    "token": "Token là đơn vị tiền điện tử phát hành trên blockchain.",
    "defi": "DeFi là tài chính phi tập trung: vay, gửi, swap… chạy bằng smart contract.",
    "airdrop": "Airdrop: dự án tặng token cho cộng đồng (thường cần làm nhiệm vụ/testnet).",
    "node": "Node là máy/thiết bị duy trì mạng blockchain, chạy node có thể được thưởng token.",
    "depin": "DePIN = Decentralized Physical Infrastructure Network (hạ tầng vật lý phi tập trung).",
    "tin tức": "Theo dõi Cointelegraph, Binance News, hoặc Twitter/X để cập nhật nhanh.",
    "giá": "Mình không thể dự đoán giá. Hãy quản lý rủi ro và theo dõi thị trường nhé."
}

def match_auto(text: str):
    if not text:
        return None
    t = text.lower()
    for k, v in AUTO_REPLY.items():
        if k in t:
            return v
    return None

def tg_send(chat_id, text):
    try:
        r = requests.post(f"{TG_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)
        return r.ok, (r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)
    except Exception as e:
        return False, str(e)

@app.route("/")
def home():
    return render_template("index.html")

# ---------- WEB → TELEGRAM + AUTO-REPLY (trả lời lại cho web) ----------
@app.post("/send")
def send_from_web():
    if not TOKEN or not OWNER_CHAT_ID:
        return jsonify(ok=False, error="Server chưa cấu hình TOKEN/CHAT_ID"), 500

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(ok=False, error="empty text"), 400

    # 1) Forward câu hỏi của người dùng từ web sang Telegram của bạn
    ok1, res1 = tg_send(OWNER_CHAT_ID, f"[WEB] Khách hỏi: {text}")

    # 2) Thử auto-reply theo bộ rule
    ar = match_auto(text)
    if ar:
        # Gửi câu trả lời auto sang Telegram (để bạn nhìn thấy luôn)
        tg_send(OWNER_CHAT_ID, f"[AUTO] {ar}")
        # Trả cho web để hiện ngay
        return jsonify(ok=True, reply=ar)

    # 3) Nếu không match auto, vẫn trả lời lịch sự trên web + bạn nhận bản gốc trên Telegram
    fallback = "Mình đã chuyển câu hỏi của bạn cho admin 📩 — sẽ trả lời sớm nhé!"
    return jsonify(ok=True, reply=fallback)

# ---------- TELEGRAM → AUTO-REPLY + FORWARD CHO BẠN KHI KHÔNG MATCH ----------
@app.post(f"/{TOKEN}")
def telegram_webhook():
    upd = request.get_json(silent=True) or {}
    msg = upd.get("message") or {}
    text = msg.get("text") or ""
    chat = msg.get("chat") or {}
    from_user = msg.get("from") or {}
    chat_id = chat.get("id")

    if not chat_id:
        return jsonify(ok=True)

    ar = match_auto(text)

    if ar:
        # Trả lời ngay trong cuộc chat Telegram đó
        tg_send(chat_id, ar)
    else:
        # Không match → nếu là tin của người khác (không phải owner),
        # forward cho bạn biết để tự trả lời.
        if OWNER_CHAT_ID and str(chat_id) != str(OWNER_CHAT_ID):
            uname = from_user.get("username") or (from_user.get("first_name","") + " " + from_user.get("last_name","")).strip()
            uname = uname or "user"
            tg_send(OWNER_CHAT_ID, f"[FWD] @{uname}: {text}")

    return jsonify(ok=True)

@app.get("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    # Local run: python server.py
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
