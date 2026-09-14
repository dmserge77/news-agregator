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
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
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
# Адрес живого сайта (это же значение используется и в data.js)
SITE_URL = "https://dmserge77.github.io/news-agregator/ai/data.js"
# Сколько раз пытаться скачать data.js (GitHub Pages кэширует ответы на 10 мин)
FETCH_ATTEMPTS = 3


def now_msk():
    """Текущее время по Москве (UTC+3)."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)


def read_last_build():
    """Определяет время последней сборки.

    Читаем с живого сайта — это единственный источник, который показывает,
    что реально видят посетители. Локальный dist/ai/data.js намеренно НЕ
    используется: он остаётся от прошлого запуска collector.py и может быть
    на много часов старше того, что уже опубликовано. На этом сторож уже
    один раз ошибся — увидел локальные 18:38 вместо онлайн 00:48.

    Возвращает (datetime | None, описание проблемы | None).
    """
    last_error = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            # Параметр ?nocache= нужен, чтобы обойти кэш страницы (max-age=600):
            # иначе сторож может увидеть старый ответ и зря дёрнуть сборку.
            url = f"{SITE_URL}?nocache={int(time.time())}"
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; news-aggregator-watchdog)",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            })
            with urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            m = re.search(r'"updated"\s*:\s*"([^"]+)"', text)
            if m:
                return datetime.strptime(m.group(1), "%d.%m.%Y, %H:%M:%S"), None
            last_error = "в ответе нет поля updated"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
        if attempt < FETCH_ATTEMPTS:
            time.sleep(5 * attempt)

    print(f"  ! не удалось прочитать время с сайта: {last_error}")
    return None, last_error


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
    with urlopen(req, timeout=30) as resp:
        return resp.status


def main():
    now = now_msk()
    print(f"Сторож: сейчас {now.strftime('%d.%m.%Y %H:%M')} МСК")

    last, read_error = read_last_build()

    if last is None:
        # Не смогли узнать время сборки. Это НЕ повод бездействовать:
        # раньше сторож в такой ситуации молча выходил, и получалось, что
        # «прочитать не удалось» = «всё хорошо». Теперь перезапускаем сборку.
        print("  ! время последней сборки неизвестно — на всякий случай перезапускаю сборку")
        request_build("не удалось прочитать время сборки")
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
    request_build(f"данные устарели на {int(age.total_seconds() // 60)} мин")


def request_build(reason):
    """Дёргает workflow_dispatch. Печатает результат, не роняя сторож."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("  ! нет GITHUB_TOKEN — перезапуск невозможен")
        return False
    try:
        status = trigger_build(token)
        print(f"  -> сборка запрошена (HTTP {status}); причина: {reason}")
        return True
    except HTTPError as e:
        # 403/404 — чаще всего мало прав у токена (нужен actions: write)
        print(f"  ! GitHub отказал ({e.code}): {reason}")
        if e.code in (401, 403, 404):
            print("      проверьте, что у workflow есть permissions: actions: write")
        return False
    except URLError as e:
        print(f"  ! сеть недоступна ({e.reason}) — причина: {reason}")
        return False
    except Exception as e:
        print(f"  ! не удалось запросить сборку: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    main()
