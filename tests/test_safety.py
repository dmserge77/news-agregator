"""Тесты безопасности: чужой текст из лент не должен становиться кодом.

Запуск из корня проекта:

    python -m unittest discover -s tests -v

Агрегатор публикует чужой текст. Заголовок из ленты попадает в карточку,
карточка собирается строкой и вставляется через innerHTML — значит
неэкранированный заголовок вида <img src=x onerror=...> выполнится
у каждого посетителя сайта.

Защита стоит в два эшелона, и оба проверяются здесь:
  * сборщик чистит текст на входе (strip_html, safe_link);
  * шаблон экранирует на выходе (esc, safeUrl).

Проверки на Python не ловят ошибку в JS, поэтому отдельный тест-сторож
смотрит сам шаблон: перед каждым чужим полем в HTML-строке обязан стоять esc().
"""

import os
import re
import ssl
import unittest
from unittest import mock

sys_path_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sys
sys.path.insert(0, sys_path_root)

import collector as c

TEMPLATE_PATH = os.path.join(sys_path_root, "_category_template.html")

# Лента с враждебным заголовком. После unescape из &lt;img&gt; получается
# настоящий тег — именно на этом ломалась первая версия чистки.
XSS_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>&lt;img src=x onerror="alert(1)"&gt;Новости про ИИ</title>
<link>https://example.com/1</link>
<description>Разбор нейросетей и LLM</description>
<pubDate>Wed, 16 Sep 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""

# Ссылка, которая начинается с https, но вылезает из атрибута href.
QUOTE_BREAK_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
<title>Новости про ИИ</title>
<link>https://example.com/" onmouseover="alert(1)</link>
<description>Разбор нейросетей и LLM</description>
<pubDate>Wed, 16 Sep 2026 10:00:00 GMT</pubDate>
</item>
</channel></rss>"""

TEST_FEED = {"url": "https://example.com/rss", "cat": "ai", "source": "Test"}


class StripHtml(unittest.TestCase):
    """Теги вырезаются из заголовка, а сам заголовок не обрезается."""

    def test_tag_is_removed(self):
        self.assertEqual(c.strip_html("<b>Жирный</b> текст"), "Жирный текст")

    def test_tag_returned_by_unescape_is_removed(self):
        # Одна замена до unescape бесполезна: тег появляется уже после неё,
        # и без второй чистки он уходит в карточку как есть.
        self.assertEqual(c.strip_html("&lt;img src=x onerror=alert(1)&gt;ИИ"), "ИИ")

    def test_angle_brackets_never_survive(self):
        for raw in ("<script>alert(1)</script>",
                    "&lt;script&gt;alert(1)&lt;/script&gt;",
                    "a < b > c",
                    "<<b>>текст"):
            clean = c.strip_html(raw)
            self.assertNotIn("<", clean, raw)
            self.assertNotIn(">", clean, raw)

    def test_long_title_is_not_truncated(self):
        # Описание обрезается до 300 символов, заголовок — никогда.
        long_title = "Очень длинный заголовок про нейросети " * 20
        clean = c.strip_html(long_title)
        self.assertGreater(len(clean), 300)
        self.assertEqual(clean, long_title.strip())

    def test_none_becomes_empty(self):
        self.assertEqual(c.strip_html(None), "")


class SafeLink(unittest.TestCase):
    """Ссылка уходит в атрибут href — одной проверки схемы мало."""

    def test_normal_links_pass(self):
        for url in ("https://habr.com/ru/articles/1/",
                    "http://example.com/feed?a=1&b=2",
                    "https://vc.ru/ai/3139979-alisa-ai"):
            self.assertEqual(c.safe_link(url), url, url)

    def test_quote_inside_link_is_rejected(self):
        # Начинается с https, значит проверка схемы её пропустит — но кавычка
        # позволяет вылезти из атрибута и подсунуть обработчик события.
        self.assertEqual(c.safe_link('https://x/" onmouseover="alert(1)'), "")

    def test_whitespace_inside_link_is_rejected(self):
        self.assertEqual(c.safe_link("https://x/ onmouseover=alert(1)"), "")

    def test_dangerous_schemes_are_rejected(self):
        for url in ("javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=",
                    "vbscript:msgbox(1)", "file:///etc/passwd"):
            self.assertEqual(c.safe_link(url), "", url)

    def test_angle_brackets_and_backslash_are_rejected(self):
        self.assertEqual(c.safe_link("https://x/<script>"), "")
        self.assertEqual(c.safe_link("https://x/\\alert"), "")

    def test_none_and_empty_become_empty(self):
        self.assertEqual(c.safe_link(None), "")
        self.assertEqual(c.safe_link(""), "")


class CleanDesc(unittest.TestCase):
    """Описание чистится тем же способом, что и заголовок."""

    def test_tag_is_removed(self):
        self.assertEqual(c.clean_desc("<p>Текст</p>"), "Текст")

    def test_tag_returned_by_unescape_is_removed(self):
        self.assertNotIn("<", c.clean_desc("&lt;img src=x&gt;Текст"))

    def test_long_text_is_truncated(self):
        self.assertTrue(c.clean_desc("слово " * 200).endswith("..."))


class ParseRssIsSafe(unittest.TestCase):
    """Сквозная проверка: после сборщика в записях нет ни одного тега."""

    def test_xss_title_comes_out_clean(self):
        items = c.parse_rss(XSS_RSS, TEST_FEED)
        self.assertEqual(len(items), 1, "запись про ИИ должна была пройти")
        for item in items:
            for field in ("title", "desc"):
                self.assertNotIn("<", item[field], field)
                self.assertNotIn(">", item[field], field)

    def test_link_that_breaks_out_of_href_is_dropped(self):
        # Ссылку починить нельзя — значит запись не берём вовсе.
        self.assertEqual(c.parse_rss(QUOTE_BREAK_RSS, TEST_FEED), [])


class TlsIsChecked(unittest.TestCase):
    """Проверка сертификата не должна вернуться в отключённое состояние."""

    def _context_from_fetch(self):
        seen = {}

        class FakeResponse:
            def read(self, size=None):
                return b"<rss></rss>"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None, context=None):
            seen["ctx"] = context
            return FakeResponse()

        with mock.patch.object(c, "urlopen", fake_urlopen):
            c.fetch_url("https://example.com/rss")
        return seen["ctx"]

    def test_hostname_is_checked(self):
        self.assertTrue(self._context_from_fetch().check_hostname)

    def test_certificate_is_required(self):
        self.assertEqual(self._context_from_fetch().verify_mode, ssl.CERT_REQUIRED)


class FeedSizeLimit(unittest.TestCase):
    """Лента без потолка может отдать гигабайты и уронить сборку."""

    def _read_with(self, payload):
        class FakeResponse:
            def read(self, size=None):
                return payload[:size] if size else payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch.object(c, "urlopen", lambda *a, **k: FakeResponse()):
            return c.fetch_url("https://example.com/rss")

    def test_normal_feed_passes(self):
        self.assertEqual(self._read_with(b"<rss/>"), b"<rss/>")

    def test_oversized_feed_raises(self):
        huge = b"x" * (c.MAX_FEED_BYTES + 10)
        with self.assertRaises(ValueError):
            self._read_with(huge)


class TemplateGuard(unittest.TestCase):
    """Сторож на шаблон: вёрстку правят руками, защиту легко вернуть назад."""

    @classmethod
    def setUpClass(cls):
        with open(TEMPLATE_PATH, encoding="utf-8") as f:
            cls.template = f.read()

    def test_helpers_are_defined(self):
        self.assertIn("function esc(", self.template)
        self.assertIn("function safeUrl(", self.template)

    def test_every_field_in_html_string_is_escaped(self):
        # Строки, из которых собирается HTML. В них чужое поле обязано быть
        # обёрнуто: текст — в esc(), ссылка — в safeUrl().
        markers = ("html +=", "innerHTML", ".href =")
        checked = 0
        for num, line in enumerate(self.template.splitlines(), 1):
            if not any(m in line for m in markers):
                continue
            if "n.title" in line:
                self.assertIn("esc(n.title)", line, f"строка {num}: n.title без esc()")
                checked += 1
            if "n.source" in line:
                self.assertIn("esc(n.source)", line, f"строка {num}: n.source без esc()")
                checked += 1
            if "n.link" in line:
                self.assertIn("safeUrl(n.link)", line, f"строка {num}: n.link без safeUrl()")
                checked += 1
            if "n.date" in line:
                self.assertIn("esc(", line, f"строка {num}: n.date без esc()")
                checked += 1
        self.assertGreaterEqual(checked, 4, "сторож не нашёл ни одной точки вставки")

    def test_modal_uses_text_content_not_html(self):
        # В модалке текст ставится через textContent — это безопасно,
        # и так должно остаться.
        for field in ("mTitle", "mBody"):
            self.assertRegex(self.template,
                             r"getElementById\('" + field + r"'\)\.textContent")

    def test_no_placeholders_left_in_the_template(self):
        """В шаблоне не должно остаться подстановок, которых нет в сборщике.

        Так было с %%CATKEY%%: полосу «Хабр» убрали, а подстановка осталась бы
        видна прямо на странице как «%%CATKEY%%». Сверяем оба списка.
        """
        collector_path = os.path.join(os.path.dirname(TEMPLATE_PATH), "collector.py")
        with open(collector_path, encoding="utf-8") as f:
            collector = f.read()
        in_template = set(re.findall(r"%%[A-Z_]+%%", self.template))
        replaced = set(re.findall(r'"(%%[A-Z_]+%%)"', collector))
        self.assertEqual(in_template, replaced,
                         "подстановки шаблона и сборщика разошлись")


class CollectorHasNoUnsafeReads(unittest.TestCase):
    """Проверки по самому файлу сборщика — на случай отката правки."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(sys_path_root, "collector.py"), encoding="utf-8") as f:
            cls.source = f.read()

    def test_cert_none_is_gone(self):
        self.assertNotIn("CERT_NONE", self.source)
        self.assertNotIn("check_hostname = False", self.source)

    def test_every_title_is_cleaned(self):
        # Заголовок из ленты не должен попадать в запись без strip_html().
        for num, line in enumerate(self.source.splitlines(), 1):
            if re.search(r"title = unescape\(", line):
                self.fail(f"строка {num}: заголовок без strip_html()")
            if re.search(r"title = _api_text\(", line):
                self.fail(f"строка {num}: заголовок без strip_html()")

    def test_every_link_is_cleaned(self):
        for num, line in enumerate(self.source.splitlines(), 1):
            if re.search(r"link = item\.findtext\(", line):
                self.fail(f"строка {num}: ссылка без safe_link()")
            if re.search(r"link = _api_text\(", line):
                self.fail(f"строка {num}: ссылка без safe_link()")


if __name__ == "__main__":
    unittest.main()
