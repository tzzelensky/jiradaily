#!/usr/bin/env python3
"""Фоновый демон: ждёт 11:30 ЕКБ в будни и шлёт отчёт."""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

TZ = ZoneInfo("Asia/Yekaterinburg")
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
REPORT = ROOT / "report.py"


def next_run(now: datetime) -> datetime:
    """Следующий Пн–Пт 11:30 ЕКБ."""
    candidate = now.replace(hour=11, minute=30, second=0, microsecond=0)
    if now >= candidate:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:  # сб/вс
        candidate += timedelta(days=1)
    return candidate


def run_report() -> None:
    cmd = [str(PYTHON if PYTHON.exists() else sys.executable), str(REPORT)]
    print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] Запуск отчёта…", flush=True)
    result = subprocess.run(cmd, cwd=str(ROOT))
    print(
        f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] Код выхода: {result.returncode}",
        flush=True,
    )


def main() -> None:
    print("Демон Jira→Telegram запущен. Ожидание 11:30 ЕКБ (Пн–Пт).", flush=True)
    while True:
        now = datetime.now(TZ)
        target = next_run(now)
        wait_s = max(1, int((target - now).total_seconds()))
        print(
            f"Следующий запуск: {target:%Y-%m-%d %H:%M:%S %Z} "
            f"(через {wait_s // 3600}ч {(wait_s % 3600) // 60}м)",
            flush=True,
        )
        # спим кусками, чтобы процесс был «живым» и пережил сдвиг часов
        end = time.time() + wait_s
        while time.time() < end:
            time.sleep(min(60, end - time.time()))
        run_report()
        time.sleep(70)  # не запустить дважды в ту же минуту


if __name__ == "__main__":
    main()
