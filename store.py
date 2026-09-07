#!/usr/bin/env python3
"""Локальное хранилище пользователей и инвайт-токенов."""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STORE_PATH = ROOT / "users.json"
_LOCK = threading.Lock()

ADMIN_CHAT_ID = "404740026"


def _empty() -> dict[str, Any]:
    return {"invites": {}, "users": {}, "teams": {}}


def load() -> dict[str, Any]:
    if not STORE_PATH.exists():
        data = _empty()
        save(data)
        return data
    with STORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("invites", {})
    data.setdefault("users", {})
    data.setdefault("teams", {})
    return data


def save(data: dict[str, Any]) -> None:
    tmp = STORE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(STORE_PATH)


def ensure_admin() -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(ADMIN_CHAT_ID, {})
        user["role"] = "admin"
        user["authorized"] = True
        user["can_create_team"] = True
        # подтянуть дефолт из .env, если ещё не привязан Jira
        if not user.get("jira_account_id"):
            import os

            aid = os.getenv("JIRA_ACCOUNT_ID", "").strip()
            name = os.getenv("JIRA_DISPLAY_NAME", "").strip()
            if aid and name:
                user["jira_account_id"] = aid
                user["jira_display_name"] = name
                user["state"] = None
            else:
                user["state"] = user.get("state") or "awaiting_jira_name"
        save(data)


def begin_awaiting_token(chat_id: str) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user.setdefault("authorized", False)
        user["state"] = "awaiting_token"
        save(data)


def get_user(chat_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return load()["users"].get(str(chat_id))


def is_admin(chat_id: str) -> bool:
    return str(chat_id) == ADMIN_CHAT_ID


def is_ready(chat_id: str) -> bool:
    u = get_user(chat_id)
    return bool(u and u.get("authorized") and u.get("jira_account_id"))


def set_state(chat_id: str, state: str | None) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user["state"] = state
        save(data)


def create_invite(label: str, created_by: str) -> str:
    token = secrets.token_urlsafe(18)
    with _LOCK:
        data = load()
        data["invites"][token] = {
            "label": label,
            "created_by": str(created_by),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "used_by": None,
            "used_at": None,
        }
        save(data)
    return token


def redeem_invite(token: str, chat_id: str) -> tuple[bool, str]:
    token = token.strip()
    with _LOCK:
        data = load()
        invite = data["invites"].get(token)
        if not invite:
            return False, "Токен не найден."
        if invite.get("used_by") and invite["used_by"] != str(chat_id):
            return False, "Этот токен уже использован."
        invite["used_by"] = str(chat_id)
        invite["used_at"] = datetime.now(timezone.utc).isoformat()
        user = data["users"].setdefault(str(chat_id), {})
        if str(chat_id) == ADMIN_CHAT_ID:
            user["role"] = "admin"
        else:
            user["role"] = "user"
        user["authorized"] = True
        user["invite_token"] = token
        user["invite_label"] = invite.get("label")
        user["state"] = "awaiting_jira_name"
        save(data)
    return True, "Ок"


def set_jira_profile(chat_id: str, display_name: str, account_id: str) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user["jira_display_name"] = display_name
        user["jira_account_id"] = account_id
        user["authorized"] = True
        user["state"] = None
        if str(chat_id) == ADMIN_CHAT_ID:
            user["role"] = "admin"
        save(data)


def list_ready_users() -> list[tuple[str, dict[str, Any]]]:
    with _LOCK:
        data = load()
        out = []
        for cid, u in data["users"].items():
            if u.get("authorized") and u.get("jira_account_id"):
                out.append((cid, u))
        return out


def list_invites_brief() -> list[str]:
    with _LOCK:
        data = load()
        lines = []
        for token, inv in data["invites"].items():
            status = "использован" if inv.get("used_by") else "свободен"
            lines.append(f"• {inv.get('label')}: <code>{token}</code> ({status})")
        return lines


def set_andrey_mode(chat_id: str, enabled: bool) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user["andrey_mode"] = bool(enabled)
        save(data)


def is_andrey_mode(chat_id: str) -> bool:
    u = get_user(chat_id)
    return bool(u and u.get("andrey_mode"))


def can_create_team(chat_id: str) -> bool:
    if is_admin(chat_id):
        return True
    u = get_user(chat_id)
    return bool(u and u.get("can_create_team"))


def grant_create_team(chat_id: str) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user["can_create_team"] = True
        save(data)


def set_pending_team(chat_id: str, team_id: str | None, state: str | None = None) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        if team_id is None:
            user.pop("pending_team_id", None)
        else:
            user["pending_team_id"] = str(team_id)
        if state is not None:
            user["state"] = state
        save(data)


def set_pending_add_name(chat_id: str, name: str | None) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        if name is None:
            user.pop("pending_add_name", None)
        else:
            user["pending_add_name"] = name
        save(data)


def pop_pending_add_name(chat_id: str) -> str | None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        name = user.pop("pending_add_name", None)
        save(data)
        return name


def create_team(owner_chat_id: str, name: str) -> dict[str, Any]:
    name = name.strip()
    team_id = "t_" + secrets.token_hex(6)
    team = {
        "id": team_id,
        "name": name,
        "owner_chat_id": str(owner_chat_id),
        "members": [],
        "notify": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        data = load()
        data.setdefault("teams", {})
        data["teams"][team_id] = team
        save(data)
    return team


def get_team(team_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return load().get("teams", {}).get(str(team_id))


def list_teams_by_owner(owner_chat_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        data = load()
        out = []
        for team in data.get("teams", {}).values():
            if str(team.get("owner_chat_id")) == str(owner_chat_id):
                out.append(team)
        out.sort(key=lambda t: t.get("created_at") or "")
        return out


def list_all_teams() -> list[dict[str, Any]]:
    with _LOCK:
        return list(load().get("teams", {}).values())


def add_team_member(
    team_id: str,
    jira_account_id: str,
    jira_display_name: str,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Добавить Jira-участника в команду. Возвращает (ok, message, team)."""
    with _LOCK:
        data = load()
        team = data.get("teams", {}).get(str(team_id))
        if not team:
            return False, "Команда не найдена.", None
        members = team.setdefault("members", [])
        for m in members:
            if m.get("jira_account_id") == jira_account_id:
                return False, f"Уже в команде: {m.get('jira_display_name')}", team
        members.append(
            {
                "jira_account_id": jira_account_id,
                "jira_display_name": jira_display_name,
            }
        )
        save(data)
        return True, "Добавлен", team


def format_team_members(team: dict[str, Any]) -> str:
    members = team.get("members") or []
    if not members:
        return "Пока никого нет."
    lines = []
    for i, m in enumerate(members, 1):
        lines.append(f"{i}. {m.get('jira_display_name') or '—'}")
    return "\n".join(lines)


def delete_team(team_id: str, owner_chat_id: str) -> tuple[bool, str]:
    with _LOCK:
        data = load()
        teams = data.setdefault("teams", {})
        team = teams.get(str(team_id))
        if not team:
            return False, "Команда не найдена."
        if str(team.get("owner_chat_id")) != str(owner_chat_id):
            return False, "Это не твоя команда."
        name = team.get("name") or team_id
        del teams[str(team_id)]
        save(data)
        return True, name


def set_team_notify(team_id: str, owner_chat_id: str, enabled: bool) -> tuple[bool, str]:
    with _LOCK:
        data = load()
        team = data.get("teams", {}).get(str(team_id))
        if not team:
            return False, "Команда не найдена."
        if str(team.get("owner_chat_id")) != str(owner_chat_id):
            return False, "Это не твоя команда."
        team["notify"] = bool(enabled)
        save(data)
        return True, team.get("name") or team_id


def team_notify_enabled(team: dict[str, Any]) -> bool:
    return team.get("notify", True)


def set_personal_notify(chat_id: str, enabled: bool) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user["notify"] = bool(enabled)
        save(data)


def personal_notify_enabled(user: dict[str, Any] | None) -> bool:
    if not user:
        return True
    return user.get("notify", True)


def set_pending_sum_user(
    chat_id: str,
    day_token: str,
    candidates: list[dict[str, str]],
) -> None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        user["pending_sum_user"] = {
            "day_token": day_token,
            "candidates": candidates,
        }
        save(data)


def pop_pending_sum_user(chat_id: str) -> dict[str, Any] | None:
    with _LOCK:
        data = load()
        user = data["users"].setdefault(str(chat_id), {})
        pending = user.pop("pending_sum_user", None)
        save(data)
        return pending


def get_pending_sum_user(chat_id: str) -> dict[str, Any] | None:
    u = get_user(chat_id)
    if not u:
        return None
    return u.get("pending_sum_user")
