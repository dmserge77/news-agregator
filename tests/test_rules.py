"""Тесты правил отбора: ключевые слова, раскладка по рубрикам, вакансии.

Запуск из корня проекта:

    python -m unittest discover -s tests -v

Здесь зафиксированы ловушки, на которые мы уже наступали. Каждая проверка —
это реальный случай, найденный замером на архиве, а не выдуманный пример.
Если тест падает после правки правил — значит правка вернула старый баг.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import collector as c


# Описание вакансии hh.ru как оно приходит на самом деле: «Вакансия компании»
# и «Центральный офис» есть в каждой записи. Именно из-за слова «компании»
# короткий ключ «ии» давал ложный признак ИИ.
HH_DESC = ("Вакансия компании: ООО «Ромашка». Регион: Москва. "
           "Центральный офис. Требуемый опыт работы: без опыта.")


class KeywordBoundaries(unittest.TestCase):
    """Короткие ключи ищутся словом целиком, а не вхождением."""

    def test_ii_inside_a_russian_word_is_not_a_match(self):
        # «ии» сидит внутри «компании», «акции», «функции», «России».
        for word in ("вакансия компании ромашка", "курс акции вырос",
                     "функции организма", "новости россии"):
            self.assertFalse(c._kw_hit(word, "ии"), word)

    def test_ii_as_an_abbreviation_is_a_match(self):
        for text in ("про ии", "ии-агент", "ии.", "(ии)", "ии,", "ии"):
            self.assertTrue(c._kw_hit(text, "ии"), text)

    def test_ii_with_a_non_breaking_hyphen_is_a_match(self):
        # В русских текстах пишут «ИИ‑компаниям» через U+2011, а не через «-».
        # Прежние ключи «ии-», «ии », «ии,», «ии.» такой текст не находили.
        self.assertTrue(c._kw_hit("ии\u2011компаниям", "ии"))

    def test_ui_inside_guix_and_build_is_not_a_match(self):
        # Из-за этого 32 записи висели в «Дизайне» без единого слова про дизайн.
        for word in ("guix", "build", "buildup", "guitar"):
            self.assertFalse(c._kw_hit(word, "ui"), word)

    def test_ui_as_a_word_is_a_match(self):
        for text in ("ui", "ui/ux", "ui-кит", "uis"):
            self.assertTrue(c._kw_hit(text, "ui"), text)

    def test_ux_inside_linux_is_not_a_match(self):
        self.assertFalse(c._kw_hit("linux", "ux"))
        self.assertTrue(c._kw_hit("ux", "ux"))

    def test_cline_inside_decline_is_not_a_match(self):
        self.assertFalse(c._kw_hit("акции компании decline растут", "cline"))
        self.assertTrue(c._kw_hit("cline выпустили desktop", "cline"))

    def test_rag_inside_storage_is_not_a_match(self):
        # «rag» сидит внутри «storage» — вхождением тянуло бы всё про SSD.
        self.assertFalse(c._kw_hit("storage 4tb ssd", "rag"))
        self.assertTrue(c._kw_hit("rag для базы знаний", "rag"))

    def test_plural_acronyms_are_still_found(self):
        # Хвостовая «s» в проверке нужна: это самые частые формы.
        self.assertTrue(c._kw_hit("сравнение llms", "llm"))
        self.assertTrue(c._kw_hit("apis и sdk", "api"))
        self.assertTrue(c._kw_hit("сравнение gpts", "gpt"))

    def test_russian_stems_are_still_found_by_substring(self):
        # Русские ключи — это основы, их ищем вхождением: «нейросет» должно
        # находиться и в «нейросети», и в «нейросетевой».
        self.assertTrue(c._kw_hit("нейросети", "нейросет"))
        self.assertTrue(c._kw_hit("нейросетевой дизайн", "нейросет"))


class Classify(unittest.TestCase):
    """Раскладка по рубрикам: узкая рубрика важнее «Нейросетей»."""

    def test_vibe_beats_the_broad_ai_category(self):
        # «Вайбкодинг» не обновлялся с 11.09 ровно из-за этого: в «Нейросетях»
        # ключевых слов в разы больше, и упоминание LLM перевешивало cursor.
        text = ("cursor и github copilot: как нейросети, llm, gpt, openai и claude "
                "меняют вайбкодинг и генерацию кода")
        self.assertEqual(c.classify(text, "ai"), "vibe")

    def test_agent_beats_the_broad_ai_category(self):
        text = "ии-агент на mcp-сервер: llm, gpt, openai, claude, нейросети"
        self.assertEqual(c.classify(text, "ai"), "agent")

    def test_cursor_goes_to_vibe(self):
        self.assertEqual(c.classify("чем заменить cursor 2", "ai"), "vibe")
        self.assertEqual(c.classify("cline выпустили desktop версию", "ai"), "vibe")

    def test_agent_articles_go_to_agent(self):
        self.assertEqual(c.classify("mcp-сервер для агента", "ai"), "agent")
        self.assertEqual(c.classify("ии-агенты в обучении персонала", "ai"), "agent")

    def test_design_still_works(self):
        self.assertEqual(c.classify("дизайн интерфейсов в figma", "ai"), "design")
        self.assertEqual(c.classify("гайд по ux для новичков", "ai"), "design")

    def test_ai_articles_go_to_ai(self):
        self.assertEqual(c.classify("сравнение llms и gpts", "ai"), "ai")
        self.assertEqual(c.classify("openai выпустила api", "ai"), "ai")
        self.assertEqual(c.classify("компании внедряют нейросети в поддержку", "ai"), "ai")

    def test_ai_abbreviations_are_recognised(self):
        self.assertEqual(c.classify("как мы сделали rag, который почти не галлюцинирует", "ai"), "ai")
        self.assertEqual(c.classify("перевод asr-моделей на русский", "ai"), "ai")

    def test_junk_is_rejected(self):
        # Всё это раньше уезжало в «Нейросети» из-за ложных подстрок.
        junk = [
            "как поставить linux и собрать build",
            "почему акции компании decline растут",
            "в таиланде обнаружили дьявольский цветок: ему не нужен свет",
            "storage для жёстких дисков",
            "настройка ragtime сервера",
        ]
        for text in junk:
            self.assertIsNone(c.classify(text, "ai"), text)


class DesignFeedDefaultCat(unittest.TestCase):
    """Ленты дизайна не разбрасываются по «Солянке».

    Статья «The Bull And Bear Case For Digital Design In The Age Of AI» пришла
    из ленты Smashing Magazine, признак ИИ в ней есть, а слова «дизайн» — нет:
    в словаре есть «web design» и «design system», но не голое «design».
    Такая запись уезжала в «Солянку», из-за чего рубрика «Дизайн» молчала.
    Причина — параметр default_cat в classify() не использовался вообще.
    """

    # Текст без единого слова из словаря дизайна, но с признаком ИИ.
    SAME_TEXT = ("the bull and bear case for digital design in the age of ai: "
                 "what changes for teams and how to prepare")

    def test_design_feed_keeps_its_own_category(self):
        self.assertEqual(c.classify(self.SAME_TEXT, "design"), "design")

    def test_other_feeds_still_go_to_misc(self):
        # Тот же текст из обычной ленты — по-прежнему «Солянка». Расширять
        # правило на все ленты нельзя: замерено, что это перетряхнуло бы
        # 215 записей («Солянка → Платформы» 65, «Солянка → Нейросети» 58).
        self.assertEqual(c.classify(self.SAME_TEXT, "ai"), "misc")
        self.assertEqual(c.classify(self.SAME_TEXT, "platform"), "misc")

    def test_trusted_list_is_only_design(self):
        self.assertEqual(c.DEFAULT_CAT_TRUSTED, {"design"})

    def test_default_cat_is_actually_used(self):
        # Ловушка: параметр однажды уже был объявлен и не использовался ни разу.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "collector.py"), encoding="utf-8") as f:
            source = f.read()
        body = source.split("def classify(")[1].split("\ndef ")[0]
        self.assertIn("default_cat", body,
                      "default_cat объявлен, но в теле classify() не используется")


class DesignSources(unittest.TestCase):
    """Awwwards убран, UX Planet, Figma и Webflow подключены (18.09.2026)."""

    def test_awwwards_is_not_in_feeds(self):
        sources = {f["source"] for f in c.FEEDS}
        self.assertNotIn("Awwwards", sources)
        # В DEAD_SOURCES его быть не должно: записи доживают 90 дней сами,
        # удалять их не за чем.
        self.assertNotIn("Awwwards", c.DEAD_SOURCES)

    def test_ux_planet_is_connected_to_design(self):
        feeds = {f["source"]: f for f in c.FEEDS}
        self.assertIn("UX Planet", feeds)
        self.assertEqual(feeds["UX Planet"]["cat"], "design")

    def test_figma_and_webflow_are_connected_to_design(self):
        feeds = {f["source"]: f for f in c.FEEDS}
        for name in ("Figma", "Webflow"):
            self.assertIn(name, feeds)
            self.assertEqual(feeds[name]["cat"], "design", name)

    def test_figma_feed_is_the_atom_address(self):
        # /blog/feed/ отдаёт 404 — лента лежит по /blog/feed/atom.xml,
        # из-за этого её раньше не находили.
        feeds = {f["source"]: f for f in c.FEEDS}
        self.assertTrue(feeds["Figma"]["url"].endswith("/blog/feed/atom.xml"),
                        feeds["Figma"]["url"])

    def test_website_builders_are_in_the_dictionary(self):
        # Русское название темы, которого в словаре не было.
        self.assertIn("конструктор сайт", c.CAT_KEYWORDS["design"])
        # Названия самих конструкторов: webflow и тильда.
        self.assertIn("webflow", c.CAT_KEYWORDS["design"])
        self.assertIn("тильд", c.CAT_KEYWORDS["design"])

    def test_every_feed_has_a_known_category(self):
        for feed in c.FEEDS:
            self.assertIn(feed["cat"], c.CATEGORIES, feed["source"])

    def test_feed_addresses_are_https(self):
        for feed in c.FEEDS:
            self.assertTrue(feed["url"].startswith("https://"), feed["url"])


class AiSignal(unittest.TestCase):
    """Проверка «это вообще про ИИ»."""

    def test_positive(self):
        for text in ("rag для базы знаний", "asr-модель для русского", "ии-агент",
                     "нейросети", "обучение модели", "про ai",
                     # «ИИ» — самое ходовое сокращение, его проверка обязана знать.
                     "techcrunch выпустило глоссарий по ии",
                     "ии\u2011компаниям пригрозили судом"):
            self.assertTrue(c.has_ai_signal(text.lower()), text)

    def test_negative(self):
        for text in ("storage 4tb ssd", "как собрать guix", "курс акции вырос",
                     "вакансия компании: ооо ромашка"):
            self.assertFalse(c.has_ai_signal(text.lower()), text)

    def test_ii_inside_a_word_is_not_a_signal(self):
        # Регрессия на «компании», «акции», «функции»: там «ии» — часть слова.
        self.assertFalse(c.has_ai_signal("функции организма"))
        self.assertFalse(c.has_ai_signal("новости россии"))

    def test_jobs_and_orders_skip_the_ai_check(self):
        # У вакансий и заказов свои фильтры.
        self.assertTrue(c.is_ai_relevant("что угодно", "jobs"))
        self.assertTrue(c.is_ai_relevant("что угодно", "orders"))

    def test_unknown_category_is_rejected(self):
        self.assertFalse(c.is_ai_relevant("нейросети", "несуществующая"))

    def test_household_false_positives_are_rejected(self):
        self.assertFalse(c.is_ai_relevant("стиральная машина с ии", "ai"))


class MlTerm(unittest.TestCase):
    """«ML» — сокращение темы ИИ, как «RAG» и «NLP» (добавлено 17.09.2026).

    Без него вакансии «Python + ML разработчик» и «Data scientist (Junior)»
    проходили в рубрику не по теме, а по слову «инженер» / «data» из
    технического списка. Ищем отдельным словом — тогда «html» и «xml»
    по-прежнему не считаются ИИ, хотя «ml» внутри них и есть.
    """

    def test_ml_is_a_signal(self):
        for text in ("ml-инженер", "python + ml разработчик", "ml engineer",
                     "data scientist (ml)", "mls"):
            self.assertTrue(c.has_ai_signal(text.lower()), text)

    def test_ml_inside_a_word_is_not_a_signal(self):
        # Главная ловушка: «ml» сидит внутри «html» и «xml».
        for text in ("верстка html", "парсер xml", "saml-авторизация",
                     "вёрстка и html5"):
            self.assertFalse(c.has_ai_signal(text.lower()), text)

    def test_ml_is_not_duplicated_in_the_tech_list(self):
        # «ml» переехало в AI_TERMS_WORD, и в хвостовом _has_word его быть
        # не должно: два списка с одним словом — это будущая рассинхронизация.
        src_path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "collector.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('_has_word(text, ["qa", "ui", "ux"])', src)


class VibeKeywords(unittest.TestCase):
    """Словарь «Вайбкодинга» (расширен 17.09.2026).

    Рубрика почти не обновлялась не из-за источников, а из-за словаря:
    статья «Куда уходят токены у кодинг-агента» не попадала никуда — слова
    «нейросет» в ней нет, а «кодинг-агент» в списке ключей не было. Замер
    по 36 лентам: новые ключи дают +40 записей из уже подключённых лент.
    """

    def test_coding_agent_articles_are_vibe(self):
        for title in ("Куда уходят токены у кодинг-агента: разбираем счёт по полям usage",
                      "Codex CLI через свой endpoint: config.toml по строкам",
                      "Как перенести навайбкоженный проект в Figma через Claude Code",
                      "Give Your Coding Agents a Memory You Own",
                      "Vercel Sandbox now supports Devin Outposts"):
            self.assertEqual(c.classify(title.lower(), "vibe"), "vibe", title)

    def test_aider_is_a_whole_word(self):
        # «aider» — инструмент ИИ-кодинга, но внутри «raider» он ни при чём.
        self.assertEqual(c.classify("aider для рефакторинга", "vibe"), "vibe")
        self.assertIsNone(c.classify("raider game про рейды", "vibe"))

    def test_old_vibe_keys_still_work(self):
        for title in ("vibe coding для продакшена", "Replit запустил новую версию",
                      "cursor обновился", "github copilot в редакторе"):
            self.assertEqual(c.classify(title.lower(), "vibe"), "vibe", title)


class NonAiJobDirections(unittest.TestCase):
    """1С и информационная безопасность — не про ИИ (17.09.2026).

    Их вакансии проходили только по слову «программист» / «инженер» из
    технического списка. Сузить сам список нельзя: на нём же держится
    «Вайбкодер/Программист-разработчик». Поэтому отдельное правило — и только
    для вакансий без собственного признака ИИ.
    """

    def test_non_ai_directions_are_rejected(self):
        for title in ("Программист-консультант 1С (стажер)",
                      "Младший инженер информационной безопасности (Junior InfoSec Engineer)",
                      "Специалист по кибербезопасности (стажер)"):
            self.assertFalse(c.is_real_ai_job(title, HH_DESC), title)

    def test_ai_vacancies_in_the_same_directions_survive(self):
        # У них признак ИИ свой, поэтому правило до них не доходит.
        for title in ("ML-инженер в области кибербезопасности",
                      "Data scientist (Junior) в консалтинг",
                      "Python + ML разработчик (стажер)",
                      "Вайбкодер/Программист-разработчик"):
            self.assertTrue(c.is_real_ai_job(title, HH_DESC), title)

    def test_one_c_is_a_whole_word(self):
        # «1с» не должно находиться внутри «21сентября»: иначе правило
        # выкосило бы обычные технические вакансии. Проверяем саму регулярку.
        pattern = [p for p in c.NON_AI_JOB_DIRECTIONS if "1с" in p][0]
        self.assertIsNone(re.search(pattern, "программист 21сентября"))
        self.assertIsNone(re.search(pattern, "программист 100с"))
        self.assertIsNotNone(re.search(pattern, "программист 1с (стажер)"))
        self.assertIsNotNone(re.search(pattern, "1с-битрикс разработчик"))


class AiSignalHeadWindow(unittest.TestCase):
    """У обычных техноизданий признак ИИ ищется только в начале материала.

    Они пишут обо всём подряд, и слово про ИИ у них часто стоит вскользь —
    в конце длинного описания. Из-за этого в «Нейросети» уезжали обзоры
    iPhone, прошивка PlayStation и Samsung One UI.

    Замер 17.09.2026 по 36 живым лентам: окно в 200 знаков отсекает ровно
    девять таких записей (список в OFFTopic ниже) и не теряет ни одной
    настоящей статьи про ИИ. Правило точечное: сделать его общим нельзя —
    это убило бы 52 записи Replit про вайбкодинг (см. test_replit_...).
    """

    # Описание техноиздания: длинное, а слово про ИИ — в самом конце.
    PADDING = "Обзор устройства и его характеристик. " * 8
    TAIL = (" Подробности о ценах и сроках поставки появятся позже. "
            "Отдельно отметим работу встроенных нейросетей и чат-ботов.")

    # Девять записей, на которых правило замерено: заголовок, источник, рубрика.
    OFFTopic = [
        ("Sony обновила прошивку PlayStation 5: главные изменения сентябрьского апдейта",
         "Hi-Tech Mail", "ai"),
        ("Samsung начала выпуск One UI 9 для Galaxy S26 — оболочка основана на Android 16",
         "Rusbase", "ai"),
        ("iQOO запускает в России технологический чемпионат «Смарт Кон»",
         "Hi-Tech Mail", "ai"),
        ("Российские ученые обнаружили необычное в атмосфере Земли",
         "Hi-Tech Mail", "ai"),
        ("Internet Archive оказался под атакой ботов и стал блокировать обычных пользователей",
         "3DNews", "ai"),
        ("Apple устранила рекордное число уязвимостей в iOS и других программных продуктах",
         "3DNews", "ai"),
        ("В сети вышли первые обзоры iPhone 18 Pro и iPhone 18 Pro Max",
         "Hi-Tech Mail", "misc"),
        ("Meta* выпустит очки без камер: для тех, кто боится слежки",
         "Hi-Tech Mail", "agent"),
        ("Открытие китайских учёных кратно ускорит производство водорода солнечным светом",
         "3DNews", "ai"),
    ]

    def long_desc(self):
        return self.PADDING + self.TAIL

    def test_window_is_two_hundred(self):
        self.assertEqual(c.AI_SIGNAL_HEAD_LEN, 200)

    def test_the_offtopic_nine_are_rejected(self):
        for title, source, cat in self.OFFTopic:
            check = c.ai_check_text(title, self.long_desc(), source)
            self.assertFalse(c.is_ai_relevant(check, cat), f"{source}: {title}")

    def test_the_same_text_would_have_passed_by_the_old_rule(self):
        # Без обрезки признак ИИ находится — значит отсекает именно окно,
        # а не какой-то другой фильтр.
        for title, source, cat in self.OFFTopic:
            full = c.ai_check_text(title, self.long_desc(), "Habr AI")
            self.assertTrue(c.is_ai_relevant(full, cat), title)

    def test_genuine_ai_articles_from_the_same_sources_survive(self):
        good = [
            ("Названы лучшие нейросети для создания видео", "Hi-Tech Mail"),
            ("Nvidia представила нейросеть для генерации видео", "3DNews"),
            ("Стартап привлёк 10 млн на ИИ-сервис для логистики", "Rusbase"),
            ("Как мы внедрили LLM в код-ревью", "Tproger"),
            ("Что умеют нейросети в 2026 году", "The Code"),
        ]
        for title, source in good:
            check = c.ai_check_text(title, self.long_desc(), source)
            self.assertTrue(c.is_ai_relevant(check, "ai"), title)

    def test_a_short_description_is_not_cut(self):
        # Обрезаем только длинные описания: короткое попадает в окно целиком.
        check = c.ai_check_text("Обзор смартфона", "Внутри работает нейросеть для фото.",
                                "Hi-Tech Mail")
        self.assertIn("нейросеть", check)
        self.assertTrue(c.is_ai_relevant(check, "ai"))

    def test_the_title_is_never_cut(self):
        # Признак ИИ в заголовке — всегда по делу, как бы длинно он ни звучал.
        title = "Как нейросети меняют разработку: разбор" + " с примерами" * 20
        check = c.ai_check_text(title, "Описание без темы.", "Hi-Tech Mail")
        self.assertIn("нейросети меняют разработку", check)
        self.assertTrue(c.is_ai_relevant(check, "ai"))

    def test_other_sources_still_see_the_whole_text(self):
        # У профильных лент ничего не меняется: там признак ИИ в конце — норма.
        for source in ("Habr AI", "Habr ML", "vc.ru", "DTF", "Hacker News"):
            check = c.ai_check_text("Заголовок", self.long_desc(), source)
            self.assertIn("нейросетей", check, source)

    def test_replit_is_not_in_the_strict_list(self):
        # Общее правило («сужаем всем, кроме ИИ-лент») замерено и отброшено:
        # оно теряло 52 живые записи Replit — они как раз про вайбкодинг.
        self.assertNotIn("Replit", c.AI_SIGNAL_HEAD_SOURCES)

    def test_strict_list_is_exactly_the_measured_sources(self):
        self.assertEqual(c.AI_SIGNAL_HEAD_SOURCES,
                         {"Hi-Tech Mail", "3DNews", "Rusbase", "Tproger", "The Code"})

    def test_parse_rss_drops_the_offtopic_from_tech_media(self):
        feed = {"url": "https://hi-tech.mail.ru/rss/all/", "cat": "misc",
                "source": "Hi-Tech Mail"}
        self.assertEqual(c.parse_rss(self.deep_rss(), feed), [])

    def test_parse_rss_keeps_the_same_record_for_another_source(self):
        # Тот же текст, но источник профильный — запись на месте.
        feed = {"url": "https://habr.com/ru/rss/hub/artificial_intelligence/?fl=ru",
                "cat": "ai", "source": "Habr AI"}
        items = c.parse_rss(self.deep_rss(), feed)
        self.assertEqual(len(items), 1)

    def deep_rss(self):
        title, _, _ = self.OFFTopic[0]
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                '<rss version="2.0"><channel><item>'
                f"<title>{title}</title>"
                "<link>https://example.com/ps5</link>"
                f"<description>{self.long_desc()}</description>"
                "<pubDate>Wed, 16 Sep 2026 10:00:00 GMT</pubDate>"
                "</item></channel></rss>")


class Jobs(unittest.TestCase):
    """Вакансии: только удалёнка, по-русски и «попроще»."""

    def test_simple_jobs_pass(self):
        good = [
            ("Стажер ML-разработчик (LLM / AI Agents)", HH_DESC),
            ("Разметчик данных для нейросетей", HH_DESC),
            ("Junior Backend разработчик", HH_DESC),
            ("AI-тренер по обучению нейросетей", HH_DESC),
            ("Бизнес-ассистент с нейросетями и вайб-кодингом", HH_DESC),
            ("Стажёр AI-дизайнер", HH_DESC),
            ("AI-помощник / Креатор коротких AI-видео", HH_DESC),
            ("Вайбкодер/Программист-разработчик", HH_DESC),
            ("Младший разработчик чат-ботов", HH_DESC),
        ]
        for title, desc in good:
            self.assertTrue(c.is_real_ai_job(title, desc), title)

    def test_interns_and_students_are_welcome(self):
        # Пользователь: «наоборот по проще оставляй стажер, без опыта, студент».
        for title in ("Стажёр-разметчик данных для нейросетей",
                      "Ассистент по обучению нейросетей (без опыта)",
                      "Студент-практикант: чат-боты и нейросети"):
            self.assertTrue(c.is_real_ai_job(title, HH_DESC), title)

    def test_senior_jobs_are_rejected(self):
        # «нам не надо супер крутые вакансии, инженера всякие синьоры,
        #  руководители, нам ченть по проще».
        bad = [
            "Senior ML Engineer",
            "Ведущий разработчик нейросетей",
            "Руководитель отдела машинного обучения",
            "Архитектор AI-платформы",
            "Team Lead (LLM)",
            "Главный инженер по данным",
            "Начальник отдела ИИ",
        ]
        for title in bad:
            self.assertFalse(c.is_real_ai_job(title, HH_DESC), title)

    def test_english_titles_are_rejected(self):
        self.assertFalse(c.is_real_ai_job("Machine Learning Engineer", HH_DESC))

    def test_hybrid_is_not_remote(self):
        self.assertFalse(c.is_real_ai_job(
            "ML-разработчик", HH_DESC + " Формат работы: гибрид."))

    def test_courses_are_not_vacancies(self):
        for title in ("Курс по нейросетям", "Школа AI-разработки", "Интенсив по LLM"):
            self.assertFalse(c.is_real_ai_job(title, HH_DESC), title)

    def test_non_it_professions_are_rejected(self):
        for title in ("Продавец-консультант", "Курьер", "Менеджер по продажам",
                      "Повар", "HR-специалист"):
            self.assertFalse(c.is_real_ai_job(title, HH_DESC), title)

    def test_the_hh_template_alone_is_not_an_ai_signal(self):
        # Регрессия на «ии» внутри «компании»: раньше шаблонное описание hh.ru
        # само по себе считалось признаком ИИ, и проходило вообще всё.
        self.assertFalse(c.is_real_ai_job("Офис-менеджер", HH_DESC))

    # Известный пробел, решения пока нет: tech_words пропускает технические,
    # но не ИИ-вакансии — «Программист-консультант 1С (стажер)», «Младший
    # инженер информационной безопасности». Сузить список нечем: на этих же
    # словах держится проход «Вайбкодер/Программист-разработчик».
    # Тест намеренно не написан, чтобы не закреплять спорное поведение.


class LongDescriptions(unittest.TestCase):
    """Профессия и уровень проверяются по заголовку, а не по длинному описанию.

    У «Работы России» описание — это текст обязанностей на несколько абзацев.
    В нём всегда найдутся «контент», «эксперт» и «университет», и проверка
    по всему тексту отбивала вакансии их же собственными обязанностями.
    Поэтому источник передаёт role_text=title.
    """

    # Реальное описание вакансии «AI-тренер для обучения нейросетей».
    DUTY = ("Ищем внимательных специалистов, которые помогут ИИ отвечать понятнее. "
            "Вам предстоит исследовать ответы, искать изъяны и предлагать идеи. "
            "Работа с контентом, оценка качества текстов. Высшее образование, "
            "университет. Опыт эксперта в предметной области приветствуется.")

    def test_role_text_saves_a_good_vacancy(self):
        title = "AI-тренер для обучения нейросетей"
        self.assertTrue(c.is_real_ai_job(title, self.DUTY, role_text=title))

    def test_without_role_text_the_same_vacancy_is_lost(self):
        # Так было до правки: слово «эксперт» из обязанностей отбивало вакансию.
        title = "AI-тренер для обучения нейросетей"
        self.assertFalse(c.is_real_ai_job(title, self.DUTY))

    def test_junk_profession_is_still_rejected_by_its_title(self):
        for title in ("Уборщик территорий", "Водитель автомобиля",
                      "Менеджер по работе с клиентами", "Офис-менеджер"):
            self.assertFalse(c.is_real_ai_job(title, self.DUTY, role_text=title), title)

    def test_senior_is_still_rejected_by_its_title(self):
        for title in ("Главный специалист по обучению нейросетей",
                      "Руководитель отдела машинного обучения"):
            self.assertFalse(c.is_real_ai_job(title, self.DUTY, role_text=title), title)

    def test_topic_is_still_checked_over_the_whole_text(self):
        # Описание всё ещё участвует — но только в проверке темы.
        self.assertTrue(c.is_real_ai_job("Разметчик", "Разметка данных для нейросетей",
                                         role_text="Разметчик"))
        self.assertFalse(c.is_real_ai_job("Специалист", "Уборка помещений",
                                          role_text="Специалист"))


class LinkPreview(unittest.TestCase):
    """Метки предпросмотра ссылки (Open Graph) в шапке страниц.

    Мессенджеры не выполняют JS и содержимое страницы не читают: карточку
    предпросмотра они собирают только из этих меток. Пока их не было, при
    вставке ссылки была видна одна серая строка адреса.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(cls.root, "_category_template.html"), encoding="utf-8") as f:
            cls.template = f.read()

    @staticmethod
    def _meta_names(text):
        """Имена меток: og:*, twitter:* и description. Значения не смотрим."""
        names = set(re.findall(r'(?:property|name)="([^"]+)"', text))
        return {n for n in names
                if n.startswith("og:") or n.startswith("twitter:") or n == "description"}

    def test_addresses_are_absolute(self):
        # Относительный путь мессенджер не разберёт: сайт лежит в подпапке
        # /news-agregator/, и «og-image.png» он бы не нашёл.
        self.assertTrue(c.SITE_URL.startswith("https://"))
        self.assertTrue(c.OG_IMAGE.startswith(c.SITE_URL + "/"))

    def test_image_url_ends_with_png(self):
        # SVG и data:-адреса в og:image не принимает ни Telegram, ни VK.
        self.assertTrue(c.OG_IMAGE.endswith(".png"))

    def test_template_carries_the_meta_block(self):
        for tag in ('property="og:title"', 'property="og:description"',
                    'property="og:image"', 'property="og:url"',
                    'property="og:type"', 'property="og:site_name"',
                    'property="og:locale"', 'name="twitter:card"',
                    'name="description"'):
            self.assertIn(tag, self.template, tag)

    def test_main_page_and_template_carry_the_same_tags(self):
        # Метки лежат в двух местах: шаблон рубрик и сборщик главной. Разошлись —
        # половина сайта уехала бы с неполной карточкой.
        block = c.og_meta_block(c.OG_MAIN_TITLE, c.OG_MAIN_DESC, c.SITE_URL + "/")
        self.assertEqual(self._meta_names(block), self._meta_names(self.template))

    def test_about_page_carries_the_same_tags(self):
        with open(os.path.join(self.root, "about", "index.html"), encoding="utf-8") as f:
            about = f.read()
        self.assertEqual(self._meta_names(about), self._meta_names(self.template))

    def test_rendered_category_page_has_absolute_addresses(self):
        html = c.render_category_page("design", c.CATEGORIES["design"])
        self.assertIn(f'property="og:url" content="{c.SITE_URL}/design/"', html)
        self.assertIn(f'property="og:image" content="{c.OG_IMAGE}"', html)

    def test_rendered_page_keeps_no_placeholder(self):
        # Незаменённая подстановка видна прямо на странице как «%%OG_TITLE%%».
        for key, info in c.CATEGORIES.items():
            html = c.render_category_page(key, info)
            self.assertNotIn("%%", html, key)

    def test_every_category_has_its_own_description(self):
        # Общий текст вместо своего — признак, что рубрику завели, а описание
        # для карточки предпросмотра забыли.
        for key in c.CATEGORIES:
            self.assertIn(key, c.CAT_OG_DESC, key)

    def test_quotes_in_the_description_are_escaped(self):
        # Кавычка разорвала бы атрибут content="...".
        block = c.og_meta_block('тест "кавычка"', 'тест "кавычка"', c.SITE_URL)
        self.assertIn("&quot;кавычка&quot;", block)

    def test_image_file_is_in_the_project(self):
        path = os.path.join(self.root, "og-image.png")
        self.assertTrue(os.path.exists(path), "нет og-image.png")
        with open(path, "rb") as f:
            head = f.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n", "это не PNG")
        # Размер читаем из заголовка PNG — без сторонних библиотек.
        self.assertEqual((int.from_bytes(head[16:20], "big"),
                          int.from_bytes(head[20:24], "big")), (1200, 630))

    def test_image_is_not_too_heavy(self):
        # Telegram не принимает картинку тяжелее 5 МБ.
        self.assertLess(os.path.getsize(os.path.join(self.root, "og-image.png")),
                        5 * 1024 * 1024)

    def test_build_dist_copies_the_image(self):
        # В dist/ попадает только перечисленное в build_dist. Забыли строку —
        # og:image ведёт на несуществующий файл, и карточка выходит без картинки.
        with open(os.path.join(self.root, "collector.py"), encoding="utf-8") as f:
            src = f.read()
        body = src.split("def build_dist(")[1].split("\ndef ")[0]
        self.assertIn("og-image.png", body)


class ApiText(unittest.TestCase):
    """Приведение полей API «Работы России» к строке."""

    def test_none_becomes_empty(self):
        self.assertEqual(c._api_text(None), "")

    def test_plain_string_passes_through(self):
        self.assertEqual(c._api_text("AI-тренер"), "AI-тренер")

    def test_dict_becomes_joined_strings(self):
        # `requirement` приходит словарём, а не строкой. Без этого в описание
        # попадал бы repr словаря.
        value = {"education": "Высшее образование — бакалавриат", "experience": 4}
        self.assertEqual(c._api_text(value), "Высшее образование — бакалавриат")

    def test_nested_values_do_not_leak(self):
        self.assertNotIn("{", c._api_text({"education": "Высшее", "extra": {"a": 1}}))


class Misc(unittest.TestCase):
    """Подрубрики «Солянки»."""

    def test_subtypes_are_known(self):
        self.assertEqual(c.classify_misc("Смешная история про нейросети", ""), "curio")
        self.assertEqual(c.classify_misc("Вышел релиз библиотеки", ""), "raznoe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
