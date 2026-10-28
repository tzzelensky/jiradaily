#!/usr/bin/env python3
"""HTTP API сервер для Telegram WebApp @jirasumbot."""

from __future__ import annotations

import collections
import json
import logging
import time
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import report
import store

log = logging.getLogger("api")

# Кольцевой буфер для логов
LOG_BUFFER: collections.deque = collections.deque(maxlen=200)


class BufferLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_BUFFER.append(
                {
                    "time": datetime.now(report.TZ).strftime("%H:%M:%S"),
                    "level": record.levelname,
                    "msg": msg,
                }
            )
        except Exception:
            pass


_buf_handler = BufferLogHandler()
_buf_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(_buf_handler)


def _send_json(handler: BaseHTTPRequestHandler, data: dict | list, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Telegram-User-Id")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    _send_json(handler, {"ok": False, "error": message}, status=status)


class WebAppApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        log.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Telegram-User-Id")
        self.end_headers()

    def _get_tg_id(self, query_params: dict) -> str:
        # Из заголовка или query-параметра или дефолт админ
        tg_id = self.headers.get("X-Telegram-User-Id") or ""
        if not tg_id:
            tg_list = query_params.get("tg_id")
            if tg_list:
                tg_id = tg_list[0]
        if not tg_id:
            tg_id = store.ADMIN_CHAT_ID
        return str(tg_id).strip()

    def _read_body(self) -> dict:
        content_len = int(self.headers.get("Content-Length") or 0)
        if content_len == 0:
            return {}
        raw = self.rfile.read(content_len)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # 1. Healthcheck
        if path == "/api/health":
            t0 = time.time()
            try:
                auth = report.jira_auth()
                resp = report.requests.get(
                    f"{report.JIRA_BASE}/rest/api/3/myself",
                    auth=auth,
                    headers={"Accept": "application/json"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                latency_ms = int((time.time() - t0) * 1000)
                _send_json(
                    self,
                    {
                        "ok": True,
                        "status": "connected",
                        "latency_ms": latency_ms,
                        "jira_base": report.JIRA_BASE,
                        "jira_email": report.JIRA_EMAIL,
                        "display_name": data.get("displayName"),
                        "account_id": data.get("accountId"),
                        "active": data.get("active"),
                    },
                )
            except Exception as exc:
                latency_ms = int((time.time() - t0) * 1000)
                _send_json(
                    self,
                    {
                        "ok": False,
                        "status": "error",
                        "latency_ms": latency_ms,
                        "error": str(exc),
                        "jira_base": report.JIRA_BASE,
                    },
                    status=500,
                )
            return

        # 2. Config & Schedule
        if path == "/api/config":
            cfg = store.get_schedule_config()
            _send_json(self, {"ok": True, "config": cfg})
            return

        # 3. Me
        if path == "/api/me":
            tg_id = self._get_tg_id(query)
            u = store.get_user(tg_id) or {}
            is_adm = store.is_admin(tg_id)
            _send_json(
                self,
                {
                    "ok": True,
                    "chat_id": tg_id,
                    "is_admin": is_adm,
                    "role": "admin" if is_adm else u.get("role", "user"),
                    "authorized": bool(u.get("authorized") or is_adm),
                    "jira_account_id": u.get("jira_account_id") or report.ACCOUNT_ID,
                    "jira_display_name": u.get("jira_display_name") or report.DISPLAY_NAME,
                    "andrey_mode": bool(u.get("andrey_mode")),
                    "can_create_team": store.can_create_team(tg_id),
                },
            )
            return

        # 4. Summary Preview
        if path == "/api/sum":
            date_str = (query.get("date") or [date.today().isoformat()])[0]
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                _send_error(self, f"Неверный формат даты: {date_str}")
                return

            tg_id = self._get_tg_id(query)
            user = store.get_user(tg_id) or {}
            account_id = (query.get("account_id") or [user.get("jira_account_id") or report.ACCOUNT_ID])[0]
            display_name = user.get("jira_display_name") or report.DISPLAY_NAME

            try:
                activity = report.fetch_activity(target_date, account_id)
                andrey = bool(user.get("andrey_mode"))
                _, raw_text = report.generate_report_text(
                    target_date,
                    account_id=account_id,
                    display_name=display_name,
                    period_note="выбранный день",
                    andrey_mode=andrey,
                )

                def _row_to_dict(r: report.IssueRow) -> dict:
                    return {
                        "key": r.key,
                        "summary": r.summary,
                        "status": r.status,
                        "url": r.url,
                        "comment_text": r.comment_text,
                    }

                created_rows = [_row_to_dict(r) for r in activity.get("created", [])]
                trans_rows = [_row_to_dict(r) for r in activity.get("transitioned", [])]
                comm_rows = [_row_to_dict(r) for r in activity.get("commented", [])]
                total = len(created_rows) + len(trans_rows) + len(comm_rows)

                _send_json(
                    self,
                    {
                        "ok": True,
                        "date": target_date.isoformat(),
                        "display_name": display_name,
                        "account_id": account_id,
                        "andrey_mode": andrey,
                        "total_count": total,
                        "created": created_rows,
                        "transitioned": trans_rows,
                        "commented": comm_rows,
                        "raw_text": raw_text,
                    },
                )
            except Exception as exc:
                log.exception("fetch_activity failed")
                _send_error(self, str(exc), status=500)
            return

        # 5. Teams list
        if path == "/api/teams":
            tg_id = self._get_tg_id(query)
            if store.is_admin(tg_id):
                teams = store.list_all_teams()
            else:
                teams = store.list_teams_by_owner(tg_id)
            _send_json(self, {"ok": True, "teams": teams})
            return

        # 6. Jira User Search (Autocomplete)
        if path == "/api/jira/search":
            q = (query.get("q") or [""])[0].strip()
            if not q:
                _send_json(self, {"ok": True, "users": []})
                return
            try:
                users = report.lookup_jira_users(q, max_results=10)
                _send_json(
                    self,
                    {
                        "ok": True,
                        "users": [
                            {
                                "account_id": u.account_id,
                                "display_name": u.display_name,
                                "email": u.email,
                            }
                            for u in users
                        ],
                    },
                )
            except Exception as exc:
                _send_error(self, str(exc), status=500)
            return

        # 7. Users list
        if path == "/api/users":
            users = store.list_all_users()
            _send_json(self, {"ok": True, "users": users})
            return

        # 8. Invites list
        if path == "/api/invites":
            invites = store.list_all_invites()
            _send_json(self, {"ok": True, "invites": invites})
            return

        # 9. Logs
        if path == "/api/logs":
            _send_json(self, {"ok": True, "logs": list(LOG_BUFFER)})
            return

        _send_error(self, f"Маршрут не найден: {path}", status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        body = self._read_body()

        # 1. Update Schedule Configuration
        if path == "/api/config":
            p_time = body.get("personal_time") or ""
            t_time = body.get("team_time") or ""
            new_cfg = store.set_schedule_config(p_time, t_time)
            log.info("График автоотчетов обновлен: personal=%s, team=%s", p_time, t_time)
            _send_json(self, {"ok": True, "config": new_cfg})
            return

        # 2. Dispatch / Send Personal Report to Telegram DM
        if path == "/api/sum/send":
            date_str = body.get("date") or date.today().isoformat()
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                _send_error(self, f"Неверная дата: {date_str}")
                return

            tg_id = body.get("chat_id") or self._get_tg_id(query)
            user = store.get_user(tg_id) or {}
            account_id = body.get("account_id") or user.get("jira_account_id") or report.ACCOUNT_ID
            display_name = user.get("jira_display_name") or report.DISPLAY_NAME

            try:
                _, text = report.generate_report_text(
                    target_date,
                    account_id=account_id,
                    display_name=display_name,
                    period_note="отправлено из WebApp",
                    andrey_mode=bool(user.get("andrey_mode")),
                )
                report.send_telegram(text, chat_id=tg_id)
                log.info("Отчёт отправлен в Telegram %s за %s", tg_id, target_date)
                _send_json(self, {"ok": True, "message": "Отчёт успешно отправлен в Telegram!"})
            except Exception as exc:
                log.exception("Ошибка отправки отчёта")
                _send_error(self, str(exc), status=500)
            return

        # 3. Create Team
        if path == "/api/teams":
            name = (body.get("name") or "").strip()
            if not name:
                _send_error(self, "Укажите название команды")
                return
            tg_id = body.get("owner_chat_id") or self._get_tg_id(query)
            team = store.create_team(tg_id, name)
            log.info("Создана команда %s (%s) владельцем %s", team["id"], name, tg_id)
            _send_json(self, {"ok": True, "team": team})
            return

        # 4. Add Team Member: /api/teams/<id>/members
        if path.startswith("/api/teams/") and path.endswith("/members"):
            parts = path.split("/")
            # /api/teams/<id>/members
            if len(parts) == 5:
                team_id = unquote(parts[3])
                aid = (body.get("jira_account_id") or "").strip()
                name = (body.get("jira_display_name") or "").strip()
                if not aid or not name:
                    _send_error(self, "Требуется jira_account_id и jira_display_name")
                    return
                ok, msg, team = store.add_team_member(team_id, aid, name)
                if not ok:
                    _send_error(self, msg)
                    return
                log.info("В команду %s добавлен %s (%s)", team_id, name, aid)
                _send_json(self, {"ok": True, "message": msg, "team": team})
                return

        # 5. Trigger Team Report to Owner DM: /api/teams/<id>/send
        if path.startswith("/api/teams/") and path.endswith("/send"):
            parts = path.split("/")
            if len(parts) == 5:
                team_id = unquote(parts[3])
                team = store.get_team(team_id)
                if not team:
                    _send_error(self, "Команда не найдена", status=404)
                    return
                owner_id = team.get("owner_chat_id") or self._get_tg_id(query)
                date_str = body.get("date")
                target_date = date.fromisoformat(date_str) if date_str else None
                try:
                    day = report.send_team_report(
                        str(owner_id),
                        target_date,
                        team_name=team.get("name") or "Команда",
                        members=team.get("members") or [],
                        period_note="отправлено из WebApp",
                    )
                    log.info("Отчёт команды %s отправлен в Telegram %s", team_id, owner_id)
                    _send_json(self, {"ok": True, "message": f"Отчёт за {day} отправлен в Telegram!"})
                except Exception as exc:
                    log.exception("send_team_report failed")
                    _send_error(self, str(exc), status=500)
                return

        # 6. Create Invite Token
        if path == "/api/invites":
            label = (body.get("label") or "WebApp invite").strip()
            tg_id = body.get("created_by") or self._get_tg_id(query)
            token = store.create_invite(label, tg_id)
            link = f"https://t.me/jirasumbot?start=inv_{token}"
            log.info("Создан инвайт-токен %s с меткой «%s»", token, label)
            _send_json(
                self,
                {
                    "ok": True,
                    "token": token,
                    "label": label,
                    "link": link,
                },
            )
            return

        _send_error(self, f"Маршрут не найден: {path}", status=404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # 1. Remove Team Member: /api/teams/<id>/members/<account_id>
        if "/members/" in path and path.startswith("/api/teams/"):
            parts = path.split("/")
            # /api/teams/<team_id>/members/<account_id>
            if len(parts) == 6:
                team_id = unquote(parts[3])
                account_id = unquote(parts[5])
                ok, msg, team = store.remove_team_member(team_id, account_id)
                if not ok:
                    _send_error(self, msg)
                    return
                log.info("Участник %s удален из команды %s", account_id, team_id)
                _send_json(self, {"ok": True, "message": msg, "team": team})
                return

        # 2. Delete Team: /api/teams/<id>
        if path.startswith("/api/teams/"):
            parts = path.split("/")
            if len(parts) == 4:
                team_id = unquote(parts[3])
                tg_id = self._get_tg_id(query)
                ok, msg = store.delete_team(team_id, tg_id)
                if not ok and not store.is_admin(tg_id):
                    _send_error(self, msg)
                    return
                if not ok and store.is_admin(tg_id):
                    # Админ может удалять любую команду
                    with store._LOCK:
                        data = store.load()
                        teams = data.setdefault("teams", {})
                        if team_id in teams:
                            del teams[team_id]
                            store.save(data)
                            ok = True
                            msg = team_id
                log.info("Удалена команда %s", team_id)
                _send_json(self, {"ok": True, "message": f"Команда {msg} удалена"})
                return

        _send_error(self, f"Маршрут не найден: {path}", status=404)


def run_api_server(host: str = "0.0.0.0", port: int = 8085) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), WebAppApiHandler)
    log.info("API сервер запущен на http://%s:%d", host, port)
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = run_api_server()
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        log.info("Остановка API сервера")
        s.server_close()
