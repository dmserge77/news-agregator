"""Тесты правил отбора: ключевые слова, раскладка по рубрикам, вакансии.

Запуск из корня проекта:

    python -m unittest discover -s tests -v

Здесь зафиксированы ловушки, на которые мы уже наступали. Каждая проверка —
это реальный случай, найденный замером на архиве, а не выдуманный пример.
Если тест падает после правки правил — значит правка вернула старый баг.
"""

import os
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
