"""Telegram bot entry point for installing and signing in to the browser app."""

import asyncio
from contextlib import suppress
import hashlib
from html import escape
import hmac
from pathlib import Path
import time

import httpx
from fastapi import HTTPException, Request


WEBHOOK_PATH = "/api/telegram/updates"
APP_CALLBACK = "warehouse-app-login"
APP_PIN_TEXT = "Склад\nНажмите «Приложение», чтобы получить ссылку и код для входа."
MEMO_PATH = Path(__file__).with_name("employee-memo.pdf")
MAX_DELIVERY_ATTEMPTS = 3
TELEGRAM_ERRORS = (httpx.HTTPError, RuntimeError, ValueError, TypeError, AttributeError)


class TelegramAPIError(RuntimeError):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


def init_telegram_onboarding(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS telegram_onboarding (
            chat_id INTEGER PRIMARY KEY CHECK(chat_id>0),
            memo_sent INTEGER NOT NULL DEFAULT 0,
            application_pinned INTEGER NOT NULL DEFAULT 0,
            pin_message_id INTEGER,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt INTEGER NOT NULL DEFAULT 0
        )
    """)


def queue_telegram_onboarding(conn, chat_id):
    if chat_id <= 0:
        return
    conn.execute("""
        INSERT INTO telegram_onboarding(chat_id)
        SELECT ? WHERE NOT EXISTS (SELECT 1 FROM blocked_telegram WHERE tg_id=?)
        ON CONFLICT(chat_id) DO UPDATE SET attempts=0, next_attempt=0
        WHERE telegram_onboarding.attempts>=?
          AND (telegram_onboarding.memo_sent=0 OR telegram_onboarding.application_pinned=0)
    """, (chat_id, chat_id, MAX_DELIVERY_ATTEMPTS))


def register_telegram_app_bot(app, token, public_url, transaction, authorize, issue_code, *, auto_configure=False):
    secret = hmac.new(token.encode(), b"warehouse-main-telegram-webhook-v1", hashlib.sha256).hexdigest()
    endpoint = public_url + WEBHOOK_PATH
    app_url = public_url + "/pwa/"

    async def telegram(client, method, *, files=None, **data):
        url = f"https://api.telegram.org/bot{token}/{method}"
        if files:
            response = await client.post(url, data=data, files=files)
        else:
            response = await client.post(url, json=data)
        payload = response.json()
        if not response.is_success or not payload.get("ok"):
            raise TelegramAPIError(payload.get("error_code") or response.status_code)
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
                if command == "/start":
                    with transaction() as conn:
                        queue_telegram_onboarding(conn, chat_id)
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
        link = reply(
            chat_id,
            "Склад — тот же склад в браузере.\n"
            f'<a href="{escape(app_url, quote=True)}">Открыть приложение</a>\n\n'
            "На iPhone откройте ссылку в Safari и выберите «Поделиться → На экран Домой». "
            "На Android откройте ссылку в Chrome и выберите «Установить приложение».\n\n"
            "Код действует 5 минут. Никому его не передавайте.",
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )
        formatted = "-".join(code[n:n + 4] for n in (0, 4, 8))
        buttons = [[{"text": "Скопировать код", "copy_text": {"text": formatted}}]]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await telegram(client, **link)
        except TELEGRAM_ERRORS:
            buttons.append([{"text": "Открыть приложение", "url": app_url}])
        return reply(chat_id, formatted, reply_markup={"inline_keyboard": buttons})

    if not auto_configure:
        return
    worker = None

    def claim_delivery():
        with transaction() as conn:
            job = conn.execute("""
                SELECT t.* FROM telegram_onboarding t
                WHERE t.next_attempt<=? AND t.attempts<?
                  AND (t.memo_sent=0 OR t.application_pinned=0)
                  AND NOT EXISTS (SELECT 1 FROM blocked_telegram b WHERE b.tg_id=t.chat_id)
                ORDER BY t.next_attempt, t.chat_id LIMIT 1
            """, (int(time.time()), MAX_DELIVERY_ATTEMPTS)).fetchone()
            if job is not None:
                conn.execute("UPDATE telegram_onboarding SET attempts=attempts+1, next_attempt=? WHERE chat_id=?",
                             (int(time.time())+90, job["chat_id"]))
            return job

    async def deliver_onboarding(client, job):
        chat_id = job["chat_id"]
        try:
            if not job["memo_sent"]:
                with MEMO_PATH.open("rb") as memo:
                    await telegram(
                        client, "sendDocument", chat_id=chat_id,
                        caption="Памятка сотрудника «Склад»",
                        files={"document": ("Склад — памятка сотрудника.pdf", memo, "application/pdf")},
                    )
                with transaction() as conn:
                    conn.execute("UPDATE telegram_onboarding SET memo_sent=1 WHERE chat_id=?", (chat_id,))

            if not job["application_pinned"]:
                message_id = job["pin_message_id"]
                if message_id is None:
                    chat = await telegram(client, "getChat", chat_id=chat_id)
                    pinned = chat.get("pinned_message") or {}
                    if pinned.get("text") != APP_PIN_TEXT:
                        sent = await telegram(
                            client, "sendMessage", chat_id=chat_id, text=APP_PIN_TEXT,
                            reply_markup={"inline_keyboard": [[{"text": "Приложение", "callback_data": APP_CALLBACK}]]},
                            disable_notification=True,
                        )
                        message_id = sent["message_id"]
                        with transaction() as conn:
                            conn.execute("UPDATE telegram_onboarding SET pin_message_id=? WHERE chat_id=?",
                                         (message_id, chat_id))
                if message_id is not None:
                    await telegram(client, "pinChatMessage", chat_id=chat_id, message_id=message_id,
                                   disable_notification=True)
                with transaction() as conn:
                    conn.execute("UPDATE telegram_onboarding SET application_pinned=1 WHERE chat_id=?", (chat_id,))
        except TelegramAPIError as error:
            if error.status in (400, 403):
                with transaction() as conn:
                    conn.execute("UPDATE telegram_onboarding SET attempts=? WHERE chat_id=?",
                                 (MAX_DELIVERY_ATTEMPTS, chat_id))
        except TELEGRAM_ERRORS:
            pass

    async def run_onboarding(client):
        with transaction() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO telegram_onboarding(chat_id)
                SELECT u.tg_id FROM users u
                WHERE u.tg_id>0 AND u.is_registered=1 AND u.role<>'guest'
                  AND NOT EXISTS (SELECT 1 FROM blocked_telegram b WHERE b.tg_id=u.tg_id)
            """)
        last_summary = None
        while True:
            job = claim_delivery()
            if job is not None:
                await deliver_onboarding(client, job)
                await asyncio.sleep(0.2)
                continue
            with transaction() as conn:
                summary = tuple(conn.execute("""
                    SELECT COUNT(*), COALESCE(SUM(t.memo_sent),0), COALESCE(SUM(t.application_pinned),0),
                           COUNT(CASE WHEN t.attempts<? AND (t.memo_sent=0 OR t.application_pinned=0)
                                      THEN 1 END)
                    FROM telegram_onboarding t
                    WHERE NOT EXISTS (SELECT 1 FROM blocked_telegram b WHERE b.tg_id=t.chat_id)
                """, (MAX_DELIVERY_ATTEMPTS,)).fetchone())
            if summary != last_summary:
                total, sent, pinned, pending = summary
                print(f"Main Telegram onboarding: total={total} memo={sent} pinned={pinned} pending={pending}",
                      flush=True)
                last_summary = summary
            await asyncio.sleep(10)

    async def configure():
        async with httpx.AsyncClient(timeout=10) as client:
            for delay in (2, 5, 12, 20):
                await asyncio.sleep(delay)
                try:
                    webhook = await telegram(client, "getWebhookInfo")
                    current = webhook.get("url")
                    if current and current != endpoint:
                        print("Main Telegram: existing external webhook retained", flush=True)
                        return
                    allowed = webhook.get("allowed_updates") or []
                    updates = list(dict.fromkeys([*allowed, "message", "callback_query"]))
                    if not current or updates != allowed:
                        await telegram(client, "setWebhook", url=endpoint, secret_token=secret, allowed_updates=updates)
                    commands = await telegram(client, "getMyCommands")
                    remaining_commands = [row for row in commands if row.get("command") != "app"]
                    if remaining_commands != commands:
                        await telegram(client, "setMyCommands", commands=remaining_commands)
                    print("Main Telegram: application button webhook ready", flush=True)
                    break
                except TELEGRAM_ERRORS:
                    continue
            else:
                print("Main Telegram: application button setup could not be confirmed", flush=True)
                return
            await run_onboarding(client)

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
