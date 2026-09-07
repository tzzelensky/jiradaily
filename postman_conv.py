#!/usr/bin/env python3
"""Конвертор Postman export (curl-style) → чистый запрос для Postman импорта."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class ParsedRequest:
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    query_params: dict[str, str] = field(default_factory=dict)


def looks_like_postman_request(text: str) -> bool:
    """
    Достаточно “узнать” запрос, чтобы попытаться конвертировать.
    В Telegram пользователи часто вставляют Postman curl с переносами и дублированием 'postman request'.
    """
    t = text.strip()
    if not t:
        return False

    has_url = re.search(r"https?://", t, flags=re.IGNORECASE) is not None
    has_header_flag = re.search(r"\s--header\s+", t, flags=re.IGNORECASE) is not None
    has_curl_or_postman = re.search(r"\b(curl|postman\s+request)\b", t, flags=re.IGNORECASE) is not None
    return has_url and (has_curl_or_postman or has_header_flag)


def parse_postman_request(text: str) -> ParsedRequest:
    req = ParsedRequest()

    # Нормализуем переносы вида: "... \\\n  --header '...'"
    cleaned = re.sub(r"\\\s*\r?\n\s*", " ", text).strip()
    # Часто в Windows/CLI переносят кавычки как ^"..." — убираем caret перед кавычкой.
    cleaned = re.sub(r"\^([\"'])", r"\1", cleaned)
    # Если в сообщении есть экранированные кавычки — максимально “отсклеим” их.
    cleaned = re.sub(r'\\(["\'])', r'\1', cleaned)

    # Убираем повторяющийся мусор: "postman request ... postman request ..."
    cleaned = re.sub(r"^(?:\s*(?:postman\s+request\s+|curl\s+)+)+", "", cleaned, flags=re.IGNORECASE)

    # URL: достаём первое вхождение http(s), даже если оно внутри кавычек/переносов.
    url_m = re.search(r"(https?://[^\s'\"\\]+)", cleaned, flags=re.IGNORECASE)
    if url_m:
        req.url = url_m.group(1)

    # Method (если указан)
    method_m = re.search(r"(?:-X|--request)\s+([A-Za-z]+)", cleaned, flags=re.IGNORECASE)
    if method_m:
        req.method = method_m.group(1).upper()

    # Headers: -H/--header 'k: v' / "-H/--header" k: v
    # Берём все вхождения.
    for m in re.finditer(
        r"(?:--header|-H)\s+((?:'[^']*'|\"[^\"]*\"|[^\s]+))",
        cleaned,
        flags=re.IGNORECASE,
    ):
        raw_val = m.group(1).strip()
        if (raw_val.startswith("'") and raw_val.endswith("'")) or (
            raw_val.startswith('"') and raw_val.endswith('"')
        ):
            raw_val = raw_val[1:-1]
        raw_val = raw_val.strip()
        if ":" not in raw_val:
            continue
        key, _, val = raw_val.partition(":")
        key = key.strip()
        val = val.strip()
        if key:
            req.headers[key] = val

    # Cookies: -b/--cookie "..."
    cookie_m = re.finditer(
        r"(?:--cookie|-b)\s+((?:'[^']*'|\"[^\"]*\"|[^\s]+))",
        cleaned,
        flags=re.IGNORECASE,
    )
    for m in cookie_m:
        raw_val = m.group(1).strip()
        if (raw_val.startswith("'") and raw_val.endswith("'")) or (
            raw_val.startswith('"') and raw_val.endswith('"')
        ):
            raw_val = raw_val[1:-1]
        cookie_val = raw_val.strip()
        if not cookie_val:
            continue
        if "Cookie" in req.headers and req.headers["Cookie"]:
            req.headers["Cookie"] = req.headers["Cookie"].rstrip() + "; " + cookie_val
        else:
            req.headers["Cookie"] = cookie_val

    # Body (если вдруг был)
    body_m = re.search(
        r"--data(?:-raw|-binary)?\s+((?:'[^']*'|\"[^\"]*\"|[^\s].*?))(?=\s+--|\s*$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if body_m:
        raw_body = body_m.group(1).strip()
        if (raw_body.startswith("'") and raw_body.endswith("'")) or (
            raw_body.startswith('"') and raw_body.endswith('"')
        ):
            raw_body = raw_body[1:-1]
        req.body = raw_body
        if req.method == "GET":
            req.method = "POST"

    # extract query params from URL
    if req.url:
        parsed = urlparse(req.url)
        if parsed.query:
            for pair in parsed.query.split("&"):
                if "=" in pair:
                    k, _, v = pair.partition("=")
                    req.query_params[k] = v
            req.url = req.url.split("?", 1)[0]

    return req


def _html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_for_telegram(req: ParsedRequest) -> str:
    curl = build_curl(req)
    if not curl:
        return "Не получилось собрать curl"
    # Держим сообщение в одном куске, чтобы не ломать HTML-теги.
    max_len = 3200
    if len(curl) > max_len:
        curl = curl[: max_len - 14] + "\n... [truncated]"
    return "<b>Готовый curl для Postman:</b>\n<pre>" + _html(curl) + "</pre>"


def build_curl(req: ParsedRequest) -> str:
    parts = ["curl"]
    if req.method != "GET":
        parts.append(f"-X {req.method}")

    url = req.url
    if req.query_params:
        qs = "&".join(f"{k}={v}" for k, v in req.query_params.items())
        url = f"{url}?{qs}"
    parts.append(f"'{url}'")

    for k, v in req.headers.items():
        parts.append(f"-H '{k}: {v}'")

    if req.body:
        escaped = req.body.replace("'", "'\\''")
        parts.append(f"-d '{escaped}'")

    return " \\\n  ".join(parts)
