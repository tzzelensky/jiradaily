#!/usr/bin/env python3
"""Jira → Telegram отчёты по выбранному пользователю."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo(os.getenv("TZ", "Asia/Yekaterinburg"))
JIRA_BASE = os.getenv("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_TOKEN = os.getenv("JIRA_API_TOKEN", "")
ACCOUNT_ID = os.getenv("JIRA_ACCOUNT_ID", "")
DISPLAY_NAME = os.getenv("JIRA_DISPLAY_NAME", "Сотрудник")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


@dataclass(frozen=True)
class IssueRow:
    key: str
    summary: str
    status: str
    url: str
    comment_text: str | None = None


@dataclass(frozen=True)
class JiraUser:
    account_id: str
    display_name: str
    email: str | None = None


def previous_working_day(today: date) -> date:
    if today.weekday() == 0:
        return today - timedelta(days=3)
    return today - timedelta(days=1)


def day_bounds(day: date) -> tuple[str, str]:
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def require_env(*names: str) -> None:
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise RuntimeError(f"Нет переменных в .env: {', '.join(missing)}")


def jira_auth() -> tuple[str, str]:
    require_env("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")
    return JIRA_EMAIL, JIRA_TOKEN


def lookup_jira_users(query: str, max_results: int = 20) -> list[JiraUser]:
    """Поиск пользователей Jira по display name / email / username."""
    auth = jira_auth()
    url = f"{JIRA_BASE}/rest/api/3/user/search"
    resp = requests.get(
        url,
        params={"query": query, "maxResults": max_results},
        auth=auth,
        headers={"Accept": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    users: list[JiraUser] = []
    for item in resp.json() or []:
        account_id = item.get("accountId")
        display = (item.get("displayName") or "").strip()
        if not account_id or not display:
            continue
        if item.get("accountType") and item.get("accountType") != "atlassian":
            continue
        users.append(
            JiraUser(
                account_id=account_id,
                display_name=display,
                email=item.get("emailAddress"),
            )
        )
    return users


def resolve_jira_user(name: str) -> JiraUser:
    """Найти одного пользователя по имени. Кидает ValueError при неоднозначности."""
    name = name.strip()
    if not name:
        raise ValueError("Пустое имя")
    users = lookup_jira_users(name)
    if not users:
        raise ValueError(f"В Jira не найден пользователь «{name}»")

    exact = [u for u in users if u.display_name.lower() == name.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        listed = ", ".join(u.display_name for u in exact[:5])
        raise ValueError(f"Несколько точных совпадений: {listed}")

    if len(users) == 1:
        return users[0]

    listed = "\n".join(f"• {u.display_name}" for u in users[:8])
    raise ValueError(
        f"Найдено несколько пользователей. Уточните имя:\n{listed}"
    )


def jira_search(jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
    auth = jira_auth()
    url = f"{JIRA_BASE}/rest/api/3/search/jql"
    payload: dict[str, Any] = {
        "jql": jql,
        "maxResults": 50,
        "fields": fields
        or ["summary", "status", "issuetype", "created", "updated", "assignee"],
    }
    issues: list[dict[str, Any]] = []
    next_token: str | None = None
    while True:
        body = dict(payload)
        if next_token:
            body["nextPageToken"] = next_token
        resp = requests.post(
            url,
            json=body,
            headers={"Accept": "application/json"},
            auth=auth,
            timeout=60,
        )
        if resp.status_code == 404:
            return jira_search_legacy(jql, fields)
        resp.raise_for_status()
        data = resp.json()
        issues.extend(data.get("issues") or [])
        if data.get("isLast", True):
            break
        next_token = data.get("nextPageToken")
        if not next_token:
            break
    return issues


def jira_search_legacy(jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
    auth = jira_auth()
    url = f"{JIRA_BASE}/rest/api/3/search"
    params: dict[str, Any] = {
        "jql": jql,
        "maxResults": 50,
        "fields": ",".join(
            fields
            or ["summary", "status", "issuetype", "created", "updated", "assignee"]
        ),
        "startAt": 0,
    }
    issues: list[dict[str, Any]] = []
    while True:
        resp = requests.get(url, params=params, auth=auth, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("issues") or []
        issues.extend(batch)
        start = data.get("startAt", 0) + len(batch)
        total = data.get("total", 0)
        if start >= total or not batch:
            break
        params["startAt"] = start
    return issues


def to_rows(issues: list[dict[str, Any]]) -> list[IssueRow]:
    rows: list[IssueRow] = []
    for issue in issues:
        key = issue.get("key", "?")
        fields = issue.get("fields") or {}
        summary = (fields.get("summary") or "").strip()
        status = ((fields.get("status") or {}).get("name")) or "?"
        rows.append(
            IssueRow(
                key=key,
                summary=summary,
                status=status,
                url=f"{JIRA_BASE}/browse/{key}",
            )
        )
    return rows


def _parse_jira_dt(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    # 2026-07-22T17:44:28.028+0500
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _adf_or_text_to_plain(body: Any) -> str:
    if body is None:
        return ""
    if isinstance(body, str):
        return body.strip()
    if isinstance(body, dict):
        # Atlassian Document Format — вытаскиваем текст рекурсивно
        parts: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "text" and node.get("text"):
                    parts.append(str(node["text"]))
                for child in node.get("content") or []:
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(body)
        return " ".join(parts).strip()
    return str(body).strip()


def list_issue_comments(issue_key: str) -> list[dict[str, Any]]:
    auth = jira_auth()
    url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment"
    start_at = 0
    comments: list[dict[str, Any]] = []
    while True:
        resp = requests.get(
            url,
            params={"startAt": start_at, "maxResults": 100},
            auth=auth,
            headers={"Accept": "application/json"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("comments") or []
        comments.extend(batch)
        start_at += len(batch)
        total = data.get("total", start_at)
        if start_at >= total or not batch:
            break
    return comments


def fetch_comments_for_day(day: date, account_id: str) -> list[IssueRow]:
    """Комментарии автора за день: ищем кандидатов и фильтруем по дате/автору."""
    start, end = day_bounds(day)
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=TZ)
    day_end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=TZ)

    # Шире окно updated — commenter в Jira часто не совпадает с календарным updated
    lookback = (day - timedelta(days=14)).isoformat()
    candidates = jira_search(
        f'commenter = "{account_id}" AND updated >= "{lookback}" ORDER BY updated DESC',
        fields=["summary", "status"],
    )
    # fallback: задачи, обновлённые в выбранный день (на случай если commenter пустой)
    if not candidates:
        candidates = jira_search(
            f'updated >= "{start}" AND updated < "{end}" ORDER BY updated DESC',
            fields=["summary", "status"],
        )

    rows: list[IssueRow] = []
    seen: set[tuple[str, str]] = set()
    for issue in candidates[:80]:
        key = issue.get("key") or "?"
        fields = issue.get("fields") or {}
        summary = (fields.get("summary") or "").strip()
        status = ((fields.get("status") or {}).get("name")) or "?"
        try:
            comments = list_issue_comments(key)
        except Exception:
            continue
        for c in comments:
            author = c.get("author") or {}
            if author.get("accountId") != account_id:
                continue
            created = _parse_jira_dt(c.get("created") or "")
            if not created:
                continue
            created_local = created.astimezone(TZ)
            if not (day_start <= created_local < day_end):
                continue
            text = _adf_or_text_to_plain(c.get("body"))
            if len(text) > 280:
                text = text[:277] + "…"
            marker = (key, c.get("id") or text)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(
                IssueRow(
                    key=key,
                    summary=summary,
                    status=status,
                    url=f"{JIRA_BASE}/browse/{key}",
                    comment_text=text or "(без текста)",
                )
            )
    return rows


def fetch_activity(day: date, account_id: str) -> dict[str, list[IssueRow]]:
    start, end = day_bounds(day)
    aid = account_id
    created = jira_search(
        f'reporter = "{aid}" AND created >= "{start}" AND created < "{end}" '
        f"ORDER BY created ASC"
    )
    transitioned = jira_search(
        f'status CHANGED BY "{aid}" DURING ("{start}", "{end}") '
        f"ORDER BY updated DESC"
    )
    commented = fetch_comments_for_day(day, aid)
    return {
        "created": to_rows(created),
        "transitioned": to_rows(transitioned),
        "commented": commented,
    }


def html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def format_section(title: str, rows: list[IssueRow]) -> str:
    if not rows:
        return f"<b>{html_escape(title)}</b>\n— нет\n"
    lines = [f"<b>{html_escape(title)}</b>"]
    for r in rows:
        line = (
            f'• <a href="{html_escape(r.url)}">{html_escape(r.key)}</a> — '
            f"{html_escape(r.summary)} "
            f"[<i>{html_escape(r.status)}</i>]"
        )
        lines.append(line)
        if r.comment_text:
            lines.append(f"  💬 {html_escape(r.comment_text)}")
    return "\n".join(lines) + "\n"


def _andrey_day_word(period_note: str, day: date) -> str:
    note = (period_note or "").lower()
    if "сегодня" in note:
        return "Сегодня"
    if "вчера" in note or "предыдущий рабочий" in note:
        return "Вчера"
    return f"За {day.strftime('%d.%m.%Y')}"


def build_andrey_report(
    day: date,
    activity: dict[str, list[IssueRow]],
    period_note: str = "предыдущий рабочий день",
) -> str:
    """Короткий дейлик в стиле Андрея — только список задач."""
    merged: dict[str, IssueRow] = {}
    for row in activity.get("created", []) + activity.get("transitioned", []):
        merged[row.key] = row
    day_word = _andrey_day_word(period_note, day)
    lines = [
        "Привет, Андрей, дела хорошо. "
        f"{day_word} делал задачки:"
    ]
    if not merged:
        lines.append("— задач не нашёл")
    else:
        for r in merged.values():
            lines.append(
                f'• <a href="{html_escape(r.url)}">{html_escape(r.key)}</a> — '
                f"{html_escape(r.summary)}"
            )
    lines.append("")
    lines.append("Вопросов нет, спасибо тебе Андрей за прекрасный дейлик")
    return "\n".join(lines)


def build_report(
    day: date,
    activity: dict[str, list[IssueRow]],
    display_name: str,
    period_note: str = "выбранный день",
) -> str:
    day_s = day.strftime("%d.%m.%Y")
    header = (
        f"<b>Отчёт: {html_escape(display_name)}</b>\n"
        f"Период: <b>{day_s}</b> ({html_escape(period_note)})\n"
    )
    total = sum(len(v) for v in activity.values())
    if total == 0 and _is_sergey_chuykin(display_name):
        items = ["Jira", "Вопросики", "Встречи", "Ревью"]
        body = "\n".join(f"{i}. {html_escape(item)}" for i, item in enumerate(items, 1))
        return (header + "\n" + body).strip()
    parts = [
        header,
        format_section("Создал", activity["created"]),
        format_section("Сменил статус", activity["transitioned"]),
        format_section("Комментарии", activity["commented"]),
    ]
    if total == 0:
        parts.append("За этот день активности в Jira не найдено.")
    return "\n".join(parts).strip()


def split_telegram_html(text: str, max_len: int = 3500) -> list[str]:
    """Режет длинный HTML по строкам, чтобы не рвать теги посередине."""
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        piece = line if not current else current + "\n" + line
        if len(piece) <= max_len:
            current = piece
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(line) <= max_len:
            current = line
            continue
        # очень длинная строка без переносов — режем по лимиту
        start = 0
        while start < len(line):
            chunks.append(line[start : start + max_len])
            start += max_len
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]


def send_telegram(text: str, chat_id: str | None = None) -> None:
    require_env("TELEGRAM_BOT_TOKEN")
    target = chat_id or TG_CHAT
    if not target:
        raise RuntimeError("Не указан chat_id")
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    chunks = split_telegram_html(text, 3500)
    for chunk in chunks:
        resp = requests.post(
            url,
            json={
                "chat_id": target,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(f"Telegram error {resp.status_code}: {resp.text}")


def generate_report_text(
    day: date | None = None,
    *,
    account_id: str | None = None,
    display_name: str | None = None,
    period_note: str | None = None,
    andrey_mode: bool = False,
) -> tuple[date, str]:
    aid = account_id or ACCOUNT_ID
    name = display_name or DISPLAY_NAME
    if not aid:
        raise RuntimeError("Не задан Jira accountId")
    report_day = day or previous_working_day(datetime.now(TZ).date())
    note = period_note
    if note is None:
        note = (
            "предыдущий рабочий день"
            if day is None
            else "выбранный день"
        )
    activity = fetch_activity(report_day, aid)
    if andrey_mode:
        return report_day, build_andrey_report(report_day, activity, note)
    return report_day, build_report(report_day, activity, name, note)


_EMPTY_ACTIVITY_OVERRIDES: dict[str, list[str]] = {
    "сергей чуйкин": ["Jira", "Вопросики", "Встречи", "Ревью"],
    "sergey chuykin": ["Jira", "Вопросики", "Встречи", "Ревью"],
    "@sergey_chuykin": ["Jira", "Вопросики", "Встречи", "Ревью"],
    "sergey_chuykin": ["Jira", "Вопросики", "Встречи", "Ревью"],
}


def _is_sergey_chuykin(display_name: str) -> bool:
    n = (display_name or "").strip().lower()
    if not n:
        return False
    if n in _EMPTY_ACTIVITY_OVERRIDES:
        return True
    return "чуйкин" in n or "chuykin" in n or "sergey_chuykin" in n


def _empty_activity_block(display_name: str) -> str:
    if _is_sergey_chuykin(display_name):
        items = ["Jira", "Вопросики", "Встречи", "Ревью"]
        return "\n".join(f"   {i}. {html_escape(item)}" for i, item in enumerate(items, 1))
    return "   — нет активности"


def _member_tasks_block(
    activity: dict[str, list[IssueRow]],
    display_name: str = "",
) -> str:
    """Краткий блок задач участника для командного отчёта."""
    merged: dict[str, IssueRow] = {}
    for row in (
        activity.get("created", [])
        + activity.get("transitioned", [])
        + activity.get("commented", [])
    ):
        merged[row.key] = row
    if not merged:
        return _empty_activity_block(display_name)
    lines = []
    for r in merged.values():
        lines.append(
            f'   • <a href="{html_escape(r.url)}">{html_escape(r.key)}</a> — '
            f"{html_escape(r.summary)} "
            f"[<i>{html_escape(r.status)}</i>]"
        )
        if r.comment_text:
            lines.append(f"     💬 {html_escape(r.comment_text)}")
    return "\n".join(lines)


def _truncate_html_block(text: str, max_len: int = 3200) -> str:
    if len(text) <= max_len:
        return text
    cut = text.rfind("\n", 0, max_len)
    if cut > max_len // 3:
        return text[:cut] + "\n… [обрезано]"
    return text[: max_len - 16] + "\n… [обрезано]"


def generate_team_report_messages(
    day: date | None,
    *,
    team_name: str,
    members: list[dict[str, str]],
    period_note: str | None = None,
) -> tuple[date, list[str]]:
    """Командный отчёт — список сообщений (заголовок + по одному на участника)."""
    report_day = day or previous_working_day(datetime.now(TZ).date())
    note = period_note or (
        "предыдущий рабочий день" if day is None else "выбранный день"
    )
    day_s = report_day.strftime("%d.%m.%Y")
    header = (
        f"<b>Отчёт команды «{html_escape(team_name)}»</b> · "
        f"<b>{day_s}</b> ({html_escape(note)})"
    )
    if not members:
        return report_day, [header + "\n\nВ команде пока нет участников."]

    messages = [header]
    max_len = 3200
    for i, m in enumerate(members, 1):
        name = m.get("jira_display_name") or "Сотрудник"
        aid = m.get("jira_account_id") or ""
        block = f"<b>{i}. {html_escape(name)}:</b>"
        if not aid:
            block += "\n   — нет accountId"
        else:
            try:
                activity = fetch_activity(report_day, aid)
                block += "\n" + _member_tasks_block(activity, name)
            except Exception as exc:
                block += f"\n   ⚠️ ошибка: {html_escape(str(exc))}"
        if len(block) > max_len:
            block = _truncate_html_block(block, max_len)
        messages.append(block)
    return report_day, messages


def send_team_report(
    chat_id: str,
    day: date | None,
    *,
    team_name: str,
    members: list[dict[str, str]],
    period_note: str | None = None,
) -> date:
    """Отправить командный отчёт несколькими сообщениями (без разрыва HTML-тегов)."""
    report_day, messages = generate_team_report_messages(
        day,
        team_name=team_name,
        members=members,
        period_note=period_note,
    )
    for msg in messages:
        send_telegram(msg, chat_id=chat_id)
    return report_day


def generate_team_report_text(
    day: date | None,
    *,
    team_name: str,
    members: list[dict[str, str]],
    period_note: str | None = None,
) -> tuple[date, str]:
    """Совместимость: одна строка (не использовать для отправки в TG)."""
    report_day, messages = generate_team_report_messages(
        day,
        team_name=team_name,
        members=members,
        period_note=period_note,
    )
    return report_day, "\n\n".join(messages)


def send_test() -> None:
    now = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    send_telegram(
        f"✅ Бот на связи.\nТест отчёта Jira → Telegram\nВремя ЕКБ: <b>{now}</b>"
    )
    print("Тестовое сообщение отправлено в Telegram.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Jira daily report → Telegram")
    parser.add_argument("--test-tg", action="store_true")
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.test_tg:
        send_test()
        return

    now = datetime.now(TZ)
    today = now.date()
    if today.weekday() >= 5 and not args.force:
        print("Выходной — отчёт не отправляем.")
        return

    day = date.fromisoformat(args.date) if args.date else previous_working_day(today)
    report_day, text = generate_report_text(day)
    if args.dry_run:
        print(text)
        return
    send_telegram(text)
    print(f"Отчёт за {report_day.isoformat()} отправлен в Telegram.")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ""
        print(f"HTTP error: {exc}\n{body}", file=sys.stderr)
        sys.exit(1)
