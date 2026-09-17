"""Прогон JS-функций из шаблона в настоящем движке.

Запуск из корня проекта:

    python tests/check_js.py

Юнит-тестов на Python здесь мало: esc() и safeUrl() живут
в `_category_template.html` и выполняются в браузере. Проверять их надо
там же, поэтому функции вырезаются из шаблона (не копируются руками)
и прогоняются через node.

Именно так вскрылось, что первая версия safeUrl() пропускала ссылку
`https://x/" onmouseover="alert(1)`: она начинается с https, значит
«схема в порядке» — и проходила дальше.

К сборке не подключён: в CI node может не стоять, а падение проверки
не должно останавливать статический сайт.
"""

import os
import shutil
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(BASE_DIR, "_category_template.html")

FUNCTIONS = ["esc", "safeUrl"]

NODE_CANDIDATES = [
    shutil.which("node"),
    r"C:\Users\Я\.workbuddy-ai\binaries\node\versions\22.22.2-2\node.exe",
    r"C:\Program Files\nodejs\node.exe",
]

CHECKS = r"""
var fails = 0, total = 0;
function check(name, got, want) {
  total++;
  if (got !== want) {
    fails++;
    console.log('  ПРОВАЛ  ' + name + ' -> ' + JSON.stringify(got) + ', ждали ' + JSON.stringify(want));
  } else {
    console.log('  ок      ' + name);
  }
}
function noTags(name, got) {
  total++;
  if (/[<>"']/.test(got)) {
    fails++;
    console.log('  ПРОВАЛ  ' + name + ' -> ' + JSON.stringify(got));
  } else {
    console.log('  ок      ' + name + ' -> ' + JSON.stringify(got));
  }
}

check('esc: обычный текст', esc('Новости про ИИ'), 'Новости про ИИ');
noTags('esc: тег обезврежен', esc('<img src=x onerror=alert(1)>ИИ'));
noTags('esc: двойная кавычка', esc('a"b'));
noTags('esc: одиночная кавычка', esc("a'b"));
noTags('esc: вылезание из атрибута', esc('x" onmouseover="alert(1)'));
check('esc: null', esc(null), '');
check('esc: undefined', esc(undefined), '');
check('esc: число', esc(42), '42');

check('safeUrl: обычная', safeUrl('https://habr.com/ru/articles/1/'), 'https://habr.com/ru/articles/1/');
check('safeUrl: http', safeUrl('http://example.com/a?b=1'), 'http://example.com/a?b=1');
check('safeUrl: пробелы вокруг', safeUrl('  https://x.com/a  '), 'https://x.com/a');
check('safeUrl: кавычка внутри', safeUrl('https://x/" onmouseover="alert(1)'), '#');
check('safeUrl: пробел внутри', safeUrl('https://x/ onmouseover=alert(1)'), '#');
check('safeUrl: javascript', safeUrl('javascript:alert(1)'), '#');
check('safeUrl: data', safeUrl('data:text/html;base64,PHNjcmlwdD4='), '#');
check('safeUrl: угол', safeUrl('https://x/<script>'), '#');
check('safeUrl: пусто', safeUrl(''), '#');
check('safeUrl: null', safeUrl(null), '#');

console.log('\nвсего ' + total + ', провалено ' + fails);
if (fails) process.exit(1);
"""


def find_node():
    for path in NODE_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return None


def extract_function(source, name):
    """Вырезает функцию по имени, считая фигурные скобки."""
    start = source.index("function " + name + "(")
    open_brace = source.index("{", start)
    depth = 0
    pos = open_brace
    while pos < len(source):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
        pos += 1
    raise ValueError(f"не нашёл закрывающую скобку у {name}()")


def main():
    node = find_node()
    if not node:
        print("node не найден — проверка пропущена (это не ошибка проекта)")
        return 0

    with open(TEMPLATE, encoding="utf-8") as f:
        source = f.read()

    parts = []
    for name in FUNCTIONS:
        try:
            parts.append(extract_function(source, name))
        except ValueError as e:
            print(f"  ПРОВАЛ  {e}")
            return 1

    tmp_dir = tempfile.mkdtemp(prefix="template_js_")
    js_path = os.path.join(tmp_dir, "checks.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(parts) + "\n\n" + CHECKS)

    result = subprocess.run([node, js_path], capture_output=True, text=True,
                            encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
