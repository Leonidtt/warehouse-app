"""Telegram follow-up for equipment checkouts that cross midnight in Moscow."""

import asyncio
import logging
import re
import secrets
import time
from datetime import datetime, time as wall_time, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

MOSCOW = ZoneInfo('Europe/Moscow')
PLANS = {'keep': 'Оставил на руках', 'overnight': 'Сдам ночью'}
logger = logging.getLogger(__name__)


def init_return_reminders(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkout_return_reminders (
            checkout_id INTEGER PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            retry_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            sent INTEGER NOT NULL DEFAULT 0,
            plan TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS checkout_return_reminders_due
        ON checkout_return_reminders(retry_at, checkout_id)
        WHERE sent=0 AND plan IS NULL AND attempts<3
    """)


def queue_return_reminder(conn, checkout_id, taken_at):
    try:
        issued = datetime.fromisoformat(taken_at)
    except (TypeError, ValueError):
        return
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=timezone.utc)
    next_day = issued.astimezone(MOSCOW).date() + timedelta(days=1)
    due = datetime.combine(next_day, wall_time.min, MOSCOW)
    conn.execute(
        'INSERT INTO checkout_return_reminders(checkout_id, token, retry_at) VALUES(?,?,?)',
        (checkout_id, secrets.token_urlsafe(18), int(due.timestamp())),
    )


def claim_due_reminder(transaction, limited_recipient, now):
    with transaction() as conn:
        owner = limited_recipient(conn)
        row = conn.execute("""
            SELECT r.token, u.tg_id AS user_id, i.name,
                   CASE WHEN c.user_id < 0 THEN c.taken_for ELSE NULL END AS guest
            FROM checkout_return_reminders r
            JOIN checkouts c ON c.id=r.checkout_id AND c.returned_at IS NULL
            JOIN items i ON i.code=c.item_code AND i.kind='equipment' AND i.is_archived=0
            JOIN users u ON u.tg_id=CASE WHEN c.user_id > 0 THEN c.user_id ELSE c.giver_id END
                AND u.is_registered=1 AND u.role!='guest'
            WHERE r.sent=0 AND r.plan IS NULL AND r.attempts<3 AND r.retry_at<=?
                AND u.tg_id>0 AND (? IS NULL OR u.tg_id=?)
                AND NOT EXISTS (SELECT 1 FROM blocked_telegram b WHERE b.tg_id=u.tg_id)
            ORDER BY r.retry_at, c.id
            LIMIT 1
        """, (now, owner, owner)).fetchone()
        if row is not None:
            conn.execute("""
                UPDATE checkout_return_reminders
                SET attempts=attempts+1, retry_at=?
                WHERE token=?
            """, (now + 300, row['token']))
        return row


def complete_delivery(transaction, token, sent):
    with transaction() as conn:
        if sent:
            conn.execute('UPDATE checkout_return_reminders SET sent=1 WHERE token=?', (token,))
        else:
            conn.execute('UPDATE checkout_return_reminders SET attempts=3 WHERE token=?', (token,))


async def send_due_reminders(transaction, limited_recipient, client, bot_token, public_url, now=None):
    now = int(time.time()) if now is None else now
    for _ in range(20):
        row = await asyncio.to_thread(claim_due_reminder, transaction, limited_recipient, now)
        if row is None:
            return
        buttons = []
        for plan, label in PLANS.items():
            params = urlencode({'return_reminder': row['token'], 'return_plan': plan})
            buttons.append({'text': label, 'web_app': {'url': f'{public_url}/?{params}'}})
        if row['guest']:
            message = f'Гость {row["guest"][:150]} не вернул технику до полуночи: {row["name"][:200]}.'
        else:
            message = f'Ты не вернул технику до полуночи: {row["name"][:200]}. Оставил на руках или ночью сдашь?'
        try:
            response = await client.post(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                json={
                    'chat_id': row['user_id'],
                    'text': message,
                    'reply_markup': {'inline_keyboard': [buttons]},
                },
            )
            sent = response.is_success and response.json().get('ok') is True
        except (httpx.HTTPError, ValueError):
            continue
        if sent or response.status_code in (400, 401, 403):
            await asyncio.to_thread(complete_delivery, transaction, row['token'], sent)


class ReturnPlan(BaseModel):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{24}$')
    plan: Literal['keep', 'overnight']


def register_return_reminders(app, get_user, transaction, limited_recipient, bot_token, public_domain):
    @app.post('/api/checkout/return-plan')
    def record_return_plan(request: ReturnPlan, x_init_data: Optional[str] = Header(None)):
        user = get_user(x_init_data)
        with transaction() as conn:
            checkout = conn.execute("""
                SELECT c.item_code
                FROM checkout_return_reminders r
                JOIN checkouts c ON c.id=r.checkout_id AND c.returned_at IS NULL
                JOIN items i ON i.code=c.item_code AND i.is_archived=0
                WHERE r.token=? AND r.attempts>0 AND (CASE WHEN c.user_id > 0 THEN c.user_id ELSE c.giver_id END)=?
            """, (request.token, user['tg_id'])).fetchone()
            if checkout is None:
                raise HTTPException(404, 'Напоминание недоступно или выдача уже закрыта')
            conn.execute('UPDATE checkout_return_reminders SET plan=? WHERE token=?', (request.plan, request.token))
        return {'code': checkout['item_code'], 'plan': PLANS[request.plan]}

    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*\.[a-z0-9-]+', public_domain, re.I):
        return
    public_url = f'https://{public_domain}'
    worker = None

    async def run():
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            while True:
                try:
                    await send_due_reminders(transaction, limited_recipient, client, bot_token, public_url)
                except Exception:
                    logger.warning('Не удалось обработать очередь напоминаний о возврате')
                await asyncio.sleep(30)

    @app.on_event('startup')
    async def start():
        nonlocal worker
        worker = asyncio.create_task(run())

    @app.on_event('shutdown')
    async def stop():
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
