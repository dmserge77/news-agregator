#!/usr/bin/env python3
"""
watchdog.py — сторож свежести новостей.

Проверяет, обновился ли сайт в текущем слоте расписания.
Если нет — перезапускает сборку через workflow_dispatch.

Запускается по расписанию GitHub Actions. Логика:
  1. Смотрим время последней сборки (из dist/ai/data.js).
  2. Определяем, в каком слоте мы находимся (слоты каждые 4 часа).
  3. Если сборка была в текущем слоте или позже — всё хорошо, выходим.
  4. Если нет — просим GitHub перезапустить сборку. При следующем
     запуске сторожа проверка повторится, пока данные не обновятся.

Запуск: python watchdog.py
Требует переменную окружения GITHUB_TOKEN (в Actions она есть всегда).
"""

import json
import os
import re
import sys
import ssl
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = "dmserge77/news-agregator"
WORKFLOW = "deploy.yml"
# Слоты расписания по МСК: 02, 06, 10, 14, 18, 22 — каждые 4 часа
SLOT_HOURS = [2, 6, 10, 14, 18, 22]
# Сколько ждать после начала слота, прежде чем считать данные устаревшими
GRACE_MINUTES = 90


def now_msk():
    """Текущее время по Москве (UTC+3)."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)


def read_last_build():
    """Определяет время последней сборки.

    Источники по приоритету:
      1. dist/ai/data.js — если сборка уже прошла (локальный запуск)
      2. online — живой сайт (в CI репозиторий чистый, файлов сборки нет)
      3. ai/news.json — накопитель, там нет времени сборки, но есть даты новостей
    """
    path = os.path.join(BASE_DIR, "dist", "ai", "data.js")
    if os.path.exists(path):
        ts = read_updated_from(path)
        if ts:
            return ts

    # Живой сайт — основной источник для CI
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = "https://dmserge77.github.io/news-agregator/ai/data.js"
        req = Request(url, headers={"User-Agent": "news-agregator-watchdog"})
        with urlopen(req, timeout=20, context=ctx) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        m = re.search(r'"updated"\s*:\s*"([^"]+)"', text)
        if m:
            return datetime.strptime(m.group(1), "%d.%m.%Y, %H:%M:%S")
    except Exception as e:
        print(f"  ! не удалось прочитать время с сайта: {e}")

    return None


def read_updated_from(path):
    """Читает "updated" из локального data.js."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r'"updated"\s*:\s*"([^"]+)"', text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%d.%m.%Y, %H:%M:%S")
    except ValueError:
        return None


def current_slot_start(now):
    """Возвращает начало текущего слота расписания."""
    for hour in reversed(SLOT_HOURS):
        if now.hour >= hour:
            start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            # Если слот только начался, даём сборке время отработать
            if (now - start) >= timedelta(minutes=GRACE_MINUTES):
                return start
            return None
    # До первого слота суток — берём последний слот вчера
    yesterday = now - timedelta(days=1)
    start = yesterday.replace(hour=SLOT_HOURS[-1], minute=0, second=0, microsecond=0)
    return start


def trigger_build(token):
    """Просит GitHub Actions перезапустить сборку."""
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    body = json.dumps({"ref": "main"}).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "news-agregator-watchdog",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urlopen(req, timeout=20, context=ctx) as resp:
        return resp.status


def main():
    now = now_msk()
    last = read_last_build()

    print(f"Сторож: сейчас {now.strftime('%d.%m.%Y %H:%M')} МСК")
    if last is None:
        print("  ! не удалось прочитать время последней сборки — пропускаю проверку")
        return
    print(f"  последняя сборка: {last.strftime('%d.%m.%Y %H:%M:%S')} МСК")

    slot = current_slot_start(now)
    if slot is None:
        print("  слот начался недавно, сборке нужно время — проверю позже")
        return
    print(f"  начало текущего слота: {slot.strftime('%d.%m.%Y %H:%M')} МСК")

    if last >= slot:
        print("  [OK] данные свежие, обновление не требуется")
        return

    age = now - last
    print(f"  [!] данные устарели на {int(age.total_seconds() // 60)} мин — перезапускаю сборку")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  ! нет GITHUB_TOKEN — перезапуск невозможен")
        return

    try:
        status = trigger_build(token)
        print(f"  -> сборка запрошена (HTTP {status})")
    except Exception as e:
        print(f"  ! не удалось запросить сборку: {e}")


if __name__ == "__main__":
    main()
