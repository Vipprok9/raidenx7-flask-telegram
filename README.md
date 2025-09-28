# raidenx7-bot (Render)

API bridge Web → Telegram.

## ENV (Render → Environment)
- `BOT_TOKEN` : Bot token từ @BotFather
- `CHAT_ID`   : chat id nhận tin (cá nhân hoặc group)

## Deploy (Render)
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn server:app`

Mở `/` để test UI; gọi API: `POST /api/send` `{ "text": "Xin chào" }`.
