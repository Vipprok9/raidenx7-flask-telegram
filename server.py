import os, time, requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# ===== App & CORS =====
app = Flask(__name__, template_folder="templates")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ===== ENV trên Render =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")              # token bot Telegram
CHAT_ID   = os.environ.get("CHAT_ID")                # chat id Telegram nhận tin
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")    # (tuỳ chọn) dùng AI
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ===== TỪ ĐIỂN TRẢ LỜI NGẮN (fallback) =====
AUTO_REPLY = {
    "hello": "Xin chào 👋, mình là bot demo!",
    "ai": "AI (Trí tuệ nhân tạo) giúp máy móc học từ dữ liệu để tự động hoá nhiệm vụ.",
    "token": "Token là đơn vị giá trị trong blockchain, dùng làm thưởng, phí hoặc quản trị.",
    "defi": "DeFi là tài chính phi tập trung, không qua trung gian, chạy trên smart contract.",
    "airdrop": "Airdrop: dự án tặng token để thu hút người dùng sớm.",
    "node": "Node là máy/thành phần chạy phần mềm mạng blockchain, giúp xác thực/ghi dữ liệu.",
    "depin": "DePIN là mạng lưới hạ tầng vật lý phi tập trung; cộng đồng góp thiết bị & nhận token.",
    "tin tức": "Theo dõi Cointelegraph, The Block, Bankless để cập nhật crypto mỗi ngày.",
    "giá": "Mình không dự đoán giá; hãy quản trị rủi ro và đa dạng hoá danh mục nhé!",
}

def match_auto(text: str):
    t = (text or "").lower().strip()
    for k, v in AUTO_REPLY.items():
        if k in t:
            return v
    return None

# ===== STYLE PROMPTS (Tiếng Việt) =====
STYLE_PROMPTS = {
    "friendly": "Bạn là trợ lý Tiếng Việt thân thiện. Giọng casual, 1 emoji khi phù hợp, trả lời ngắn gọn (1–3 câu). Không vòng vo.",
    "expert":   "Bạn là trợ lý kỹ thuật Tiếng Việt. Trả lời mạch lạc, có định nghĩa ngắn, cơ chế và 1 ví dụ. Giọng trang trọng, súc tích.",
}

# ======= AI trả lời (nếu có OPENAI_API_KEY) =======
def ai_reply(user_text: str, style: str = "friendly") -> str | None:
    if not OPENAI_API_KEY:
        return None
    try:
        # OpenAI SDK (>=2024) — kiểu dùng đơn giản
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        system_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["friendly"])
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.6 if style == "friendly" else 0.2,
            max_tokens=200 if style == "expert" else 120,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("AI error:", e)
        return None

# ===== Gửi Telegram =====
def tg_send(chat_id: str, text: str):
    if not (BOT_TOKEN and chat_id and text):
        return False
    try:
        r = requests.post(f"{TG_API}/sendMessage",
                          json={"chat_id": chat_id, "text": text},
                          timeout=10)
        return r.ok
    except Exception as e:
        print("TG send error:", e)
        return False

# ======= Routes =======
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json(force=True, silent=True) or {}
    user_text = f"{data.get('text','')}".strip()
    style = (data.get("style") or "friendly").lower()

    if not user_text:
        return jsonify({"ok": False, "error": "Thiếu nội dung"}), 400

    # 1) Gửi câu hỏi sang Telegram (để bạn thấy log trên điện thoại/desktop)
    tg_send(CHAT_ID, f"[WEB] {user_text}")

    # 2) Thử dùng AI trước (nếu có KEY), nếu fail → fallback auto
    reply = ai_reply(user_text, style=style) or match_auto(user_text)

    # 3) Nếu vẫn không có, trả lời mặc định
    if not reply:
        reply = "Mình đã chuyển câu hỏi cho chủ bot, sẽ trả lời sớm!"

    # 4) Gửi câu trả lời về Telegram (để lưu vết)
    tg_send(CHAT_ID, f"[BOT] {reply}")

    return jsonify({"ok": True, "reply": reply})

# Health check
@app.route("/healthz")
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
