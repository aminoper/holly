#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Knight_Quiz - نسخه نهایی + سیستم امتیاز جدید

مودها:
- !quiz [n] : آماده‌سازی n سوال چندگزینه‌ای از ۲ منبع (Trivia API + OpenTDB) + تصویر سوال
- !flags [n]: مسابقه پرچم‌شناسی چهارگزینه‌ای
- !start    : شروع مسابقه‌ای که با !quiz یا !question یا !flags آماده شده
- !question [n] : مسابقه تشریحی (بدون گزینه) با n سوال
                  منبع سوال‌ها فقط فایل questions.txt است (فرمت: سوال|جواب|دسته|سختی)
- !top      : بهترین بازیکنان تاریخ
- !resetbot : ریست کردن تمام مسابقه‌های در حال اجرا (برای همه آزاد است)
- !point @player ±N : کم/زیاد کردن امتیاز کلی بازیکن (فقط Administrator)
- /help و !help : راهنما
"""

import os
import asyncio
import json
import random
import io
import html
import unicodedata
from dataclasses import dataclass
from typing import Optional, Dict, List

import discord
from discord.ext import commands
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# ------------------ Argos Translate (آفلاین) ------------------
try:
    import argostranslate.translate as argos_translate
    ARGOS_AVAILABLE = True
except Exception:
    argos_translate = None
    ARGOS_AVAILABLE = False

ARGOS_EN_FA_TRANSLATOR = None


def translate_en_to_fa(text: str) -> str:
    """
    ترجمه‌ی متن انگلیسی به فارسی با Argos Translate.
    اگر Argos یا بسته‌ی en→fa نصب نباشد، همان متن اصلی برگردانده می‌شود.
    """
    global ARGOS_EN_FA_TRANSLATOR

    if not text:
        return text

    if not ARGOS_AVAILABLE:
        return text

    try:
        # اگر هنوز ترجمه‌گر en→fa را نگرفته‌ایم، الان بگیریم
        if ARGOS_EN_FA_TRANSLATOR is None:
            languages = argos_translate.get_installed_languages()
            from_lang = next((lang for lang in languages if lang.code.startswith("en")), None)
            to_lang = next((lang for lang in languages if lang.code.startswith("fa")), None)
            if from_lang and to_lang:
                ARGOS_EN_FA_TRANSLATOR = from_lang.get_translation(to_lang)
            else:
                print("[Knight_Quiz] بسته‌ی زبان en→fa در Argos نصب نشده است؛ متن انگلیسی برگردانده می‌شود.")
                return text

        return ARGOS_EN_FA_TRANSLATOR.translate(text)
    except Exception as e:
        print(f"[Knight_Quiz] خطا در Argos Translate: {e}")
        return text


if ARGOS_AVAILABLE:
    print("[Knight_Quiz] Argos Translate شناسایی شد و برای همه ترجمه‌ها استفاده می‌شود.")
else:
    print("[Knight_Quiz] Argos Translate پیدا نشد؛ متن‌ها بدون ترجمه باقی می‌مانند.")

# ------------------ بارگذاری متغیرهای محیطی از فایل .env ------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN or TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
    raise RuntimeError("❌ لطفاً توکن واقعی بات را داخل فایل .env در متغیر DISCORD_BOT_TOKEN قرار بده.")

# فقط سرور مجاز (برای اینکه بات فقط در سرور خودت باشد)
# اگر نخواهی محدود باشد، می‌توانی این متغیر را در .env ست نکنی یا 0 بگذاری
ALLOWED_GUILD_ID = int(os.getenv("ALLOWED_GUILD_ID", "0"))

# ------------------ تنظیمات عمومی ------------------
INTENTS = discord.Intents.default()
INTENTS.message_content = True  # برای خواندن پیام ها
INTENTS.reactions = True        # برای شنیدن ری‌اکشن‌ها

BOT_PREFIX = "!"
bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=INTENTS,
    help_command=None  # غیرفعال کردن help پیش‌فرض
)

SCORES_FILE = "scores.json"
QUESTIONS_FILE = "questions.txt"  # منبع سوال‌های تشریحی !question

# تایم‌اوت‌ها
QUIZ_TIMEOUT_SECONDS = 10       # برای سوال‌های چهار گزینه‌ای
QUESTION_TIMEOUT_SECONDS = 15   # برای سوال‌های تشریحی

DEFAULT_NUM_QUESTIONS = 30

EMBED_HEADER_TEXT = "Hollywood Server"
EMBED_FOOTER = "Dev : Amin Dark Knight 🦇"

# ------------ رنگ‌ها به صورت HEX ------------
# رنگ‌های Embed
COLOR_QUESTION_EMBED = "#FFFF00"          # زرد
COLOR_TIMEOUT_ANSWER_EMBED = "#00FF00"    # سبز
COLOR_CORRECT_PLAYER_EMBED = "#00FF00"    # سبز
COLOR_ROUND_SCORES_EMBED = "#FF0000"      # قرمز
COLOR_FINAL_RESULTS_EMBED = "#FFD700"     # طلایی
COLOR_HELP_EMBED = "#88FF00"              # سبز لیمویی
COLOR_TOPRANK_EMBED = "#FFD000"           # طلایی مایل به نارنجی
COLOR_PENALTY_EMBED = "#FF4800"           # نارنجی برای کم کردن امتیاز
# رنگ متن سوال و گزینه‌ها روی تصویر
QUESTION_TEXT_COLOR_HEX = "#FFFF00"       # سوال زرد
OPTION_TEXT_COLOR_HEX = "#FFFFFF"         # گزینه‌ها سفید
TEXT_STROKE_COLOR_HEX = "#000000"         # حاشیه مشکی

# مسیر تصویر پس‌زمینه سوال‌ها
QUESTION_BG_PATH = "question_bg.png"
# مسیر فونت اختصاصی (اختیاری)
QUESTION_FONT_PATH = "question_font.ttf"
# اندازه فونت سوال‌ها و گزینه‌ها
QUESTION_FONT_SIZE = 64   # اگر خواستی دو شماره کم شود، بگذار 62
OPTION_FONT_SIZE = 55     # اگر خواستی دو شماره کم شود، بگذار 53

# محدودیت طول سوال و گزینه‌ها (برای جلوگیری از سوال‌های خیلی طولانی)
MAX_QUESTION_CHARS = 80
MAX_OPTION_CHARS = 45

# دسته‌های مختلف برای تنوع موضوعی سوال‌ها (بدون food و بدون music)
TRIVIA_CATEGORIES = ",".join([
    "arts_and_literature",
    "film_and_tv",
    "general_knowledge",
    "geography",
    "history",
    "science",
    "society_and_culture",
    "sport_and_leisure",
])

# دسته‌های OpenTDB (بدون دسته موسیقی، غذا دسته مستقل ندارد)
OPENTDB_CATEGORIES = [
    9,   # General Knowledge
    17,  # Science & Nature
    18,  # Science: Computers
    20,  # Mythology
    21,  # Sports
    22,  # Geography
    23,  # History
    24,  # Politics
    25,  # Art
    27,  # Animals
    30,  # Science: Gadgets
]

# ------------------ نگاشت دسته‌ها به خانواده‌های مشترک ------------------

TRIVIA_FAMILY_MAP: Dict[str, str] = {
    "arts_and_literature": "art_lit",
    "film_and_tv": "film_tv",
    "general_knowledge": "general",
    "geography": "geography",
    "history": "history",
    "science": "science",
    "society_and_culture": "society_culture",
    "sport_and_leisure": "sport",
}

OPENTDB_FAMILY_MAP: Dict[int, str] = {
    9: "general",          # General Knowledge
    17: "science",         # Science & Nature
    18: "science",         # Science: Computers
    20: "mythology",       # Mythology (فقط در OpenTDB → خانواده‌ی خاص خودش)
    21: "sport",           # Sports
    22: "geography",       # Geography
    23: "history",         # History
    24: "politics",        # Politics (فقط در OpenTDB → خانواده‌ی خاص خودش)
    25: "art_lit",         # Art
    27: "animals",         # Animals (فقط در OpenTDB → خانواده‌ی خاص خودش)
    30: "science",         # Gadgets → science
}

# آماده‌سازی reshaper برای فارسی
reshaper = arabic_reshaper.ArabicReshaper({"language": "fa", "delete_harakat": False})


# ------------------ توابع کمکی رنگ ------------------
def hex_to_rgb(hex_str: str):
    """تبدیل رنگ HEX به (R, G, B) برای Pillow."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        raise ValueError(f"کد رنگ نامعتبر: {hex_str}")
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return (r, g, b)


def color_from_hex(hex_str: str) -> discord.Color:
    """تبدیل HEX به رنگ Discord."""
    return discord.Color.from_str(hex_str)


# ------------------ توابع کمکی دیگر ------------------
def shape_text(text: str) -> str:
    """متن فارسی را برای نمایش درست (اتصال حروف + راست به چپ) آماده می‌کند."""
    try:
        reshaped = reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def load_global_scores() -> Dict[int, int]:
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {int(k): int(v) for k, v in data.items()}
        except Exception:
            return {}
    return {}


def save_global_scores(scores: Dict[int, int]):
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def make_embed(body: str, color: discord.Color) -> discord.Embed:
    """
    یک Embed می‌سازد که در بالاترین قسمت متن:
    Hollywood Server
    را نشان می‌دهد.
    برای همه چیز به جز امبد تایمر از این استفاده می‌کنیم.
    """
    description = f"**{EMBED_HEADER_TEXT}**\n\n{body}"
    embed = discord.Embed(description=description, color=color)
    embed.set_footer(text=EMBED_FOOTER)
    return embed


def make_timer_embed(seconds: int) -> discord.Embed:
    """
    امبد تایمر زرد که *هدر و فوتر ندارد* (طبق خواسته تو).
    """
    desc = f"⏱ {seconds} ثانیه"
    return discord.Embed(description=desc, color=color_from_hex(COLOR_QUESTION_EMBED))


def build_scores_embed(
    guild: discord.Guild,
    scores: Dict[int, int],
    description_prefix: str,
    color_hex: str,
    order_map: Optional[Dict[int, int]] = None,
) -> discord.Embed:
    """
    ساخت امبد رتبه‌بندی.
    اگر order_map داده شود، در صورت مساوی بودن امتیاز، کسی که زودتر به آن امتیاز رسیده بالاتر است.
    نفرات ۱، ۲، ۳ با مدال نمایش داده می‌شوند.
    از نفر چهارم به بعد عدد + خط تیره.
    هر بازیکن در دو خط:
    - خط اول: مدال/شماره + منشن (سمت چپ)
    - خط دوم: امتیاز (متن فارسی راست‌به‌چپ)
    """
    body = description_prefix

    if scores:
        def sort_key(item):
            user_id, score = item
            order_value = order_map.get(user_id, 10**9) if order_map else 10**9
            return (-score, order_value)

        sorted_scores = sorted(scores.items(), key=sort_key)

        lines = []
        for idx, (user_id, score) in enumerate(sorted_scores, start=1):
            member = guild.get_member(user_id)
            if member:
                mention = member.mention
            else:
                mention = f"<@{user_id}>"

            # خط اول: مدال یا شماره + منشن
            if idx == 1:
                header = f"🥇 {mention}"
            elif idx == 2:
                header = f"🥈 {mention}"
            elif idx == 3:
                header = f"🥉 {mention}"
            else:
                header = f"{idx} - {mention}"

            # خط دوم: امتیاز
            score_line = f"امتیاز : {score}"

            # هر بازیکن دو خطی، بین بازیکن‌ها یک خط خالی
            lines.append(f"{header}\n{score_line}")

        body += "\n\n" + "\n\n".join(lines)
    else:
        body += "\n\nهیچ امتیازی ثبت نشده است."

    return make_embed(body, color_from_hex(color_hex))


def _load_question_font(size: int) -> ImageFont.FreeTypeFont:
    """
    تلاش می‌کند فونت اختصاصی (question_font.ttf) را لود کند.
    اگر نبود، از arial یا فونت پیش‌فرض استفاده می‌کند.
    """
    if os.path.exists(QUESTION_FONT_PATH):
        try:
            return ImageFont.truetype(QUESTION_FONT_PATH, size)
        except Exception:
            pass
    for f in ["arial.ttf", "Arial.ttf"]:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _measure_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    """طول پیکسلی یک خط (بعد از شکل‌دهی فارسی) را برمی‌گرداند."""
    shaped = shape_text(text)
    bbox = draw.textbbox((0, 0), shaped, font=font, stroke_width=3)
    return bbox[2] - bbox[0]


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """متن را بر اساس حداکثر عرض پیکسل به چند خط می‌شکند."""
    words = text.split(" ")
    lines = []
    current = ""

    for word in words:
        test_line = (current + " " + word).strip()
        width = _measure_line(draw, test_line, font)
        if width <= max_width or not current:
            current = test_line
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def _compress_to_limit(base_rgb: Image.Image, filename: str, kb_limit: int) -> Optional[discord.File]:
    """
    تصویر را به صورت JPEG فشرده می‌کند تا به حدود حجم تعیین شده برسد.
    """
    target_bytes = kb_limit * 1024
    last_buf: Optional[io.BytesIO] = None

    for quality in [95, 85, 75, 65, 55, 45, 35]:
        buf = io.BytesIO()
        base_rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        size = buf.tell()
        last_buf = buf
        if size <= target_bytes:
            break

    if last_buf is None:
        return None

    last_buf.seek(0)
    return discord.File(last_buf, filename=filename)


def render_question_image(question_text: str, options: list) -> Optional[discord.File]:
    """
    سوال و گزینه‌ها را روی تصویر question_bg.png رندر می‌کند
    و به صورت یک فایل JPEG با حداکثر ~60KB برمی‌گرداند.
    سوال و گزینه‌ها کمی پایین‌تر نمایش داده می‌شوند.
    """
    if not os.path.exists(QUESTION_BG_PATH):
        return None

    try:
        base = Image.open(QUESTION_BG_PATH).convert("RGBA")
    except Exception:
        return None

    draw = ImageDraw.Draw(base)
    question_font = _load_question_font(QUESTION_FONT_SIZE)
    option_font = _load_question_font(OPTION_FONT_SIZE)

    max_width = base.width - 160
    line_spacing = 14  # فاصله خطوط

    question_lines = _wrap_text(draw, question_text, question_font, max_width)

    items = []

    # چند خط خالی در بالا برای اینکه کل بلوک کمی پایین‌تر بیاید
    items.append(("", False))
    items.append(("", False))

    # خود سوال
    for ql in question_lines:
        items.append((ql, False))

    # فاصله بین سوال و گزینه‌ها (سه خط خالی)
    items.append(("", False))
    items.append(("", False))
    items.append(("", False))

    # گزینه‌ها
    for idx, opt in enumerate(options, start=1):
        opt_lines = _wrap_text(draw, opt, option_font, max_width)
        if not opt_lines:
            continue
        first_line = f"{idx}_ {opt_lines[0]}"
        items.append((first_line, True))
        for extra in opt_lines[1:]:
            items.append((f"    {extra}", True))
        # یک خط خالی اضافی بین هر گزینه
        items.append(("", False))

    shaped_lines = [shape_text(text) for (text, _) in items]

    line_heights = []
    for (text, is_option), shaped in zip(items, shaped_lines):
        font = option_font if is_option else question_font
        bbox = draw.textbbox((0, 0), shaped or " ", font=font, stroke_width=3)
        line_heights.append(bbox[3] - bbox[1])

    total_height = sum(line_heights) + line_spacing * (len(line_heights) - 1)
    # نقطه شروع کمی پایین‌تر
    start_y = max(80, (base.height - total_height) // 3 + 40)

    current_y = start_y
    for (raw_line, is_option), shaped_line, h in zip(items, shaped_lines, line_heights):
        font = option_font if is_option else question_font

        if not raw_line:
            current_y += h + line_spacing
            continue

        bbox = draw.textbbox((0, 0), shaped_line, font=font, stroke_width=3)
        line_width = bbox[2] - bbox[0]
        x = (base.width - line_width) // 2

        if is_option:
            fill_color = hex_to_rgb(OPTION_TEXT_COLOR_HEX)
        else:
            fill_color = hex_to_rgb(QUESTION_TEXT_COLOR_HEX)

        draw.text(
            (x, current_y),
            shaped_line,
            font=font,
            fill=fill_color,
            stroke_width=3,
            stroke_fill=hex_to_rgb(TEXT_STROKE_COLOR_HEX),
        )
        current_y += h + line_spacing

    base_rgb = base.convert("RGB")
    return _compress_to_limit(base_rgb, "question.jpg", kb_limit=60)


def render_question_only_image(question_text: str) -> Optional[discord.File]:
    """
    فقط خود سوال (بدون گزینه) را در تصویر رندر می‌کند (برای دستور !question).
    سوال کمی پایین‌تر از وسط تصویر قرار می‌گیرد.
    """
    if not os.path.exists(QUESTION_BG_PATH):
        return None

    try:
        base = Image.open(QUESTION_BG_PATH).convert("RGBA")
    except Exception:
        return None

    draw = ImageDraw.Draw(base)
    question_font = _load_question_font(QUESTION_FONT_SIZE)

    max_width = base.width - 160
    line_spacing = 10

    question_lines = _wrap_text(draw, question_text, question_font, max_width)
    shaped_lines = [shape_text(text) for text in question_lines]

    line_heights = []
    for shaped in shaped_lines:
        bbox = draw.textbbox((0, 0), shaped or " ", font=question_font, stroke_width=3)
        line_heights.append(bbox[3] - bbox[1])

    total_height = sum(line_heights) + line_spacing * (len(line_heights) - 1)
    # کمی پایین‌تر از مرکز
    start_y = (base.height - total_height) // 2 + 8

    current_y = start_y
    for shaped_line, h in zip(shaped_lines, line_heights):
        bbox = draw.textbbox((0, 0), shaped_line, font=question_font, stroke_width=3)
        line_width = bbox[2] - bbox[0]
        x = (base.width - line_width) // 2

        draw.text(
            (x, current_y),
            shaped_line,
            font=question_font,
            fill=hex_to_rgb(QUESTION_TEXT_COLOR_HEX),
            stroke_width=3,
            stroke_fill=hex_to_rgb(TEXT_STROKE_COLOR_HEX),
        )
        current_y += h + line_spacing

    base_rgb = base.convert("RGB")
    return _compress_to_limit(base_rgb, "question_open.jpg", kb_limit=60)


# ------------------ مدل داده سوال خام و آماده (quiz) ------------------
@dataclass
class RawQuizQuestion:
    source: str           # trivia یا opentdb
    question_en: str
    correct_en: str
    incorrects_en: List[str]
    family: str           # خانواده‌ی موضوعی (برای کنترل ۲۰٪)


@dataclass
class PreparedQuizQuestion:
    question_fa: str
    options_fa: List[str]
    correct_index: int
    correct_text_fa: str
    file: Optional[discord.File]
    source: str           # منبع (trivia / opentdb)
    family: str           # خانواده‌ی موضوعی


# ------------------ مدل داده پرچم‌ها برای !flags ------------------
@dataclass
class FlagCountry:
    name_en: str   # نام انگلیسی کشور
    name_fa: str   # نام فارسی کشور
    flag_url: str  # آدرس اینترنتی تصویر پرچم


@dataclass
class PreparedFlagQuestion:
    flag_url: str
    options_fa: List[str]
    correct_index: int
    correct_text_fa: str


FLAG_COUNTRIES: List[FlagCountry] = []


def load_flag_countries() -> List[FlagCountry]:
    """
    یک بار از REST Countries لیست کشورها را می‌گیرد و
    برای هر کشور: نام انگلیسی، نام فارسی (در صورت وجود) و URL پرچم را ذخیره می‌کند.
    اگر ترجمه فارسی موجود نباشد، با Argos ترجمه می‌کند (در صورت نصب بودن).
    """
    global FLAG_COUNTRIES
    if FLAG_COUNTRIES:
        return FLAG_COUNTRIES

    url = "https://restcountries.com/v3.1/all"
    params = {
        "fields": "name,flags,translations"
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Knight_Quiz] خطا در دریافت پرچم‌ها از REST Countries: {e}")
        return []

    countries: List[FlagCountry] = []

    for item in data:
        try:
            name_data = item.get("name", {}) or {}
            name_en = name_data.get("common") or name_data.get("official")
            flags = item.get("flags", {}) or {}
            flag_url = flags.get("png") or flags.get("svg")

            if not name_en or not flag_url:
                continue

            translations = item.get("translations", {}) or {}
            fa_entry = translations.get("fa") or translations.get("per") or {}
            name_fa = None

            if isinstance(fa_entry, dict):
                # اگر ترجمهٔ آماده داشته باشد
                name_fa = fa_entry.get("common") or fa_entry.get("official")

            if not name_fa:
                # اگر ترجمه آماده نبود، با Argos ترجمه کن (در صورت وجود)
                name_fa = translate_en_to_fa(name_en) or name_en

            countries.append(FlagCountry(
                name_en=name_en,
                name_fa=name_fa,
                flag_url=flag_url,
            ))
        except Exception:
            continue

    FLAG_COUNTRIES = countries
    print(f"[Knight_Quiz] {len(FLAG_COUNTRIES)} پرچم از REST Countries لود شد.")
    return FLAG_COUNTRIES


# ------------------ مدل سوال‌های txt برای !question ------------------
@dataclass
class TxtQuestion:
    question: str
    answer: str
    category: str
    difficulty: str


def load_txt_questions(path: str) -> List[TxtQuestion]:
    """
    سوال‌ها را از فایل txt با فرمت:
    سوال | جواب | دسته | سختی
    می‌خواند.
    """
    questions: List[TxtQuestion] = []
    if not os.path.exists(path):
        print(f"[Knight_Quiz] questions.txt پیدا نشد: {path}")
        return questions

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 2:
                    continue
                q = parts[0]
                a = parts[1]
                cat = parts[2] if len(parts) > 2 else ""
                diff = parts[3] if len(parts) > 3 else ""
                questions.append(TxtQuestion(question=q, answer=a, category=cat, difficulty=diff))
    except Exception as e:
        print(f"[Knight_Quiz] خطا در خواندن questions.txt: {e}")

    print(f"[Knight_Quiz] {len(questions)} سوال از فایل txt لود شد.")
    return questions


TXT_QUESTION_BANK: List[TxtQuestion] = load_txt_questions(QUESTIONS_FILE)


# ------------------ گرفتن سوال از ۲ منبع برای quiz ------------------
def fetch_raw_trivia_questions(limit: int) -> List[RawQuizQuestion]:
    """
    گرفتن سوال از Trivia API با چند دسته و دو سطح سختی (easy, medium).
    """
    if limit <= 0:
        return []

    url = "https://the-trivia-api.com/v2/questions"
    params = {
        "limit": min(limit, 50),
        "categories": TRIVIA_CATEGORIES,
        "difficulties": "easy,medium",
        "types": "text_choice",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[Knight_Quiz] خطا در Trivia API: {e}")
        return []

    results: List[RawQuizQuestion] = []
    if not isinstance(data, list):
        return results

    for item in data:
        q = item.get("question", {}).get("text", "")
        correct = item.get("correctAnswer", "")
        incorrect = item.get("incorrectAnswers", [])
        if not q or not correct or len(incorrect) != 3:
            continue

        cat_raw = item.get("category")
        if isinstance(cat_raw, dict):
            cat_str = cat_raw.get("id") or cat_raw.get("slug") or cat_raw.get("name") or ""
        else:
            cat_str = str(cat_raw) if cat_raw is not None else ""
        family = TRIVIA_FAMILY_MAP.get(cat_str, f"trivia_{cat_str or 'other'}")

        results.append(RawQuizQuestion(
            source="trivia",
            question_en=q,
            correct_en=correct,
            incorrects_en=incorrect,
            family=family,
        ))
    return results


def fetch_raw_opentdb_questions(limit: int) -> List[RawQuizQuestion]:
    """
    گرفتن سوال از OpenTDB از چند دسته‌ی رندوم (حداکثر ۷ دسته) با سختی easy/medium.
    """
    if limit <= 0:
        return []

    results: List[RawQuizQuestion] = []
    if not OPENTDB_CATEGORIES:
        return results

    # حداکثر ۷ دسته‌ی رندوم (برای تنوع موضوعی)
    cats = random.sample(OPENTDB_CATEGORIES, k=min(7, len(OPENTDB_CATEGORIES)))
    # تعداد پایه‌ی سوال برای هر دسته (کمی بیشتر برای انعطاف)
    base_per_cat = max(1, limit // len(cats))

    # برای اینکه هم easy و هم medium داشته باشیم، بین دسته‌ها پخش می‌کنیم
    difficulties = ["easy"] * (len(cats) // 2) + ["medium"] * (len(cats) - len(cats) // 2)
    random.shuffle(difficulties)

    for idx, cat_id in enumerate(cats):
        amount = base_per_cat * 2  # بیش‌ازحد برای اینکه بعداً بتوانیم فیلتر کنیم
        amount = min(amount, 50)
        difficulty = difficulties[idx] if idx < len(difficulties) else random.choice(["easy", "medium"])

        params = {
            "amount": amount,
            "type": "multiple",
            "difficulty": difficulty,
            "category": cat_id,
        }
        try:
            resp = requests.get(url="https://opentdb.com/api.php", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[Knight_Quiz] خطا در OpenTDB (cat={cat_id}): {e}")
            continue

        if not isinstance(data, dict):
            continue

        family = OPENTDB_FAMILY_MAP.get(cat_id, f"opentdb_{cat_id}")
        for item in data.get("results", []):
            q = html.unescape(item.get("question", ""))
            correct = html.unescape(item.get("correct_answer", ""))
            incorrect = [html.unescape(x) for x in item.get("incorrect_answers", [])]
            if not q or not correct or len(incorrect) != 3:
                continue
            results.append(RawQuizQuestion(
                source="opentdb",
                question_en=q,
                correct_en=correct,
                incorrects_en=incorrect,
                family=family,
            ))

    return results


def collect_raw_mc_questions(total: int) -> List[RawQuizQuestion]:
    """
    گرفتن سوال‌های خام انگلیسی از ۲ منبع با این ویژگی‌ها:
    - حدوداً ۴۰٪ Trivia ، ۶۰٪ OpenTDB (در حد امکان)
    - فیلتر طول روی متن انگلیسی (سوال و گزینه‌ها)
    - تلاش برای اینکه هیچ خانواده‌ای بیش از ۲۰٪ سوال‌ها نگیرد
    - اگر محدودیت‌ها باعث کمبود شود، مسابقه لغو نمی‌شود و به شکل هوشمند شُل می‌شود.
    """
    if total <= 0:
        return []

    # نسبت‌های هدف
    trivia_target = max(1, int(round(total * 0.4)))
    opentdb_target = total - trivia_target
    if opentdb_target < 1:
        opentdb_target = 1
        trivia_target = total - 1

    # برای اینکه مجموع دقیقاً total شود
    sum_target = trivia_target + opentdb_target
    if sum_target != total:
        # تنظیم کوچک اگر گرد کردن باعث اختلاف شده باشد
        opentdb_target += (total - sum_target)

    # کمی بیش‌ازحد از هر منبع می‌گیریم تا بعداً فیلتر و تعادل خانواده‌ها را اعمال کنیم
    trivia_raw_all = fetch_raw_trivia_questions(max(trivia_target * 3, trivia_target + 5))
    opentdb_raw_all = fetch_raw_opentdb_questions(max(opentdb_target * 3, opentdb_target + 5))

    def filter_english(raw_list: List[RawQuizQuestion]) -> List[RawQuizQuestion]:
        filtered: List[RawQuizQuestion] = []
        for rq in raw_list:
            if not rq.question_en or len(rq.question_en) > MAX_QUESTION_CHARS * 2:
                continue
            options = [rq.correct_en] + rq.incorrects_en
            if len(options) != 4:
                continue
            if any((not opt) or len(opt) > MAX_OPTION_CHARS * 2 for opt in options):
                continue
            filtered.append(rq)
        return filtered

    trivia_pool = filter_english(trivia_raw_all)
    opentdb_pool = filter_english(opentdb_raw_all)

    pool_by_source: Dict[str, List[RawQuizQuestion]] = {
        "trivia": trivia_pool,
        "opentdb": opentdb_pool,
    }

    for lst in pool_by_source.values():
        random.shuffle(lst)

    # اگر هیچ سوالی نگرفتیم
    all_questions = [q for lst in pool_by_source.values() for q in lst]
    if not all_questions:
        return []

    # خانواده‌ها
    all_families = {q.family for q in all_questions}
    if not all_families:
        all_families = {"unknown"}

    max_per_family = max(1, int(total * 0.2))  # 20٪ سقف نرم

    desired_per_source = {
        "trivia": trivia_target,
        "opentdb": opentdb_target,
    }

    selected: List[RawQuizQuestion] = []
    family_counts: Dict[str, int] = {}
    indices: Dict[str, int] = {src: 0 for src in pool_by_source}
    # ترجیح می‌دهیم اول OpenTDB پر شود تا به نسبت ۶۰٪ نزدیک باشیم
    sources_order = ["opentdb", "trivia"]

    # فاز ۱: تلاش برای احترام به نسبت هر منبع + سقف خانواده‌ها
    while len(selected) < total:
        progress = False
        for src in sources_order:
            if desired_per_source[src] <= 0:
                continue
            lst = pool_by_source[src]
            idx = indices[src]
            # رد کردن سوال‌هایی که خانواده‌شان به سقف رسیده
            while idx < len(lst) and family_counts.get(lst[idx].family, 0) >= max_per_family:
                idx += 1
            if idx >= len(lst):
                indices[src] = idx
                continue

            rq = lst[idx]
            indices[src] = idx + 1
            selected.append(rq)
            family_counts[rq.family] = family_counts.get(rq.family, 0) + 1
            desired_per_source[src] -= 1
            progress = True

            if len(selected) >= total:
                break

        if not progress:
            break

    # فاز ۲: اگر هنوز کم داریم، از هر منبعی که سوال مانده، با حفظ سقف خانواده‌ها پر می‌کنیم
    if len(selected) < total:
        remaining: List[RawQuizQuestion] = []
        for src in sources_order:
            lst = pool_by_source[src]
            idx = indices[src]
            if idx < len(lst):
                remaining.extend(lst[idx:])
        random.shuffle(remaining)

        for rq in remaining:
            if len(selected) >= total:
                break
            if family_counts.get(rq.family, 0) >= max_per_family:
                continue
            selected.append(rq)
            family_counts[rq.family] = family_counts.get(rq.family, 0) + 1

    # فاز ۳: اگر باز هم کم داریم، مجبوریم از محدودیت خانواده بگذریم که مسابقه حتماً اجرا شود
    if len(selected) < total:
        used_ids = {id(q) for q in selected}
        remaining_all: List[RawQuizQuestion] = []
        for src in sources_order:
            for rq in pool_by_source[src]:
                if id(rq) not in used_ids:
                    remaining_all.append(rq)
        random.shuffle(remaining_all)

        for rq in remaining_all:
            if len(selected) >= total:
                break
            selected.append(rq)

    # اگر به هر دلیل بیشتر از total شد، کوتاه می‌کنیم
    if len(selected) > total:
        selected = selected[:total]

    return selected


# امتیازهای کلی (تاریخی)
global_scores: Dict[int, int] = load_global_scores()
global_score_order_map: Dict[int, int] = {}
global_score_step_counter: int = 0


def add_match_scores_to_global(match_scores: Dict[int, int]):
    """
    امتیازهای یک مسابقه را بعد از پایان مسابقه
    به امتیاز کلی اضافه می‌کند.

    فقط امتیازهای مثبت به امتیاز کلی اضافه می‌شوند
    (برای اینکه امتیاز کلی بازیکن‌ها منفی نشود).
    """
    global global_scores, global_score_order_map, global_score_step_counter

    changed = False
    for user_id, score in match_scores.items():
        if score <= 0:
            continue
        global_scores[user_id] = global_scores.get(user_id, 0) + score
        global_score_step_counter += 1
        global_score_order_map[user_id] = global_score_step_counter
        changed = True

    if changed:
        save_global_scores(global_scores)


# مسابقه چندگزینه‌ای
active_quizzes: Dict[int, "QuizSession"] = {}
# مسابقه تشریحی (بدون گزینه) برای !question
active_question_sessions: Dict[int, "QuestionSession"] = {}
# مسابقه پرچم‌ها برای !flags
active_flag_sessions: Dict[int, "FlagSession"] = {}


# ------------------ کلاس مسابقه چندگزینه‌ای (quiz) ------------------
class QuizSession:
    def __init__(self, channel: discord.TextChannel, num_questions: int = DEFAULT_NUM_QUESTIONS):
        self.channel = channel
        self.num_questions = num_questions

        self.prepared_questions: List[PreparedQuizQuestion] = []

        self.asked_count = 0
        self.scores: Dict[int, int] = {}
        self.current_answered = False
        self.current_correct_answer: Optional[int] = None
        self.current_correct_text_fa: Optional[str] = None
        self.current_view: Optional["AnswerView"] = None
        self.current_question_message: Optional[discord.Message] = None
        self.answered_users = set()
        self.finished = False
        self.question_resolved = False
        self.current_question_id = 0

        self.score_order_map: Dict[int, int] = {}
        self.score_step_counter: int = 0

        # آمار تنوع دسته‌ها و منابع برای این مسابقه
        self.family_stats: Dict[str, int] = {}
        self.source_stats: Dict[str, int] = {}

        self.started: bool = False

    async def preload_questions(self, ctx: commands.Context) -> bool:
        """
        در این مرحله:
        - از ۲ منبع سوال می‌گیرد با نسبت حدودی ۴۰٪ Trivia / ۶۰٪ OpenTDB
        - فیلتر روی متن انگلیسی (طول سوال و گزینه‌ها)
        - کنترل تنوع خانواده‌ها (تا جای ممکن زیر ۲۰٪)
        - سپس ترجمه (با Argos) و ساخت تصویر را انجام می‌دهد
        و پیشرفت را در یک امبد لودینگ نشان می‌دهد.
        """
        loading_body = f"در حال دریافت و آماده‌سازی {self.num_questions} سوال از چند منبع...\nلطفاً صبر کنید."
        loading_embed = make_embed(loading_body, color_from_hex(COLOR_QUESTION_EMBED))
        loading_msg = await ctx.send(embed=loading_embed)

        raw_candidates = collect_raw_mc_questions(self.num_questions)
        if not raw_candidates:
            error_embed = make_embed(
                "❌ نتوانستم هیچ سوالی از سرورهای سوال‌ها دریافت کنم. لطفاً بعداً دوباره امتحان کن.",
                color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED),
            )
            await loading_msg.edit(embed=error_embed)
            return False

        self.prepared_questions = []
        self.asked_count = 0

        for raw in raw_candidates:
            if len(self.prepared_questions) >= self.num_questions:
                break

            question_en = raw.question_en
            correct_en = raw.correct_en
            incorrects_en = raw.incorrects_en

            # یک فیلتر اضافی روی طول انگلیسی (برای اطمینان)
            if len(question_en) > MAX_QUESTION_CHARS * 2:
                continue

            # ترجمه سوال با Argos
            question_fa = translate_en_to_fa(question_en) or question_en

            options_en = list(incorrects_en) + [correct_en]
            if len(options_en) != 4:
                continue

            random.shuffle(options_en)
            correct_index = options_en.index(correct_en)

            options_fa: List[str] = []
            too_long_option = False
            for opt_en in options_en:
                opt_fa = translate_en_to_fa(opt_en) or opt_en
                # اگر ترجمه خیلی طولانی شود، ردش می‌کنیم
                if len(opt_fa) > MAX_OPTION_CHARS:
                    too_long_option = True
                options_fa.append(opt_fa)

            if too_long_option:
                continue

            correct_text_fa = options_fa[correct_index]

            question_file = render_question_image(question_fa, options_fa)

            pq = PreparedQuizQuestion(
                question_fa=question_fa,
                options_fa=options_fa,
                correct_index=correct_index,
                correct_text_fa=correct_text_fa,
                file=question_file,
                source=raw.source,
                family=raw.family,
            )
            self.prepared_questions.append(pq)

            progress_body = f"{len(self.prepared_questions)}/{self.num_questions} سوال آماده شد..."
            progress_embed = make_embed(progress_body, color_from_hex(COLOR_QUESTION_EMBED))
            try:
                await loading_msg.edit(embed=progress_embed)
            except Exception:
                pass

        if not self.prepared_questions:
            error_embed = make_embed(
                "❌ نتوانستم سوال مناسبی پیدا کنم. لطفاً دوباره امتحان کن.",
                color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED),
            )
            await loading_msg.edit(embed=error_embed)
            return False

        # ممکن است به دلایلی کمی کمتر از تعداد درخواستی آماده شده باشد
        self.num_questions = len(self.prepared_questions)

        # محاسبه‌ی آمار خانواده‌ها و منبع‌ها برای این مسابقه
        self.family_stats = {}
        self.source_stats = {}
        for pq in self.prepared_questions:
            fam = getattr(pq, "family", "unknown")
            src = getattr(pq, "source", "unknown")
            self.family_stats[fam] = self.family_stats.get(fam, 0) + 1
            self.source_stats[src] = self.source_stats.get(src, 0) + 1

        ready_body = (
            f"✅ همه سوال‌ها آماده شدند.\n"
            f"{self.num_questions} سوال با موفقیت آماده شد.\n\n"
            "برای شروع مسابقه دستور `!start` را بزن."
        )
        ready_embed = make_embed(ready_body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await loading_msg.edit(embed=ready_embed)

        return True

    async def quiz_countdown(self, timer_message: discord.Message, question_id: int):
        """
        تایمر ۱۰ ثانیه‌ای برای quiz.
        """
        seconds = QUIZ_TIMEOUT_SECONDS
        while seconds >= 0:
            if self.finished or self.question_resolved or question_id != self.current_question_id:
                return
            try:
                await timer_message.edit(embed=make_timer_embed(seconds))
            except Exception:
                pass
            await asyncio.sleep(1)
            seconds -= 1

        # اگر هنوز سوال حل نشده، یعنی تایم‌اوت شده
        if self.finished or self.question_resolved or question_id != self.current_question_id:
            return

        self.question_resolved = True
        self.current_answered = False

        if self.current_view and self.current_question_message:
            for item in self.current_view.children:
                item.disabled = True
            try:
                await self.current_question_message.edit(view=self.current_view)
            except Exception:
                pass

        correct_fa = self.current_correct_text_fa or "پاسخ صحیح"
        answer_body = f"⏱️ زمان تمام شد!\n\nپاسخ درست:\n**{correct_fa}**"
        answer_embed = make_embed(answer_body, color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED))
        await self.channel.send(embed=answer_embed)

        scores_embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=scores_embed)

        await self.send_next_question()

    async def send_next_question(self):
        if self.finished:
            return

        if self.asked_count >= self.num_questions or self.asked_count >= len(self.prepared_questions):
            await self.finish_quiz()
            return

        self.current_answered = False
        self.answered_users.clear()
        self.question_resolved = False
        self.current_question_id += 1
        question_id = self.current_question_id

        prepared = self.prepared_questions[self.asked_count]
        self.asked_count += 1

        self.current_correct_answer = prepared.correct_index
        self.current_correct_text_fa = prepared.correct_text_fa

        view = AnswerView(self, prepared.options_fa)
        self.current_view = view

        body = f"سوال {self.asked_count} از {self.num_questions}:"
        embed = make_embed(body, color_from_hex(COLOR_QUESTION_EMBED))

        if prepared.file is not None:
            embed.set_image(url="attachment://question.jpg")
            msg = await self.channel.send(embed=embed, view=view, file=prepared.file)
        else:
            lines = [body, "", prepared.question_fa, ""]
            for i, opt in enumerate(prepared.options_fa, start=1):
                lines.append(f"{i}_ {opt}")
            fallback_body = "\n".join(lines)
            embed = make_embed(fallback_body, color_from_hex(COLOR_QUESTION_EMBED))
            msg = await self.channel.send(embed=embed, view=view)

        self.current_question_message = msg

        # امبد تایمر زرد ۱۰ ثانیه‌ای
        timer_msg = await self.channel.send(embed=make_timer_embed(QUIZ_TIMEOUT_SECONDS))
        asyncio.create_task(self.quiz_countdown(timer_msg, question_id))

    async def handle_correct_answer(self, user: discord.User):
        if self.finished or self.question_resolved:
            return
        self.question_resolved = True
        self.current_answered = True

        # فقط امتیاز مسابقه‌ای (لوکال)
        self.scores[user.id] = self.scores.get(user.id, 0) + 1

        self.score_step_counter += 1
        self.score_order_map[user.id] = self.score_step_counter

        if self.current_view and self.current_question_message:
            for item in self.current_view.children:
                item.disabled = True
            try:
                await self.current_question_message.edit(view=self.current_view)
            except Exception:
                pass

        correct_text = self.current_correct_text_fa or "پاسخ صحیح"
        body = f"✅ درسته : {correct_text}\n{user.mention} +1 امتیاز"
        green_embed = make_embed(body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await self.channel.send(embed=green_embed)

        scores_embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=scores_embed)

        await self.send_next_question()

    async def finish_quiz(self):
        self.finished = True
        await self.channel.send("# پایان مسابقه ⏰")

        embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="🏆 نتیجه نهایی مسابقه:",
            color_hex=COLOR_FINAL_RESULTS_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=embed)

        # ✅ بعد از پایان مسابقه، امتیازهای این مسابقه به امتیاز کلی اضافه می‌شود
        add_match_scores_to_global(self.scores)

        if self.channel.id in active_quizzes:
            del active_quizzes[self.channel.id]


# ------------------ مسابقه پرچم‌ها (flags) ------------------
class FlagSession:
    def __init__(self, channel: discord.TextChannel, num_questions: int = DEFAULT_NUM_QUESTIONS):
        self.channel = channel
        self.num_questions = num_questions

        self.prepared_questions: List[PreparedFlagQuestion] = []
        self.asked_count = 0
        self.scores: Dict[int, int] = {}

        self.finished = False
        self.question_resolved = False
        self.started: bool = False

        self.current_correct_answer: Optional[int] = None
        self.current_correct_text_fa: Optional[str] = None
        self.current_view: Optional["AnswerView"] = None
        self.current_question_message: Optional[discord.Message] = None
        self.answered_users = set()
        self.current_question_id: int = 0

        self.score_order_map: Dict[int, int] = {}
        self.score_step_counter: int = 0

    async def preload_questions(self, ctx: commands.Context) -> bool:
        """
        سوال‌های مسابقه پرچم‌ها را آماده می‌کند:
        - گرفتن لیست کشورها از REST Countries (یا کش شده)
        - انتخاب تصادفی num_questions کشور بدون تکرار
        - ساخت ۴ گزینه (۱ صحیح + ۳ اشتباه) با نام فارسی
        """
        loading_body = (
            f"در حال آماده‌سازی مسابقه پرچم‌ها با {self.num_questions} سوال...\n"
            f"لطفاً صبر کنید."
        )
        loading_embed = make_embed(loading_body, color_from_hex(COLOR_QUESTION_EMBED))
        loading_msg = await ctx.send(embed=loading_embed)

        all_countries = load_flag_countries()
        if not all_countries or len(all_countries) < 4:
            error_embed = make_embed(
                "❌ نتوانستم پرچم‌های کافی از سرور دریافت کنم. لطفاً بعداً دوباره امتحان کن.",
                color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED),
            )
            await loading_msg.edit(embed=error_embed)
            return False

        if self.num_questions > len(all_countries):
            self.num_questions = len(all_countries)

        # انتخاب کشورها بدون تکرار برای این مسابقه
        selected_countries = random.sample(all_countries, self.num_questions)

        self.prepared_questions = []
        self.asked_count = 0

        for idx, correct_country in enumerate(selected_countries, start=1):
            # ۳ کشور اشتباه (بدون تکرار و غیر از کشور صحیح)
            wrong_pool = [c for c in all_countries if c is not correct_country]
            if len(wrong_pool) < 3:
                continue
            wrong_countries = random.sample(wrong_pool, 3)

            options_fa = [correct_country.name_fa] + [w.name_fa for w in wrong_countries]
            random.shuffle(options_fa)
            correct_index = options_fa.index(correct_country.name_fa)

            pq = PreparedFlagQuestion(
                flag_url=correct_country.flag_url,
                options_fa=options_fa,
                correct_index=correct_index,
                correct_text_fa=correct_country.name_fa,
            )
            self.prepared_questions.append(pq)

            progress_body = f"{len(self.prepared_questions)}/{self.num_questions} سوال آماده شد..."
            progress_embed = make_embed(progress_body, color_from_hex(COLOR_QUESTION_EMBED))
            try:
                await loading_msg.edit(embed=progress_embed)
            except Exception:
                pass

        if not self.prepared_questions:
            error_embed = make_embed(
                "❌ نتوانستم سوال مناسبی برای پرچم‌ها بسازم. لطفاً دوباره امتحان کن.",
                color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED),
            )
            await loading_msg.edit(embed=error_embed)
            return False

        # در صورت فیلتر شدن بعضی سوال‌ها ممکن است کمتر از num_questions شود
        self.num_questions = len(self.prepared_questions)

        ready_body = (
            f"✅ سوال‌های مسابقه پرچم‌ها آماده شدند.\n"
            f"{self.num_questions} سوال با موفقیت آماده شد.\n\n"
            "برای شروع مسابقه دستور `!start` را بزن."
        )
        ready_embed = make_embed(ready_body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await loading_msg.edit(embed=ready_embed)

        return True

    async def flags_countdown(self, timer_message: discord.Message, question_id: int):
        """
        تایمر ۱۰ ثانیه‌ای برای سوال‌های پرچم‌ها.
        از نظر ظاهر و منطق مثل quiz است.
        """
        seconds = QUIZ_TIMEOUT_SECONDS
        while seconds >= 0:
            if self.finished or self.question_resolved or question_id != self.current_question_id:
                return
            try:
                await timer_message.edit(embed=make_timer_embed(seconds))
            except Exception:
                pass
            await asyncio.sleep(1)
            seconds -= 1

        # تایم‌اوت
        if self.finished or self.question_resolved or question_id != self.current_question_id:
            return

        self.question_resolved = True

        # دکمه‌ها را غیرفعال کن
        if self.current_view and self.current_question_message:
            for item in self.current_view.children:
                item.disabled = True
            try:
                await self.current_question_message.edit(view=self.current_view)
            except Exception:
                pass

        correct_fa = self.current_correct_text_fa or "پاسخ صحیح"
        answer_body = f"⏱️ زمان تمام شد!\n\nپاسخ درست:\n**{correct_fa}**"
        answer_embed = make_embed(answer_body, color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED))
        await self.channel.send(embed=answer_embed)

        scores_embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=scores_embed)

        await self.send_next_question()

    async def send_next_question(self):
        if self.finished:
            return

        if self.asked_count >= self.num_questions or self.asked_count >= len(self.prepared_questions):
            await self.finish_quiz()
            return

        self.question_resolved = False
        self.answered_users.clear()
        self.current_question_id += 1
        question_id = self.current_question_id

        prepared = self.prepared_questions[self.asked_count]
        self.asked_count += 1

        self.current_correct_answer = prepared.correct_index
        self.current_correct_text_fa = prepared.correct_text_fa

        view = AnswerView(self, prepared.options_fa, labels=prepared.options_fa)
        self.current_view = view

        # متن سوال پرچم
        body = f"سوال {self.asked_count} از {self.num_questions}\n**پرچم کدوم کشوره؟**"
        embed = make_embed(body, color_from_hex(COLOR_QUESTION_EMBED))

        # تصویر پرچم از URL
        embed.set_image(url=prepared.flag_url)
        msg = await self.channel.send(embed=embed, view=view)
        self.current_question_message = msg

        # امبد تایمر ۱۰ ثانیه‌ای
        timer_msg = await self.channel.send(embed=make_timer_embed(QUIZ_TIMEOUT_SECONDS))
        asyncio.create_task(self.flags_countdown(timer_msg, question_id))

    async def handle_correct_answer(self, user: discord.User):
        if self.finished or self.question_resolved:
            return
        self.question_resolved = True

        # فقط امتیاز مسابقه‌ای
        self.scores[user.id] = self.scores.get(user.id, 0) + 1
        self.score_step_counter += 1
        self.score_order_map[user.id] = self.score_step_counter

        # دکمه‌ها را غیرفعال کن
        if self.current_view and self.current_question_message:
            for item in self.current_view.children:
                item.disabled = True
            try:
                await self.current_question_message.edit(view=self.current_view)
            except Exception:
                pass

        correct_text = self.current_correct_text_fa or "پاسخ صحیح"
        body = f"✅ درسته : {correct_text}\n{user.mention} +1 امتیاز"
        green_embed = make_embed(body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await self.channel.send(embed=green_embed)

        scores_embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=scores_embed)

        await self.send_next_question()

    async def finish_quiz(self):
        self.finished = True
        await self.channel.send("# پایان مسابقه پرچم‌ها ⏰")

        embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="🏁 نتیجه نهایی مسابقه پرچم‌ها:",
            color_hex=COLOR_FINAL_RESULTS_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=embed)

        # ✅ بعد از پایان مسابقه، امتیازهای این مسابقه به امتیاز کلی اضافه می‌شود
        add_match_scores_to_global(self.scores)

        if self.channel.id in active_flag_sessions:
            del active_flag_sessions[self.channel.id]


# ------------------ مسابقه سوال تشریحی (question) ------------------

def normalize_answer_text(text: str) -> str:
    """نرمال‌سازی متن برای مقایسه جواب‌ها (فارسی + انگلیسی)."""

    # ۱) حذف فاصله‌های دو طرف
    text = text.strip()

    # ۲) نرمال‌سازی یونی‌کد (فرم سازگار)
    text = unicodedata.normalize("NFKC", text)

    # ۳) یکسان‌سازی حروف عربی/فارسی + حذف کاراکترهای نامرئی
    char_map = {
        "ي": "ی",
        "ى": "ی",
        "ئ": "ی",
        "ی": "ی",

        "ك": "ک",

        "ۀ": "ه",
        "ة": "ه",

        "ؤ": "و",

        "أ": "ا",
        "إ": "ا",
        "آ": "ا",

        "\u200c": "",  # نیم‌فاصله
        "\u200f": "",  # علامت جهت راست‌به‌چپ
        "\ufeff": "",  # BOM
    }
    text = text.translate(str.maketrans(char_map))

    # ۴) بی‌حس کردن حروف بزرگ/کوچک انگلیسی
    text = text.casefold()

    # ۵) حذف/جایگزینی علائم نگارشی با فاصله
    for ch in [".", "!", "?", "،", ",", "؛", ":", "ـ", "«", "»",
               "(", ")", "[", "]", "{", "}", "-", "_", "/", "\\"]:
        text = text.replace(ch, " ")

    # ۶) جمع کردن فاصله‌های پشت‌سرهم به یک فاصله
    text = " ".join(text.split())

    return text


class QuestionSession:
    def __init__(self, channel: discord.TextChannel, num_questions: int = DEFAULT_NUM_QUESTIONS):
        self.channel = channel
        self.num_questions = num_questions
        self.current_index = 0
        self.asked_count = 0
        self.questions: List[TxtQuestion] = []
        self.scores: Dict[int, int] = {}
        self.finished = False
        self.question_resolved = False
        self.started: bool = False

        self.current_correct_text_fa: Optional[str] = None
        self.current_correct_text_en: Optional[str] = None  # برای سازگاری با تابع مقایسه

        self.score_order_map: Dict[int, int] = {}
        self.score_step_counter: int = 0

        self.current_question_id: int = 0

    async def preload_questions(self, ctx: commands.Context) -> bool:
        """
        شبیه quiz: یک امبد لودینگ، سپس آماده‌سازی سوال‌ها از فایل txt و در پایان امبد آماده شدن.
        """
        loading_body = (
            f"در حال آماده‌سازی مسابقه تشریحی با {self.num_questions} سوال از فایل questions.txt...\n"
            f"لطفاً صبر کنید."
        )
        loading_embed = make_embed(loading_body, color_from_hex(COLOR_QUESTION_EMBED))
        loading_msg = await ctx.send(embed=loading_embed)

        global TXT_QUESTION_BANK
        if not TXT_QUESTION_BANK:
            error_embed = make_embed(
                "❌ نتوانستم سوالی از فایل questions.txt پیدا کنم. لطفاً فایل را بررسی کن.",
                color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED),
            )
            await loading_msg.edit(embed=error_embed)
            return False

        total_available = len(TXT_QUESTION_BANK)
        if self.num_questions > total_available:
            self.num_questions = total_available

        indices = list(range(total_available))
        random.shuffle(indices)

        self.questions = []
        for i in range(self.num_questions):
            idx = indices[i]
            self.questions.append(TXT_QUESTION_BANK[idx])
            progress_body = f"{i+1}/{self.num_questions} سوال آماده شد..."
            progress_embed = make_embed(progress_body, color_from_hex(COLOR_QUESTION_EMBED))
            await loading_msg.edit(embed=progress_embed)

        ready_body = (
            f"✅ سوال‌های مسابقه تشریحی آماده شدند.\n"
            f"{self.num_questions} سوال انتخاب شد.\n\n"
            "برای شروع مسابقه دستور `!start` را بزن."
        )
        ready_embed = make_embed(ready_body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await loading_msg.edit(embed=ready_embed)
        return True

    async def start(self, ctx: commands.Context):
        if self.started:
            await self.channel.send("⚠️ این مسابقه قبلاً شروع شده است.")
            return
        self.started = True

        if not self.questions:
            # اگر به هر دلیلی preload نشده باشد
            global TXT_QUESTION_BANK
            if not TXT_QUESTION_BANK:
                await self.channel.send("❌ نتوانستم سوالی از فایل questions.txt پیدا کنم. لطفاً فایل را بررسی کن.")
                if self.channel.id in active_question_sessions:
                    del active_question_sessions[self.channel.id]
                return
            total_available = len(TXT_QUESTION_BANK)
            if self.num_questions > total_available:
                self.num_questions = total_available
            self.questions = random.sample(TXT_QUESTION_BANK, self.num_questions)

        start_body = "مسابقه شروع شد 📢"
        start_embed = make_embed(start_body, color_from_hex(COLOR_QUESTION_EMBED))
        await ctx.send(embed=start_embed)

        await self.send_next_question()

    async def question_countdown(self, timer_message: discord.Message, question_id: int):
        """
        تایمر ۱۵ ثانیه‌ای برای سوال‌های تشریحی.
        این تسک فقط نمایش تایمر را کنترل می‌کند و اگر تا پایان زمان
        هنوز جواب درست داده نشده باشد، handle_timeout را صدا می‌زند.
        """
        seconds = QUESTION_TIMEOUT_SECONDS

        while seconds >= 0:
            # اگر مسابقه تمام شده یا سوال عوض شده، این تایمر دیگه به درد نمی‌خوره
            if self.finished or self.question_resolved or question_id != self.current_question_id:
                return

            try:
                await timer_message.edit(embed=make_timer_embed(seconds))
            except Exception:
                pass

            await asyncio.sleep(1)
            seconds -= 1

        # اگر زمان تمام شد و هنوز کسی درست جواب نداده، تایم‌اوت
        if self.finished or self.question_resolved or question_id != self.current_question_id:
            return

        await self.handle_timeout()

    async def send_next_question(self):
        while True:
            if self.asked_count >= self.num_questions or self.current_index >= len(self.questions):
                await self.finish_quiz()
                return

            self.question_resolved = False
            self.current_correct_text_fa = None
            self.current_correct_text_en = None

            q_data: TxtQuestion = self.questions[self.current_index]
            self.current_index += 1

            question_text = q_data.question
            answer_text = q_data.answer

            # اگر سوال خیلی طولانی باشد، رد می‌شود و سراغ بعدی می‌رویم
            if len(question_text) > MAX_QUESTION_CHARS * 2:
                continue

            question_fa = question_text
            correct_fa = answer_text

            if len(question_fa) > MAX_QUESTION_CHARS:
                continue

            self.current_correct_text_fa = correct_fa
            self.current_correct_text_en = answer_text  # برای سازگاری با is_correct_answer

            question_number = self.asked_count + 1
            self.asked_count += 1

            body = f"سوال {question_number} از {self.num_questions}:"
            embed = make_embed(body, color_from_hex(COLOR_QUESTION_EMBED))

            question_file = render_question_only_image(question_fa)

            if question_file is not None:
                embed.set_image(url="attachment://question_open.jpg")
                await self.channel.send(embed=embed, file=question_file)
            else:
                lines = [body, "", question_fa]
                fallback_body = "\n".join(lines)
                embed = make_embed(fallback_body, color_from_hex(COLOR_QUESTION_EMBED))
                await self.channel.send(embed=embed)

            # ست کردن آیدی سوال برای هماهنگی
            self.current_question_id += 1
            question_id = self.current_question_id

            # امبد تایمر زرد ۱۵ ثانیه‌ای
            timer_msg = await self.channel.send(embed=make_timer_embed(QUESTION_TIMEOUT_SECONDS))

            # تسک تایمر + تسک گوش دادن به پاسخ درست
            asyncio.create_task(self.question_countdown(timer_message=timer_msg, question_id=question_id))
            asyncio.create_task(self.collect_answers(question_id=question_id))
            return

    async def collect_answers(self, question_id: int):
        """
        منتظر *اولین جواب درست* می‌ماند.
        پیام‌های اشتباه یا بی‌ربط هیچ واکنشی ایجاد نمی‌کنند.
        اگر در بازه‌ی زمانی QUESTION_TIMEOUT_SECONDS هیچ جواب درستی نرسد،
        این تابع کاری نمی‌کند و اعلام تمام شدن زمان را تسک تایمر انجام می‌دهد.
        """
        def check(m: discord.Message) -> bool:
            # فقط پیام‌های همین کانال و غیر بات
            if m.author.bot:
                return False
            if m.channel.id != self.channel.id:
                return False

            # اگر مسابقه یا این سوال تمام شده باشد، این لیسنر دیگر معتبر نیست
            if self.finished or self.question_resolved:
                return False
            if question_id != self.current_question_id:
                return False

            # فقط پیام‌هایی که بعد از نرمال‌سازی، جواب درست باشند، پذیرفته می‌شوند
            return self.is_correct_answer(m.content)

        try:
            msg: discord.Message = await bot.wait_for(
                "message",
                timeout=QUESTION_TIMEOUT_SECONDS + 7,
                check=check,
            )
        except asyncio.TimeoutError:
            # یعنی در این بازه‌ی زمانی هیچ پیام "درستی" نرسیده است.
            # در این حالت، تایمر خودش در انتها handle_timeout را صدا می‌زند.
            return

        # اگر در فاصله‌ی رسیدن پیام درست تا بیدار شدن این تابع، سوال عوض شده باشد، کاری نکن
        if self.finished or self.question_resolved or question_id != self.current_question_id:
            return

        await self.handle_correct_answer(msg.author)

    def is_correct_answer(self, user_text: str) -> bool:
        """فقط وقتی جواب کاربر بعد از نرمال‌سازی
        دقیقا برابر جواب ذخیره‌شده باشد True برمی‌گرداند.
        """
        user_norm = normalize_answer_text(user_text)
        fa_norm = normalize_answer_text(self.current_correct_text_fa or "")
        en_norm = normalize_answer_text(self.current_correct_text_en or "")

        # لاگ دیباگ در کنسول، برای وقتی که خواستی تست کنی
        print(
            "[DEBUG][answer_check] "
            f"user_raw={repr(user_text)} user_norm={repr(user_norm)} | "
            f"fa_raw={repr(self.current_correct_text_fa)} fa_norm={repr(fa_norm)} | "
            f"en_raw={repr(self.current_correct_text_en)} en_norm={repr(en_norm)}"
        )

        if not user_norm:
            return False

        # فقط تطابق کامل بعد از نرمال‌سازی پذیرفته می‌شود
        if fa_norm and user_norm == fa_norm:
            return True
        if en_norm and user_norm == en_norm:
            return True

        return False

    async def handle_timeout(self):
        if self.finished or self.question_resolved:
            return
        self.question_resolved = True
        correct_fa = self.current_correct_text_fa or "پاسخ صحیح"

        answer_body = f"⏱️ زمان تمام شد!\n\nپاسخ درست:\n**{correct_fa}**"
        answer_embed = make_embed(answer_body, color_from_hex(COLOR_TIMEOUT_ANSWER_EMBED))
        await self.channel.send(embed=answer_embed)

        scores_embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=scores_embed)

        await self.send_next_question()

    async def handle_correct_answer(self, user: discord.User):
        if self.finished or self.question_resolved:
            return
        self.question_resolved = True

        # فقط امتیاز مسابقه‌ای (لوکال)
        self.scores[user.id] = self.scores.get(user.id, 0) + 1

        self.score_step_counter += 1
        self.score_order_map[user.id] = self.score_step_counter

        correct_text = self.current_correct_text_fa or "پاسخ صحیح"
        body = f"✅ درسته : {correct_text}\n{user.mention} +1 امتیاز"
        green_embed = make_embed(body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await self.channel.send(embed=green_embed)

        scores_embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=scores_embed)

        await self.send_next_question()

    async def finish_quiz(self):
        self.finished = True
        await self.channel.send("# پایان مسابقه ⏰")

        embed = build_scores_embed(
            guild=self.channel.guild,
            scores=self.scores,
            description_prefix="🏆 نتیجه نهایی مسابقه:",
            color_hex=COLOR_FINAL_RESULTS_EMBED,
            order_map=self.score_order_map,
        )
        await self.channel.send(embed=embed)

        # ✅ بعد از پایان مسابقه تشریحی، امتیازهای مثبت این مسابقه به امتیاز کلی اضافه می‌شود
        add_match_scores_to_global(self.scores)

        if self.channel.id in active_question_sessions:
            del active_question_sessions[self.channel.id]


# ------------------ ویو دکمه های پاسخ (برای quiz و flags) ------------------

class AnswerView(discord.ui.View):
    def __init__(self, session, options_fa, labels: Optional[List[str]] = None):
        super().__init__(timeout=None)
        self.session = session
        self.options_fa = options_fa

        for i, _ in enumerate(options_fa):
            # اگر labels داده شده باشد (مثلاً در flags)،
            # متن دکمه = labels[i] خواهد بود.
            # اگر labels نباشد (مثل quiz)، دکمه‌ها ۱، ۲، ۳، ۴ هستند.
            if labels is not None and i < len(labels):
                label = labels[i]
            else:
                label = str(i + 1)

            # رنگ دکمه‌ها:
            # - برای FlagSession → success (سبز/خاکستری)
            # - برای بقیه (مثل QuizSession) → primary
            if isinstance(self.session, FlagSession):
                btn_style = discord.ButtonStyle.success
            else:
                btn_style = discord.ButtonStyle.primary

            button = discord.ui.Button(
                label=label,
                style=btn_style,
                custom_id=f"answer_{i}",
            )
            button.callback = self.make_callback(i)
            self.add_item(button)

    def make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id in self.session.answered_users:
                await interaction.response.send_message(
                    "⛔ شما قبلاً روی یک گزینه کلیک کرده‌اید.",
                    ephemeral=True
                )
                return

            self.session.answered_users.add(interaction.user.id)

            if self.session.finished or self.session.question_resolved:
                await interaction.response.send_message(
                    "این سوال قبلاً تمام شده است.",
                    ephemeral=True
                )
                return

            if index == self.session.current_correct_answer:
                await interaction.response.send_message(
                    "✅ پاسخ شما درست بود!",
                    ephemeral=True
                )
                await self.session.handle_correct_answer(interaction.user)
            else:
                await interaction.response.send_message(
                    "❌ پاسخ شما اشتباه بود.",
                    ephemeral=True
                )

        return callback


# ------------------ ایونت ها و کامندها ------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

    # اگر بات روی چند سرور باشد، به جز سرور مجاز از بقیه لفت می‌دهد
    if ALLOWED_GUILD_ID:
        for guild in bot.guilds:
            if guild.id != ALLOWED_GUILD_ID:
                print(f"🚪 Leaving unauthorized guild: {guild.name} ({guild.id})")
                try:
                    await guild.leave()
                except Exception:
                    pass


@bot.event
async def on_guild_join(guild: discord.Guild):
    # اگر کسی بعداً بات را به سرور دیگری اد کند، فوراً لفت می‌دهد
    if ALLOWED_GUILD_ID and guild.id != ALLOWED_GUILD_ID:
        print(f"🚪 Joined unauthorized guild, leaving: {guild.name} ({guild.id})")
        try:
            await guild.leave()
        except Exception:
            pass


# ------------------ ری‌اکشن برای مسابقه تشریحی (✅ / ❌) ------------------
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # خود بات را نادیده بگیر
    if bot.user and payload.user_id == bot.user.id:
        return

    # فقط روی سرور کار کنیم (DM نیست)
    if payload.guild_id is None:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    # member را اگر در payload باشد برمی‌داریم، اگر نبود از API می‌گیریم
    member = payload.member
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except Exception:
            return

    # فقط ادمین‌ها اجازه دارند با ری‌اکشن امتیاز را دستکاری کنند
    if not member.guild_permissions.administrator:
        return

    # گرفتن کانال
    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(payload.channel_id)
        except Exception:
            return

    if not isinstance(channel, discord.TextChannel):
        return

    # فقط اگر مسابقه تشریحی در این کانال فعال است
    session = active_question_sessions.get(channel.id)
    if session is None:
        return

    # مسابقه باید در حال اجرا باشد و این سوال هنوز تمام نشده باشد
    if session.finished or session.question_resolved:
        return

    # فقط دو ایموجی ✅ و ❌
    emoji_str = str(payload.emoji)
    if emoji_str == "✅":
        delta = 1
        mode = "add"
    elif emoji_str == "❌":
        delta = -1
        mode = "sub"
    else:
        return

    # پیام هدف (جواب بازیکن)
    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return

    target_user = message.author

    # روی پیام بات‌ها امتیازی اعمال نکن
    if target_user.bot:
        return

    # 🔹 تغییر امتیاز فقط در همین مسابقه تشریحی (لوکال، نه امتیاز کلی)
    session.scores[target_user.id] = session.scores.get(target_user.id, 0) + delta
    session.score_step_counter += 1
    session.score_order_map[target_user.id] = session.score_step_counter

    # ✅ حالت اضافه کردن امتیاز با امبد سبز
    if mode == "add":
        body = (
            f"✅ با تأیید ادمین، یک امتیاز به {target_user.mention} در این مسابقه اضافه شد.\n"
            f"(امتیاز فقط در همین مسابقه تغییر کرد)"
        )
        green_embed = make_embed(body, color_from_hex(COLOR_CORRECT_PLAYER_EMBED))
        await channel.send(embed=green_embed)

        # امبد رتبه‌بندی اصلی بعد از تایمر (داخل handle_timeout) ارسال می‌شود
        return

    # ❌ حالت کم کردن امتیاز با امبد نارنجی + امبد رتبه‌بندی
    if mode == "sub":
        body = (
            f"⚠️ با تأیید ادمین، یک امتیاز از {target_user.mention} در این مسابقه کم شد.\n"
            f"(امتیاز فقط در همین مسابقه تغییر کرد)"
        )
        orange_embed = make_embed(body, color_from_hex(COLOR_PENALTY_EMBED))
        await channel.send(embed=orange_embed)

        # بلافاصله امبد رتبه‌بندی تا این لحظه
        scores_embed = build_scores_embed(
            guild=guild,
            scores=session.scores,
            description_prefix="📊 رتبه و امتیاز بازیکنان تا این لحظه:",
            color_hex=COLOR_ROUND_SCORES_EMBED,
            order_map=session.score_order_map,
        )
        await channel.send(embed=scores_embed)


HELP_BODY = (
    "📖 **راهنمای دستورات **\n\n"
    "🟨 **دستورات اسلش**\n"
    "• `/help` — نمایش همین راهنما\n\n"
    "🟦 **دستورات متنی **\n\n"
    f"• `{BOT_PREFIX}quiz [تعداد]` — آماده‌سازی مسابقه چندگزینه‌ای با تعداد سوال دلخواه "
    f"(مثلاً `{BOT_PREFIX}quiz 10`). اگر تعداد را ننویسی، پیش‌فرض ۳۰ سوال است.\n\n"
    f"• `{BOT_PREFIX}flags [تعداد]` — آماده‌سازی مسابقه پرچم‌شناسی چهارگزینه‌ای.\n\n"
    f"• `{BOT_PREFIX}question [تعداد]` — آماده‌سازی مسابقه تشریحی.\n\n"
    f"• `{BOT_PREFIX}start` — شروع مسابقه‌ای که با `!quiz` یا `!question` یا `!flags` آماده شده است.\n\n"
    f"• `{BOT_PREFIX}top` — نمایش بهترین بازیکنان تاریخ این بازی‌ها.\n\n"
    f"• `{BOT_PREFIX}resetbot` — ریست کردن مسابقه‌های در حال اجرا.\n\n"
    f"• `{BOT_PREFIX}point @player ±N` — کم/زیاد کردن امتیاز کلی بازیکن (فقط Administrator).\n"
)


def build_help_response_embed():
    return make_embed(HELP_BODY, color_from_hex(COLOR_HELP_EMBED))


# اسلش کامند /help
@bot.tree.command(name="help", description="راهنمای دستورات بات Knight_Quiz")
async def help_cmd(interaction: discord.Interaction):
    embed = build_help_response_embed()
    if os.path.exists(QUESTION_BG_PATH):
        file = discord.File(QUESTION_BG_PATH, filename="help_bg.png")
        embed.set_image(url="attachment://help_bg.png")
        # برای جلوگیری از خطای Unknown interaction، از defer+followup می‌توانی استفاده کنی؛
        # ولی ساده‌ترین کار این است که مستقیماً پاسخ بدهیم:
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed)


# کامند متنی !help
@bot.command(name="help")
async def help_text_cmd(ctx: commands.Context):
    embed = build_help_response_embed()
    if os.path.exists(QUESTION_BG_PATH):
        file = discord.File(QUESTION_BG_PATH, filename="help_bg.png")
        embed.set_image(url="attachment://help_bg.png")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)


# کامند !quiz برای آماده‌سازی مسابقه چندگزینه‌ای (برای همه آزاد است)
@bot.command(name="quiz")
async def quiz_cmd(ctx: commands.Context, num_questions: Optional[int] = None):
    if (
        ctx.channel.id in active_quizzes
        or ctx.channel.id in active_question_sessions
        or ctx.channel.id in active_flag_sessions
    ):
        await ctx.send("⛔ در این کانال یک مسابقه در حال اجراست. لطفاً صبر کنید تا تمام شود.")
        return

    if num_questions is None:
        num_questions = DEFAULT_NUM_QUESTIONS

    if num_questions <= 0:
        await ctx.send("تعداد سوال باید یک عدد مثبت باشد.")
        return

    session = QuizSession(ctx.channel, num_questions=num_questions)
    active_quizzes[ctx.channel.id] = session

    success = await session.preload_questions(ctx)
    if not success:
        if ctx.channel.id in active_quizzes:
            del active_quizzes[ctx.channel.id]
        return


# کامند !flags برای آماده‌سازی مسابقه پرچم‌ها (برای همه آزاد است)
@bot.command(name="flags")
async def flags_cmd(ctx: commands.Context, num_questions: Optional[int] = None):
    # جلوگیری از تداخل با مسابقه دیگر در همان کانال
    if (
        ctx.channel.id in active_quizzes
        or ctx.channel.id in active_question_sessions
        or ctx.channel.id in active_flag_sessions
    ):
        await ctx.send("⛔ در این کانال یک مسابقه در حال اجراست. لطفاً صبر کنید تا تمام شود.")
        return

    if num_questions is None:
        num_questions = DEFAULT_NUM_QUESTIONS

    if num_questions <= 0:
        await ctx.send("تعداد سوال باید یک عدد مثبت باشد.")
        return

    session = FlagSession(ctx.channel, num_questions=num_questions)
    active_flag_sessions[ctx.channel.id] = session

    success = await session.preload_questions(ctx)
    if not success:
        if ctx.channel.id in active_flag_sessions:
            del active_flag_sessions[ctx.channel.id]
        return


# کامند !question برای آماده‌سازی مسابقه تشریحی (فقط ادمین با پرمیشن Administrator)
@bot.command(name="question")
async def question_cmd(ctx: commands.Context, num_questions: Optional[int] = None):
    # 🚫 محدودیت: فقط کسی که پرمیشن Administrator دارد
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("⛔ فقط ادمین های سرور (با پرمیشن **Administrator**) می‌توانند از دستور `!question` استفاده کنند.")
        return

    if (
        ctx.channel.id in active_quizzes
        or ctx.channel.id in active_question_sessions
        or ctx.channel.id in active_flag_sessions
    ):
        await ctx.send("⛔ در این کانال یک مسابقه در حال اجراست. لطفاً صبر کنید تا تمام شود.")
        return

    if num_questions is None:
        num_questions = DEFAULT_NUM_QUESTIONS

    if num_questions <= 0:
        await ctx.send("تعداد سوال باید یک عدد مثبت باشد.")
        return

    session = QuestionSession(ctx.channel, num_questions=num_questions)
    active_question_sessions[ctx.channel.id] = session

    success = await session.preload_questions(ctx)
    if not success:
        if ctx.channel.id in active_question_sessions:
            del active_question_sessions[ctx.channel.id]
        return


# کامند !start برای شروع مسابقه‌ای که با !quiz یا !question یا !flags آماده شده
@bot.command(name="start")
async def start_cmd(ctx: commands.Context):
    quiz_session = active_quizzes.get(ctx.channel.id)
    flag_session = active_flag_sessions.get(ctx.channel.id)
    question_session = active_question_sessions.get(ctx.channel.id)

    # اولویت: quiz > flags > question

    # ۱) اگر quiz آماده است
    if quiz_session and not quiz_session.finished:
        session = quiz_session

        if session.finished:
            await ctx.send("⏰ این مسابقه قبلاً تمام شده است. برای مسابقه جدید از `!quiz` استفاده کن.")
            return

        if session.started:
            await ctx.send("⚠️ این مسابقه قبلاً شروع شده است.")
            return

        if not session.prepared_questions:
            await ctx.send("❌ هنوز هیچ سوالی برای این مسابقه آماده نشده است. ابتدا `!quiz` را اجرا کن.")
            return

        session.started = True
        start_body = "مسابقه شروع شد 📢"
        start_embed = make_embed(start_body, color_from_hex(COLOR_QUESTION_EMBED))
        await ctx.send(embed=start_embed)

        await session.send_next_question()
        return

    # ۲) اگر flags آماده است
    if flag_session and not flag_session.finished:
        session = flag_session

        if session.started:
            await ctx.send("⚠️ این مسابقه قبلاً شروع شده است.")
            return

        if not session.prepared_questions:
            await ctx.send("❌ هنوز هیچ سوالی برای این مسابقه آماده نشده است. ابتدا `!flags` را اجرا کن.")
            return

        session.started = True
        start_body = "مسابقه پرچم‌ها شروع شد 📢"
        start_embed = make_embed(start_body, color_from_hex(COLOR_QUESTION_EMBED))
        await ctx.send(embed=start_embed)

        await session.send_next_question()
        return

    # ۳) اگر question آماده است
    if question_session and not question_session.finished:
        await question_session.start(ctx)
        return

    await ctx.send("❌ در این کانال هیچ مسابقه‌ای آماده نشده است. ابتدا با `!quiz` یا `!question` یا `!flags` سوال‌ها را آماده کن.")


# کامند !top
@bot.command(name="top", aliases=["toprank", "topRank"])
async def top_cmd(ctx: commands.Context, limit: int = 10):
    global global_scores, global_score_order_map

    if not global_scores:
        await ctx.send("هنوز هیچ امتیاز کلی ثبت نشده است.")
        return

    def sort_key(item):
        user_id, score = item
        order_value = global_score_order_map.get(user_id, 10**9)
        return (-score, order_value)

    sorted_scores = sorted(global_scores.items(), key=sort_key)
    sorted_scores = sorted_scores[:limit]

    scores_for_embed = {user_id: score for user_id, score in sorted_scores}

    body_prefix = "🏆 بهترین بازیکنان تاریخ این بازی‌ها:"
    embed = build_scores_embed(
        guild=ctx.guild,
        scores=scores_for_embed,
        description_prefix=body_prefix,
        color_hex=COLOR_TOPRANK_EMBED,
        order_map=global_score_order_map,
    )
    await ctx.send(embed=embed)


# کامند !debugfamilies — نمایش تنوع خانواده‌ها و منبع‌ها در مسابقه‌ی quiz فعلی
@bot.command(name="debugfamilies")
@commands.has_permissions(administrator=True)
async def debugfamilies_cmd(ctx: commands.Context):
    """
    دیباگ تنوع سوال‌ها:
    - درصد سوال‌های هر منبع (Trivia / OpenTDB)
    - توزیع سوال‌ها بین خانواده‌های موضوعی
    - لیست خانواده‌هایی که از حد حدودی ۲۰٪ بیشتر شده‌اند
    """
    session = active_quizzes.get(ctx.channel.id)
    if not session or not session.prepared_questions:
        await ctx.send("❌ در این کانال هیچ مسابقه‌ی `quiz` فعالی برای نمایش دسته‌ها نیست.")
        return

    total = len(session.prepared_questions)
    if total == 0:
        await ctx.send("ℹ️ هنوز هیچ سوالی در این مسابقه ثبت نشده است.")
        return

    # اگر به هر دلیلی family_stats یا source_stats خالی بود، همین‌جا دوباره محاسبه می‌کنیم
    if not getattr(session, "family_stats", None) or not getattr(session, "source_stats", None):
        session.family_stats = {}
        session.source_stats = {}
        for pq in session.prepared_questions:
            fam = getattr(pq, "family", "unknown")
            src = getattr(pq, "source", "unknown")
            session.family_stats[fam] = session.family_stats.get(fam, 0) + 1
            session.source_stats[src] = session.source_stats.get(src, 0) + 1

    # ---------- بخش ۱: توزیع منبع سوال‌ها ----------
    source_pretty = {
        "trivia": "Trivia API",
        "opentdb": "OpenTDB",
        "unknown": "نامشخص",
    }

    source_lines = []
    for src, count in sorted(session.source_stats.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        label = source_pretty.get(src, src)
        # یک نوار ساده براساس درصد (هر بلوک ≈ ۵٪)
        bar_len = max(1, int(pct / 5)) if pct > 0 else 0
        bar = "█" * bar_len
        source_lines.append(f"- **{label}** : {count} سؤال (~{pct:.1f}٪) {bar}")

    source_body = "\n".join(source_lines) if source_lines else "هیچ منبعی ثبت نشده است."

    # ---------- بخش ۲: توزیع خانواده‌های موضوعی ----------
    family_lines = []
    over_limit = []  # خانواده‌هایی که از ۲۰٪ بیشتر شده‌اند
    for fam, count in sorted(session.family_stats.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        bar_len = max(1, int(pct / 5)) if pct > 0 else 0
        bar = "█" * bar_len
        family_lines.append(f"- **{fam}** : {count} سؤال (~{pct:.1f}٪) {bar}")
        if pct > 20.0:
            over_limit.append((fam, count, pct))

    family_body = "\n".join(family_lines) if family_lines else "هیچ خانواده‌ای ثبت نشده است."

    # ---------- بخش ۳: نتیجه‌ی محدودیت ۲۰٪ ----------
    if over_limit:
        warn_lines = ["⚠️ **خانواده‌هایی که از حد ۲۰٪ بیشتر شده‌اند:**"]
        for fam, count, pct in over_limit:
            warn_lines.append(f"- `{fam}` → {count} سؤال ({pct:.1f}٪)")
        limit_body = "\n".join(warn_lines)
    else:
        limit_body = "✅ هیچ خانواده‌ای از حد ۲۰٪ بیشتر نشده است (در انتخاب اولیه)."

    body = (
        "🔍 **دیباگ تنوع سوال‌های مسابقه‌ی فعلی (quiz)**\n"
        f"تعداد کل سوال‌ها: **{total}**\n\n"
        "### 📦 توزیع منبع سوال‌ها:\n"
        f"{source_body}\n\n"
        "### 🧩 توزیع خانواده‌های موضوعی:\n"
        f"{family_body}\n\n"
        "### ⚖ وضعیت محدودیت حدودی ۲۰٪ برای خانواده‌ها:\n"
        f"{limit_body}"
    )

    embed = make_embed(body, color_from_hex(COLOR_HELP_EMBED))
    await ctx.send(embed=embed)


# کامند !resetbot — برای همه آزاد، ریست کردن مسابقه‌ها
@bot.command(name="resetbot")
async def resetbot_cmd(ctx: commands.Context):
    global active_quizzes, active_flag_sessions, active_question_sessions

    # همه مسابقه‌های در حال اجرا را خاتمه‌خورده علامت می‌کنیم
    for s in list(active_quizzes.values()):
        s.finished = True
    for s in list(active_flag_sessions.values()):
        s.finished = True
    for s in list(active_question_sessions.values()):
        s.finished = True

    active_quizzes.clear()
    active_flag_sessions.clear()
    active_question_sessions.clear()

    embed = make_embed(
        "♻ بات ریست شد ، الان دوباره میتونی دستور مسابقه ها رو اجرا کنی",
        discord.Color.blue()
    )
    await ctx.send(embed=embed)


# کامند !point @player ±N — فقط Administrator
@bot.command(name="point")
async def point_cmd(ctx: commands.Context, member: discord.Member, amount: int):
    global global_scores, global_score_order_map, global_score_step_counter

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("⛔ فقط ادمین های سرور (با پرمیشن **Administrator**) می‌توانند از دستور `!point` استفاده کنند.")
        return

    global_scores[member.id] = global_scores.get(member.id, 0) + amount
    global_score_step_counter += 1
    global_score_order_map[member.id] = global_score_step_counter
    save_global_scores(global_scores)

    new_score = global_scores[member.id]
    sign = "+" if amount >= 0 else ""
    body = f"امتیاز کلی {member.mention} {sign}{amount} تغییر کرد.\nامتیاز جدید: **{new_score}**"
    embed = make_embed(body, color_from_hex(COLOR_TOPRANK_EMBED))
    await ctx.send(embed=embed)


def main():
    bot.run(TOKEN)


if __name__ == "__main__":
    main()