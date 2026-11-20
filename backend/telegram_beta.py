"""Beta bot entry point for installing and signing in to the browser app."""

import asyncio
from contextlib import suppress
import hashlib
from html import escape
import hmac

import httpx
from fastapi import HTTPException, Request


WEBHOOK_PATH = "/api/telegram/updates"
APP_CALLBACK = "beta-app-login"
APP_PIN_TEXT = "Склад Бета\nНажмите «Приложение», чтобы получить ссылку и код для входа."
TELEGRAM_ERRORS = (httpx.HTTPError, RuntimeError, ValueError, TypeError, AttributeError)


def register_telegram_app_bot(app, token, public_url, transaction, authorize, issue_code, *, owner_chat_id=None, auto_configure=False):
    secret = hmac.new(token.encode(), b"warehouse-beta-telegram-webhook-v1", hashlib.sha256).hexdigest()
    endpoint = public_url + WEBHOOK_PATH
    app_url = public_url + "/pwa/"

    async def telegram(client, method, **data):
        response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=data)
        payload = response.json()
        if not response.is_success or not payload.get("ok"):
            raise RuntimeError(method)
        return payload.get("result")

    def reply(chat_id, text, **options):
        return {
            "method": "sendMessage", "chat_id": chat_id, "text": text,
            "reply_markup": {
                "keyboard": [[{"text": "Приложение"}]],
                "resize_keyboard": True,
                "is_persistent": True,
            },
            **options,
        }

    @app.post(WEBHOOK_PATH, include_in_schema=False)
    async def telegram_updates(request: Request):
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(provided.encode(), secret.encode()):
            raise HTTPException(403, "Доступ запрещён")
        update = await request.json()
        if not isinstance(update, dict):
            return {}
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            if callback.get("data") != APP_CALLBACK or not isinstance(callback.get("id"), str):
                return {}
            message = callback.get("message")
        else:
            message = update.get("message")
        if not isinstance(message, dict):
            return {}
        chat = message.get("chat")
        sender = (callback if isinstance(callback, dict) else message).get("from")
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return {}
        chat_id = chat.get("id")
        if chat.get("type") != "private" or type(chat_id) is not int or chat_id <= 0 or sender.get("id") != chat_id:
            return {}
        if isinstance(callback, dict):
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await telegram(client, "answerCallbackQuery", callback_query_id=callback["id"])
            except TELEGRAM_ERRORS:
                pass
        else:
            text = message.get("text")
            words = text.split(maxsplit=1) if isinstance(text, str) else []
            if not words:
                return {}
            command = words[0].split("@", 1)[0].casefold()
            if command in ("/start", "/help"):
                return reply(chat_id, "Нажмите «Приложение», чтобы получить ссылку и код для входа.")
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
            f'<a href="{escape(app_url, quote=True)}">Открыть приложение</a>\n\n'
            "На iPhone откройте ссылку в Safari и выберите «Поделиться → На экран Домой». "
            "На Android откройте ссылку в Chrome и выберите «Установить приложение».\n\n"
            f"Код для входа: {formatted}\nКод действует 5 минут. Никому его не передавайте.",
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )

    if not auto_configure:
        return
    worker = None

    async def configure():
        message_id = None
        async with httpx.AsyncClient(timeout=10) as client:
            for delay in (2, 5, 12, 20):
                await asyncio.sleep(delay)
                try:
                    webhook = await telegram(client, "getWebhookInfo")
                    current = webhook.get("url")
                    if current and current != endpoint:
                        print("Beta Telegram: existing external webhook retained", flush=True)
                        return
                    allowed = webhook.get("allowed_updates") or []
                    updates = list(dict.fromkeys([*allowed, "message", "callback_query"]))
                    if not current or updates != allowed:
                        await telegram(client, "setWebhook", url=endpoint, secret_token=secret, allowed_updates=updates)
                    commands = await telegram(client, "getMyCommands")
                    remaining_commands = [row for row in commands if row.get("command") != "app"]
                    if remaining_commands != commands:
                        await telegram(client, "setMyCommands", commands=remaining_commands)
                    if owner_chat_id:
                        if message_id is None:
                            chat = await telegram(client, "getChat", chat_id=owner_chat_id)
                            pinned = chat.get("pinned_message") or {}
                            if pinned.get("text") != APP_PIN_TEXT:
                                sent = await telegram(
                                    client, "sendMessage", chat_id=owner_chat_id, text=APP_PIN_TEXT,
                                    reply_markup={"inline_keyboard": [[{"text": "Приложение", "callback_data": APP_CALLBACK}]]},
                                    disable_notification=True,
                                )
                                message_id = sent["message_id"]
                        if message_id is not None:
                            await telegram(client, "pinChatMessage", chat_id=owner_chat_id, message_id=message_id, disable_notification=True)
                        print("Beta Telegram: application message pinned", flush=True)
                    print("Beta Telegram: application button webhook ready", flush=True)
                    return
                except TELEGRAM_ERRORS:
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
