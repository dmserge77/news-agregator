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


class Misc(unittest.TestCase):
    """Подрубрики «Солянки»."""

    def test_subtypes_are_known(self):
        self.assertEqual(c.classify_misc("Смешная история про нейросети", ""), "curio")
        self.assertEqual(c.classify_misc("Вышел релиз библиотеки", ""), "raznoe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
