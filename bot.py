#!/usr/bin/env python3
"""Telegram-бот с доступом по инвайт-токенам и отчётами по выбранному Jira-юзеру."""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

import postman_conv
import report
import store

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

TZ = ZoneInfo("Asia/Yekaterinburg")
API = f"https://api.telegram.org/bot{report.TG_TOKEN}"


def tg_api(method: str, **payload):
    resp = requests.post(f"{API}/{method}", json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(data)
    return data.get("result")


def reply(chat_id: str, text: str) -> None:
    report.send_telegram(text, chat_id=chat_id)


def reply_markup(chat_id: str, text: str, keyboard: list[list[dict]]) -> None:
    tg_api(
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup={"inline_keyboard": keyboard},
    )


def team_help_block() -> str:
    cfg = store.get_schedule_config()
    team_t = cfg.get("team_time", "12:00")
    return (
        "<b>Команды (teams)</b>\n"
        "/create_team \"Название\" — создать команду\n"
        "/add_team Имя из Jira — добавить участника\n"
        "/sum_team — отчёт по команде (today / yesterday / дата)\n"
        "/list_teams — список ваших команд\n"
        "/delete_team — удалить команду\n"
        f"/team_notify on — включить автоотчёт команды ({team_t} ЕКБ)\n"
        "/team_notify off — выключить автоотчёт команды\n"
        f"Автоотчёт команды: Пн–Пт в {team_t} ЕКБ (если не выключен)"
    )


def help_text(chat_id: str) -> str:
    cfg = store.get_schedule_config()
    p_t = cfg.get("personal_time", "11:30")
    t_t = cfg.get("team_time", "12:00")
    lines = [
        "<b>Команды</b>",
        "/sum — отчёт за предыдущий рабочий день",
        "/sum today — за сегодня",
        "/sum yesterday — за вчера",
        "/sum 2026-07-22 — за дату",
        "/sum_user Имя — отчёт по любому Jira-юзеру (по умолчанию вчера)",
        "/sum_user \"Имя\" today — за сегодня",
        "/changename — сменить Jira-пользователя для статистики",
        f"/notify on — включить личный автоотчёт ({p_t} ЕКБ)",
        "/notify off — выключить личный автоотчёт",
        "/help — этот список",
        "/start — статус / начать привязку",
        "",
        "Также можно просто вставить <b>curl / postman request</b> — бот сам переделает в чистый запрос.",
    ]
    if store.can_create_team(chat_id):
        lines.extend(["", team_help_block()])
    if store.is_admin(chat_id):
        lines.extend(
            [
                "",
                "<b>Админ</b>",
                "/add_user Имя — создать инвайт-токен",
                "/list_users — пользователи и токены",
                "/give_cmd chat_id — выдать право создавать команды",
            ]
        )
    u = store.get_user(chat_id)
    if u and u.get("jira_display_name"):
        lines.extend(
            [
                "",
                f"Сейчас смотришь: <b>{report.html_escape(u['jira_display_name'])}</b>",
            ]
        )
    lines.append(f"\nАвтоотчёт: Пн–Пт в {p_t} ЕКБ (личный), {t_t} ЕКБ (команды).")
    return "\n".join(lines)


def next_weekday_at(now: datetime, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= candidate:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def next_scheduled_run(now: datetime) -> datetime:
    cfg = store.get_schedule_config()
    try:
        h, m = [int(x) for x in cfg.get("personal_time", "11:30").split(":")[:2]]
    except Exception:
        h, m = 11, 30
    return next_weekday_at(now, h, m)


def next_team_scheduled_run(now: datetime) -> datetime:
    cfg = store.get_schedule_config()
    try:
        h, m = [int(x) for x in cfg.get("team_time", "12:00").split(":")[:2]]
    except Exception:
        h, m = 12, 0
    return next_weekday_at(now, h, m)


def send_personal_auto_reports() -> None:
    for chat_id, user in store.list_ready_users():
        if not store.personal_notify_enabled(user):
            continue
        try:
            day, text = report.generate_report_text(
                account_id=user["jira_account_id"],
                display_name=user.get("jira_display_name") or "Сотрудник",
                period_note="предыдущий рабочий день",
                andrey_mode=bool(user.get("andrey_mode")),
            )
            reply(chat_id, text)
            log.info("Автоотчёт %s → %s", day, chat_id)
        except Exception:
            log.exception("Автоотчёт для %s", chat_id)
            try:
                reply(chat_id, "⚠️ Не удалось сформировать автоотчёт.")
            except Exception:
                log.exception("Не удалось отправить ошибку")


def send_team_auto_reports() -> None:
    for team in store.list_all_teams():
        owner = team.get("owner_chat_id")
        if not owner:
            continue
        if not store.team_notify_enabled(team):
            continue
        try:
            day = report.send_team_report(
                str(owner),
                None,
                team_name=team.get("name") or "Команда",
                members=team.get("members") or [],
                period_note="предыдущий рабочий день",
            )
            log.info("Автоотчёт команды %s → %s (%s)", team.get("id"), owner, day)
        except Exception:
            log.exception("Автоотчёт команды %s", team.get("id"))
            try:
                reply(str(owner), "⚠️ Не удалось сформировать автоотчёт команды.")
            except Exception:
                log.exception("Не удалось отправить ошибку команды")


def scheduler_loop(stop: threading.Event) -> None:
    log.info("Планировщик запущен (динамическое время из WebApp)")
    last_personal: date | None = None
    last_team: date | None = None
    while not stop.is_set():
        now = datetime.now(TZ)
        personal_t = next_scheduled_run(now)
        team_t = next_team_scheduled_run(now)
        next_t = min(personal_t, team_t)
        wait_s = max(1.0, (next_t - now).total_seconds())
        log.info(
            "Следующие: личный=%s команда=%s",
            personal_t.isoformat(),
            team_t.isoformat(),
        )
        if stop.wait(timeout=min(60.0, wait_s)):
            break
        now = datetime.now(TZ)
        if now.weekday() >= 5:
            continue
        cfg = store.get_schedule_config()
        try:
            ph, pm = [int(x) for x in cfg.get("personal_time", "11:30").split(":")[:2]]
        except Exception:
            ph, pm = 11, 30
        try:
            th, tm = [int(x) for x in cfg.get("team_time", "12:00").split(":")[:2]]
        except Exception:
            th, tm = 12, 0

        p_start = now.replace(hour=ph, minute=pm, second=0, microsecond=0)
        if p_start <= now < p_start + timedelta(minutes=2) and last_personal != now.date():
            send_personal_auto_reports()
            last_personal = now.date()
        t_start = now.replace(hour=th, minute=tm, second=0, microsecond=0)
        if t_start <= now < t_start + timedelta(minutes=2) and last_team != now.date():
            send_team_auto_reports()
            last_team = now.date()


def parse_sum_day(args: list[str]) -> tuple[date, str]:
    today = datetime.now(TZ).date()
    if not args:
        return report.previous_working_day(today), "предыдущий рабочий день"
    token = args[0].lower()
    if token in {"today", "сегодня"}:
        return today, "сегодня"
    if token in {"yesterday", "вчера"}:
        return today - timedelta(days=1), "вчера"
    return date.fromisoformat(args[0]), "выбранный день"


def handle_sum(chat_id: str, args: list[str]) -> None:
    user = store.get_user(chat_id)
    if not user or not user.get("jira_account_id"):
        reply(chat_id, "Сначала привяжи Jira-имя через /start или /changename")
        return
    reply(chat_id, "⏳ Обрабатываю…")
    try:
        day, note = parse_sum_day(args)
        _, text = report.generate_report_text(
            day,
            account_id=user["jira_account_id"],
            display_name=user.get("jira_display_name") or "Сотрудник",
            period_note=note,
            andrey_mode=bool(user.get("andrey_mode")),
        )
        reply(chat_id, text)
    except Exception as exc:
        log.exception("/sum failed")
        reply(
            chat_id,
            f"⚠️ Ошибка при формировании отчёта:\n<code>{report.html_escape(str(exc))}</code>",
        )


def parse_sum_user_args(args: list[str]) -> tuple[str, str]:
    """Вернуть (имя, day_token). day_token по умолчанию yesterday."""
    if not args:
        return "", "yesterday"
    joined = " ".join(args).strip()
    name = ""
    rest: list[str] = []
    if joined[:1] in {'"', "'"}:
        q = joined[0]
        end = joined.find(q, 1)
        if end != -1:
            name = joined[1:end].strip()
            rest = joined[end + 1 :].strip().split()
        else:
            name = joined.strip(q).strip()
    else:
        day_tokens = {"today", "сегодня", "yesterday", "вчера"}
        if len(args) >= 2:
            last = args[-1]
            is_day = last.lower() in day_tokens
            if not is_day:
                try:
                    date.fromisoformat(last)
                    is_day = True
                except ValueError:
                    is_day = False
            if is_day:
                name = " ".join(args[:-1]).strip()
                rest = [last]
            else:
                name = joined
        else:
            name = joined
    day_token = rest[0] if rest else "yesterday"
    return name, day_token


def run_sum_user_report(
    chat_id: str,
    account_id: str,
    display_name: str,
    day_token: str,
) -> None:
    reply(chat_id, "⏳ Формирую отчёт…")
    try:
        today = datetime.now(TZ).date()
        t = (day_token or "yesterday").lower().strip()
        if t in {"default", "", "yesterday", "вчера"}:
            day, note = today - timedelta(days=1), "вчера"
        elif t in {"today", "сегодня"}:
            day, note = today, "сегодня"
        else:
            day, note = date.fromisoformat(day_token), "выбранный день"
        _, text = report.generate_report_text(
            day,
            account_id=account_id,
            display_name=display_name,
            period_note=note,
            andrey_mode=False,
        )
        reply(chat_id, text)
    except Exception as exc:
        log.exception("/sum_user failed")
        reply(
            chat_id,
            f"⚠️ Ошибка отчёта:\n<code>{report.html_escape(str(exc))}</code>",
        )


def handle_sum_user(chat_id: str, args: list[str]) -> None:
    name, day_token = parse_sum_user_args(args)
    if not name:
        reply(
            chat_id,
            'Формат: <code>/sum_user "Имя из Jira"</code>\n'
            'или <code>/sum_user "Имя" today</code> / <code>yesterday</code> / <code>YYYY-MM-DD</code>\n'
            "По умолчанию — вчера.",
        )
        return
    try:
        users = report.lookup_jira_users(name)
    except Exception as exc:
        log.exception("sum_user lookup")
        reply(chat_id, f"⚠️ Ошибка Jira: <code>{report.html_escape(str(exc))}</code>")
        return
    if not users:
        reply(chat_id, f"❌ В Jira не найден пользователь «{report.html_escape(name)}»")
        return

    exact = [u for u in users if u.display_name.lower() == name.lower()]
    if len(exact) == 1:
        u = exact[0]
        threading.Thread(
            target=run_sum_user_report,
            args=(chat_id, u.account_id, u.display_name, day_token),
            daemon=True,
        ).start()
        return
    if len(users) == 1:
        u = users[0]
        threading.Thread(
            target=run_sum_user_report,
            args=(chat_id, u.account_id, u.display_name, day_token),
            daemon=True,
        ).start()
        return

    # несколько совпадений — кнопки
    candidates = [
        {"account_id": u.account_id, "display_name": u.display_name}
        for u in (exact if len(exact) > 1 else users)[:10]
    ]
    store.set_pending_sum_user(chat_id, day_token, candidates)
    keyboard = [
        [{"text": c["display_name"][:64], "callback_data": f"sumuser:{i}"}]
        for i, c in enumerate(candidates)
    ]
    reply_markup(chat_id, "Найдено несколько пользователей. Выбери нужного:", keyboard)


def bind_jira_name(chat_id: str, name: str) -> None:
    try:
        jira_user = report.resolve_jira_user(name)
    except ValueError as exc:
        reply(chat_id, f"❌ {report.html_escape(str(exc))}\nПопробуй ещё раз.")
        return
    except Exception as exc:
        log.exception("jira lookup")
        reply(chat_id, f"⚠️ Ошибка Jira: <code>{report.html_escape(str(exc))}</code>")
        return

    store.set_jira_profile(chat_id, jira_user.display_name, jira_user.account_id)
    reply(
        chat_id,
        "✅ Всё ок.\n"
        f"Jira-пользователь: <b>{report.html_escape(jira_user.display_name)}</b>\n\n"
        + help_text(chat_id),
    )


def handle_start(chat_id: str) -> None:
    if store.is_admin(chat_id):
        store.ensure_admin()
        user = store.get_user(chat_id) or {}
        if user.get("jira_account_id"):
            reply(chat_id, "Ты админ, доступ есть.\n\n" + help_text(chat_id))
            return
        store.set_state(chat_id, "awaiting_jira_name")
        reply(
            chat_id,
            "Ты админ. Для отчётов укажи <b>имя из Jira</b> "
            "(как в display name), например: <code>Тимофей Зеленский</code>",
        )
        return

    user = store.get_user(chat_id)
    if user and user.get("authorized") and user.get("jira_account_id"):
        reply(chat_id, "Снова привет!\n\n" + help_text(chat_id))
        return
    if user and user.get("authorized") and not user.get("jira_account_id"):
        store.set_state(chat_id, "awaiting_jira_name")
        reply(
            chat_id,
            "Токен уже принят. Введи <b>имя из Jira</b> для статистики.",
        )
        return

    store.set_state(chat_id, "awaiting_token")
    store.begin_awaiting_token(chat_id)
    reply(chat_id, "Доступ закрыт. Пришли <b>инвайт-токен</b> от админа.")


def handle_add_user(chat_id: str, args: list[str]) -> None:
    if not store.is_admin(chat_id):
        return  # чужим молчим
    if not args:
        reply(chat_id, "Формат: <code>/add_user ИмяПользователя</code>")
        return
    label = " ".join(args).strip()
    token = store.create_invite(label, chat_id)
    reply(
        chat_id,
        f"Инвайт для <b>{report.html_escape(label)}</b>:\n"
        f"<code>{token}</code>\n\n"
        "Передай этот токен пользователю. Он пишет боту /start и вставляет токен.",
    )


def handle_list_users(chat_id: str) -> None:
    if not store.is_admin(chat_id):
        return
    lines = ["<b>Пользователи</b>"]
    for cid, u in store.load()["users"].items():
        role = u.get("role", "?")
        name = u.get("jira_display_name") or "—"
        auth = "ok" if u.get("authorized") else "no"
        team_right = "cmd" if u.get("can_create_team") or cid == store.ADMIN_CHAT_ID else "-"
        lines.append(
            f"• <code>{cid}</code> [{role}/{team_right}] {report.html_escape(name)} ({auth})"
        )
    invites = store.list_invites_brief()
    if invites:
        lines.append("\n<b>Инвайты</b>")
        lines.extend(invites)
    reply(chat_id, "\n".join(lines))


def parse_team_name(args: list[str]) -> str:
    raw = " ".join(args).strip()
    if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
        return raw[1:-1].strip()
    return raw


def day_token_from_args(args: list[str]) -> str:
    if not args:
        return "default"
    token = args[0].lower()
    if token in {"today", "сегодня"}:
        return "today"
    if token in {"yesterday", "вчера"}:
        return "yesterday"
    return args[0]


def parse_day_token(token: str) -> tuple[date, str]:
    today = datetime.now(TZ).date()
    t = (token or "default").lower()
    if t in {"default", ""}:
        return report.previous_working_day(today), "предыдущий рабочий день"
    if t in {"today", "сегодня"}:
        return today, "сегодня"
    if t in {"yesterday", "вчера"}:
        return today - timedelta(days=1), "вчера"
    return date.fromisoformat(token), "выбранный день"


def team_buttons(teams: list[dict], prefix: str, day_token: str | None = None) -> list[list[dict]]:
    rows = []
    for t in teams:
        tid = t["id"]
        label = t.get("name") or tid
        if day_token is not None:
            cb = f"{prefix}:{tid}:{day_token}"
        else:
            cb = f"{prefix}:{tid}"
        rows.append([{"text": label[:64], "callback_data": cb[:64]}])
    return rows


def handle_give_cmd(chat_id: str, args: list[str]) -> None:
    if not store.is_admin(chat_id):
        return
    if not args:
        reply(chat_id, "Формат: <code>/give_cmd telegram_chat_id</code>")
        return
    target = args[0].strip()
    if not target.isdigit():
        reply(chat_id, "chat_id должен быть числом (Telegram user id).")
        return
    store.grant_create_team(target)
    reply(chat_id, f"✅ Право на создание команд выдано <code>{target}</code>")
    try:
        reply(
            target,
            "Вам выдали право на создание команды\n\n" + team_help_block(),
        )
    except Exception:
        log.exception("notify give_cmd target=%s", target)
        reply(chat_id, "⚠️ Право выдано, но уведомить пользователя не удалось (нет чата с ботом).")
    try:
        cmds = list(BASE_BOT_COMMANDS) + list(TEAM_BOT_COMMANDS)
        tg_api(
            "setMyCommands",
            commands=cmds,
            scope={"type": "chat", "chat_id": int(target)},
        )
    except Exception:
        log.exception("setMyCommands after give_cmd %s", target)


def handle_create_team(chat_id: str, args: list[str]) -> None:
    if not store.can_create_team(chat_id):
        reply(chat_id, "Нет права создавать команды. Попроси админа: /give_cmd")
        return
    name = parse_team_name(args)
    if not name:
        reply(chat_id, 'Формат: <code>/create_team "Название команды"</code>')
        return
    team = store.create_team(chat_id, name)
    reply(
        chat_id,
        f"✅ Команда <b>{report.html_escape(team['name'])}</b> создана.\n"
        f"Добавить участников: <code>/add_team Имя из Jira</code>",
    )


def add_member_to_team(chat_id: str, team_id: str, jira_name: str) -> None:
    try:
        jira_user = report.resolve_jira_user(jira_name)
    except ValueError as exc:
        reply(chat_id, f"❌ {report.html_escape(str(exc))}\nПопробуй ещё раз.")
        return
    except Exception as exc:
        log.exception("jira lookup for team")
        reply(chat_id, f"⚠️ Ошибка Jira: <code>{report.html_escape(str(exc))}</code>")
        return

    ok, msg, team = store.add_team_member(
        team_id, jira_user.account_id, jira_user.display_name
    )
    if not team:
        reply(chat_id, f"❌ {msg}")
        return
    if not ok:
        reply(
            chat_id,
            f"ℹ️ {report.html_escape(msg)}\n\n"
            f"<b>{report.html_escape(team.get('name') or '')}</b>\n"
            f"{report.html_escape(store.format_team_members(team))}",
        )
        return
    store.set_pending_team(chat_id, None, state=None)
    reply(
        chat_id,
        f"✅ Добавлен: <b>{report.html_escape(jira_user.display_name)}</b>\n\n"
        f"<b>Команда «{report.html_escape(team.get('name') or '')}»</b>:\n"
        f"{report.html_escape(store.format_team_members(team))}\n\n"
        "Можно добавить ещё: <code>/add_team Имя</code>",
    )


def handle_add_team(chat_id: str, args: list[str]) -> None:
    if not store.can_create_team(chat_id):
        reply(chat_id, "Нет права на команды.")
        return
    teams = store.list_teams_by_owner(chat_id)
    if not teams:
        reply(chat_id, 'Сначала создай команду: <code>/create_team "Название"</code>')
        return
    name = " ".join(args).strip()
    if len(teams) == 1:
        team_id = teams[0]["id"]
        if name:
            add_member_to_team(chat_id, team_id, name)
        else:
            store.set_pending_team(chat_id, team_id, state="awaiting_add_team_name")
            reply(
                chat_id,
                f"Команда <b>{report.html_escape(teams[0].get('name') or '')}</b>.\n"
                "Пришли <b>имя из Jira</b> для добавления.",
            )
        return
    # несколько команд — кнопки выбора
    if name:
        store.set_pending_add_name(chat_id, name)
    else:
        store.set_pending_add_name(chat_id, None)
    reply_markup(
        chat_id,
        "Выбери команду для добавления участника:",
        team_buttons(teams, "team:add"),
    )


def handle_sum_team(chat_id: str, args: list[str]) -> None:
    if not store.can_create_team(chat_id):
        reply(chat_id, "Нет права на команды.")
        return
    teams = store.list_teams_by_owner(chat_id)
    if not teams:
        reply(chat_id, 'Сначала создай команду: <code>/create_team "Название"</code>')
        return
    day_token = day_token_from_args(args)
    if len(teams) == 1:
        threading.Thread(
            target=run_sum_team,
            args=(chat_id, teams[0]["id"], day_token),
            daemon=True,
        ).start()
        return
    reply_markup(
        chat_id,
        "Выбери команду для отчёта:",
        team_buttons(teams, "team:sum", day_token),
    )


def run_sum_team(chat_id: str, team_id: str, day_token: str) -> None:
    team = store.get_team(team_id)
    if not team or str(team.get("owner_chat_id")) != str(chat_id):
        reply(chat_id, "Команда не найдена.")
        return
    reply(chat_id, "⏳ Формирую отчёт команды…")
    try:
        day, note = parse_day_token(day_token)
        report.send_team_report(
            chat_id,
            day,
            team_name=team.get("name") or "Команда",
            members=team.get("members") or [],
            period_note=note,
        )
    except Exception as exc:
        log.exception("/sum_team failed")
        reply(
            chat_id,
            f"⚠️ Ошибка отчёта команды:\n<code>{report.html_escape(str(exc))}</code>",
        )


def handle_list_teams(chat_id: str) -> None:
    if not store.can_create_team(chat_id):
        reply(chat_id, "Нет права на команды.")
        return
    teams = store.list_teams_by_owner(chat_id)
    if not teams:
        reply(chat_id, 'Команд нет. Создай: <code>/create_team "Название"</code>')
        return
    lines = ["<b>Ваши команды</b>"]
    for t in teams:
        notify = "вкл" if store.team_notify_enabled(t) else "выкл"
        lines.append(
            f"\n<b>{report.html_escape(t.get('name') or t['id'])}</b> "
            f"(уведы: {notify})"
        )
        lines.append(report.html_escape(store.format_team_members(t)))
    reply(chat_id, "\n".join(lines))


def parse_on_off(args: list[str]) -> bool | None:
    if not args:
        return None
    arg = args[0].lower().strip()
    if arg in {"on", "1", "вкл"}:
        return True
    if arg in {"off", "0", "выкл"}:
        return False
    return None


def handle_notify(chat_id: str, args: list[str]) -> None:
    enabled = parse_on_off(args)
    if enabled is None:
        reply(chat_id, "Формат: <code>/notify on</code> или <code>/notify off</code>")
        return
    store.set_personal_notify(chat_id, enabled)
    cfg = store.get_schedule_config()
    p_t = cfg.get("personal_time", "11:30")
    if enabled:
        reply(chat_id, f"Личный автоотчёт ({p_t} ЕКБ): <b>вкл</b>")
    else:
        reply(chat_id, f"Личный автоотчёт ({p_t} ЕКБ): <b>выкл</b>")


def apply_team_notify(chat_id: str, team_id: str, enabled: bool) -> None:
    ok, name = store.set_team_notify(team_id, chat_id, enabled)
    if not ok:
        reply(chat_id, f"❌ {report.html_escape(name)}")
        return
    cfg = store.get_schedule_config()
    t_t = cfg.get("team_time", "12:00")
    state = "вкл" if enabled else "выкл"
    reply(
        chat_id,
        f"Автоотчёт команды <b>{report.html_escape(name)}</b> ({t_t} ЕКБ): <b>{state}</b>",
    )


def handle_team_notify(chat_id: str, args: list[str]) -> None:
    if not store.can_create_team(chat_id):
        reply(chat_id, "Нет права на команды.")
        return
    enabled = parse_on_off(args)
    if enabled is None:
        reply(chat_id, "Формат: <code>/team_notify on</code> или <code>/team_notify off</code>")
        return
    teams = store.list_teams_by_owner(chat_id)
    if not teams:
        reply(chat_id, 'Команд нет. Создай: <code>/create_team "Название"</code>')
        return
    if len(teams) == 1:
        apply_team_notify(chat_id, teams[0]["id"], enabled)
        return
    flag = "on" if enabled else "off"
    reply_markup(
        chat_id,
        f"Выбери команду, чтобы {'включить' if enabled else 'выключить'} автоотчёт:",
        team_buttons(teams, "team:notify", flag),
    )


def apply_delete_team(chat_id: str, team_id: str) -> None:
    ok, name = store.delete_team(team_id, chat_id)
    if not ok:
        reply(chat_id, f"❌ {report.html_escape(name)}")
        return
    reply(chat_id, f"🗑 Команда <b>{report.html_escape(name)}</b> удалена.")


def handle_delete_team(chat_id: str) -> None:
    if not store.can_create_team(chat_id):
        reply(chat_id, "Нет права на команды.")
        return
    teams = store.list_teams_by_owner(chat_id)
    if not teams:
        reply(chat_id, "Команд нет.")
        return
    if len(teams) == 1:
        apply_delete_team(chat_id, teams[0]["id"])
        return
    reply_markup(
        chat_id,
        "Выбери команду для удаления:",
        team_buttons(teams, "team:del"),
    )


def handle_callback_query(cq: dict) -> None:
    try:
        cq_id = cq.get("id")
        data = (cq.get("data") or "").strip()
        from_user = cq.get("from") or {}
        chat_id = str(from_user.get("id", ""))
        if not cq_id or not chat_id:
            return
        tg_api("answerCallbackQuery", callback_query_id=cq_id)

        # /sum_user выбор пользователя
        if data.startswith("sumuser:"):
            if not (store.is_ready(chat_id) or store.is_admin(chat_id) or store.can_create_team(chat_id)):
                # всё равно пускаем авторизованных
                user = store.get_user(chat_id)
                if not (user and user.get("authorized")) and not store.is_admin(chat_id):
                    return
            try:
                idx = int(data.split(":", 1)[1])
            except ValueError:
                return
            pending = store.get_pending_sum_user(chat_id)
            if not pending:
                reply(chat_id, "Выбор устарел. Снова /sum_user")
                return
            candidates = pending.get("candidates") or []
            if idx < 0 or idx >= len(candidates):
                reply(chat_id, "Неверный выбор.")
                return
            chosen = candidates[idx]
            day_token = pending.get("day_token") or "yesterday"
            store.pop_pending_sum_user(chat_id)
            threading.Thread(
                target=run_sum_user_report,
                args=(
                    chat_id,
                    chosen["account_id"],
                    chosen.get("display_name") or "Сотрудник",
                    day_token,
                ),
                daemon=True,
            ).start()
            return

        if not store.can_create_team(chat_id):
            return

        parts = data.split(":")
        # team:add:<team_id>  OR  team:sum:<team_id>:<day_token>
        if len(parts) < 3 or parts[0] != "team":
            return
        action, team_id = parts[1], parts[2]
        team = store.get_team(team_id)
        if not team or str(team.get("owner_chat_id")) != chat_id:
            reply(chat_id, "Команда не найдена или чужая.")
            return

        if action == "add":
            pending_name = store.pop_pending_add_name(chat_id)
            if pending_name:
                add_member_to_team(chat_id, team_id, pending_name)
            else:
                store.set_pending_team(chat_id, team_id, state="awaiting_add_team_name")
                reply(
                    chat_id,
                    f"Команда <b>{report.html_escape(team.get('name') or '')}</b>.\n"
                    "Пришли <b>имя из Jira</b> для добавления.",
                )
            return

        if action == "sum":
            day_token = parts[3] if len(parts) > 3 else "default"
            threading.Thread(
                target=run_sum_team,
                args=(chat_id, team_id, day_token),
                daemon=True,
            ).start()
            return

        if action == "del":
            apply_delete_team(chat_id, team_id)
            return

        if action == "notify":
            flag = parts[3] if len(parts) > 3 else "off"
            apply_team_notify(chat_id, team_id, flag in {"on", "1", "вкл"})
            return
    except Exception:
        log.exception("handle_callback_query")


def try_postman_convert(chat_id: str, text: str) -> bool:
    """Если текст похож на postman/curl — конвертируем и отвечаем. Возвращает True если обработано."""
    if not postman_conv.looks_like_postman_request(text):
        return False
    try:
        req = postman_conv.parse_postman_request(text)
        if not req.url:
            return False
        try:
            tg_api(
                "sendMessage",
                chat_id=chat_id,
                text=postman_conv.format_for_telegram(req),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            log.exception("reply postman converted")
    except Exception as exc:
        log.exception("postman convert")
        try:
            reply(
                chat_id,
                f"⚠️ Ошибка парсинга запроса:\n<code>{report.html_escape(str(exc))}</code>",
            )
        except Exception:
            log.exception("reply postman error")
    return True


def handle_plain_text(chat_id: str, text: str, user: dict | None) -> None:
    state = (user or {}).get("state")
    if state == "awaiting_token":
        ok, msg = store.redeem_invite(text, chat_id)
        if not ok:
            reply(chat_id, f"❌ {msg}")
            return
        reply(
            chat_id,
            "Токен принят ✅\nТеперь введи <b>имя из Jira</b> "
            "(display name), по которому смотреть статистику.",
        )
        return
    if state in {"awaiting_jira_name", "awaiting_changename"}:
        bind_jira_name(chat_id, text)
        return
    if state == "awaiting_add_team_name":
        team_id = (user or {}).get("pending_team_id")
        if not team_id:
            store.set_state(chat_id, None)
            reply(chat_id, "Команда не выбрана. Снова /add_team")
            return
        add_member_to_team(chat_id, team_id, text)
        return
    # авто-детект postman/curl — доступно всем авторизованным
    if (user and user.get("authorized")) or store.is_admin(chat_id):
        if try_postman_convert(chat_id, text):
            return
    # авторизованный без команды — подсказка
    if store.is_ready(chat_id):
        reply(chat_id, "Не понял. Смотри /help")


def handle_message(msg: dict) -> None:
    # Сообщения, вставленные через inline-режим (via @jirasumbot), не обрабатываем повторно.
    if msg.get("via_bot"):
        return

    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    text = (msg.get("text") or "").strip()
    if not text or not chat_id:
        return

    user = store.get_user(chat_id)
    parts = text.split()
    raw_cmd = parts[0]
    cmd = raw_cmd.split("@", 1)[0].lower()
    args = parts[1:]
    is_command = raw_cmd.startswith("/")

    # --- закрытость ---
    if store.is_admin(chat_id):
        store.ensure_admin()
        user = store.get_user(chat_id)
    elif not user or not user.get("authorized"):
        # посторонним отвечаем только на /start или если ждём токен
        if cmd == "/start":
            handle_start(chat_id)
            return
        if user and user.get("state") == "awaiting_token" and not is_command:
            handle_plain_text(chat_id, text, user)
            return
        log.info("Игнор постороннего chat_id=%s", chat_id)
        return

    # --- команды ---
    if cmd == "/start":
        handle_start(chat_id)
        return
    if cmd == "/help":
        if store.is_ready(chat_id) or store.is_admin(chat_id):
            reply(chat_id, help_text(chat_id))
        else:
            reply(chat_id, "Сначала заверши привязку (/start).")
        return
    if cmd == "/add_user":
        handle_add_user(chat_id, args)
        return
    if cmd == "/list_users":
        handle_list_users(chat_id)
        return
    if cmd == "/give_cmd":
        handle_give_cmd(chat_id, args)
        return
    if cmd == "/create_team":
        handle_create_team(chat_id, args)
        return
    if cmd == "/add_team":
        handle_add_team(chat_id, args)
        return
    if cmd == "/sum_team":
        handle_sum_team(chat_id, args)
        return
    if cmd == "/list_teams":
        handle_list_teams(chat_id)
        return
    if cmd == "/delete_team":
        handle_delete_team(chat_id)
        return
    if cmd == "/team_notify":
        handle_team_notify(chat_id, args)
        return
    if cmd == "/notify":
        handle_notify(chat_id, args)
        return
    if cmd == "/webapp":
        reply_markup(
            chat_id,
            "🚀 <b>Панель управления Jira Daily Report</b>\n\n"
            "Выбор времени (барабан револьвера), отчеты, команды и токены:",
            [[{"text": "⚡ Открыть WebApp", "web_app": {"url": "https://jirasumbot.duckdns.org"}}]],
        )
        return
    if cmd == "/changename":
        if not (user and user.get("authorized")) and not store.is_admin(chat_id):
            return
        store.set_state(chat_id, "awaiting_changename")
        current = (user or {}).get("jira_display_name") or "—"
        reply(
            chat_id,
            f"Текущее имя: <b>{report.html_escape(current)}</b>\n"
            "Пришли новое <b>имя из Jira</b>.",
        )
        return
    if cmd == "/sum":
        if not store.is_ready(chat_id):
            reply(chat_id, "Сначала укажи Jira-имя (/start или /changename).")
            return
        threading.Thread(
            target=handle_sum, args=(chat_id, args), daemon=True
        ).start()
        return
    if cmd == "/sum_user":
        if not ((user and user.get("authorized")) or store.is_admin(chat_id)):
            return
        handle_sum_user(chat_id, args)
        return
    if cmd == "/andreymode":
        # скрытая команда — не светим в /help
        if not (store.is_ready(chat_id) or store.is_admin(chat_id)):
            return
        arg = (args[0].lower() if args else "").strip()
        if arg not in {"on", "off", "1", "0", "вкл", "выкл"}:
            reply(chat_id, "Формат: <code>/andreymode on</code> или <code>/andreymode off</code>")
            return
        enabled = arg in {"on", "1", "вкл"}
        store.set_andrey_mode(chat_id, enabled)
        if enabled:
            reply(chat_id, "Andrey mode: <b>ON</b>")
        else:
            reply(chat_id, "Andrey mode: <b>OFF</b>")
        return

    if is_command:
        if store.is_ready(chat_id) or store.is_admin(chat_id):
            reply(chat_id, "Неизвестная команда. /help")
        return

    handle_plain_text(chat_id, text, user)


def handle_inline_query(inline_query: dict) -> None:
    """
    Telegram inline mode (`@bot ...`) присылает update.inline_query.
    Мы конвертим текст из inline_query.query в готовый curl.
    """
    try:
        inline_query_id = inline_query.get("id")
        query_text = (inline_query.get("query") or "").strip()
        from_user = inline_query.get("from") or {}
        user_id = str(from_user.get("id", ""))
        if not inline_query_id or not query_text or not user_id:
            return

        user = store.get_user(user_id)
        if not ((user and user.get("authorized")) or store.is_admin(user_id)):
            # Не показываем результаты, чтобы не светить функциональность
            tg_api(
                "answerInlineQuery",
                inline_query_id=inline_query_id,
                results=[],
                cache_time=0,
                is_personal=True,
            )
            return

        if not postman_conv.looks_like_postman_request(query_text):
            tg_api(
                "answerInlineQuery",
                inline_query_id=inline_query_id,
                results=[],
                cache_time=0,
                is_personal=True,
            )
            return

        req = postman_conv.parse_postman_request(query_text)
        if not req.url:
            tg_api(
                "answerInlineQuery",
                inline_query_id=inline_query_id,
                results=[],
                cache_time=0,
                is_personal=True,
            )
            return

        curl = postman_conv.build_curl(req) or ""
        if not curl:
            tg_api(
                "answerInlineQuery",
                inline_query_id=inline_query_id,
                results=[],
                cache_time=0,
                is_personal=True,
            )
            return

        # Inline-ответы чувствительны к размеру текста — подрежем, чтобы не падать.
        if len(curl) > 3500:
            curl = curl[:3497] + "..."

        tg_api(
            "answerInlineQuery",
            inline_query_id=inline_query_id,
            results=[
                {
                    "type": "article",
                    "id": "postman_curl",
                    "title": "Postman → curl",
                    "input_message_content": {
                        "message_text": curl,
                    },
                }
            ],
            cache_time=0,
            is_personal=True,
        )
    except Exception:
        log.exception("handle_inline_query")


def _cmd(command: str, description: str) -> dict:
    return {"command": command, "description": description[:256]}


BASE_BOT_COMMANDS = [
    _cmd("start", "Статус / начать привязку"),
    _cmd("webapp", "📱 Открыть WebApp админку"),
    _cmd("help", "Список команд"),
    _cmd("sum", "Личный отчёт (today/yesterday/дата)"),
    _cmd("sum_user", "Отчёт по любому Jira-пользователю"),
    _cmd("changename", "Сменить Jira-имя для статистики"),
    _cmd("notify", "Личный автоотчёт: on/off"),
]

TEAM_BOT_COMMANDS = [
    _cmd("create_team", "Создать команду"),
    _cmd("add_team", "Добавить участника в команду"),
    _cmd("sum_team", "Отчёт по команде"),
    _cmd("list_teams", "Список ваших команд"),
    _cmd("delete_team", "Удалить команду"),
    _cmd("team_notify", "Автоотчёт команды: on/off"),
]

ADMIN_BOT_COMMANDS = [
    _cmd("add_user", "Создать инвайт-токен"),
    _cmd("list_users", "Пользователи и токены"),
    _cmd("give_cmd", "Выдать право создавать команды"),
]


def register_bot_commands() -> None:
    """Меню команд при нажатии / в чате с ботом и WebApp-кнопка меню."""
    try:
        tg_api(
            "setChatMenuButton",
            menu_button={
                "type": "web_app",
                "text": "📱 WebApp",
                "web_app": {"url": "https://jirasumbot.duckdns.org"},
            },
        )
        log.info("Chat menu button установлен на https://jirasumbot.duckdns.org")
    except Exception:
        log.exception("setChatMenuButton failed")

    tg_api("setMyCommands", commands=BASE_BOT_COMMANDS)
    # персональные меню по чатам
    for chat_id, user in store.load().get("users", {}).items():
        cmds = list(BASE_BOT_COMMANDS)
        if store.is_admin(chat_id) or user.get("can_create_team"):
            cmds.extend(TEAM_BOT_COMMANDS)
        if store.is_admin(chat_id):
            cmds.extend(ADMIN_BOT_COMMANDS)
        try:
            tg_api(
                "setMyCommands",
                commands=cmds,
                scope={"type": "chat", "chat_id": int(chat_id)},
            )
        except Exception:
            log.exception("setMyCommands for %s", chat_id)
    log.info("Меню команд Telegram обновлено")


def poll_loop(stop: threading.Event) -> None:
    try:
        tg_api("deleteWebhook", drop_pending_updates=False)
    except Exception:
        log.exception("deleteWebhook")
    try:
        register_bot_commands()
    except Exception:
        log.exception("register_bot_commands")

    offset = None
    log.info("Бот слушает. admin=%s", store.ADMIN_CHAT_ID)
    while not stop.is_set():
        try:
            updates = tg_api(
                "getUpdates",
                offset=offset,
                timeout=50,
                allowed_updates=["message", "inline_query", "callback_query"],
            )
        except requests.RequestException:
            log.exception("getUpdates network error")
            stop.wait(timeout=3)
            continue
        except Exception:
            log.exception("getUpdates error")
            stop.wait(timeout=3)
            continue

        for upd in updates or []:
            offset = upd["update_id"] + 1
            try:
                if upd.get("callback_query"):
                    handle_callback_query(upd["callback_query"])
                    continue
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    handle_message(msg)
                elif upd.get("inline_query"):
                    handle_inline_query(upd.get("inline_query") or {})
            except Exception:
                log.error("handle update:\n%s", traceback.format_exc())


def main() -> None:
    report.require_env("TELEGRAM_BOT_TOKEN", "JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    store.ensure_admin()
    try:
        reply(
            store.ADMIN_CHAT_ID,
            "🤖 Бот перезапущен.\n"
            "Новое: меню команд по «/», /sum_user, безопасная нарезка длинных отчётов.",
        )
    except Exception:
        log.exception("startup notification")
    stop = threading.Event()
    try:
        import api_server

        api_srv = api_server.run_api_server(host="0.0.0.0", port=8085)
        threading.Thread(target=api_srv.serve_forever, daemon=True).start()
        log.info("API сервер WebApp запущен на 0.0.0.0:8085")
    except Exception:
        log.exception("Не удалось запустить API сервер WebApp")

    threading.Thread(target=scheduler_loop, args=(stop,), daemon=True).start()
    try:
        poll_loop(stop)
    except KeyboardInterrupt:
        stop.set()
        log.info("Остановка")


if __name__ == "__main__":
    main()
