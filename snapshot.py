#!/usr/bin/env python3
"""
Снимок накопителя новостей и восстановление из него.

Зачем: накопители `<категория>/news.json` не попадают в git (см. .gitignore)
и живут только в кэше GitHub Actions. Кэш удаляется после 7 дней без обращений,
поэтому при долгом простое 90 дней истории обнуляются до последних 20–50
записей из лент. Снимок в репозитории это страхует.

Использование:
    python snapshot.py save                # снять снимок в _snapshots/
    python snapshot.py save --note "текст" # снимок с пометкой
    python snapshot.py restore <файл.gz>   # восстановить накопители
    python snapshot.py list                # показать снимки
"""
import gzip
import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(BASE_DIR, "_snapshots")

CATEGORIES = ["ai", "vibe", "agent", "platform", "design", "misc", "jobs", "orders"]


def cat_path(cat):
    return os.path.join(BASE_DIR, cat, "news.json")


def read_items(cat):
    try:
        with open(cat_path(cat), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def cmd_save(note=""):
    """Фаза 1 — читаем всё в память. Фаза 2 — пишем один файл."""
    data = {}
    counts = {}
    total = 0
    for cat in CATEGORIES:
        items = read_items(cat)
        data[cat] = items
        counts[cat] = len(items)
        total += len(items)

    if total == 0:
        print("! Накопители пусты — снимок не имеет смысла, отменяю.")
        return 1

    payload = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "total": total,
        "counts": counts,
        "items": data,
    }

    os.makedirs(SNAP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out = os.path.join(SNAP_DIR, f"news-{stamp}.json.gz")

    # mtime=0 — чтобы одинаковые данные давали одинаковый файл
    with gzip.GzipFile(out, "wb", mtime=0) as gz:
        gz.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    raw = sum(os.path.getsize(cat_path(c)) for c in CATEGORIES if os.path.exists(cat_path(c)))
    print(f"[OK] снимок: {os.path.relpath(out, BASE_DIR)}")
    print(f"     записей: {total}   было {raw / 1024:.0f} КБ -> стало {os.path.getsize(out) / 1024:.0f} КБ")
    for cat in CATEGORIES:
        print(f"       {cat:10} {counts[cat]:5}")
    return 0


def cmd_restore(path):
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    if not os.path.exists(path):
        print(f"! файл не найден: {path}")
        return 1

    with gzip.open(path, "rt", encoding="utf-8") as f:
        payload = json.load(f)

    items = payload["items"]
    print(f"Снимок от {payload['created']}  (записей {payload['total']})")

    # Фаза 1 — проверяем всё до записи
    plan = []
    for cat in CATEGORIES:
        got = items.get(cat)
        if got is None:
            print(f"  ! в снимке нет категории {cat} — пропускаю")
            continue
        plan.append((cat, got))

    # Фаза 2 — пишем
    for cat, got in plan:
        with open(cat_path(cat), "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=2)
        print(f"  восстановлен {cat:10} {len(got):5}")
    print("[OK] готово")
    return 0


def cmd_list():
    if not os.path.isdir(SNAP_DIR):
        print("снимков нет")
        return 0
    files = sorted(f for f in os.listdir(SNAP_DIR) if f.endswith(".json.gz"))
    if not files:
        print("снимков нет")
        return 0
    for name in files:
        path = os.path.join(SNAP_DIR, name)
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                head = json.load(f)
            print(f"  {name:32} {head['total']:5} записей  {head['created']}  {head.get('note', '')}")
        except Exception as e:
            print(f"  {name:32} ! не читается: {e}")
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    mode = sys.argv[1]
    if mode == "save":
        note = ""
        if "--note" in sys.argv:
            i = sys.argv.index("--note")
            if i + 1 < len(sys.argv):
                note = sys.argv[i + 1]
        return cmd_save(note)
    if mode == "restore":
        if len(sys.argv) < 3:
            print("укажите файл снимка: python snapshot.py restore _snapshots/<файл>.json.gz")
            return 1
        return cmd_restore(sys.argv[2])
    if mode == "list":
        return cmd_list()
    print(f"неизвестный режим: {mode}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
