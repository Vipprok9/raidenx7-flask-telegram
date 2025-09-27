import os, time, requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
# Cho phép gọi từ web tĩnh (Cloudflare Pages,…)
CORS(app, resources={r"/*": {"origins": "*"}})

# ===== ENV trên Render =====
# TELEGRAM_TOKEN : token bot từ BotFather
# TARGET_CHAT_ID : chat id Telegram (bạn/nhóm nhận forward)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("TARGET_CHAT_ID", "")

TG_API = f"https://api.telegram.org/bot{TOKEN}"

# ===== AUTO-REPLY TRENDS (bạn mở rộng thêm được) =====
AUTO_REPLY = {
    "hello": "Xin chào 👋, mình là bot trợ lý của RaidenX7!",
    "ai": "AI (Trí tuệ nhân tạo) giúp tự động hóa và ra quyết định từ dữ liệu.",
    "token": "Token là đơn vị giá trị phát hành trên blockchain (ERC-20, SPL…).",
    "defi": "DeFi là tài chính phi tập trung: lending, DEX, yield…",
    "airdrop": "Airdrop: dự án tặng token cho người dùng đủ điều kiện.",
    "node": "Node là máy/thiết bị duy trì mạng blockchain.",
    "depin": "DePIN = Decentralized Physical Infrastructure Networks.",
    "tin tức": "Theo dõi Cointelegraph, The Block, Messari… để cập nhật nhé.",
    "giá": "Mình không dự đoán giá; bạn nên quản trị rủi ro cẩn thận.",
}

def match_auto(text: str) -> str | None:
    t = (text or "").lower().strip()
    for k, v in AUTO_REPLY.items():
        if k in t:
            return v
    return None

def tg_send(chat_id, text):
    try:
        r = requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                          timeout=10)
        ok = r.status_code == 200 and r.json().get("ok")
        return ok, r.text
    except Exception as e:
        return False, str(e)

@app.get("/")
def home():
    # Trang chat
    return render_template("index.html")

@app.get("/ping")
def ping():
    return jsonify(ok=True, time=int(time.time()))

# ===== Web Chat → Flask =====
@app.post("/webchat")
def webchat():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(ok=False, reply="Bạn chưa nhập gì."), 400

    # 1) forward cho bạn biết (tuỳ chọn)
    if OWNER_CHAT_ID:
        tg_send(OWNER_CHAT_ID, f"[Web] {text}")

    # 2) thử auto-reply theo rule
    ar = match_auto(text)
    if ar:
        # cũng có thể gửi trả lời vào Telegram nếu muốn
        if OWNER_CHAT_ID:
            tg_send(OWNER_CHAT_ID, f"[AUTO] {ar}")
        return jsonify(ok=True, reply=ar)

    # 3) fallback
    return jsonify(ok=True, reply="Mình đã chuyển câu hỏi cho chủ bot, sẽ trả lời sớm!")

# ===== Telegram → (auto-reply + forward) =====
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
        tg_send(chat_id, ar)
    else:
        # không match → ping chủ bot
        if OWNER_CHAT_ID and str(chat_id) != str(OWNER_CHAT_ID):
            uname = from_user.get("username") or from_user.get("first_name") or "user"
            tg_send(OWNER_CHAT_ID, f"[TG] {uname}: {text}")

    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
