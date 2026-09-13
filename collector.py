#!/usr/bin/env python3
"""
AI News Hub — автосборщик новостей из RSS/Atom лент.
Раскладывает новости по категориям в отдельные папки.
Запуск: python collector.py
"""

import json, os, re, sys, ssl, glob, shutil
from datetime import datetime, timedelta
from html import unescape
from urllib.request import urlopen, Request
from urllib.parse import quote
from xml.etree import ElementTree

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(__file__)
MAX_AGE_DAYS = 14

CATEGORIES = {
    "ai":       {"label": "Нейросети",    "emoji": "🧠", "accent": "#0071e3"},
    "vibe":     {"label": "Вайбкодинг",   "emoji": "✨", "accent": "#34c759"},
    "agent":    {"label": "ИИ-агенты",    "emoji": "🤖", "accent": "#ff9500"},
    "platform": {"label": "Платформы",    "emoji": "⚡", "accent": "#5856d6"},
    "design":   {"label": "Дизайн",       "emoji": "🎨", "accent": "#e3a133"},
    "jobs":     {"label": "Вакансии",     "emoji": "💼", "accent": "#e34133"},
    "orders":   {"label": "Есть заказ",   "emoji": "💰", "accent": "#e3a133"},
}

# Подкатегории для "Есть заказ" — каждая отдельная папка
ORDER_TYPES = {
    "sites":   {"label": "Сайты",         "emoji": "🌐", "accent": "#0071e3"},
    "prompts": {"label": "Промты",        "emoji": "✍️", "accent": "#34c759"},
    "ai":      {"label": "AI-задачи",     "emoji": "🤖", "accent": "#ff9500"},
    "design":  {"label": "Дизайн",        "emoji": "🎨", "accent": "#5856d6"},
    "content": {"label": "Контент",       "emoji": "📝", "accent": "#e34133"},
}

FEEDS = [
    {"url": "https://hnrss.org/frontpage", "cat": "ai", "source": "Hacker News"},
    {"url": "https://lobste.rs/rss", "cat": "ai", "source": "Lobsters"},
    {"url": "https://github.blog/feed/", "cat": "vibe", "source": "GitHub Blog"},
    {"url": "https://huggingface.co/blog/feed.xml", "cat": "platform", "source": "Hugging Face"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "cat": "ai", "source": "NYT Tech"},
    # Русскоязычные
    {"url": "https://habr.com/ru/rss/hub/artificial_intelligence/?fl=ru", "cat": "ai", "source": "Habr AI"},
    {"url": "https://habr.com/ru/rss/hub/machine_learning/?fl=ru", "cat": "ai", "source": "Habr ML"},
    {"url": "https://vc.ru/rss", "cat": "ai", "source": "vc.ru"},
    # Дизайн
    {"url": "https://habr.com/ru/rss/hubs/web_design/articles/?fl=ru", "cat": "design", "source": "Habr Веб-дизайн"},
    {"url": "https://habr.com/ru/rss/hubs/web_design/news/?fl=ru", "cat": "design", "source": "Habr Веб-дизайн"},
    {"url": "https://www.smashingmagazine.com/feed/", "cat": "design", "source": "Smashing Magazine"},
    {"url": "https://uxdesign.cc/feed", "cat": "design", "source": "UX Collective"},
    {"url": "https://www.awwwards.com/feed/", "cat": "design", "source": "Awwwards"},
]

CAT_KEYWORDS = {
    "ai": ["gpt", "claude", "llama", "gemini", "openai", "anthropic", "diffusion",
           "нейросет", "модель", "языков", "language model", "deep learning", "llm",
           "transformer", "neural", "machine learning"],
    "vibe": ["vibe coding", "cursor", "copilot", "bolt.new", "lovable", "replit",
             "вайбкод", "промпт", "генерац", "no-code", "low-code", "app generator",
             "ai coding", "generate code"],
    "agent": ["ai agent", "autogpt", "auto-gpt", "agent", "агент", "crewai",
              "langgraph", "function call", "tool use", "autonomous"],
    "platform": ["api", "platform", "платформ", "saas", "free tier", "бесплат",
                 "hosting", "spaces", "hugging face", "framework"],
    "design": ["figma", "тильд", "tilda", "веб-дизайн", "web design", "verstka",
               "верстк", "ui", "ux", "дизайн сайт", "дизайн", "design system",
               "интерфейс", "interface", "landing", "лендинг", "макет", "prototype",
               "прототип", "webflow", "photoshop", "illustrator", "логотип",
               "вебдизайн", "ux/ui", "ui/ux", "дизайнер"],
    "jobs": [],
    "orders": [],
}


def detect_lang(text):
    """Определяет язык: 'ru' если есть кириллица, иначе 'en'."""
    return "ru" if re.search(r"[а-яА-ЯёЁ]", text) else "en"


def classify(text, default_cat):
    text = text.lower()
    scores = {cat: 0 for cat in CATEGORIES}
    for cat, keywords in CAT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else default_cat


def clean_desc(html_text):
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:297] + "..." if len(text) > 300 else text


def parse_date(date_str):
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")
    s = date_str.strip()
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                 "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # eTXT шлёт вида "2026-08-27 15:52:27"
    for fmt in ["%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"202\d-\d{2}-\d{2}", s)
    if m:
        return m.group()
    return datetime.now().strftime("%Y-%m-%d")


def parse_rss(xml_text, feed):
    items = []
    root = ElementTree.fromstring(xml_text)
    for item in root.iter("item"):
        title = unescape(item.findtext("title", "")).strip()
        link = item.findtext("link", "").strip()
        desc = unescape(item.findtext("description", "")).strip()
        pubdate = item.findtext("pubDate", "")
        if not title or not link:
            continue
        items.append({
            "title": title, "link": link,
            "desc": clean_desc(desc),
            "date": parse_date(pubdate),
            "source": feed["source"],
            "cat": classify(title + " " + desc, feed["cat"]),
            "lang": detect_lang(title + " " + desc),
        })
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = unescape(entry.findtext("{http://www.w3.org/2005/Atom}title", "")).strip()
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        desc = unescape(entry.findtext("{http://www.w3.org/2005/Atom}summary", "")).strip()
        updated = entry.findtext("{http://www.w3.org/2005/Atom}updated", "")
        if not title or not link:
            continue
        items.append({
            "title": title, "link": link,
            "desc": clean_desc(desc),
            "date": parse_date(updated),
            "source": feed["source"],
            "cat": classify(title + " " + desc, feed["cat"]),
            "lang": detect_lang(title + " " + desc),
        })
    return items


def fetch_url(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    with urlopen(req, timeout=15, context=ctx) as resp:
        return resp.read()


# Ключевые слова для подкатегорий вакансий
JOB_TYPES = {
    "ai_dev":   {"label": "AI-разработка",  "emoji": "🤖",
                 "kw": ["ai engineer", "ml engineer", "machine learning", "deep learning",
                        "nlp engineer", "computer vision", "llm", "gpt", "prompt engineer",
                        "data scientist", "data engineer", "искусственный интеллект",
                        "машинное обучение", "нейросет", "нейрон", "дата саентист",
                        "дата инженер", "ml", "ai", "computer vision", "nlp",
                        "data analyst", "data science"]},
    "dev":      {"label": "Разработка",      "emoji": "💻",
                 "kw": ["backend", "frontend", "fullstack", "разработчик", "программист",
                        "developer", "software", "web", "python", "java",
                        "javascript", "typescript", "react", "node"]},
    "design":   {"label": "Дизайн",          "emoji": "🎨",
                 "kw": ["дизайнер", "designer", "ux/ui", "ui/ux", "графический",
                        "web designer", "product designer", "figma", "illustrator",
                        "photoshop", "creative", "art"]},
    "test":     {"label": "Тестирование",    "emoji": "🔍",
                 "kw": ["тестировщик", "qa", "тест", "test", "quality assurance",
                        "automation", "manual"]},
}


def classify_job(title, desc):
    """Определяет подкатегорию вакансии."""
    text = (title + " " + desc).lower()
    # Сначала проверяем AI-разработку (она приоритетнее)
    if any(w in text for w in JOB_TYPES["ai_dev"]["kw"]):
        return "ai_dev"
    for key, cat in JOB_TYPES.items():
        if key == "ai_dev":
            continue
        if any(w in text for w in cat["kw"]):
            return key
    return "ai_dev"  # fallback


def is_real_ai_job(title, desc):
    """Проверяет, что это релевантная онлайн/удалённая AI-вакансия."""
    text = (title + " " + desc).lower()
    # Блок-лист профессий и офлайна
    block = ["продавец", "кассир", "грузчик", "мерчендайзер", "уборщик", "водитель",
             "курьер", "кладовщик", "официант", "бармен", "администратор",
             "продавец-консультант", "охранник", "упаковщик", "комплектовщик",
             "сортировщик", "фасовщик", "пекарь", "повар", "швея",
             "продаж", "менеджер по продаж", "менеджер по работе", "account manager",
             "менеджер", "sales", "маркетолог", "marketing", "директолог",
             "seo", "smm", "таргетолог", "копирайтер", "контент", "content",
             "hr", "hr-", "рекрутер", "recruiter"]
    if any(w in text for w in block):
        return False

    # Блокируем обучение/курсы/стажировки
    edu = ["курс", "обучение", "школа", "интенсив", "вебинар", "тренинг",
           "марафон", "академия", "университет", "course", "training",
           "bootcamp", "internship", "стажировка", "студент", "junior",
           "без опыта", "без опыта работы", "practice", "стажер"]
    if any(w in text for w in edu):
        return False

    # Блокируем офлайн-локации
    office = ["офис", "работа в офисе", "г. ", "офлайн", "offline", "на месте",
              "в офисе", "работа на месте", "не удаленная", "полный день"]
    # Если есть офлайн-слова и нет удалёнки — отбрасываем
    has_office = any(w in text for w in office)
    has_remote = any(w in text for w in ["удален", "remote", "дистанц", "online",
                                          "онлайн", "гибрид", "hybrid", "дома"])
    if has_office and not has_remote:
        return False

    # Должны быть AI-слова или тех. скиллы
    ai_words = ["ai", "нейросет", "искусственный интеллект", "машинное обучение",
                "gpt", "llm", "deep learning", "data science", "prompt",
                "python", "tensorflow", "pytorch", "nlp", "computer vision",
                "нейрон", "чат-бот", "chatbot", "ai agent", "ml engineer"]
    if any(w in text for w in ai_words):
        return True

    tech_words = ["backend", "frontend", "разработчик", "программист", "developer",
                  "software", "qa", "тестировщик", "devops",
                  "data", "инженер", "engineer", "аналитик", "analyst",
                  "design", "дизайн", "ux", "ui", "figma"]
    return any(w in text for w in tech_words)


def classify_order(title, desc):
    """Определяет подкатегорию заказа."""
    text = (title + " " + desc).lower()
    if any(w in text for w in ["сайт", "лендинг", "landing", "site", "web", "html",
                                "css", "frontend", "wordpress", "tilda", "тильда",
                                "сайта", "сайтов"]):
        return "sites"
    if any(w in text for w in ["промт", "prompt", "prompt engineering", "prompt engineer",
                                "chatgpt prompt", "gpt prompt"]):
        return "prompts"
    if any(w in text for w in ["ai", "нейросет", "искусственный интеллект", "нейрон",
                                "машинное обучение", "чат-бот", "chatbot", "gpt",
                                "llm", "ml", "data science", "computer vision",
                                "распознаван", "генерац", "ai agent"]):
        return "ai"
    if any(w in text for w in ["дизайн", "design", "figma", "логотип", "лого",
                                "фирменный", "бренд", "ui", "ux", "график",
                                "illustrator", "photoshop", "верстк"]):
        return "design"
    return "content"


def fetch_fl_orders():
    """Парсит заказы с fl.ru."""
    items = []
    seen_titles = {}
    keywords = [
        "искусственный интеллект", "нейросети", "сайт", "ai", "gpt",
        "chatbot", "промт", "prompt", "design", "дизайн",
        "лендинг", "telegram bot", "телеграм бот", "написать бота",
        "сделать сайт", "разработка сайта", "верстка", "ui ux",
        "машинное обучение", "ml", "data science", "нейросеть API",
        "бот для", "парсинг", "скрипт", "автоматизация",
    ]

    for kw in keywords:
        try:
            url = f"https://www.fl.ru/rss/projects.xml?category=all&search={quote(kw)}"
            xml = fetch_url(url).decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            for item in root.iter("item"):
                title = unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title:
                    continue

                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                if link:
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": parse_date(pubdate),
                        "source": "FL.ru",
                        "cat": "orders",
                        "order_type": classify_order(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            pass
    print(f"  -> {len(items)} заказов с FL.ru")
    return items


def fetch_freelancehunt_orders():
    """Парсит заказы с freelancehunt.com через RSS."""
    items = []
    seen_titles = {}
    categories = ["ai-machine-learning", "chatbots", "web-design", "html-css",
                   "javascript", "python", "php", "data-parsing"]

    for cat in categories:
        try:
            url = f"https://freelancehunt.com/en/projects/rss/{cat}.xml"
            xml = fetch_url(url).decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            for item in root.iter("item"):
                title = unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")
                if not title:
                    continue
                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1
                if link:
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": parse_date(pubdate),
                        "source": "Freelancehunt",
                        "cat": "orders",
                        "order_type": classify_order(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            pass
    print(f"  -> {len(items)} заказов с Freelancehunt")
    return items


def fetch_etxt_orders():
    """Парсит заказы с eTXT.ru через RSS."""
    items = []
    seen_norm = set()
    try:
        url = "http://www.etxt.ru/rss/tasks/"
        xml = fetch_url(url).decode("utf-8", errors="replace")
        root = ElementTree.fromstring(xml)
        for item in root.iter("item"):
            title = unescape(item.findtext("title", "")).strip()
            link = item.findtext("link", "").strip()
            desc = unescape(item.findtext("description", "")).strip()
            pubdate = item.findtext("pubDate", "")
            if not title:
                continue
            # Нормализуем: убираем номер заказа (№XXXX)
            norm = re.sub(r"[\s#]\d{4,}[/\s-]*\d*", "", title).strip().lower()
            if norm in seen_norm:
                continue
            seen_norm.add(norm)
            if link:
                items.append({
                    "title": title,
                    "link": link,
                    "desc": clean_desc(desc),
                    "date": parse_date(pubdate),
                    "source": "eTXT",
                    "cat": "orders",
                    "order_type": classify_order(title, desc),
                    "lang": "ru",
                })
    except Exception as e:
        print(f"  ! eTXT: {e}")
    print(f"  -> {len(items)} заказов с eTXT")
    return items


def fetch_hh_vacancies():
    """Парсит вакансии с hh.ru через RSS. Ищет AI/ML/нейросети."""
    items = []
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение",
                "ai engineer", "data scientist", "gpt", "llm", "prompt engineer"]
    seen_links = set()
    seen_titles = {}  # title -> count
    now = datetime.now().strftime("%Y-%m-%d")

    for kw in keywords:
        try:
            url = f"https://hh.ru/search/vacancy/rss?text={quote(kw)}&area=113"
            xml = fetch_url(url).decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            for item in root.iter("item"):
                title = unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title:
                    continue

                # Отбрасываем курсы/обучения, вебинары
                skip_words = ["курс", "обучение", "школа", "интенсив", "вебинар",
                              "тренинг", "марафон", "академия", "университет",
                              "course", "training", "bootcamp"]
                text_lower = (title + " " + desc).lower()
                if any(w in text_lower for w in skip_words):
                    continue

                # Отбрасываем нерелевантные вакансии
                if not is_real_ai_job(title, desc):
                    continue

                # Дедубликация: одинаковый заголовок не более 1 раза
                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                if link and link not in seen_links:
                    seen_links.add(link)
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": parse_date(pubdate),
                        "source": "hh.ru",
                        "cat": "jobs",
                        "job_type": classify_job(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            print(f"  ! hh.ru ({kw}): {e}")
    print(f"  -> {len(items)} вакансий с hh.ru")
    return items


def fetch_trudvsem_vacancies():
    """Парсит вакансии через API Работа России."""
    items = []
    seen = set()
    now = datetime.now().strftime("%Y-%m-%d")
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение"]

    for kw in keywords:
        try:
            url = f"https://opendata.trudvsem.ru/api/v1/vacancies?text={quote(kw)}&limit=50"
            data = fetch_url(url).decode("utf-8", errors="replace")
            parsed = json.loads(data)
            vacancies = parsed.get("results", {}).get("vacancies", [])
            for v in vacancies:
                vdata = v.get("vacancy", {})
                title = vdata.get("title", "")
                if isinstance(title, dict):
                    title = title.get("$", "") or str(title)
                link = vdata.get("vac_url", "")
                desc_raw = vdata.get("requirement", "")
                if isinstance(desc_raw, dict):
                    desc_raw = desc_raw.get("$", "") or str(desc_raw)
                duty_raw = vdata.get("duty", "")
                if isinstance(duty_raw, dict):
                    duty_raw = duty_raw.get("$", "") or str(duty_raw)
                desc = str(desc_raw) + " " + str(duty_raw)
                date_str = vdata.get("creation_date", "")[:10]

                if not title or not title.strip():
                    continue

                skip_words = ["курс", "обучение", "школа", "интенсив", "вебинар",
                              "тренинг", "марафон", "академия", "университет"]
                if any(w in (title + desc).lower() for w in skip_words):
                    continue

                if not is_real_ai_job(title, desc):
                    continue

                if link and link not in seen:
                    seen.add(link)
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": date_str or now,
                        "source": "Работа России",
                        "cat": "jobs",
                        "job_type": classify_job(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            print(f"  ! trudvsem ({kw}): {e}")
    print(f"  -> {len(items)} вакансий с Работа России")
    return items


def load_news(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_news(filepath, items):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def save_data_js(filepath, items, cat_keys=None):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    ts = datetime.now().strftime("%d.%m.%Y, %H:%M:%S")
    data = {"items": items, "cat_keys": list(CATEGORIES.keys()), "updated": ts} if cat_keys is None else items
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("window.NEWS_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")


def generate_category_page(cat_key, cat_info):
    """Генерируем index.html для конкретной категории."""
    tmpl_path = os.path.join(BASE_DIR, "_category_template.html")
    if not os.path.exists(tmpl_path):
        return
    with open(tmpl_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("%%TITLE%%", cat_info["emoji"] + " " + cat_info["label"])
    html = html.replace("%%ACCENT%%", cat_info["accent"])
    for k in CATEGORIES:
        html = html.replace(f"%%ACT_{k}%%", "active" if k == cat_key else "")
    cat_dir = os.path.join(BASE_DIR, cat_key)
    os.makedirs(cat_dir, exist_ok=True)
    with open(os.path.join(cat_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def generate_main_page(all_news):
    """Генерируем главную страницу — хаб со ссылками и счётчиками категорий."""
    counts = {k: 0 for k in CATEGORIES}
    for n in all_news:
        if n["cat"] in counts:
            counts[n["cat"]] += 1
    total = len(all_news)

    cards = ""
    for k, cat in CATEGORIES.items():
        cards += f'''<a href="{k}/index.html" class="cat-card" style="--accent:{cat['accent']}">
<div class="cat-emoji">{cat['emoji']}</div>
<div class="cat-name">{cat['label']}</div>
<div class="cat-count">{counts[k]} новостей</div>
</a>
'''

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI News Hub</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🤖</text></svg>">
<style>
:root {{
  --bg: #f5f5f7; --card-bg: #ffffff; --text: #1d1d1f;
  --text2: #6e6e73; --border: #e5e5ea; --accent: #0071e3;
  --shadow: 0 2px 12px rgba(0,0,0,0.08);
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1c1c1e; --card-bg: #2c2c2e; --text: #f5f5f7;
    --text2: #98989d; --border: #3a3a3c; --shadow: 0 2px 12px rgba(0,0,0,0.3);
  }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5; padding: 20px;
}}
.container {{ max-width: 1100px; margin: 0 auto; }}

header {{
  text-align: center;
  padding: 30px 0 20px;
}}
header h1 {{
  font-size: 2.5rem; font-weight: 700;
  background: linear-gradient(135deg, #0071e3, #5856d6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}}
header p {{ color: var(--text2); margin-top: 4px; font-size: 1.1rem; }}
#lastUpdated {{ font-size: .85rem; color: var(--text2); margin-top: 4px; }}

.cat-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
  margin-top: 24px;
}}
.cat-card {{
  display: block;
  background: var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  text-decoration: none;
  color: var(--text);
  box-shadow: var(--shadow);
  transition: transform .15s ease, box-shadow .15s ease;
}}
.cat-card:hover {{
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,.12);
  border-color: var(--accent);
}}
.cat-emoji {{ font-size: 2.2rem; }}
.cat-name {{ font-size: 1.1rem; font-weight: 600; margin-top: 10px; }}
.cat-count {{ font-size: .85rem; color: var(--text2); margin-top: 4px; }}

footer {{ color: var(--text2); font-size: 0.85rem; padding: 30px 0; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>AI News Hub</h1>
    <p>Нейросети · Вайбкодинг · Дизайн · ИИ-агенты · Платформы</p>
    <div id="lastUpdated"></div>
  </header>

  <nav class="cat-grid">
{cards}  </nav>

  <footer>
    Автосборщик новостей о мире AI
  </footer>
</div>
<script>
document.getElementById('lastUpdated').textContent =
    'Обновлено: ' + new Date().toLocaleString('ru-RU', {{timeZone:'Europe/Moscow'}}) + ' (МСК)' + ' · всего {total} новостей';
</script>
</body>
</html>"""
    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [OK] Главная страница — {total} новостей по {len([k for k, v in counts.items() if v > 0])} категориям")


def build_dist():
    """Собирает папку dist/ — готовые к публикации файлы."""
    dist = os.path.join(BASE_DIR, "dist")
    if os.path.exists(dist):
        shutil.rmtree(dist)
    os.makedirs(dist, exist_ok=True)

    # Копируем index.html (главная)
    shutil.copy2(os.path.join(BASE_DIR, "index.html"), os.path.join(dist, "index.html"))

    # Копируем категории: только index.html и data.js
    for cat_key in CATEGORIES:
        src_cat = os.path.join(BASE_DIR, cat_key)
        dst_cat = os.path.join(dist, cat_key)
        os.makedirs(dst_cat, exist_ok=True)
        for fname in ("index.html", "data.js"):
            src = os.path.join(src_cat, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst_cat, fname))

    print(f"  [OK] dist/ собран ({len(os.listdir(dist))} элементов)")


def main():
    # 1. Собираем новые новости из RSS
    all_news = []
    seen_links = set()

    for feed in FEEDS:
        try:
            print(f"Читаю: {feed['url']}")
            xml = fetch_url(feed["url"]).decode("utf-8", errors="replace")
            items = parse_rss(xml, feed)
            added = 0
            for item in items:
                if item["link"] not in seen_links:
                    all_news.append(item)
                    seen_links.add(item["link"])
                    added += 1
            print(f"  -> {len(items)} записей, новых: {added}")
        except Exception as e:
            print(f"  ! Ошибка: {e}")

    # 1b. Собираем вакансии
    print("Собираю вакансии с hh.ru...")
    for v in fetch_hh_vacancies():
        if v["link"] not in seen_links:
            all_news.append(v)
            seen_links.add(v["link"])
    print("Собираю вакансии с Работа России...")
    for v in fetch_trudvsem_vacancies():
        if v["link"] not in seen_links:
            all_news.append(v)
            seen_links.add(v["link"])

    # 1c. Собираем заказы
    print("Собираю заказы с FL.ru...")
    for o in fetch_fl_orders():
        if o["link"] not in seen_links:
            all_news.append(o)
            seen_links.add(o["link"])

    # 2. Загружаем существующие новости (чтобы не потерять ручные правки)
    for key in CATEGORIES:
        fpath = os.path.join(BASE_DIR, key, "news.json")
        for item in load_news(fpath):
            if item["link"] not in seen_links:
                all_news.append(item)
                seen_links.add(item["link"])

    # 3. Фильтр по дате
    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    filtered = []
    for item in all_news:
        try:
            d = datetime.strptime(item.get("date", "2000-01-01"), "%Y-%m-%d")
            if d < cutoff:
                continue
        except ValueError:
            pass
        filtered.append(item)

    # 4. Сортируем
    filtered.sort(key=lambda x: x.get("date", "2000-01-01"), reverse=True)

    # 5. Раскладываем по папкам
    for key, cat in CATEGORIES.items():
        items = [n for n in filtered if n["cat"] == key]
        cat_dir = os.path.join(BASE_DIR, key)
        save_news(os.path.join(cat_dir, "news.json"), items)
        save_data_js(os.path.join(cat_dir, "data.js"), items)
        generate_category_page(key, cat)

    # 6. Генерируем главную
    generate_main_page(filtered)

    # 7. Собираем дистрибутив
    build_dist()

    print(f"\n[OK] Всего новостей: {len(filtered)}")


if __name__ == "__main__":
    main()
