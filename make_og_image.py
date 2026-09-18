# -*- coding: utf-8 -*-
"""Картинка для карточки предпросмотра ссылки (og-image.png).

Запуск вручную, из корня проекта:

    python make_og_image.py

Нужен Pillow и шрифты Windows. **В сборку этот файл не входит**: сам сайт
собирается только стандартной библиотекой, а картинка — готовая, лежит рядом
в репозитории. Скрипт нужен, чтобы её можно было перерисовать: текст на
картинке запечён в пиксели, и если на сайте меняется формулировка, картинку
надо перерисовать, иначе она начнёт расходиться со страницей.

Так уже было: в описании карточки стояло «6 раз в сутки», а на картинке
осталось «шесть раз в день», и это заметил пользователь.

Размер 1200×630 — стандарт карточки предпросмотра (1.91:1).
"""
import os

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE_DIR, "og-image.png")

W, H = 1200, 630

# Цвета взяты с самого сайта: фон страницы и градиент заголовка.
BG = (245, 245, 247)
TEXT2 = (110, 110, 115)
GRAD_FROM = (0, 113, 227)
GRAD_TO = (88, 86, 214)

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"
FONT_EMOJI = r"C:\Windows\Fonts\seguiemj.ttf"

TITLE = "AI News Hub"
SUBTITLE = "Новости про искусственный интеллект"
NOTE = "Восемь рубрик · обновление 6 раз в сутки"

# Значки рубрик — те же, что в CATEGORIES у сборщика.
CATS = ["\U0001F9E0", "\u2728", "\U0001F916", "\u26A1",
        "\U0001F3A8", "\U0001F372", "\U0001F4BC", "\U0001F4B0"]


def gradient(width, height):
    """Горизонтальный градиент — как у заголовка на сайте."""
    g = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(g)
    for x in range(width):
        t = x / max(1, width - 1)
        d.line([(x, 0), (x, height)], fill=tuple(
            int(a + (b - a) * t) for a, b in zip(GRAD_FROM, GRAD_TO)))
    return g


def build():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    title_font = ImageFont.truetype(FONT_BOLD, 104)
    sub_font = ImageFont.truetype(FONT_REG, 40)
    emoji_font = ImageFont.truetype(FONT_EMOJI, 62)
    note_font = ImageFont.truetype(FONT_REG, 30)

    # Заголовок рисуем маской, а градиент заливаем через неё.
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((W / 2, 218), TITLE, font=title_font,
                              fill=255, anchor="mm")
    im.paste(gradient(W, H), (0, 0), mask)

    d.text((W / 2, 312), SUBTITLE, font=sub_font, fill=TEXT2, anchor="mm")

    step = 118
    left = W / 2 - step * (len(CATS) - 1) / 2
    for i, emoji in enumerate(CATS):
        # embedded_color обязателен: без него эмодзи выходят чёрными.
        d.text((left + i * step, 448), emoji, font=emoji_font,
               anchor="mm", embedded_color=True)

    d.text((W / 2, 556), NOTE, font=note_font, fill=TEXT2, anchor="mm")

    im.save(OUT)
    return im


if __name__ == "__main__":
    im = build()
    size = os.path.getsize(OUT)
    print(f"[OK] {OUT} — {im.size[0]}x{im.size[1]}, {round(size / 1024)} КБ")
