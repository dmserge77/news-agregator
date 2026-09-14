#!/usr/bin/env python3
"""
AI News Hub — автосборщик новостей из RSS/Atom лент.
Раскладывает новости по категориям в отдельные папки.
Запуск: python collector.py
"""

import json, os, re, sys, ssl, shutil
from datetime import datetime, timedelta
from html import unescape
from urllib.request import urlopen, Request
from urllib.parse import quote
from xml.etree import ElementTree

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(__file__)
MAX_AGE_DAYS = 90


def now_msk():
    """Текущее время по Москве (UTC+3)."""
    return datetime.utcnow() + timedelta(hours=3)

CATEGORIES = {
    "ai":       {"label": "Нейросети",    "emoji": "🧠", "accent": "#0071e3"},
    "vibe":     {"label": "Вайбкодинг",   "emoji": "✨", "accent": "#34c759"},
    "agent":    {"label": "ИИ-агенты",    "emoji": "🤖", "accent": "#ff9500"},
    "platform": {"label": "Платформы",    "emoji": "⚡", "accent": "#5856d6"},
    "design":   {"label": "Дизайн",       "emoji": "🎨", "accent": "#e3a133"},
    "misc":     {"label": "Солянка",      "emoji": "🍲", "accent": "#c9762d"},
    "jobs":     {"label": "Вакансии",     "emoji": "💼", "accent": "#e34133"},
    "orders":   {"label": "Есть заказ",   "emoji": "💰", "accent": "#e3a133"},
}

# Категории, содержимое которых НЕ проверяется на AI-релевантность
# (вакансии и заказы фильтруются своими отдельными функциями)
NO_AI_CHECK = {"jobs", "orders"}

# Подкатегории для "Есть заказ" — каждая отдельная папка
ORDER_TYPES = {
    "sites":     {"label": "Сайты",           "emoji": "🌐", "accent": "#0071e3"},
    "prompts":   {"label": "Промты",          "emoji": "✍️", "accent": "#34c759"},
    "ai":        {"label": "AI-разработка",   "emoji": "🤖", "accent": "#ff9500"},
    "media":     {"label": "Изображения",     "emoji": "🎨", "accent": "#5856d6"},
    "audio":     {"label": "Видео и аудио",   "emoji": "🎧", "accent": "#c9762d"},
    "automate":  {"label": "Автоматизация",   "emoji": "🔧", "accent": "#e34133"},
}

# Подкатегории для "Солянка" — каждая отдельная папка
MISC_TYPES = {
    "raznoe": {"label": "Разное",   "emoji": "📰", "accent": "#c9762d"},
    "curio":  {"label": "Курьёзы",  "emoji": "🤪", "accent": "#e3a133"},
}

FEEDS = [
    # --- Англоязычные ---
    {"url": "https://hnrss.org/frontpage", "cat": "ai", "source": "Hacker News"},
    {"url": "https://lobste.rs/rss", "cat": "ai", "source": "Lobsters"},
    {"url": "https://github.blog/feed/", "cat": "vibe", "source": "GitHub Blog"},
    {"url": "https://github.blog/category/engineering/feed/", "cat": "vibe", "source": "GitHub Eng"},
    {"url": "https://blog.replit.com/feed.xml", "cat": "vibe", "source": "Replit"},
    {"url": "https://huggingface.co/blog/feed.xml", "cat": "platform", "source": "Hugging Face"},
    {"url": "https://vercel.com/blog/feed.xml", "cat": "platform", "source": "Vercel"},
    {"url": "https://blog.railway.app/rss.xml", "cat": "platform", "source": "Railway"},
    # --- Русскоязычные: ИИ и ML ---
    {"url": "https://habr.com/ru/rss/hub/artificial_intelligence/?fl=ru", "cat": "ai", "source": "Habr AI"},
    {"url": "https://habr.com/ru/rss/hub/machine_learning/?fl=ru", "cat": "ai", "source": "Habr ML"},
    {"url": "https://habr.com/ru/rss/hubs/artificial_intelligence/news/?fl=ru", "cat": "ai", "source": "Habr AI Новости"},
    {"url": "https://habr.com/ru/rss/hubs/machine_learning/news/?fl=ru", "cat": "ai", "source": "Habr ML Новости"},
    {"url": "https://habr.com/ru/rss/hub/natural_language_processing/?fl=ru", "cat": "ai", "source": "Habr NLP"},
    {"url": "https://habr.com/ru/rss/hub/bigdata/?fl=ru", "cat": "platform", "source": "Habr Big Data"},
    {"url": "https://habr.com/ru/rss/hub/python/?fl=ru", "cat": "vibe", "source": "Habr Python"},
    {"url": "https://habr.com/ru/rss/hub/open_source/?fl=ru", "cat": "platform", "source": "Habr Open Source"},
    {"url": "https://habr.com/ru/rss/hub/devops/?fl=ru", "cat": "platform", "source": "Habr DevOps"},
    {"url": "https://habr.com/ru/rss/hub/api/?fl=ru", "cat": "platform", "source": "Habr API"},
    {"url": "https://habr.com/ru/rss/hubs/cloud_computing/?fl=ru", "cat": "platform", "source": "Habr Облака"},
    {"url": "https://habr.com/ru/rss/hub/freelance/?fl=ru", "cat": "misc", "source": "Habr Фриланс"},
    {"url": "https://tproger.ru/feed/", "cat": "vibe", "source": "Tproger"},
    {"url": "https://thecode.media/feed/", "cat": "platform", "source": "The Code"},
    {"url": "https://www.kaspersky.ru/blog/feed/", "cat": "platform", "source": "Kaspersky"},
    {"url": "https://www.comnews.ru/rss.xml", "cat": "platform", "source": "ComNews"},
    {"url": "https://te-st.org/feed/", "cat": "platform", "source": "Теплица соцтех"},
    {"url": "https://dtf.ru/rss/", "cat": "misc", "source": "DTF"},
    {"url": "https://rb.ru/feeds/all/", "cat": "misc", "source": "Rusbase"},
    {"url": "https://nauka.tass.ru/rss/v2.xml", "cat": "misc", "source": "ТАСС Наука"},
    # --- Русскоязычные: техно-медиа (проходят фильтр по ИИ) ---
    {"url": "https://3dnews.ru/news/rss/", "cat": "misc", "source": "3DNews"},
    {"url": "https://hi-tech.mail.ru/rss/all/", "cat": "misc", "source": "Hi-Tech Mail"},
    # --- Дизайн ---
    {"url": "https://habr.com/ru/rss/hubs/web_design/articles/?fl=ru", "cat": "design", "source": "Habr Веб-дизайн"},
    {"url": "https://habr.com/ru/rss/hubs/web_design/news/?fl=ru", "cat": "design", "source": "Habr Веб-дизайн"},
    {"url": "https://habr.com/ru/rss/hub/design/?fl=ru", "cat": "design", "source": "Habr Дизайн"},
    {"url": "https://www.smashingmagazine.com/feed/", "cat": "design", "source": "Smashing Magazine"},
    {"url": "https://uxdesign.cc/feed", "cat": "design", "source": "UX Collective"},
    {"url": "https://www.awwwards.com/feed/", "cat": "design", "source": "Awwwards"},
]

CAT_KEYWORDS = {
    "ai": ["gpt", "chatgpt", "gpt-4", "gpt-5", "claude", "llama", "gemini", "deepseek",
           "qwen", "mistral", "grok", "midjourney", "stable diffusion", "sora",
           "openai", "anthropic", "deepmind", "hugging face", "нейросет", "нейронн",
           "искусственный интеллект", "ии-", "ии ", "ии,", "ии.", "машинное обучение",
           "машинного обучения", "языкова", "llm", "deep learning", "transformer",
           "diffusion", "chatbot", "чат-бот", "чатбот", "инференс", "обучение модель",
           "генеративн", "мультимодальн", "токен", "эмбеддинг", "датасет"],
    "vibe": ["vibe coding", "вайбкод", "cursor", "github copilot", "copilot",
             "bolt.new", "lovable", "replit", "codeium", "windsurf", "cline",
             "ai coding", "промпт-инжинир", "prompt engineering", "no-code",
             "low-code", "генерация кода", "кодогенерац", "автодополнение кода"],
    "agent": ["ai agent", "ии-агент", "autogpt", "auto-gpt", "crewai", "langgraph",
              "langchain", "mcp-сервер", "model context protocol", "function call",
              "tool use", "tool use", "автономн", "оркестрац агент", "агентная систем",
              "agentic"],
    "platform": ["api", "платформ", "saas", "free tier", "бесплатн", "хостинг",
                 "hosting", "framework", "фреймворк", "облачн", "инфраструктур",
                 "серверн", "open source", "опенсорс", "релиз", "обновление",
                 "разработк", "библиотек", "sdk", "разработчик"],
    "design": ["figma", "тильд", "tilda", "веб-дизайн", "web design", "верстк",
               "ui", "ux", "дизайн", "design system", "интерфейс", "interface",
               "landing", "лендинг", "макет", "prototype", "прототип", "webflow",
               "photoshop", "illustrator", "логотип", "вебдизайн", "ux/ui", "ui/ux",
               "дизайнер", "нейро-дизайн", "нейросетевой дизайн"],
    "misc": [],
    "jobs": ["вакансия", "вакансии", "ищем", "требуется", "зарплата", "оплата",
             "резюме", "собеседование", "оффер", "грейд", "senior", "middle",
             "junior", "remote", "удалёнка", "гибрид", "full-time", "part-time",
             "мы ищем", "в команду", "в штат", "зарплатная вилка", "компания ищет",
             "hh.ru", "headhunter", "трудоустройство", "работа", "подработка"],
    # Заказы в RSS не приходят — они собираются только через fetch_fl_orders().
    # Здесь пусто, чтобы статьи про фриланс не попадали в рубрику заказов.
    "orders": [],
}

# Что гарантированно говорит о связи материала с ИИ.
# Если ни одного совпадения — новость в сборник не попадает.
AI_STRONG = [
    "искусственный интеллект", "искусственного интеллекта", "искусственном интеллекте",
    "нейросет", "нейронн", "машинное обучение", "машинного обучения", "глубокое обучение",
    "генеративн", "мультимодальн", "языковая модель", "языковой модели",
    "языковых модел", "большая языковая", "чат-бот", "чатбот", "промпт", "промт",
    "датасет", "инференс", "токенизац",
    "artificial intelligence", "neural network", "neural net", "machine learning",
    "deep learning", "generative ai", "large language model", "language model",
    "llm", "chatbot", "chat bot", "prompt engineering", "fine-tuning", "fine tuning",
    "diffusion model", "transformer model", "computer vision", "inference",
    # Слова из мира заказов и услуг
    "нейрофото", "нейрокартинк", "нейроарт", "нейрохудожник", "нейроаватар",
    "нейроозвуч", "нейровидео", "нейроконтент", "нейротекст", "нейросетев",
    "распознаван", "разметка данных", "обучение модели", "дообучение",
    "сгенерировать изображен", "генерация изображен", "генерация видео",
    "синтез речи", "клонирование голоса", "ai-агент", "ии-агент",
]
# Названия компаний и моделей — тоже сильный сигнал
AI_NAMES = [
    "gpt", "chatgpt", "openai", "anthropic", "claude", "gemini", "google deepmind",
    "deepmind", "llama", "meta ai", "mistral", "deepseek", "qwen", "grok", "xai",
    "hugging face", "stability ai", "midjourney", "stablediffusion", "stable diffusion",
    "copilot", "cursor", "perplexity", "sora", "nvidia", "сбер", "gigachat", "гигачат",
    "yandexgpt", "яндекс gpt", "шедеврум", "кандинский", "адам", "gpt-4", "gpt-5",
]
# Мусор: не ИИ, а бытовая техника, дизайн интерьера и прочее
FALSE_POSITIVES = [
    "стиральн", "холодильник", "пылесос", "микроволнов", "мультиварк", "посудомоеч",
    "кондиционер", "телевизор", "смартфон обзор", "наушники", "кроссовк", "автомобил",
    "шин", "квартир", "ремонт", "мебел", "интерьер", "кухн", "ванн",
]


def has_ai_signal(text):
    """Есть ли в тексте явный признак темы ИИ."""
    t = text.lower()
    if any(w in t for w in AI_STRONG):
        return True
    if any(w in t for w in AI_NAMES):
        return True
    # "AI" отдельным словом, а не внутри "mail", "said", "captain".
    # Исключение: перечисление графических форматов (svg, ai, pdf, eps) —
    # там "ai" это Adobe Illustrator, а не искусственный интеллект.
    if re.search(r"(?<![a-z])ai(?![a-z])", t):
        if re.search(r"(svg|eps|png|jpg|pdf|cdr|dxf)\s*,\s*ai\b", t):
            return False
        if re.search(r"\bai\s*,\s*(pdf|eps|svg|cdr|dxf|png)", t):
            return False
        return True
    return False


def is_ai_relevant(text, cat):
    """Пропускает только материалы про ИИ. Вакансии и заказы не проверяются."""
    if cat in NO_AI_CHECK:
        return True
    if cat not in CATEGORIES:
        return False
    t = text.lower()
    if any(w in t for w in FALSE_POSITIVES):
        return False
    return has_ai_signal(t)


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
    if scores[best] > 0:
        return best
    # Ничего не подошло, но материал всё равно про ИИ — это «Солянка»
    if has_ai_signal(text):
        return "misc"
    return None


def clean_desc(html_text):
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:297] + "..." if len(text) > 300 else text


def parse_date(date_str):
    if not date_str:
        return now_msk().strftime("%Y-%m-%d")
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
    return now_msk().strftime("%Y-%m-%d")


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
        text = title + " " + desc
        cat = classify(text, feed["cat"])
        if not is_ai_relevant(text, cat):
            continue
        item_data = {
            "title": title, "link": link,
            "desc": clean_desc(desc),
            "date": parse_date(pubdate),
            "source": feed["source"],
            "cat": cat,
            "lang": detect_lang(text),
        }
        if cat == "misc":
            item_data["misc_type"] = classify_misc(title, desc)
        items.append(item_data)
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = unescape(entry.findtext("{http://www.w3.org/2005/Atom}title", "")).strip()
        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        desc = unescape(entry.findtext("{http://www.w3.org/2005/Atom}summary", "")).strip()
        updated = entry.findtext("{http://www.w3.org/2005/Atom}updated", "")
        if not title or not link:
            continue
        text = title + " " + desc
        cat = classify(text, feed["cat"])
        if not is_ai_relevant(text, cat):
            continue
        entry_data = {
            "title": title, "link": link,
            "desc": clean_desc(desc),
            "date": parse_date(updated),
            "source": feed["source"],
            "cat": cat,
            "lang": detect_lang(text),
        }
        if cat == "misc":
            entry_data["misc_type"] = classify_misc(title, desc)
        items.append(entry_data)
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


# Маркеры веб-разработки. Такой заказ проходит в «Есть заказ» ДАЖЕ БЕЗ ИИ:
# сайты — отдельное направление рубрики, здесь важен не ИИ, а сама работа.
SITE_MARKERS = [
    "сайт", "сайта", "сайтов", "сайте", "лендинг", "landing", "веб-сайт", "website",
    "web site", "интернет-магазин", "магазин на", "html", "css", "javascript",
    "верстк", "вёрстк", "сверстать", "разверстать", "frontend", "фронтенд",
    "backend", "бэкенд", "wordpress", "вордпресс", "tilda", "тильд", "битрикс",
    "bitrix", "opencart", "modx", "joomla", "django", "laravel", "react",
    "vue", "next.js", "nuxt", "web-приложен", "веб-приложен", "веб приложен",
    "web приложен", "парсинг сайта", "доработка сайта", "правки на сайте",
    "перенести сайт", "настроить сайт", "лендинг-пейдж", "одностраничник",
    "многостраничник", "хостинг", "домен", "cms", "crm-систем", "доработка crm",
]


def classify_order(title, desc):
    """Определяет подкатегорию заказа. Сайты идут первыми — с ИИ или без."""
    text = (title + " " + desc).lower()
    if any(w in text for w in SITE_MARKERS):
        return "sites"
    if any(w in text for w in ["промт", "prompt", "промпт", "промт-инжинир",
                                "prompt engineering", "prompt engineer",
                                "chatgpt prompt", "gpt prompt", "текст для нейросет"]):
        return "prompts"
    if any(w in text for w in ["озвуч", "voice over", "voiceover", "дубляж",
                                "липсинк", "lip sync", "lipsync", "подкаст",
                                "аудио", "звук", "музык", "вокал", "синтез речи",
                                "tts", "speech", "клонирован голос", "клонировать голос",
                                "видео", "ролик", "рилс", "reels", "shorts", "шортс",
                                "монтаж", "видеомонтаж", "анимац", "аватар"]):
        return "audio"
    if any(w in text for w in ["нейрофото", "нейрокартинк", "генерац изображен",
                                "генерац картин", "сгенерировать изображен",
                                "иллюстрац", "изображен", "картинк", "баннер",
                                "арт", "midjourney", "stable diffusion", "dall-e",
                                "flux", "обрисовать", "ретуш", "фото", "фотограф"]):
        return "media"
    if any(w in text for w in ["автоматизац", "парсинг", "парсер", "скрипт",
                                "бот", "telegram-бот", "телеграм-бот", "чат-бот",
                                "chatbot", "интеграц", "api", "выгрузк", "спарсить",
                                "собрать данные", "excel", "таблиц", "google sheets"]):
        return "automate"
    return "ai"


def is_ai_order(title, desc):
    """Заказ проходит, если он про ИИ ИЛИ про сайты (сайты — без требования ИИ)."""
    text = (title + " " + desc).lower()
    # Реклама, SEO, лидоген — не разработка, рубрике не подходят
    if any(w in text for w in ["директолог", "яндекс директ", "контекстн", "seo",
                                "сео", "лидген", "аффилиац", "таргет", "обзвон",
                                "посещаемост", "раскрутк", "продвижени"]):
        return False
    # Статьи и новости — не заказы (в заказы попадают только через FL.ru)
    if any(w in text for w in ["объявил", "объявила", "на днях", "в интервью",
                                "рассказал", "рассказала", "выяснил", "я фрилансер",
                                "как я ", "почему бизнес", "обнаружил", "написал свой"]):
        return False
    if any(w in text for w in SITE_MARKERS):
        return True
    if has_ai_signal(text):
        return True
    # Парсинг, боты и автоматизация — профильные темы рубрики
    return any(w in text for w in ["парсинг", "парсер", "спарсить", "автоматизац",
                                    "чат-бот", "chatbot", "telegram бот",
                                    "телеграм бот", "скрипт для", "бот для"])


# Маркеры рубрики «Курьёзы» внутри «Солянки».
# Только то, что мы ОПОВЕЩАЕМ: шутки, мемы, нелепые истории, скандалы, фейлы.
# Никаких «советов» и «лайфхаков» — мы не советуем, мы оповещаем.
CURIO_MARKERS = [
    "шутк", "пошутил", "пошутила", "шутит", "шутить", "юмор", "юморист",
    "мем", "мемы", "мемасик", "мемчик", "смешн", "смешно", "смех", "насмешил",
    "забавн", "прикол", "курьёз", "курьез", "нелеп", "абсурдн", "анекдот",
    "скандал", "фейл", "fail", "провал", "опозорил", "конфуз", "недоразумени",
    "разыграл", "розыгрыш", "устроил переполох", "рассмешил", "перепутал",
    "приняли за", "перепутали", "обманул", "обманули", "нейросеть ошиблась",
    "галлюцинир", "галлюцинац", "нагенерировал", "сгенерировал ерунду",
    "funny", "joke", "humor", "meme", "mishap", "blunder", "embarrassing",
    "ridiculous", "absurd", "hallucinat", "went wrong", "prank", "weird",
]


def classify_misc(title, desc):
    """Определяет подкатегорию «Солянки»: курьёзы или всё остальное."""
    text = (title + " " + desc).lower()
    if any(w in text for w in CURIO_MARKERS):
        return "curio"
    return "raznoe"


def fetch_fl_orders():
    """Парсит заказы с fl.ru. Ищет только ИИ-заказы и сайты."""
    items = []
    seen_titles = {}
    errors = []
    keywords = [
        # ИИ
        "нейросети", "искусственный интеллект", "нейросеть", "gpt", "chatgpt",
        "промт", "prompt", "машинное обучение", "llm", "ai агент", "ai-агент",
        "нейрофото", "нейроарт", "генерация изображений", "midjourney",
        "обучение модели", "датасет", "разметка данных", "computer vision",
        "распознавание", "ии", "ai видео", "ai озвучка", "ai аватар",
        "автоматизация", "парсинг", "чат-бот", "telegram бот",
        # Сайты (без требования ИИ)
        "сайт", "лендинг", "верстка", "html", "wordpress", "тильда", "битрикс",
        "интернет-магазин", "доработка сайта", "frontend", "web приложение",
    ]

    for kw in keywords:
        try:
            url = f"https://www.fl.ru/rss/projects.xml?category=all&search={quote(kw)}"
            raw = fetch_url(url)
            xml = raw.decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            raw_count = 0
            for item in root.iter("item"):
                title = unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title:
                    continue
                raw_count += 1

                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                # Отсекаем всё, что не про ИИ и не про сайты
                if not is_ai_order(title, desc):
                    continue

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
            print(f"    [{kw}] ответ {len(raw)} б, записей: {raw_count}")
        except Exception as e:
            errors.append(f"{kw}: {e}")
    if errors:
        print(f"  ! FL.ru ошибки ({len(errors)} из {len(keywords)} запросов):")
        for err in errors[:5]:
            print(f"      {err}")
    print(f"  -> {len(items)} заказов с FL.ru")
    return items


def fetch_hh_vacancies():
    """Парсит вакансии с hh.ru через RSS. Ищет AI/ML/нейросети."""
    items = []
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение",
                "ai engineer", "data scientist", "gpt", "llm", "prompt engineer"]
    seen_links = set()
    seen_titles = {}  # title -> count
    now = now_msk().strftime("%Y-%m-%d")

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
    now = now_msk().strftime("%Y-%m-%d")
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


def write_if_changed(filepath, content):
    """Пишет файл только если содержимое изменилось — чтобы не плодить пустые коммиты."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            if f.read() == content:
                return
    except FileNotFoundError:
        pass
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def save_news(filepath, items):
    write_if_changed(filepath, json.dumps(items, ensure_ascii=False, indent=2))


def save_data_js(filepath, items, cat_keys=None):
    ts = now_msk().strftime("%d.%m.%Y, %H:%M:%S")
    data = {"items": items, "cat_keys": list(CATEGORIES.keys()), "updated": ts} if cat_keys is None else items
    body = "window.NEWS_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    write_if_changed(filepath, body)


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
    write_if_changed(os.path.join(cat_dir, "index.html"), html)


def generate_main_page(all_news):
    """Генерируем главную страницу — хаб со ссылками и счётчиками категорий."""
    counts = {k: 0 for k in CATEGORIES}
    for n in all_news:
        if n["cat"] in counts:
            counts[n["cat"]] += 1
    total = len(all_news)
    build_time = now_msk().strftime("%d.%m.%Y, %H:%M:%S")

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
<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){{
        m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }}}}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    }})(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=112543447', 'ym');

    ym(112543447, 'init', {{ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true}});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/112543447" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->
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
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
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
.cat-emoji {{
  font-size: 2.2rem;
  margin-bottom: 12px;
  display: inline-block;
  line-height: 1;
}}
.cat-name {{
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 10px;
  line-height: 1.3;
}}
.cat-count {{
  font-size: .85rem;
  color: var(--text2);
  margin-top: 4px;
}}
.cat-card:last-child {{
  margin-bottom: 0;
}}
.cat-card:focus-visible {{
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}}
.cat-card:active {{
  transform: translateY(0);
  box-shadow: 0 4px 12px rgba(0,0,0,.08);
}}

footer {{ color: var(--text2); font-size: 0.85rem; padding: 30px 0; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>AI News Hub</h1>
    <p>Нейросети · Вайбкодинг · Дизайн · ИИ-агенты · Платформы · Солянка</p>
    <div id="lastUpdated"></div>
  </header>

  <nav class="cat-grid">
{cards}  </nav>

  <footer>
    Автосборщик новостей о мире AI · <a href="about/index.html" style="color:var(--text2)">ℹ️ О проекте</a>
  </footer>
</div>
<script>
document.getElementById('lastUpdated').textContent =
    'Обновлено: {build_time} (МСК)' + ' · всего {total} новостей';
</script>
</body>
</html>"""
    write_if_changed(os.path.join(BASE_DIR, "index.html"), html)
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

    # Копируем статичные страницы (about)
    src_about = os.path.join(BASE_DIR, "about")
    if os.path.isdir(src_about):
        shutil.copytree(src_about, os.path.join(dist, "about"), dirs_exist_ok=True)

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

    # 2. Загружаем существующие новости (чтобы не потерять ручные правки).
    #    Устаревшие заказы (не про ИИ и не про сайты) отбрасываем — иначе
    #    старый мусор из накопителя возвращался бы в каждую сборку.
    dropped = 0
    for key in CATEGORIES:
        fpath = os.path.join(BASE_DIR, key, "news.json")
        for item in load_news(fpath):
            if item.get("cat") == "orders" and not is_ai_order(item.get("title", ""), item.get("desc", "")):
                dropped += 1
                continue
            if item["link"] not in seen_links:
                all_news.append(item)
                seen_links.add(item["link"])
    if dropped:
        print(f"  [чистка] отброшено устаревших заказов: {dropped}")

    # 3. Фильтр по дате
    cutoff = now_msk() - timedelta(days=MAX_AGE_DAYS)
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
