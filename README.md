# raidenx7-bot (Render)

API bridge Web → Telegram.

## ENV (Render → Environment)
- `TELEGRAM_TOKEN`: Bot token từ @BotFather
- `TARGET_CHAT_ID`: chat id nhận tin

## Deploy
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn server:app`
