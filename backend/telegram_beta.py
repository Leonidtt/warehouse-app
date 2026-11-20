"""Beta bot entry point for installing and signing in to the browser app."""

import asyncio
from contextlib import suppress
import hashlib
import hmac

import httpx
from fastapi import HTTPException, Request


WEBHOOK_PATH = "/api/telegram/updates"


def register_telegram_app_bot(app, token, public_url, transaction, authorize, issue_code, auto_configure=False):
    secret = hmac.new(token.encode(), b"warehouse-beta-telegram-webhook-v1", hashlib.sha256).hexdigest()
    endpoint = public_url + WEBHOOK_PATH
    app_url = public_url + "/pwa/"

    def reply(chat_id, text, markup=None):
        result = {"method": "sendMessage", "chat_id": chat_id, "text": text}
        if markup:
            result["reply_markup"] = markup
        return result

    @app.post(WEBHOOK_PATH, include_in_schema=False)
    async def telegram_updates(request: Request):
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(provided.encode(), secret.encode()):
            raise HTTPException(403, "Доступ запрещён")
        update = await request.json()
        if not isinstance(update, dict):
            return {}
        message = update.get("message")
        if not isinstance(message, dict):
            return {}
        chat, sender, text = message.get("chat") or {}, message.get("from") or {}, message.get("text")
        if not isinstance(text, str) or not isinstance(chat, dict) or not isinstance(sender, dict):
            return {}
        chat_id = chat.get("id")
        if chat.get("type") != "private" or type(chat_id) is not int or chat_id <= 0 or sender.get("id") != chat_id:
            return {}
        command = text.strip().split(maxsplit=1)
        if not command:
            return {}
        command = command[0].split("@", 1)[0].casefold()
        if command in ("/start", "/help"):
            return reply(chat_id, "Нажмите «Приложение», чтобы получить ссылку и код для входа.",
                         {"keyboard": [[{"text": "Приложение"}]], "resize_keyboard": True})
        if command not in ("приложение", "/app"):
            return {}

        update_id = update.get("update_id")
        if type(update_id) is not int:
            return {}
        with transaction() as conn:
            claimed = conn.execute("INSERT OR IGNORE INTO telegram_bot_updates(update_id) VALUES (?)", (update_id,))
            if not claimed.rowcount:
                return {}
            conn.execute("DELETE FROM telegram_bot_updates WHERE received_at < datetime('now','-7 days')")
            try:
                authorize(conn, chat_id)
                code = issue_code(conn, chat_id, rate_limit=True)
            except HTTPException as error:
                return reply(chat_id, error.detail)
        formatted = "-".join(code[n:n + 4] for n in (0, 4, 8))
        return reply(
            chat_id,
            "Склад Бета — тот же склад в браузере.\n"
            "На iPhone откройте ссылку в Safari и выберите «Поделиться → На экран Домой». "
            "На Android откройте ссылку в Chrome и выберите «Установить приложение».\n\n"
            f"Код для входа: {formatted}\nКод действует 5 минут. Никому его не передавайте.",
            {"inline_keyboard": [[{"text": "Открыть приложение", "url": app_url}]]},
        )

    if not auto_configure:
        return
    worker = None

    async def configure():
        async with httpx.AsyncClient(timeout=10) as client:
            async def telegram(method, **data):
                response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=data)
                payload = response.json()
                if not response.is_success or not payload.get("ok"):
                    raise RuntimeError(method)
                return payload.get("result")

            for delay in (2, 5, 12, 20):
                await asyncio.sleep(delay)
                try:
                    current = (await telegram("getWebhookInfo")).get("url")
                    if current and current != endpoint:
                        print("Beta Telegram: existing external webhook retained", flush=True)
                        return
                    if not current:
                        await telegram("setWebhook", url=endpoint, secret_token=secret, allowed_updates=["message"])
                    commands = await telegram("getMyCommands")
                    if not any(row.get("command") == "app" for row in commands):
                        await telegram("setMyCommands", commands=[*commands, {"command": "app", "description": "Ссылка на приложение и код для входа"}])
                    print("Beta Telegram: application button webhook ready", flush=True)
                    return
                except (httpx.HTTPError, RuntimeError, ValueError, TypeError, AttributeError):
                    continue
            print("Beta Telegram: application button setup could not be confirmed", flush=True)

    @app.on_event("startup")
    async def start():
        nonlocal worker
        worker = asyncio.create_task(configure())

    @app.on_event("shutdown")
    async def stop():
        if worker is not None:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
