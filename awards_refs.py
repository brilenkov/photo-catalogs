#!/usr/bin/env python3
"""
35awards References Collector
=============================
Универсальный инструмент для сбора референсов с 35awards.com по ключевому слову.

РЕЖИМЫ ЗАПУСКА:
  1. CLI с параметрами:
     python awards_refs.py --query "женский портрет" --count 40
     python awards_refs.py -q "fashion" -c 30 -o my_gallery.html
     python awards_refs.py -q "ню" --use-vlm "девушка в кадре"
     python awards_refs.py -q "все номинации"

  2. Интерактивный режим (без параметров):
     python awards_refs.py
     → программа спросит все параметры

  3. Веб-режим (опционально, нужен Flask):
     python awards_refs.py --web
     → откроется http://localhost:5000 с формой

ТРЕБОВАНИЯ:
  pip install requests beautifulsoup4 pillow
  (опционально) pip install flask  для веб-режима
  (опционально) z-ai CLI установлен  для --use-vlm

КАК ЭТО РАБОТАЕТ:
  1. Парсит страницы winnersXXth.html (8-11 конкурсы)
  2. Кеширует HTML локально (data/contests/)
  3. Ищет фото по номинации (ключевое слово)
  4. Скачивает фото в высоком разрешении (1500px) с кешированием
  5. Опционально фильтрует через VLM (z-ai vision)
  6. Генерирует HTML с полными фото в base64 (работает офлайн)

КЛЮЧЕВЫЕ СЛОВА (русский / английский):
  Номинации 35awards:
    "женский портрет" / "female portrait"
    "мода" / "fashion" / "гламур" / "glamour"
    "постановка" / "staged"
    "ню" / "nude" / "18+"
    "спорт" / "motion" / "движение"
    "улица" / "street"
    "пейзаж" / "landscape"
    "макро" / "macro"
    "детский портрет" / "child portrait"
    "архитектура" / "urban"
    "натюрморт" / "still life"
    "репортаж" / "reportage"
    "чб" / "black and white"
    "концепт" / "conceptual"
    "подводная" / "underwater"
    "аэро" / "aerial"
    "мужской портрет" / "male portrait"
    "животные" / "wildlife"
    "питомцы" / "pets"
    "мобильная" / "mobile"

  Составные:
    "девушки" / "women" → Female portrait + Fashion & Glamour + Staged + Nude
    "все" / "all" → все номинации

АВТОР: Z.ai · 2026
"""

import argparse
import base64
import io
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from urllib.parse import quote

# ==========================================================================
# КОНФИГУРАЦИЯ
# ==========================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONTESTS_DIR = os.path.join(DATA_DIR, "contests")
PHOTOS_CACHE_DIR = os.path.join(DATA_DIR, "photos_cache")
HTML_CACHE_DIR = os.path.join(DATA_DIR, "html_cache")

for d in [DATA_DIR, CONTESTS_DIR, PHOTOS_CACHE_DIR, HTML_CACHE_DIR]:
    os.makedirs(d, exist_ok=True)

# Конкурсы для парсинга — 9 штук: 2015, 2016, 5th-11th
CONTESTS = [
    {"edition": "2015", "year": "2015",      "file": "winners2015.html", "format": "old_2015"},
    {"edition": "2016", "year": "2016",      "file": "winners2016.html", "format": "old_2016"},
    {"edition": "5th",  "year": "2017-2018", "file": "winners5th.html",  "format": "5th"},
    {"edition": "6th",  "year": "2018-2019", "file": "winners6th.html",  "format": "modern"},
    {"edition": "7th",  "year": "2019-2020", "file": "winners7th.html",  "format": "modern_ru"},
    {"edition": "8th",  "year": "2022-2023", "file": "winners8th.html",  "format": "modern"},
    {"edition": "9th",  "year": "2023-2024", "file": "winners9th.html",  "format": "modern"},
    {"edition": "10th", "year": "2024",      "file": "winners10th.html", "format": "modern"},
    {"edition": "11th", "year": "2025",      "file": "winners11th.html", "format": "modern"},
]

# Маппинг ключевых слов на номинации 35awards
KEYWORD_MAP = {
    # Русские
    "женский портрет": ["Female portrait"],
    "портрет девушки": ["Female portrait"],
    "женщина": ["Female portrait"],
    "девушка": ["Female portrait", "Fashion & Glamour"],
    "девушки": ["Female portrait", "Fashion & Glamour", "Staged photo", "Nude 18+"],
    "женщины": ["Female portrait", "Fashion & Glamour", "Staged photo", "Nude 18+"],
    "мода": ["Fashion & Glamour"],
    "гламур": ["Fashion & Glamour"],
    "fashion": ["Fashion & Glamour"],
    "glamour": ["Fashion & Glamour"],
    "постановка": ["Staged photo"],
    "постановочное": ["Staged photo"],
    "staged": ["Staged photo"],
    "ню": ["Nude 18+"],
    "nude": ["Nude 18+"],
    "18+": ["Nude 18+"],
    "обнаженная": ["Nude 18+"],
    "спорт": ["Motion"],
    "движение": ["Motion"],
    "motion": ["Motion"],
    "sport": ["Motion"],
    "улица": ["Street photo"],
    "street": ["Street photo"],
    "пейзаж": ["Landscape - daytime", "Landscape - night (+Astrophotography)"],
    "landscape": ["Landscape - daytime", "Landscape - night (+Astrophotography)"],
    "макро": ["Macro"],
    "macro": ["Macro"],
    "детский портрет": ["Child portrait"],
    "дети": ["Child portrait", "Children staged photography"],
    "child": ["Child portrait", "Children staged photography"],
    "архитектура": ["Urban landscape (+Architecture)"],
    "urban": ["Urban landscape (+Architecture)"],
    "город": ["Urban landscape (+Architecture)"],
    "натюрморт": ["Still life"],
    "still life": ["Still life"],
    "репортаж": ["Reportage photography"],
    "reportage": ["Reportage photography"],
    "чб": ["Black and white"],
    "черно-белое": ["Black and white"],
    "black and white": ["Black and white"],
    "концепт": ["Conceptual photo"],
    "conceptual": ["Conceptual photo"],
    "подводная": ["Underwater photography"],
    "underwater": ["Underwater photography"],
    "аэро": ["Aerial photography"],
    "aerial": ["Aerial photography"],
    "мужской портрет": ["Male portrait"],
    "мужчина": ["Male portrait"],
    "male portrait": ["Male portrait"],
    "животные": ["Wildlife"],
    "wildlife": ["Wildlife"],
    "природа": ["Wildlife", "Landscape - daytime"],
    "питомцы": ["Pets"],
    "pets": ["Pets"],
    "мобильная": ["Mobile photography"],
    "mobile": ["Mobile photography"],
    # Прямые номинации (английский)
    "female portrait": ["Female portrait"],
    "fashion & glamour": ["Fashion & Glamour"],
    "staged photo": ["Staged photo"],
    "nude 18+": ["Nude 18+"],
    "street photo": ["Street photo"],
    "landscape - daytime": ["Landscape - daytime"],
    "landscape - night": ["Landscape - night (+Astrophotography)"],
    "child portrait": ["Child portrait"],
    "children staged photography": ["Children staged photography"],
    "conceptual photo": ["Conceptual photo"],
    "urban landscape": ["Urban landscape (+Architecture)"],
    "still life": ["Still life"],
    "reportage photography": ["Reportage photography"],
    "black and white": ["Black and white"],
    "underwater photography": ["Underwater photography"],
    "aerial photography": ["Aerial photography"],
    "male portrait": ["Male portrait"],
    "mobile photography": ["Mobile photography"],
    # Спец
    "все": None,  # все номинации
    "all": None,
}

# Список всех номинаций (для "все")
ALL_NOMINATIONS = [
    "Female portrait", "Fashion & Glamour", "Staged photo", "Nude 18+",
    "Motion", "Street photo", "Landscape - daytime",
    "Landscape - night (+Astrophotography)", "Macro", "Child portrait",
    "Children staged photography", "Conceptual photo",
    "Urban landscape (+Architecture)", "Still life",
    "Reportage photography", "Black and white",
    "Underwater photography", "Aerial photography",
    "Male portrait", "Wildlife", "Pets", "Mobile photography",
]

# Маппинг: edition → (url_year, {nomination_name: nomination_id})
# url_year используется для построения URL: winners{url_year}/nomination/{id}/
# Для 2015 нет отдельных страниц номинаций (старый формат)
EDITION_NOMINATION_IDS = {
    "2015": ("2015", {}),  # Нет nomination pages, используем старый формат
    "2016": ("2016", {
        "Black and white": "87", "Conceptual photo": "88", "Portrait": "89",
        "Children photo": "90", "Landscape - daytime": "91", "Wildlife": "93",
        "Glamour/Nude 18+": "94", "Macro": "97",
        "Nude 18+": "94",  # alias
        "Female portrait": "89",  # Portrait = Female portrait in 2016
        "Fashion & Glamour": "94",
        "Street photo": "95", "Motion": "96",
        "Aerial photography": "98", "Still life": "99",
        "Mobile photography": "100", "Urban landscape (+Architecture)": "101",
        "Underwater photography": "102", "Male portrait": "89",
        "Pets": "103", "Reportage photography": "104",
        "Landscape - night (+Astrophotography)": "105",
    }),
    "5th": ("2019", {
        "Aerial photography": "512", "Black and white": "474",
        "Children photo": "498", "Conceptual photo": "495",
        "Daily Life": "505", "Fashion & Glamour": "510",
        "Female portrait": "496", "Landscape - daytime": "499",
        "Male portrait": "497", "Motion": "513",
        "Nude 18+": "503", "Staged photo": "504",
        "Street photo": "506", "Macro": "500",
        "Wildlife": "507", "Pets": "508",
        "Mobile photography": "509", "Still life": "502",
        "Underwater photography": "511", "Reportage photography": "501",
        "Urban landscape (+Architecture)": "514",
    }),
    "6th": ("2020", {
        "Aerial photography (photo from drone)": "588", "Black and white": "607",
        "Children photo": "590", "Conceptual photo": "593",
        "Fashion & Glamour": "606", "Female portrait": "592",
        "Landscape - daytime": "599", "Landscape - night (evening)": "600",
        "Male portrait": "596", "Motion": "669",
        "Nude 18+": "598", "Staged photo": "602",
        "Street photo": "604", "Macro": "601",
        "Wildlife": "605", "Pets": "603",
        "Mobile photography": "608", "Still life": "597",
        "Underwater photography": "591", "Reportage photography": "594",
        "Urban landscape (+Architecture)": "595",
    }),
    "7th": ("2021", {
        # 7th использует русские названия
        "Аэрофотография": "678", "Городской пейзаж (Архитектура)": "679",
        "Движение": "698", "Детская постановочная фотография": "680",
        "Детский портрет": "707", "Дикий животный мир": "681",
        "Женский портрет": "682", "Концептуальная фотография": "683",
        "Макро": "684", "Мобильная фотография": "685",
        "Мужской портрет": "686", "Ню 18+": "688",
        "Подводная фотография": "689", "Репортажная фотография": "690",
        "Серия фотографий": "691", "Съемка со вспышкой": "692",
        "Уличная фотография": "693", "Фэшн и гламур": "694",
        "Черно-белая фотография": "695", "Натюрморт": "696",
        "Питомцы": "697", "Пейзаж - дневной": "699",
        "Пейзаж - ночной": "700", "Daily Life": "701",
    }),
    "8th": ("2022", {
        "Aerial photography": "759", "Black and white": "782",
        "Child portrait": "763", "Children staged photography": "762",
        "Conceptual photo": "766", "Daily Life": "775",
        "Fashion & Glamour": "781", "Female portrait": "765",
        "Landscape - daytime": "773", "Landscape - night (+Astrophotography)": "774",
        "Macro": "777", "Male portrait": "764",
        "Mobile photography": "779", "Motion": "780",
        "Nude 18+": "778", "Pets": "776",
        "Reportage photography": "783", "Still life": "784",
        "Street photo": "785", "Staged photo": "786",
        "Underwater photography": "787", "Urban landscape (+Architecture)": "788",
        "Wildlife": "789",
    }),
    "9th": ("2023", {
        "Aerial photography": "844", "Black and white": "867",
        "Child portrait": "848", "Children staged photography": "847",
        "Conceptual photo": "851", "Daily Life": "866",
        "Fashion & Glamour": "866", "Female portrait": "850",
        "Landscape - daytime": "858", "Landscape - night (+Astrophotography)": "859",
        "Macro": "862", "Male portrait": "849",
        "Mobile photography": "864", "Motion": "865",
        "Nude 18+": "863", "Pets": "861",
        "Reportage photography": "868", "Still life": "869",
        "Street photo": "870", "Staged photo": "871",
        "Underwater photography": "872", "Urban landscape (+Architecture)": "873",
        "Wildlife": "874",
    }),
    "10th": ("10th", {
        "Aerial photography": "1002", "Black and white": "1025",
        "Child portrait": "1006", "Children staged photography": "1005",
        "Conceptual photo": "1010", "Fashion & Glamour": "1024",
        "Female portrait": "1009", "Landscape - daytime": "1016",
        "Landscape - night (+Astrophotography)": "1017",
        "Macro": "1020", "Male portrait": "1008",
        "Mobile photography": "1022", "Motion": "1023",
        "Nude 18+": "1021", "Pets": "1019",
        "Reportage photography": "1026", "Still life": "1027",
        "Street photo": "1028", "Staged photo": "1029",
        "Underwater photography": "1030", "Urban landscape (+Architecture)": "1031",
        "Wildlife": "1032",
    }),
    "11th": ("11th", {
        "Aerial photography": "1191", "Black and white": "1192",
        "Child portrait": "1193", "Children staged photography": "1194",
        "Conceptual photo": "1195", "Fashion & Glamour": "1196",
        "Female portrait": "1197", "Landscape - daytime": "1198",
        "Landscape - night (+Astrophotography)": "1199",
        "Macro": "1200", "Male portrait": "1201",
        "Mobile photography": "1202", "Motion": "1203",
        "Nude 18+": "1204", "Pets": "1205",
        "Reportage photography": "1206", "Still life": "1207",
        "Street photo": "1208", "Staged photo": "1209",
        "Underwater photography": "1210", "Urban landscape (+Architecture)": "1211",
        "Wildlife": "1212",
    }),
}

# Страны — перевод
RU_COUNTRY = {
    "Russian Federation": "Россия", "United States": "США",
    "United Kingdom": "Великобритания", "Kazakhstan": "Казахстан",
    "Belarus": "Беларусь", "Iran": "Иран", "Cuba": "Куба",
    "Viet Nam": "Вьетнам", "Brazil": "Бразилия", "Lithuania": "Литва",
    "Canada": "Канада", "Austria": "Австрия", "Bulgaria": "Болгария",
    "Germany": "Германия", "Israel": "Израиль", "Ukraine": "Украина",
    "Poland": "Польша", "Japan": "Япония", "RUSSIA": "Россия",
    "United Arab Emirates": "ОАЭ", "Latvia": "Латвия", "Spain": "Испания",
    "Italy": "Италия", "France": "Франция", "Netherlands": "Нидерланды",
    "Australia": "Австралия", "New Zealand": "Новая Зеландия",
    "Chile": "Чили", "Iceland": "Исландия", "Croatia": "Хорватия",
    "Indonesia": "Индонезия", "India": "Индия", "China": "Китай",
    "Czech Republic": "Чехия", "Slovakia": "Словакия",
    "Malaysia": "Малайзия", "Switzerland": "Швейцария",
    "Belgium": "Бельгия", "Ireland": "Ирландия", "Estonia": "Эстония",
    "Slovenia": "Словения", "Georgia": "Грузия", "Armenia": "Армения",
    "Romania": "Румыния", "Serbia": "Сербия", "Hungary": "Венгрия",
    "Sweden": "Швеция", "Norway": "Норвегия", "Finland": "Финляндия",
    "Denmark": "Дания", "Portugal": "Португалия", "Greece": "Греция",
    "Turkey": "Турция", "Mexico": "Мексика", "Argentina": "Аргентина",
    "Colombia": "Колумбия", "Peru": "Перу", "Egypt": "Египет",
    "Thailand": "Таиланд", "Philippines": "Филиппины",
    "South Africa": "ЮАР", "Kenya": "Кения", "Morocco": "Марокко",
}

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


# ==========================================================================
# 1. ЗАГРУЗКА И КЕШИРОВАНИЕ HTML СТРАНИЦ 35AWARDS
# ==========================================================================

def fetch_contest_html(edition, force=False):
    """Скачать HTML страницу конкурса winnersXXth/ с кешированием."""
    file_name = f"winners{edition}.html"
    local_path = os.path.join(CONTESTS_DIR, file_name)
    
    if os.path.exists(local_path) and not force and os.path.getsize(local_path) > 50000:
        return local_path
    
    url = f"https://35awards.com/winners{edition}/"
    print(f"  Скачиваю {url}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            data = resp.read()
        with open(local_path, "wb") as f:
            f.write(data)
        print(f"    OK: {len(data)} байт")
        return local_path
    except Exception as e:
        print(f"    ОШИБКА: {e}")
        return None


def fetch_all_contests(force=False):
    """Скачать все HTML страницы конкурсов."""
    print("\n=== Загрузка HTML страниц конкурсов (9 штук) ===")
    paths = {}
    for c in CONTESTS:
        p = fetch_contest_html(c["edition"], force=force)
        if p:
            paths[c["edition"]] = {
                "path": p,
                "year": c["year"],
                "edition": c["edition"],
                "format": c["format"],
            }
    print(f"\n→ Загружено конкурсов: {len(paths)}/{len(CONTESTS)}")
    return paths


# ==========================================================================
# 2. ПАРСИНГ HTML — ИЗВЛЕЧЕНИЕ ФОТО ИЗ НОМИНАЦИЙ
# ==========================================================================

def slugify_author(name):
    if not name:
        return ""
    return quote(re.sub(r"\s+", "-", name.strip()), safe="-")


def extract_photo_from_col(col_div, edition, year, nomination, rank, section):
    """Извлечь метаданные фото из col-1 div."""
    from bs4 import BeautifulSoup
    img = col_div.find("img", src=re.compile(r"photos_col"))
    if not img:
        return None
    
    src = img.get("src", "")
    large_img = img.get("large-img", "")
    author_attr = img.get("author", "")
    
    m = re.search(r"/(\d+)_\d+r\.jpg", src)
    photo_id = m.group(1) if m else ""
    m2 = re.search(r"/photos_col/r2/(\d+)/", src)
    path_prefix = m2.group(1) if m2 else ""
    
    info = col_div.find("div", class_="photo_info")
    author_name = ""
    country = ""
    city = ""
    title = ""
    country_code = ""
    
    if info:
        bebas_bold = info.find("span", class_="bebasBold")
        if bebas_bold:
            author_name = bebas_bold.get_text(strip=True)
        bebas = info.find("div", class_="bebas")
        if bebas:
            loc_text = bebas.get_text(strip=True, separator=" ")
            flag = bebas.find("span", class_=re.compile(r"flag-icon-(\w+)"))
            if flag:
                m3 = re.search(r"flag-icon-(\w+)", " ".join(flag.get("class", [])))
                if m3:
                    country_code = m3.group(1).upper()
            if ", " in loc_text:
                parts = loc_text.split(", ", 1)
                country = parts[0].strip()
                city = parts[1].strip() if len(parts) > 1 else ""
            else:
                country = loc_text.strip()
        col5 = info.find("div", class_="col-5")
        if col5:
            title = col5.get_text(strip=True)
    
    if not author_name and author_attr:
        author_name = author_attr
    
    large_url = ""
    if photo_id and path_prefix:
        large_url = f"https://35awards.com/photos_temp/sizes/{path_prefix}/{photo_id}_1500n.jpg"
    elif large_img:
        large_url = large_img
    
    author_slug = slugify_author(author_name)
    author_url = f"https://35awards.com/authors/{author_slug}/" if author_slug else ""
    photo_page_url = f"https://35awards.com/ru/photo/{photo_id}/" if photo_id else ""
    
    return {
        "edition": edition,
        "year": year,
        "nomination": nomination,
        "rank": rank,
        "section": section,
        "photo_id": photo_id,
        "author_name": author_name,
        "country": country,
        "country_code": country_code,
        "city": city,
        "title": title or "(без названия)",
        "photo_url_large": large_url,
        "photo_url_thumb": src,
        "photo_page_url": photo_page_url,
        "author_url": author_url,
    }


def extract_nomination_photos(html_path, edition, year, target_nomination, max_photos=15,
                              fmt="modern"):
    """Извлечь фото из номинации. Поддерживает разные форматы страниц."""
    if fmt == "old_2015":
        return extract_2015_format(html_path, edition, year, target_nomination, max_photos)
    elif fmt == "old_2016":
        return extract_2016_format(html_path, edition, year, target_nomination, max_photos)
    elif fmt == "5th":
        return extract_5th_format(html_path, edition, year, target_nomination, max_photos)
    else:
        return extract_modern_format(html_path, edition, year, target_nomination, max_photos)


def extract_modern_format(html_path, edition, year, target_nomination, max_photos=15):
    """Современный формат (6th-11th): h2 + best100 rows."""
    from bs4 import BeautifulSoup
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    
    h2s = soup.find_all("h2")
    results = []
    seen_photo_ids = set()
    
    for i, h2 in enumerate(h2s):
        text = h2.get_text(strip=True)
        if not text.startswith(target_nomination):
            continue
        if not (("100 BEST SINGLE PHOTOS" in text and "WINNERS" in text) or
                ("Viewers Choice" in text and "series" not in text.lower())):
            continue
        
        section = "Viewers Choice" if "Viewers Choice" in text else "100 BEST"
        next_h2 = h2s[i + 1] if i + 1 < len(h2s) else None
        
        photos_in_section = []
        for elem in h2.find_all_next():
            if next_h2 and elem is next_h2:
                break
            cls = elem.get("class", []) if hasattr(elem, "get") else []
            if "best100" in cls:
                cols = elem.find_all("div", class_="col-1", recursive=False)
                for col in cols:
                    photos_in_section.append(col)
        
        for col in photos_in_section:
            if len(results) >= max_photos:
                break
            img = col.find("img", src=re.compile(r"photos_col"))
            if img:
                src = img.get("src", "")
                m = re.search(r"/(\d+)_\d+r\.jpg", src)
                pid = m.group(1) if m else ""
                if pid and pid in seen_photo_ids:
                    continue
                if pid:
                    seen_photo_ids.add(pid)
            
            info = extract_photo_from_col(col, edition, year, target_nomination,
                                          len(results) + 1, section)
            if info:
                results.append(info)
        
        if len(results) >= max_photos:
            break
    
    return results


def extract_2015_format(html_path, edition, year, target_nomination, max_photos=15):
    """Формат 2015: h2 '18+' + photoListWinners (top 3) + photoListWinners_other."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    
    # В 2015 номинация называется "18+", не "Nude 18+"
    search_nom = target_nomination
    if target_nomination == "Nude 18+":
        search_nom = "18+"
    
    # Для 2015 другие номинации тоже могут отличаться
    nom_map_2015 = {
        "Female portrait": "Human",  # В 2015 нет Female portrait, есть Human
        "Fashion & Glamour": "Human",
        "Staged photo": "Human",
        "Nude 18+": "18+",
        "Black and white": "Black and White",
    }
    if target_nomination in nom_map_2015:
        search_nom = nom_map_2015[target_nomination]
    
    # Найти h2 с нужной номинацией
    h2_target = None
    for h2 in soup.find_all("h2"):
        if search_nom in h2.get_text(strip=True):
            h2_target = h2
            break
    
    if not h2_target:
        return []
    
    parent = h2_target.parent
    photo_list = parent.find_next_sibling("div", class_="photoListWinners")
    photo_other = parent.find_next_sibling("div", class_="photoListWinners_other")
    
    results = []
    
    def process_photo_list(container, section):
        if not container:
            return
        items = container.find_all("a", href=True)
        for a in items:
            if len(results) >= max_photos:
                break
            href = a.get("href", "")
            img = a.find("img")
            if not img:
                continue
            src = img.get("src", "")
            
            m = re.search(r"/(\d+)\.jpg", href)
            photo_id = m.group(1) if m else ""
            if not photo_id:
                m2 = re.search(r"/(\d+)_\d+n\.jpg", src)
                photo_id = m2.group(1) if m2 else ""
            
            m3 = re.search(r"/(\d+)/\d+_\d+n\.jpg", src)
            path_prefix = m3.group(1) if m3 else ""
            
            large_url = f"https://35awards.com/photos_temp/sizes/{path_prefix}/{photo_id}_1500n.jpg" if photo_id and path_prefix else ""
            
            # Найти caption по data-sub-html
            caption_id = a.get("data-sub-html", "").lstrip("#")
            caption = soup.find("div", id=caption_id) if caption_id else None
            
            author_name = ""
            author_url = ""
            title = "(без названия)"
            
            if caption:
                author_links = caption.find_all("a", href=re.compile(r"\.35photo\.ru/"))
                for al in author_links:
                    i_tag = al.find("i")
                    if i_tag:
                        author_name = i_tag.get_text(strip=True)
                        if author_name:
                            author_url_full = al.get("href", "")
                            m4 = re.search(r"https?://([^./]+)\.35photo\.ru", author_url_full)
                            if m4:
                                author_slug = m4.group(1)
                                author_url = f"https://35awards.com/author/{author_slug}/"
                            break
                    link_text = al.get_text(strip=True)
                    if link_text and not author_name:
                        author_name = link_text
                        author_url_full = al.get("href", "")
                        m4 = re.search(r"https?://([^./]+)\.35photo\.ru", author_url_full)
                        if m4:
                            author_slug = m4.group(1)
                            author_url = f"https://35awards.com/author/{author_slug}/"
                        break
                
                b_tag = caption.find("b")
                if b_tag:
                    title_text = b_tag.get_text(strip=True)
                    if title_text:
                        title = title_text
            
            results.append({
                "edition": edition,
                "year": year,
                "nomination": target_nomination,
                "rank": len(results) + 1,
                "section": section,
                "photo_id": photo_id,
                "author_name": author_name,
                "country": "",
                "country_code": "",
                "city": "",
                "title": title,
                "photo_url_large": large_url,
                "photo_url_thumb": src,
                "photo_page_url": "",
                "author_url": author_url,
            })
    
    process_photo_list(photo_list, "100 BEST")
    process_photo_list(photo_other, "Viewers Choice")
    
    return results[:max_photos]


def extract_2016_format(html_path, edition, year, target_nomination, max_photos=15):
    """Формат 2016: h2 'Glamour/Nude 18+' + photoListWinners + photoListWinners_other."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    
    # В 2016 номинация "Glamour/Nude 18+"
    search_nom = target_nomination
    if target_nomination == "Nude 18+":
        search_nom = "Glamour/Nude 18+"
    
    # Найти h2
    h2_target = None
    for h2 in soup.find_all("h2"):
        if search_nom in h2.get_text(strip=True):
            h2_target = h2
            break
    
    if not h2_target:
        return []
    
    parent = h2_target.parent
    photo_list = parent.find_next_sibling("div", class_="photoListWinners")
    
    # photoListWinners_other в 2016 обёрнут в div.container
    photo_other = None
    for sib in parent.find_next_siblings()[:5]:
        inner = sib.find("div", class_="photoListWinners_other")
        if inner:
            photo_other = inner
            break
    
    results = []
    
    def process_2016_container(container, section):
        if not container:
            return
        items = container.find_all("a", class_="item")
        if not items:
            items = container.find_all("a", href=True)
        for a in items:
            if len(results) >= max_photos:
                break
            href = a.get("href", "")
            img = a.find("img", src=re.compile(r"photos_temp"))
            if not img:
                continue
            src = img.get("src", "")
            
            m = re.search(r"/(\d+)\.jpg", href)
            photo_id = m.group(1) if m else ""
            if not photo_id:
                m2 = re.search(r"/(\d+)_\d+n\.jpg", src)
                photo_id = m2.group(1) if m2 else ""
            
            m3 = re.search(r"/(\d+)/\d+_\d+n\.jpg", src)
            path_prefix = m3.group(1) if m3 else ""
            
            large_url = f"https://35awards.com/photos_temp/sizes/{path_prefix}/{photo_id}_1500n.jpg" if photo_id and path_prefix else ""
            
            caption_div = a.find_next_sibling("div", class_="caption")
            if not caption_div:
                caption_div = a.parent.find("div", class_="caption")
            
            author_name = ""
            author_url = ""
            title = "(без названия)"
            
            if caption_div:
                author_links = caption_div.find_all("a", href=re.compile(r"^/author/"))
                for al in author_links:
                    link_text = al.get_text(strip=True)
                    if link_text:
                        href_a = al.get("href", "")
                        author_name = link_text
                        author_url = urljoin("https://35awards.com", href_a)
                        break
                
                all_divs = caption_div.find_all("div")
                title_candidates = []
                for d in all_divs:
                    style = d.get("style", "")
                    if "0.8em" in style or ".8em" in style:
                        d_text = d.get_text(strip=True)
                        if d_text and d_text != author_name:
                            title_candidates.append(d_text)
                if title_candidates:
                    title = title_candidates[0]
            
            results.append({
                "edition": edition,
                "year": year,
                "nomination": target_nomination,
                "rank": len(results) + 1,
                "section": section,
                "photo_id": photo_id,
                "author_name": author_name,
                "country": "",
                "country_code": "",
                "city": "",
                "title": title,
                "photo_url_large": large_url,
                "photo_url_thumb": src,
                "photo_page_url": "",
                "author_url": author_url,
            })
    
    process_2016_container(photo_list, "100 BEST")
    process_2016_container(photo_other, "Viewers Choice")
    
    return results[:max_photos]


def extract_5th_format(html_path, edition, year, target_nomination, max_photos=15):
    """Формат 5th: parentGenre + carousel-items + author td."""
    from bs4 import BeautifulSoup
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    
    # Найти parentGenre с нужной номинацией
    nude_pg = None
    next_pg = None
    all_pgs = soup.find_all("div", class_="parentGenre")
    
    for i, pg in enumerate(all_pgs):
        text = pg.get_text(strip=True, separator=" ")
        if target_nomination in text:
            nude_pg = pg
            next_pg = all_pgs[i + 1] if i + 1 < len(all_pgs) else None
            break
    
    if not nude_pg:
        return []
    
    # Найти carousel items между nude_pg и next_pg
    carousels = []
    for elem in nude_pg.find_all_next():
        if next_pg and elem is next_pg:
            break
        if elem.name == "div" and "carousel-item" in (elem.get("class") or []):
            carousels.append(elem)
    
    # Получить URL фото из carousels
    photo_urls = []
    for ci in carousels:
        inner = ci.find("div")
        if inner:
            style = inner.get("style", "")
            bg_m = re.search(r"background:url\(([^)]+)\)", style)
            if bg_m:
                url = bg_m.group(1)
                photo_urls.append(url)
    
    results = []
    for i, url in enumerate(photo_urls[:max_photos]):
        m = re.search(r"/(\d+)/(\d+)_\d+n\.jpg", url)
        if not m:
            continue
        path_prefix = m.group(1)
        photo_id = m.group(2)
        large_url = url.replace("_500n", "_1500n")
        
        results.append({
            "edition": edition,
            "year": year,
            "nomination": target_nomination,
            "rank": i + 1,
            "section": "100 BEST",
            "photo_id": photo_id,
            "author_name": "",
            "country": "",
            "country_code": "",
            "city": "",
            "title": "(без названия)",
            "photo_url_large": large_url,
            "photo_url_thumb": url,
            "photo_page_url": "",
            "author_url": "",
        })
    
    # Найти авторов в td с "Nude 18+ Single works" или аналогичном
    for td in soup.find_all("td"):
        text = td.get_text(separator=" ", strip=True)
        if target_nomination in text and "Single works" in text:
            author_links = td.find_all("a", href=re.compile(r"^/author/"))
            for j, link in enumerate(author_links[:max_photos]):
                if j >= len(results):
                    break
                href = link.get("href", "")
                author_name = link.get_text(strip=True)
                row = link.find_parent("div", class_="row")
                loc = ""
                if row:
                    bebas_divs = row.find_all("div", class_="bebas")
                    for bd in bebas_divs:
                        bd_text = bd.get_text(strip=True)
                        if bd_text and bd_text != author_name and "," in bd_text:
                            loc = bd_text
                            break
                
                country = ""
                city = ""
                if ", " in loc:
                    parts = loc.split(", ", 1)
                    country = parts[0].strip()
                    city = parts[1].strip() if len(parts) > 1 else ""
                else:
                    country = loc
                
                from urllib.parse import urljoin
                full_url = urljoin("https://35awards.com", href)
                author_slug = href.strip("/").split("/")[-1]
                
                results[j]["author_name"] = author_name
                results[j]["country"] = country
                results[j]["city"] = city
                results[j]["author_url"] = full_url
            break
    
    return results


def fetch_nomination_page(url_year, nomination_id, edition):
    """Скачать отдельную страницу номинации с кешированием."""
    fname = f"nomination_{edition}_{url_year}_{nomination_id}.html"
    local_path = os.path.join(CONTESTS_DIR, fname)
    
    if os.path.exists(local_path) and os.path.getsize(local_path) > 5000:
        return local_path
    
    url = f"https://35awards.com/winners{url_year}/nomination/{nomination_id}/"
    print(f"      Скачиваю {url}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
            data = resp.read()
        with open(local_path, "wb") as f:
            f.write(data)
        return local_path
    except Exception as e:
        print(f"      ОШИБКА: {e}")
        return None


def extract_from_nomination_page(html_path, edition, year, nomination_name, max_photos=20):
    """Парсинг отдельной страницы номинации (winnersYYYY/nomination/ID/).
    
    Структура: genreItemPage (фото) + authorBlock (автор) пары.
    """
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    
    # Найти все genreItemPage (контейнеры фото) и authorBlock (контейнеры авторов)
    genre_items = soup.find_all("div", class_="genreItemPage")
    author_blocks = soup.find_all("div", class_="authorBlock")
    
    if not genre_items:
        return []
    
    results = []
    seen_photo_ids = set()
    
    # genreItemPage и authorBlock чередуются
    # Нужно их сопоставить — они идут в одном порядке
    for i, gi in enumerate(genre_items[:max_photos]):
        # Найти фото в genreItemPage
        img = gi.find("img")
        if not img:
            continue
        
        src = img.get("data-src", "") or img.get("src", "")
        if not src:
            continue
        
        # Извлечь photo_id и path_prefix
        # URL: https://35awards.com/photos_temp/sizes/1326/6632208_800n.jpg
        m = re.search(r"/(\d+)/(\d+)_\d+n\.jpg", src)
        if not m:
            continue
        path_prefix = m.group(1)
        photo_id = m.group(2)
        
        if photo_id in seen_photo_ids:
            continue
        seen_photo_ids.add(photo_id)
        
        # Построить URL полного фото
        large_url = f"https://35awards.com/photos_temp/sizes/{path_prefix}/{photo_id}_1500n.jpg"
        
        # Найти соответствующий authorBlock (по индексу)
        author_name = ""
        author_url = ""
        country = ""
        city = ""
        title = "(без названия)"
        
        if i < len(author_blocks):
            ab = author_blocks[i]
            
            # Автор: ссылка /author/slug/ с текстом
            author_link = ab.find("a", href=re.compile(r"^/author/"))
            if author_link:
                # Найти ссылку с текстом (не аватар)
                all_author_links = ab.find_all("a", href=re.compile(r"^/author/"))
                for al in all_author_links:
                    link_text = al.get_text(strip=True)
                    if link_text:
                        href_a = al.get("href", "")
                        author_name = link_text
                        author_url = urljoin("https://35awards.com", href_a)
                        break
            
            # Город/страна
            hometown_links = ab.find_all("a", class_="hometown")
            for hl in hometown_links:
                href = hl.get("href", "")
                text = hl.get_text(strip=True)
                if "/country/RU" in href or "/country/" in href and "/city/" not in href:
                    country = text
                elif "/city/" in href:
                    city = text
        
        results.append({
            "edition": edition,
            "year": year,
            "nomination": nomination_name,
            "rank": i + 1,
            "section": "Nomination Page",
            "photo_id": photo_id,
            "author_name": author_name,
            "country": country,
            "country_code": "",
            "city": city,
            "title": title,
            "photo_url_large": large_url,
            "photo_url_thumb": src,
            "photo_page_url": f"https://35awards.com/ru/photo/{photo_id}/" if photo_id else "",
            "author_url": author_url,
        })
    
    return results


def search_photos(keyword, contests_data, max_per_nomination=15):
    """Найти фото по ключевому слову."""
    # Определить номинации по ключевому слову
    kw_lower = keyword.lower().strip()
    
    nominations = None
    for k, v in KEYWORD_MAP.items():
        if k.lower() == kw_lower or k.lower() in kw_lower:
            nominations = v
            break
    
    if nominations is None and kw_lower in ["все", "all"]:
        nominations = ALL_NOMINATIONS
    elif nominations is None:
        # Прямой поиск по номинации
        for nom in ALL_NOMINATIONS:
            if kw_lower in nom.lower():
                nominations = [nom]
                break
    
    if nominations is None:
        print(f"\n❌ Ключевое слово '{keyword}' не распознано.")
        print(f"   Доступные ключевые слова: {', '.join(list(KEYWORD_MAP.keys())[:20])}...")
        print(f"   Или используйте точное название номинации на английском.")
        return []
    
    print(f"\n=== Поиск по ключевому слову: '{keyword}' ===")
    print(f"    Номинации: {', '.join(nominations)}")
    print(f"    Конкурсов: {len(contests_data)}")
    print(f"    Максимум фото на номинацию: {max_per_nomination}")
    
    all_photos = []
    for ed, ed_data in contests_data.items():
        html_path = ed_data["path"]
        year = ed_data["year"]
        fmt = ed_data.get("format", "modern")
        print(f"\n  {ed} ({year}) [{fmt}]:")
        
        # Для 2015 используем старый формат (нет nomination pages)
        if ed == "2015":
            for nom in nominations:
                photos = extract_nomination_photos(html_path, ed, year, nom,
                                                    max_per_nomination, fmt=fmt)
                if photos:
                    print(f"    {nom}: {len(photos)} фото (главная страница)")
                    all_photos.extend(photos)
                else:
                    print(f"    {nom}: не найдено на главной странице")
            continue
        
        # Для остальных — используем отдельные страницы номинаций
        ed_info = EDITION_NOMINATION_IDS.get(ed)
        if not ed_info:
            print(f"    Нет маппинга номинаций для {ed}")
            continue
        
        url_year, nom_ids = ed_info
        
        for nom in nominations:
            # Найти ID номинации
            nom_id = nom_ids.get(nom)
            
            # Для 7-го конкурса номинации на русском — попробуем маппинг
            if not nom_id and ed == "7th":
                # Маппинг английских названий на русские для 7th
                nom_map_7th = {
                    "Female portrait": "Женский портрет",
                    "Fashion & Glamour": "Фэшн и гламур",
                    "Staged photo": "Серия фотографий",  # Приблизительно
                    "Nude 18+": "Ню 18+",
                    "Motion": "Движение",
                    "Street photo": "Уличная фотография",
                    "Landscape - daytime": "Пейзаж - дневной",
                    "Landscape - night (+Astrophotography)": "Пейзаж - ночной",
                    "Macro": "Макро",
                    "Child portrait": "Детский портрет",
                    "Children staged photography": "Детская постановочная фотография",
                    "Conceptual photo": "Концептуальная фотография",
                    "Urban landscape (+Architecture)": "Городской пейзаж (Архитектура)",
                    "Still life": "Натюрморт",
                    "Reportage photography": "Репортажная фотография",
                    "Black and white": "Черно-белая фотография",
                    "Underwater photography": "Подводная фотография",
                    "Aerial photography": "Аэрофотография",
                    "Male portrait": "Мужской портрет",
                    "Wildlife": "Дикий животный мир",
                    "Pets": "Питомцы",
                    "Mobile photography": "Мобильная фотография",
                }
                ru_nom = nom_map_7th.get(nom)
                if ru_nom:
                    nom_id = nom_ids.get(ru_nom)
            
            # Для 2016 — Glamour/Nude 18+ вместо Nude 18+
            if not nom_id and ed == "2016" and nom == "Nude 18+":
                nom_id = nom_ids.get("Glamour/Nude 18+")
            
            if not nom_id:
                print(f"    {nom}: нет ID номинации для {ed}")
                # Fallback: попробовать парсить с главной страницы
                photos = extract_nomination_photos(html_path, ed, year, nom,
                                                    max_per_nomination, fmt=fmt)
                if photos:
                    print(f"    {nom}: {len(photos)} фото (главная страница, fallback)")
                    all_photos.extend(photos)
                continue
            
            # Скачать и распарсить отдельную страницу номинации
            nom_page_path = fetch_nomination_page(url_year, nom_id, ed)
            if not nom_page_path:
                print(f"    {nom}: не удалось загрузить страницу номинации")
                continue
            
            photos = extract_from_nomination_page(nom_page_path, ed, year, nom, max_per_nomination)
            if photos:
                print(f"    {nom}: {len(photos)} фото (страница номинации)")
                all_photos.extend(photos)
            else:
                print(f"    {nom}: не найдено на странице номинации")
    
    print(f"\n→ Всего найдено: {len(all_photos)} фото")
    return all_photos


# ==========================================================================
# 3. СКАЧИВАНИЕ ФОТО С КЕШИРОВАНИЕМ
# ==========================================================================

def download_photo(url, dest, timeout=30, retries=2):
    """Скачать фото с кешированием."""
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return True
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Referer": "https://35awards.com/"
            })
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
                data = resp.read()
                if len(data) < 500:
                    continue
                with open(dest, "wb") as f:
                    f.write(data)
                return True
        except Exception:
            if attempt < retries:
                time.sleep(1)
                continue
            return False
    return False


def download_all_photos(photos, show_progress=True):
    """Скачать все фото с кешированием + создать thumb и full версии."""
    from PIL import Image, ImageFilter
    
    print(f"\n=== Скачивание {len(photos)} фото + создание thumb/full ===")
    downloaded = 0
    for i, p in enumerate(photos):
        url = p.get("photo_url_large") or p.get("photo_url_thumb", "")
        if not url:
            continue
        
        # Имя оригинального файла (1500px с 35awards)
        fname = f"{p['edition']}_{p['nomination'].replace(' ', '_').replace('&', 'and').replace('+', 'p')}_{p['rank']:02d}_{p['photo_id']}.jpg"
        orig_path = os.path.join(PHOTOS_CACHE_DIR, fname)
        
        # Thumb и full пути
        thumb_path = os.path.join(PHOTOS_CACHE_DIR, f"thumb_{fname}")
        full_path = os.path.join(PHOTOS_CACHE_DIR, f"full_{fname}")
        
        # Скачать оригинал
        if not download_photo(url, orig_path):
            p["local_path"] = None
            p["local_filename"] = None
            p["thumb_path"] = None
            p["full_path"] = None
            continue
        
        p["local_path"] = orig_path
        p["local_filename"] = fname
        
        # Создать thumb (400px) если не существует
        if not os.path.exists(thumb_path):
            try:
                img = Image.open(orig_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.thumbnail((400, 500), Image.LANCZOS)
                img.save(thumb_path, format="JPEG", quality=78)
            except Exception as e:
                print(f"  ОШИБКА thumb {fname}: {e}")
        
        # Создать full (1400px) если не существует
        if not os.path.exists(full_path):
            try:
                img = Image.open(orig_path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                if max(img.size) > 1400:
                    ratio = 1400 / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                img.save(full_path, format="JPEG", quality=82)
            except Exception as e:
                print(f"  ОШИБКА full {fname}: {e}")
        
        # Сохранить пути для генерации HTML
        p["thumb_path"] = thumb_path if os.path.exists(thumb_path) else orig_path
        p["full_path"] = full_path if os.path.exists(full_path) else orig_path
        
        downloaded += 1
        if show_progress and (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(photos)}] скачано: {downloaded}")
        
        time.sleep(0.15)
    
    print(f"\n→ Скачано: {downloaded}/{len(photos)}")
    print(f"→ Кеш: {PHOTOS_CACHE_DIR}")
    print(f"   (оригиналы + thumb_*.jpg + full_*.jpg)")
    return photos


# ==========================================================================
# 4. VLM-ФИЛЬТРАЦИЯ (опционально, через z-ai CLI)
# ==========================================================================

def pixelate_image(img, block_size=60):
    from PIL import Image
    small = img.resize(
        (max(1, img.size[0] // block_size), max(1, img.size[1] // block_size)),
        Image.LANCZOS
    )
    return small.resize(img.size, Image.NEAREST)


def censor_for_vlm(img_path):
    """Создать цензурированную версию для прохождения VLM-фильтра."""
    from PIL import Image, ImageFilter
    censored_dir = os.path.join(DATA_DIR, "censored_for_vlm")
    os.makedirs(censored_dir, exist_ok=True)
    censored_path = os.path.join(censored_dir, os.path.basename(img_path))
    
    if os.path.exists(censored_path):
        return censored_path
    
    try:
        img = Image.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        censored = pixelate_image(img, block_size=60)
        censored = censored.filter(ImageFilter.GaussianBlur(radius=4))
        censored.save(censored_path, quality=70)
        return censored_path
    except Exception:
        return None


def find_z_ai():
    """Найти исполняемый файл z-ai на любой ОС."""
    import shutil
    # На Windows shutil.which найдёт z-ai.cmd или z-ai.exe
    path = shutil.which("z-ai")
    if path:
        return path
    # Fallback: попробовать типичные пути
    if sys.platform == "win32":
        # npm global bin
        for candidate in [
            os.path.expanduser("~/AppData/Roaming/npm/z-ai.cmd"),
            os.path.expanduser("~/AppData/Roaming/npm/z-ai"),
            "C:\\Program Files\\nodejs\\z-ai.cmd",
        ]:
            if os.path.exists(candidate):
                return candidate
    return None


def vlm_check_photo(photo_path, question, max_retries=2):
    """Задать вопрос VLM о фото. Возвращает текстовый ответ."""
    prompt = f"""Ответь на вопрос одним словом ДА или НЕТ.
Вопрос: {question}
Формат ответа: только ДА или НЕТ"""
    
    # Найти z-ai исполняемый файл (кросс-платформенно)
    z_ai_path = find_z_ai()
    if not z_ai_path:
        return None, "z-ai CLI не найден. Установите: npm install -g z-ai-web-dev-sdk"
    
    # На Windows используем shell=True для .cmd файлов
    use_shell = sys.platform == "win32" and z_ai_path.endswith(".cmd")
    
    for attempt in range(max_retries + 1):
        try:
            cmd = [z_ai_path, "vision", "-p", prompt, "-i", photo_path]
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=60,
                shell=use_shell
            )
            if result.returncode != 0:
                stderr = result.stderr or ""
                if "429" in stderr or "Too many requests" in stderr:
                    print(f"      [rate limited, waiting 45s...]")
                    time.sleep(45)
                    continue
                return None, f"returncode={result.returncode}, stderr={stderr[:200]}"
            
            output = result.stdout
            lines = output.split('\n')
            json_start = -1
            for i, line in enumerate(lines):
                if line.strip().startswith('{'):
                    json_start = i
                    break
            if json_start < 0:
                return None, "no JSON in output"
            
            json_str = '\n'.join(lines[json_start:])
            data = json.loads(json_str)
            content = data["choices"][0]["message"]["content"].strip().upper()
            return content, None
        except subprocess.TimeoutExpired:
            return None, "timeout (60s)"
        except FileNotFoundError as e:
            return None, f"z-ai не найден: {e}. Установите: npm install -g z-ai-web-dev-sdk"
        except Exception as e:
            return None, str(e)
    
    return None, "rate limited after retries"


def filter_by_vlm(photos, question, auto_censor_nude=True):
    """Отфильтровать фото через VLM по вопросу (ДА/НЕТ)."""
    print(f"\n=== VLM-фильтрация: '{question}' ===")
    print(f"    Фото для проверки: {len(photos)}")
    
    # Проверить, что z-ai доступен, до начала цикла
    z_ai_path = find_z_ai()
    if not z_ai_path:
        print(f"\n❌ z-ai CLI не найден!")
        print(f"   Установите: npm install -g z-ai-web-dev-sdk")
        print(f"   Или проверьте, что z-ai в PATH")
        print(f"   Пропускаю VLM-фильтрацию, оставляю все фото.")
        return photos
    
    print(f"   z-ai найден: {z_ai_path}")
    
    filtered = []
    for i, p in enumerate(photos):
        local_path = p.get("local_path")
        if not local_path or not os.path.exists(local_path):
            continue
        
        # Для nude — цензурируем
        is_nude = "Nude" in p.get("nomination", "") or "18+" in p.get("nomination", "")
        if is_nude and auto_censor_nude:
            analysis_path = censor_for_vlm(local_path)
            if not analysis_path:
                print(f"  [{i+1}/{len(photos)}] {p['edition']} {p['nomination'][:15]} #{p['rank']}: пропуск (не удалось цензурировать)")
                continue
        else:
            analysis_path = local_path
        
        print(f"  [{i+1}/{len(photos)}] {p['edition']} {p['nomination'][:15]} #{p['rank']}: ", end="", flush=True)
        
        result, error = vlm_check_photo(analysis_path, question)
        if result and "ДА" in result:
            filtered.append(p)
            print("ДА ✓")
        elif result and "НЕТ" in result:
            print("НЕТ ✗")
        else:
            print(f"ОШИБКА: {error}")
            # Если ошибка "z-ai не найден" — останавливаемся
            if "не найден" in str(error) or "FileNotFoundError" in str(error):
                print(f"\n❌ z-ai CLI недоступен. Останавливаю VLM-фильтрацию.")
                print(f"   Оставляю все оставшиеся фото без фильтрации.")
                filtered.extend(photos[i:])
                break
            # Включаем фото, если VLM не смог проверить (не теряем)
            filtered.append(p)
            print("    → оставлено (VLM не ответил)")
        
        time.sleep(3)
    
    print(f"\n→ Прошло фильтр: {len(filtered)}/{len(photos)}")
    return filtered


# ==========================================================================
# 5. ГЕНЕРАЦИЯ HTML-ГАЛЕРЕИ С ПОЛНЫМИ ФОТО
# ==========================================================================

def encode_image_as_base64(image_path, max_size=1400, quality=82):
    """Кодировать ПОЛНОЕ фото в base64 для встраивания в HTML (для модалки)."""
    from PIL import Image
    try:
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        print(f"  ОШИБКА кодирования (full) {image_path}: {e}")
        return ""


def encode_thumbnail_as_base64(image_path, size=(400, 500), quality=78):
    """Кодировать МАЛЕНЬКОЕ превью в base64 (для сетки)."""
    from PIL import Image
    try:
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        print(f"  ОШИБКА кодирования (thumb) {image_path}: {e}")
        return ""


def escape_html(text):
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ru_country(name):
    if not name:
        return ""
    return RU_COUNTRY.get(name, name)


def generate_html_gallery(photos, output_path, title="Референсы с 35awards",
                          subtitle="", query=""):
    """Сгенерировать HTML-галерею с превью (для сетки) и полными фото (для модалки)."""
    print(f"\n=== Генерация HTML-галереи ===")
    print(f"    Фото: {len(photos)}")
    print(f"    Путь: {output_path}")
    
    # Кодируем ДВА варианта: thumbnail (400px) для сетки + full (1400px) для модалки
    # Используем уже созданные thumb_path и full_path из кеша
    print("    Кодирую превью (400px) и полные фото (1400px)...")
    for i, p in enumerate(photos):
        thumb_path = p.get("thumb_path")
        full_path = p.get("full_path")
        local_path = p.get("local_path")
        
        # Превью — для сетки
        if thumb_path and os.path.exists(thumb_path):
            p["thumb_b64"] = encode_thumbnail_as_base64(thumb_path, size=(400, 500), quality=78)
        elif local_path and os.path.exists(local_path):
            p["thumb_b64"] = encode_thumbnail_as_base64(local_path, size=(400, 500), quality=78)
        else:
            p["thumb_b64"] = ""
        
        # Полное фото — для модалки
        if full_path and os.path.exists(full_path):
            p["full_b64"] = encode_image_as_base64(full_path, max_size=1400, quality=82)
        elif local_path and os.path.exists(local_path):
            p["full_b64"] = encode_image_as_base64(local_path, max_size=1400, quality=82)
        else:
            p["full_b64"] = ""
        
        if (i + 1) % 10 == 0:
            print(f"      [{i+1}/{len(photos)}] обработано")
    
    # Фильтруем фото без base64
    photos = [p for p in photos if p.get("full_b64") and p.get("thumb_b64")]
    print(f"    Готовых фото: {len(photos)}")
    
    if not photos:
        print("❌ Нет фото для галереи!")
        return None
    
    # CSS
    CSS = """
:root {
    --c-bg: #0a0a0a; --c-panel: #141414; --c-panel-2: #1a1a1a;
    --c-text: #e8e6e3; --c-text-dim: #8a8680; --c-text-mute: #5a5650;
    --c-accent: #c9a04a; --c-divider: #222222;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
    background: var(--c-bg); color: var(--c-text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 15px; line-height: 1.6; -webkit-font-smoothing: antialiased;
}
.cover {
    min-height: 60vh;
    background: radial-gradient(ellipse at 70% 30%, rgba(201,160,74,0.12) 0%, transparent 50%),
                linear-gradient(180deg, #0a0a0a 0%, #141414 100%);
    display: flex; flex-direction: column; justify-content: center;
    padding: 60px 8vw;
}
.cover-eyebrow {
    font-size: 12px; letter-spacing: 6px; color: var(--c-accent);
    text-transform: uppercase; font-weight: 600; margin-bottom: 24px;
}
.cover-title {
    font-size: clamp(40px, 7vw, 80px); font-weight: 200;
    line-height: 0.95; color: var(--c-text); letter-spacing: -3px; margin-bottom: 24px;
}
.cover-title strong { font-weight: 900; color: var(--c-accent); }
.cover-subtitle {
    font-size: clamp(15px, 1.8vw, 18px); color: var(--c-text-dim);
    line-height: 1.5; max-width: 700px; margin-bottom: 30px;
}
.cover-meta {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 30px; max-width: 700px; padding-top: 30px;
    border-top: 1px solid var(--c-divider);
}
.cover-stat-value {
    font-size: 32px; font-weight: 700; color: var(--c-accent);
    line-height: 1; margin-bottom: 6px;
}
.cover-stat-label {
    font-size: 10px; color: var(--c-text-mute);
    letter-spacing: 2px; text-transform: uppercase;
}
.section {
    padding: 40px 8vw; border-top: 1px solid var(--c-divider);
}
.section-header { margin-bottom: 32px; }
.section-eyebrow {
    font-size: 11px; color: var(--c-accent);
    letter-spacing: 4px; text-transform: uppercase;
    font-weight: 600; margin-bottom: 10px;
}
.section-title {
    font-size: clamp(28px, 4vw, 40px); font-weight: 200;
    color: var(--c-text); line-height: 1.1;
}
.photo-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
}
.photo-card {
    background: var(--c-panel); border-radius: 8px; overflow: hidden;
    cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;
    position: relative;
}
.photo-card:hover { transform: translateY(-3px); box-shadow: 0 10px 30px rgba(0,0,0,0.6); }
.photo-card-img {
    width: 100%; aspect-ratio: 3/4; object-fit: cover;
    display: block; background: #000;
}
.photo-card-overlay {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: linear-gradient(0deg, rgba(0,0,0,0.95) 0%, transparent 100%);
    padding: 18px 14px 12px; color: white;
}
.photo-card-author {
    font-size: 14px; font-weight: 600; color: var(--c-accent);
    margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.photo-card-nom { font-size: 10px; color: rgba(255,255,255,0.7); letter-spacing: 0.5px; }
.photo-card-num {
    position: absolute; top: 10px; left: 10px;
    background: rgba(0,0,0,0.85); color: var(--c-accent);
    font-size: 12px; font-weight: 700; padding: 5px 10px; border-radius: 3px;
}
.photo-card-edition {
    position: absolute; top: 10px; right: 10px;
    background: rgba(0,0,0,0.85); color: var(--c-text-dim);
    font-size: 10px; padding: 4px 8px; border-radius: 3px;
    letter-spacing: 1px; text-transform: uppercase;
}
.modal {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.97); z-index: 1000; padding: 40px; overflow: auto;
}
.modal.active { display: flex; align-items: center; justify-content: center; }
.modal-content { max-width: 95vw; max-height: 95vh; position: relative; text-align: center; }
.modal-img { max-width: 100%; max-height: 92vh; display: block; border-radius: 4px; margin: 0 auto; object-fit: contain; transition: opacity 0.3s ease; cursor: zoom-in; }
.modal-meta { margin-top: 20px; color: var(--c-text); }
.modal-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.modal-author { font-size: 16px; color: var(--c-accent); margin-bottom: 6px; }
.modal-author a { color: var(--c-accent); text-decoration: none; border-bottom: 1px solid var(--c-divider); }
.modal-author a:hover { border-color: var(--c-accent); }
.modal-location { font-size: 13px; color: var(--c-text-dim); margin-bottom: 12px; }

/* Информационная панель в модалке — место, номинация, год */
.modal-info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin: 16px 0;
    padding: 16px;
    background: var(--c-panel);
    border-radius: 6px;
    border: 1px solid var(--c-divider);
}
.modal-info-item {
    text-align: center;
}
.modal-info-label {
    font-size: 10px;
    color: var(--c-text-mute);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.modal-info-value {
    font-size: 14px;
    color: var(--c-accent);
    font-weight: 600;
}
.modal-info-value.rank {
    font-size: 20px;
    font-weight: 900;
}
.modal-nomination { font-size: 12px; color: var(--c-text-dim); letter-spacing: 1px; text-transform: uppercase; }
.modal-links { margin-top: 14px; display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; }
.modal-link { font-size: 13px; color: var(--c-accent); text-decoration: none; border-bottom: 1px solid transparent; padding: 4px 0; }
.modal-link:hover { border-color: var(--c-accent); }

/* Метаданные на карточке фото в сетке */
.photo-card-meta {
    display: flex;
    gap: 6px;
    margin-top: 4px;
    flex-wrap: wrap;
}
.photo-card-tag {
    font-size: 9px;
    color: rgba(255,255,255,0.6);
    background: rgba(0,0,0,0.4);
    padding: 2px 5px;
    border-radius: 2px;
    letter-spacing: 0.5px;
}
.modal-close {
    position: fixed; top: 20px; right: 30px;
    background: var(--c-panel); color: var(--c-text);
    border: 1px solid var(--c-divider); padding: 10px 16px;
    border-radius: 4px; font-size: 14px; cursor: pointer; z-index: 1001;
}
.modal-close:hover { background: var(--c-accent); color: #0a0a0a; }
.modal-nav {
    position: fixed; top: 50%; transform: translateY(-50%);
    background: var(--c-panel); color: var(--c-text);
    border: 1px solid var(--c-divider); width: 50px; height: 50px;
    border-radius: 50%; font-size: 24px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; z-index: 1001;
}
.modal-nav:hover { background: var(--c-accent); color: #0a0a0a; }
.modal-prev { left: 20px; }
.modal-next { right: 20px; }
.nav-top {
    position: fixed; top: 20px; right: 20px; z-index: 100;
    display: flex; gap: 8px;
}
.nav-btn {
    background: rgba(20,20,20,0.9); color: var(--c-text);
    border: 1px solid var(--c-divider); padding: 8px 14px;
    border-radius: 4px; font-size: 11px; cursor: pointer;
    text-decoration: none; letter-spacing: 1px; backdrop-filter: blur(8px);
}
.nav-btn:hover { background: rgba(201,160,74,0.15); border-color: var(--c-accent); color: var(--c-accent); }
.footer {
    padding: 50px 8vw; background: var(--c-bg); text-align: center;
    border-top: 1px solid var(--c-divider);
}
.footer-text { font-size: 14px; color: var(--c-text-dim); max-width: 600px; margin: 0 auto; line-height: 1.6; }
.footer-source { font-size: 11px; color: var(--c-text-mute); letter-spacing: 2px; text-transform: uppercase; margin-top: 20px; }
@media (max-width: 768px) {
    .cover, .section, .footer { padding-left: 20px; padding-right: 20px; }
    .photo-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
    .modal { padding: 20px 10px; }
    .modal-nav { width: 40px; height: 40px; font-size: 18px; }
    .modal-prev { left: 5px; } .modal-next { right: 5px; }
}
"""
    
    # Группировка по номинациям
    by_nomination = {}
    for p in photos:
        nom = p.get("nomination", "Другое")
        if nom not in by_nomination:
            by_nomination[nom] = []
        by_nomination[nom].append(p)
    
    html_parts = []
    
    html_parts.append(f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape_html(title)}</title>
<style>{CSS}</style>
</head>
<body>
""")
    
    # NAV
    html_parts.append('<div class="nav-top">')
    html_parts.append('<a href="#" class="nav-btn" onclick="window.scrollTo({top:0,behavior:\'smooth\'});return false;">↑ Наверх</a>')
    html_parts.append('</div>')
    
    # COVER
    html_parts.append(f"""
<div class="cover">
    <div class="cover-eyebrow">35awards · референсы для съёмок</div>
    <h1 class="cover-title">Референсы<br><strong>{escape_html(query)}</strong></h1>
    <p class="cover-subtitle">{escape_html(subtitle) or 'Работы-победители и финалисты международного фотоконкурса 35awards. Все фото в полном разрешении — кликните для увеличения.'}</p>
    <div class="cover-meta">
        <div><div class="cover-stat-value">{len(photos)}</div><div class="cover-stat-label">Работ</div></div>
        <div><div class="cover-stat-value">{len(by_nomination)}</div><div class="cover-stat-label">Номинаций</div></div>
        <div><div class="cover-stat-value">4</div><div class="cover-stat-label">Конкурса</div></div>
        <div><div class="cover-stat-value">2022-25</div><div class="cover-stat-label">Годы</div></div>
    </div>
</div>
""")
    
    # Секции по номинациям
    # Генерируем безопасный ключ для JS (без пробелов, &, +, -)
    import re as _re
    def make_nom_key(nom):
        return _re.sub(r'[^a-zA-Z0-9]', '_', nom)
    
    for nom, nom_photos in by_nomination.items():
        nom_key = make_nom_key(nom)
        html_parts.append(f"""
<div class="section" id="{nom_key}">
    <div class="section-header">
        <div class="section-eyebrow">Номинация 35awards</div>
        <h2 class="section-title"><strong>{escape_html(nom)}</strong></h2>
        <div style="font-size: 14px; color: var(--c-text-dim); margin-top: 8px;">{len(nom_photos)} работ</div>
    </div>
    <div class="photo-grid">
""")
        
        for i, p in enumerate(nom_photos):
            author = escape_html(p.get('author_name', 'Автор'))
            edition = escape_html(p.get('edition', ''))
            year = escape_html(p.get('year', ''))
            rank = p.get('rank', '')
            section = p.get('section', '100 BEST')
            nom = escape_html(p.get('nomination', ''))
            
            # Тег места (с указанием секции)
            rank_label = f"#{rank}"
            if section == "Viewers Choice":
                rank_label = f"VC #{rank}"
            
            html_parts.append(f"""
<div class="photo-card" onclick="openModal('{nom_key}_{i}')">
    <div class="photo-card-num">{rank_label}</div>
    <div class="photo-card-edition">{edition}</div>
    <img src="{p['thumb_b64']}" alt="{author}" class="photo-card-img" loading="lazy">
    <div class="photo-card-overlay">
        <div class="photo-card-author">{author}</div>
        <div class="photo-card-nom">{nom}</div>
        <div class="photo-card-meta">
            <span class="photo-card-tag">{year}</span>
            <span class="photo-card-tag">{edition}</span>
        </div>
    </div>
</div>""")
        
        html_parts.append('</div></div>')
    
    # MODAL
    html_parts.append("""
<div class="modal" id="modal" onclick="if(event.target===this)closeModal()">
    <button class="modal-close" onclick="closeModal()">✕ Закрыть (Esc)</button>
    <button class="modal-nav modal-prev" onclick="navigateModal(-1)">‹</button>
    <button class="modal-nav modal-next" onclick="navigateModal(1)">›</button>
    <div class="modal-content">
        <img class="modal-img" id="modal-img" src="">
        <div class="modal-meta" id="modal-meta"></div>
    </div>
</div>
""")
    
    # JS
    html_parts.append("""
<script>
const photoData = {
""")
    
    for nom, nom_photos in by_nomination.items():
        nom_key = make_nom_key(nom)
        html_parts.append(f"  '{nom_key}': [")
        for i, p in enumerate(nom_photos):
            title = p["title"] if p["title"] != "(без названия)" else "Без названия"
            location_parts = []
            if p.get("country"):
                location_parts.append(ru_country(p["country"]))
            if p.get("city"):
                location_parts.append(p["city"])
            location = ", ".join(location_parts) if location_parts else ""
            
            p_data = {
                'id': f'{nom_key}_{i}',
                'thumb': p['thumb_b64'],
                'full': p['full_b64'],
                'author': p.get('author_name', ''),
                'title': title,
                'location': location,
                'nomination': p.get('nomination', ''),
                'edition': p.get('edition', ''),
                'year': p.get('year', ''),
                'rank': p.get('rank', 0),
                'section': p.get('section', '100 BEST'),
                'author_url': p.get('author_url', ''),
                'photo_page_url': p.get('photo_page_url', ''),
            }
            html_parts.append(f"    {json.dumps(p_data, ensure_ascii=False)},")
        html_parts.append("  ],")
    
    html_parts.append("""
};

let currentNom = '';
let currentIndex = 0;

function openModal(photoId, nom) {
    if (nom === undefined) {
        // photoId format: "NominationKey_Index" — берём всё до последнего _
        const lastUnderscore = photoId.lastIndexOf('_');
        currentNom = photoId.substring(0, lastUnderscore);
        const photos = photoData[currentNom] || [];
        currentIndex = photos.findIndex(p => p.id === photoId);
    } else {
        currentNom = nom;
        const photos = photoData[currentNom] || [];
        currentIndex = photos.findIndex(p => p.id === photoId);
    }
    if (currentIndex < 0) currentIndex = 0;
    showPhoto();
    document.getElementById('modal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('modal').classList.remove('active');
    document.body.style.overflow = '';
}

function navigateModal(direction) {
    const photos = photoData[currentNom] || [];
    if (photos.length === 0) return;
    currentIndex = (currentIndex + direction + photos.length) % photos.length;
    showPhoto();
}

function showPhoto() {
    const photos = photoData[currentNom] || [];
    const p = photos[currentIndex];
    if (!p) return;
    
    // Сначала показываем превью (быстро), потом подгружаем полное
    const imgEl = document.getElementById('modal-img');
    imgEl.src = p.thumb;
    imgEl.style.opacity = '0.6';
    
    // Предзагрузка полного фото
    const fullImg = new Image();
    fullImg.onload = function() {
        imgEl.src = p.full;
        imgEl.style.opacity = '1';
    };
    fullImg.onerror = function() {
        imgEl.style.opacity = '1';
    };
    fullImg.src = p.full;
    
    // Формируем метку места
    let rankLabel = '#' + p.rank;
    if (p.section === 'Viewers Choice') {
        rankLabel = 'VC #' + p.rank + ' (Выбор зрителей)';
    } else if (p.section === '100 BEST') {
        rankLabel = '#' + p.rank + ' (100 BEST)';
    }
    
    let metaHtml = '';
    metaHtml += '<div class="modal-title">' + escapeHtml(p.title) + '</div>';
    metaHtml += '<div class="modal-author">';
    if (p.author_url) {
        metaHtml += '<a href="' + p.author_url + '" target="_blank">' + escapeHtml(p.author) + '</a>';
    } else {
        metaHtml += escapeHtml(p.author);
    }
    metaHtml += '</div>';
    if (p.location) {
        metaHtml += '<div class="modal-location">' + escapeHtml(p.location) + '</div>';
    }
    
    // Информационная панель: место, номинация, год, конкурс
    metaHtml += '<div class="modal-info-grid">';
    metaHtml += '<div class="modal-info-item"><div class="modal-info-label">Место</div><div class="modal-info-value rank">' + escapeHtml(rankLabel) + '</div></div>';
    metaHtml += '<div class="modal-info-item"><div class="modal-info-label">Номинация</div><div class="modal-info-value">' + escapeHtml(p.nomination) + '</div></div>';
    metaHtml += '<div class="modal-info-item"><div class="modal-info-label">Конкурс</div><div class="modal-info-value">' + escapeHtml(p.edition) + '</div></div>';
    metaHtml += '<div class="modal-info-item"><div class="modal-info-label">Год</div><div class="modal-info-value">' + escapeHtml(p.year) + '</div></div>';
    metaHtml += '</div>';
    
    metaHtml += '<div class="modal-nomination">' + (currentIndex + 1) + ' из ' + photos.length + ' в подборке</div>';
    metaHtml += '<div class="modal-links">';
    // Скачать полное фото
    metaHtml += '<a href="' + p.full + '" download="' + escapeHtml(p.author) + '_' + p.edition + '_rank' + p.rank + '.jpg" class="modal-link">⬇ Скачать оригинал</a>';
    // Открыть в новой вкладке
    metaHtml += '<a href="' + p.full + '" target="_blank" class="modal-link">🔗 Открыть в новой вкладке</a>';
    if (p.author_url) {
        metaHtml += '<a href="' + p.author_url + '" target="_blank" class="modal-link">Профиль автора →</a>';
    }
    if (p.photo_page_url) {
        metaHtml += '<a href="' + p.photo_page_url + '" target="_blank" class="modal-link">Страница работы →</a>';
    }
    metaHtml += '</div>';
    document.getElementById('modal-meta').innerHTML = metaHtml;
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('keydown', (e) => {
    if (!document.getElementById('modal').classList.contains('active')) return;
    if (e.key === 'Escape') closeModal();
    if (e.key === 'ArrowLeft') navigateModal(-1);
    if (e.key === 'ArrowRight') navigateModal(1);
    if (e.key === 'f' || e.key === 'F') toggleFullscreen();
});

// Двойной клик по фото — полноэкранный режим
document.addEventListener('DOMContentLoaded', function() {
    const modalImg = document.getElementById('modal-img');
    if (modalImg) {
        modalImg.addEventListener('dblclick', toggleFullscreen);
    }
});

function toggleFullscreen() {
    const modal = document.getElementById('modal');
    if (!document.fullscreenElement) {
        if (modal.requestFullscreen) {
            modal.requestFullscreen();
        } else if (modal.webkitRequestFullscreen) {
            modal.webkitRequestFullscreen();
        } else if (modal.msRequestFullscreen) {
            modal.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}
</script>
""")
    
    # FOOTER
    html_parts.append(f"""
<div class="footer">
    <p class="footer-text">{len(photos)} работ-победителей 35awards. Кликните на фото для увеличения. Стрелки ← → для навигации, Esc для закрытия, F или двойной клик — полноэкранный режим. Все фото встроены в HTML — работает офлайн.</p>
    <p class="footer-source">Источник: 35awards.com · 8-й — 11-й конкурсы · {time.strftime('%Y')}</p>
</div>
""")
    
    html_parts.append("</body></html>")
    
    # Запись
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("".join(html_parts))
    
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n✓ HTML создан: {output_path}")
    print(f"  Размер: {size_mb:.1f} МБ")
    print(f"  Фото: {len(photos)}")
    return output_path


# ==========================================================================
# 6. ВЕБ-ИНТЕРФЕЙС (опционально, Flask)
# ==========================================================================

def run_web_server():
    """Запустить веб-интерфейс на Flask."""
    try:
        from flask import Flask, request, jsonify, send_file
    except ImportError:
        print("❌ Flask не установлен. Установите: pip install flask")
        return
    
    app = Flask(__name__)
    
    @app.route("/")
    def index():
        return """
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>35awards References Collector</title>
<style>
body { background: #0a0a0a; color: #e8e6e3; font-family: -apple-system, sans-serif; padding: 40px; max-width: 900px; margin: 0 auto; }
h1 { color: #c9a04a; margin-bottom: 8px; }
.subtitle { color: #8a8680; margin-bottom: 30px; font-size: 14px; }
label { display: block; margin: 16px 0 8px; color: #8a8680; font-size: 14px; }
input, select, textarea { width: 100%; padding: 12px; background: #141414; color: #e8e6e3; border: 1px solid #222; border-radius: 4px; font-size: 15px; box-sizing: border-box; }
select option { background: #141414; }
button { background: #c9a04a; color: #0a0a0a; border: none; padding: 14px 28px; font-size: 16px; font-weight: bold; border-radius: 4px; cursor: pointer; margin-top: 20px; width: 100%; }
button:hover { background: #d4a04a; }
button:disabled { background: #5a5650; cursor: not-allowed; }
.hint { font-size: 13px; color: #5a5650; margin-top: 6px; }
.status { margin-top: 20px; padding: 16px; background: #141414; border-radius: 4px; display: none; }
.checkbox-row { display: flex; align-items: center; gap: 10px; margin: 12px 0; }
.checkbox-row input { width: auto; }
.checkbox-row label { margin: 0; cursor: pointer; }
.form-row { display: flex; gap: 16px; }
.form-row > div { flex: 1; }
.results { margin-top: 20px; }
.result-item { background: #141414; padding: 16px; border-radius: 4px; margin-top: 12px; border-left: 3px solid #c9a04a; }
.result-link { color: #c9a04a; font-size: 16px; text-decoration: none; font-weight: 600; }
.result-link:hover { text-decoration: underline; }
.result-meta { color: #8a8680; font-size: 12px; margin-top: 6px; }
.progress { margin-top: 10px; font-size: 13px; color: #8a8680; }
</style></head><body>
<h1>📸 35awards References Collector</h1>
<p class="subtitle">Сбор референсов с 35awards.com — победители и финалисты 9 конкурсов (2015—2025)</p>

<form id="form">
<label>Номинация:</label>
<select id="query">
<optgroup label="— Девушки —">
<option value="девушки">Все девушки (4 номинации)</option>
<option value="женский портрет">Женский портрет</option>
<option value="fashion">Мода и гламур (Fashion & Glamour)</option>
<option value="постановка">Постановочное фото (Staged)</option>
<option value="ню">Nude 18+</option>
</optgroup>
<optgroup label="— Портреты —">
<option value="детский портрет">Детский портрет</option>
<option value="мужской портрет">Мужской портрет</option>
</optgroup>
<optgroup label="— Жанры —">
<option value="улица">Уличная фотография (Street)</option>
<option value="пейзаж">Пейзаж (дневной + ночной)</option>
<option value="макро">Макро</option>
<option value="архитектура">Архитектура / Городской пейзаж</option>
<option value="натюрморт">Натюрморт</option>
<option value="репортаж">Репортаж</option>
<option value="концепт">Концептуальная фотография</option>
</optgroup>
<optgroup label="— Специальные —">
<option value="спорт">Спорт / Движение (Motion)</option>
<option value="чб">Чёрно-белое (Black and White)</option>
<option value="подводная">Подводная фотография</option>
<option value="аэро">Аэрофотография</option>
<option value="животные">Дикий животный мир (Wildlife)</option>
<option value="питомцы">Питомцы (Pets)</option>
<option value="мобильная">Мобильная фотография</option>
</optgroup>
<optgroup label="— Всё —">
<option value="все">Все номинации</option>
</optgroup>
</select>

<div class="form-row">
<div>
<label>Максимум фото:</label>
<input type="number" id="count" value="40" min="5" max="500" step="5">
<div class="hint">До 500. Для маленького каталога — 20-40, для полного — 200-500</div>
</div>
<div>
<label>Фото на номинацию (для "все"):</label>
<input type="number" id="per_nom" value="15" min="5" max="50">
<div class="hint">Сколько брать из каждой номинации</div>
</div>
</div>

<div class="checkbox-row">
<input type="checkbox" id="per_nomination">
<label for="per_nomination">📋 Создать отдельные каталоги для каждой номинации (плюс общий)</label>
</div>
<div class="hint" style="margin-left: 26px;">Каждая номинация получит свой HTML-файл со ВСЕМИ найденными работами</div>

<label>Доп. фильтр через VLM (опционально):</label>
<input type="text" id="vlm_filter" placeholder="например: девушка в кадре? (оставьте пустым если не нужно)">
<div class="hint">Если заполнено — каждое фото проверяется через VLM. Требуется z-ai CLI.</div>

<button type="submit" id="submitBtn">🚀 Собрать каталог</button>
</form>

<div class="status" id="status"></div>
<div class="results" id="results"></div>

<script>
let pollInterval = null;

document.getElementById('form').onsubmit = async (e) => {
    e.preventDefault();
    const q = document.getElementById('query').value;
    const c = parseInt(document.getElementById('count').value);
    const pn = parseInt(document.getElementById('per_nom').value);
    const perNom = document.getElementById('per_nomination').checked;
    const vlm = document.getElementById('vlm_filter').value;
    
    const status = document.getElementById('status');
    const results = document.getElementById('results');
    const btn = document.getElementById('submitBtn');
    
    btn.disabled = true;
    btn.textContent = '⏳ Сборка...';
    status.style.display = 'block';
    status.textContent = '⏳ Запускаю сборку...';
    results.innerHTML = '';
    
    try {
        const resp = await fetch('/collect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({query: q, count: c, per_nomination: perNom, per_nom: pn, vlm_filter: vlm})
        });
        const data = await resp.json();
        
        if (data.success) {
            status.textContent = '✅ Готово! ' + data.message;
            let html = '';
            if (data.files && data.files.length > 0) {
                html += '<h3 style="color:#c9a04a;margin-top:20px">📂 Каталоги:</h3>';
                data.files.forEach(f => {
                    html += '<div class="result-item">';
                    html += '<a href="' + f.url + '" target="_blank" class="result-link">📄 ' + f.name + '</a>';
                    html += '<div class="result-meta">' + f.photos + ' фото · ' + f.size + '</div>';
                    html += '</div>';
                });
            }
            results.innerHTML = html;
        } else {
            status.textContent = '❌ Ошибка: ' + data.error;
        }
    } catch (err) {
        status.textContent = '❌ Ошибка сети: ' + err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Собрать каталог';
    }
};
</script>
</body></html>
"""
    
    collecting = {"active": False}
    
    @app.route("/collect", methods=["POST"])
    def collect():
        if collecting["active"]:
            return jsonify({"success": False, "error": "Уже идёт сборка, подождите"})
        
        data = request.json
        query = data.get("query", "").strip()
        count = int(data.get("count", 40))
        per_nom = int(data.get("per_nom", 15))
        per_nomination = data.get("per_nomination", False)
        vlm_filter = data.get("vlm_filter", "").strip()
        
        if not query:
            return jsonify({"success": False, "error": "Выберите номинацию"})
        
        collecting["active"] = True
        try:
            # 1. Загрузить конкурсы
            contests_data = fetch_all_contests()
            
            # 2. Найти фото
            # Если per_nomination — берём больше фото с каждой страницы номинации
            search_max = count if per_nomination else per_nom
            photos = search_photos(query, contests_data, max_per_nomination=search_max)
            
            if not photos:
                return jsonify({"success": False, "error": f"Не найдено фото по запросу '{query}'"})
            
            # 3. Скачать
            download_all_photos(photos)
            
            # 4. VLM-фильтр (если есть)
            if vlm_filter:
                photos = filter_by_vlm(photos, vlm_filter)
            
            # 5. Сгенерировать HTML
            files = []
            timestamp = int(time.time())
            
            if per_nomination:
                # Группировать по номинациям и создать отдельный HTML для каждой
                from collections import defaultdict
                by_nom = defaultdict(list)
                for p in photos:
                    by_nom[p.get("nomination", "Другое")].append(p)
                
                for nom, nom_photos in by_nom.items():
                    safe_nom = re.sub(r'[^a-zA-Z0-9]', '_', nom)
                    output_path = os.path.join(BASE_DIR, f"gallery_{timestamp}_{safe_nom}.html")
                    generate_html_gallery(nom_photos, output_path,
                                          title=f"{nom} — 35awards",
                                          query=nom)
                    if os.path.exists(output_path):
                        size_mb = os.path.getsize(output_path) / 1024 / 1024
                        files.append({
                            "name": f"{nom} ({len(nom_photos)} фото)",
                            "url": f"/gallery/{os.path.basename(output_path)}",
                            "photos": len(nom_photos),
                            "size": f"{size_mb:.1f} МБ",
                        })
                
                # Общий каталог (все фото)
                all_path = os.path.join(BASE_DIR, f"gallery_{timestamp}_ALL.html")
                all_photos_trimmed = photos[:count]
                generate_html_gallery(all_photos_trimmed, all_path,
                                      title=f"Все: {query}",
                                      query=query)
                if os.path.exists(all_path):
                    size_mb = os.path.getsize(all_path) / 1024 / 1024
                    files.insert(0, {
                        "name": f"Общий каталог ({len(all_photos_trimmed)} фото)",
                        "url": f"/gallery/{os.path.basename(all_path)}",
                        "photos": len(all_photos_trimmed),
                        "size": f"{size_mb:.1f} МБ",
                    })
            else:
                # Один общий каталог
                photos_trimmed = photos[:count]
                output_path = os.path.join(BASE_DIR, f"gallery_{timestamp}.html")
                generate_html_gallery(photos_trimmed, output_path,
                                      title=f"Референсы: {query}",
                                      query=query)
                if os.path.exists(output_path):
                    size_mb = os.path.getsize(output_path) / 1024 / 1024
                    files.append({
                        "name": f"Каталог ({len(photos_trimmed)} фото)",
                        "url": f"/gallery/{os.path.basename(output_path)}",
                        "photos": len(photos_trimmed),
                        "size": f"{size_mb:.1f} МБ",
                    })
            
            return jsonify({
                "success": True,
                "message": f"Собрано {len(photos)} фото, создано {len(files)} каталогов",
                "files": files,
            })
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()[-500:]})
        finally:
            collecting["active"] = False
    
    @app.route("/gallery/<filename>")
    def gallery(filename):
        safe = os.path.basename(filename)  # Prevent path traversal
        path = os.path.join(BASE_DIR, safe)
        if os.path.exists(path):
            return send_file(path)
        return "File not found", 404
    
    # Determine port (for hosting: Render, Heroku, etc. use PORT env)
    port = int(os.environ.get("PORT", 5000))
    
    print(f"\n🌐 Веб-интерфейс запущен: http://localhost:{port}")
    print("   Откройте в браузере. Для остановки: Ctrl+C")
    app.run(host="0.0.0.0", port=port, debug=False)


# ==========================================================================
# 7. ИНТЕРАКТИВНЫЙ РЕЖИМ
# ==========================================================================

def interactive_mode():
    """Интерактивный режим — спрашивает параметры у пользователя."""
    print("\n" + "=" * 60)
    print("  35AWARDS REFERENCES COLLECTOR — ИНТЕРАКТИВНЫЙ РЕЖИМ")
    print("=" * 60)
    
    print("\nДоступные ключевые слова:")
    print("  женский портрет, fashion, ню, постановка, спорт, улица,")
    print("  пейзаж, макро, детский портрет, архитектура, натюрморт,")
    print("  репортаж, чб, концепт, подводная, аэро, мужской портрет,")
    print("  животные, питомцы, мобильная, девушки, все")
    
    query = input("\n🔎 Введите ключевое слово: ").strip()
    if not query:
        print("❌ Ключевое слово не введено")
        return
    
    count_str = input("📊 Сколько фото собрать? [40]: ").strip()
    count = int(count_str) if count_str else 40
    
    per_nom_str = input("📈 Фото на номинацию для поиска? [15]: ").strip()
    per_nom = int(per_nom_str) if per_nom_str else 15
    
    per_nom_cat = input("📋 Отдельные каталоги по номинациям? (y/n) [n]: ").strip().lower()
    per_nomination = per_nom_cat in ("y", "yes", "д", "да")
    
    vlm = input("🤖 VLM-фильтр? (например: 'девушка в кадре?') [пусто = нет]: ").strip()
    
    output = input("📁 Путь для HTML [gallery.html]: ").strip()
    if not output:
        output = "gallery.html"
    if not output.endswith(".html"):
        output += ".html"
    
    run_collection(query, count, vlm, output, per_nomination=per_nomination, per_nom=per_nom)


# ==========================================================================
# 8. ОСНОВНОЙ ЗАПУСК
# ==========================================================================

def run_collection(query, count, vlm_filter, output_path, per_nomination=False, per_nom=15):
    """Основная функция сбора референсов."""
    print(f"\n{'='*60}")
    print(f"  СБОРКА РЕФЕРЕНСОВ")
    print(f"{'='*60}")
    print(f"  Запрос: {query}")
    print(f"  Кол-во: {count}")
    print(f"  Фото на номинацию: {per_nom}")
    print(f"  Отдельные каталоги: {'да' if per_nomination else 'нет'}")
    print(f"  VLM-фильтр: {vlm_filter or 'нет'}")
    print(f"  Output: {output_path}")
    print(f"{'='*60}")
    
    # 1. Загрузить конкурсы (с кешированием)
    contests_data = fetch_all_contests()
    
    # 2. Найти фото по ключевому слову
    # Если per_nomination — берём больше фото с каждой страницы номинации
    search_max = count if per_nomination else per_nom
    photos = search_photos(query, contests_data, max_per_nomination=search_max)
    
    if not photos:
        print("❌ Фото не найдены. Проверьте ключевое слово.")
        return None
    
    print(f"\n→ Найдено {len(photos)} фото")
    
    # 3. Скачать фото
    download_all_photos(photos)
    
    # 4. VLM-фильтр (если есть)
    if vlm_filter:
        photos = filter_by_vlm(photos, vlm_filter)
    
    # 5. Сгенерировать HTML
    if per_nomination:
        # Отдельные каталоги по номинациям
        from collections import defaultdict
        by_nom = defaultdict(list)
        for p in photos:
            by_nom[p.get("nomination", "Другое")].append(p)
        
        print(f"\n=== Генерация {len(by_nom) + 1} каталогов ===")
        output_dir = os.path.dirname(output_path) or "."
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        
        generated = []
        for nom, nom_photos in by_nom.items():
            safe_nom = re.sub(r'[^a-zA-Z0-9]', '_', nom)
            nom_path = os.path.join(output_dir, f"{base_name}_{safe_nom}.html")
            generate_html_gallery(nom_photos, nom_path,
                                  title=f"{nom} — 35awards",
                                  query=nom)
            if os.path.exists(nom_path):
                size_mb = os.path.getsize(nom_path) / 1024 / 1024
                print(f"  ✓ {nom}: {len(nom_photos)} фото, {size_mb:.1f} МБ")
                generated.append(nom_path)
        
        # Общий каталог
        all_photos_trimmed = photos[:count]
        generate_html_gallery(all_photos_trimmed, output_path,
                              title=f"Все: {query}",
                              query=query)
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / 1024 / 1024
            print(f"  ✓ Общий: {len(all_photos_trimmed)} фото, {size_mb:.1f} МБ")
            generated.insert(0, output_path)
        
        print(f"\n{'='*60}")
        print(f"  ✅ ГОТОВО! Создано {len(generated)} каталогов")
        print(f"{'='*60}")
        for g in generated:
            print(f"  📄 {g}")
        print(f"{'='*60}")
        return generated
    else:
        # Один общий каталог
        photos_trimmed = photos[:count]
        generate_html_gallery(photos_trimmed, output_path,
                              title=f"Референсы: {query}",
                              query=query)
        
        print(f"\n{'='*60}")
        print(f"  ✅ ГОТОВО!")
        print(f"{'='*60}")
        print(f"  HTML: {output_path}")
        print(f"  Размер: {os.path.getsize(output_path) / 1024 / 1024:.1f} МБ")
        print(f"  Фото: {len(photos_trimmed)}")
        print(f"  Откройте в браузере двойным кликом.")
        print(f"{'='*60}")
        return output_path


def main():
    parser = argparse.ArgumentParser(
        description="35awards References Collector — сбор референсов с 35awards.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ПРИМЕРЫ:
  # CLI с параметрами
  python awards_refs.py --query "женский портрет" --count 40
  python awards_refs.py -q "fashion" -c 30 -o my_gallery.html
  python awards_refs.py -q "ню" --use-vlm "девушка в кадре?"
  python awards_refs.py -q "улица" -c 20
  
  # Отдельные каталоги по номинациям
  python awards_refs.py -q "девушки" -c 100 --per-nomination
  
  # Интерактивный режим (без параметров)
  python awards_refs.py
  
  # Веб-режим
  python awards_refs.py --web
  
КЛЮЧЕВЫЕ СЛОВА:
  женский портрет, fashion, ню, постановка, спорт, улица, пейзаж,
  макро, детский портрет, архитектура, натюрморт, репортаж, чб,
  концепт, подводная, аэро, мужской портрет, животные, питомцы,
  мобильная, девушки, все
        """)
    
    parser.add_argument("-q", "--query", help="Ключевое слово или номинация")
    parser.add_argument("-c", "--count", type=int, default=40, help="Сколько фото (по умолчанию 40)")
    parser.add_argument("-o", "--output", default="gallery.html", help="Путь для HTML")
    parser.add_argument("--per-nom", type=int, default=15, help="Фото на номинацию для поиска (по умолчанию 15)")
    parser.add_argument("--per-nomination", action="store_true", help="Создать отдельные каталоги для каждой номинации")
    parser.add_argument("--use-vlm", help="VLM-фильтр (например: 'девушка в кадре?')")
    parser.add_argument("--web", action="store_true", help="Запустить веб-интерфейс")
    parser.add_argument("--refresh", action="store_true", help="Принудительно обновить HTML конкурсов")
    parser.add_argument("--list-keywords", action="store_true", help="Показать все ключевые слова")
    
    args = parser.parse_args()
    
    if args.list_keywords:
        print("\n=== Доступные ключевые слова ===")
        for kw, noms in KEYWORD_MAP.items():
            if noms:
                print(f"  {kw:25s} → {', '.join(noms)}")
            else:
                print(f"  {kw:25s} → все номинации")
        return
    
    if args.web:
        run_web_server()
        return
    
    if not args.query:
        interactive_mode()
        return
    
    run_collection(args.query, args.count, args.use_vlm, args.output,
                   per_nomination=args.per_nomination, per_nom=args.per_nom)


# ==========================================================================
# WSGI app для хостинга (Render, Heroku, PythonAnywhere)
# ==========================================================================
# Для хостинга используйте wsgi.py (см. в комплекте)
# Или: gunicorn 'awards_refs:create_wsgi_app()'


def create_wsgi_app():
    """Создать Flask app для WSGI-серверов (gunicorn, uwsgi).
    Использование: gunicorn 'awards_refs:create_wsgi_app()' --bind 0.0.0.0:$PORT
    """
    from flask import Flask, request, jsonify, send_file
    from collections import defaultdict
    
    app = Flask(__name__)
    collecting = {"active": False}
    
    # Встроенный HTML интерфейс
    INDEX_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>35awards References</title>
<style>
body { background: #0a0a0a; color: #e8e6e3; font-family: -apple-system, sans-serif; padding: 40px; max-width: 900px; margin: 0 auto; }
h1 { color: #c9a04a; margin-bottom: 8px; }
.subtitle { color: #8a8680; margin-bottom: 30px; font-size: 14px; }
label { display: block; margin: 16px 0 8px; color: #8a8680; font-size: 14px; }
input, select, textarea { width: 100%; padding: 12px; background: #141414; color: #e8e6e3; border: 1px solid #222; border-radius: 4px; font-size: 15px; box-sizing: border-box; }
select option { background: #141414; }
button { background: #c9a04a; color: #0a0a0a; border: none; padding: 14px 28px; font-size: 16px; font-weight: bold; border-radius: 4px; cursor: pointer; margin-top: 20px; width: 100%; }
button:hover { background: #d4a04a; }
button:disabled { background: #5a5650; cursor: not-allowed; }
.hint { font-size: 13px; color: #5a5650; margin-top: 6px; }
.status { margin-top: 20px; padding: 16px; background: #141414; border-radius: 4px; display: none; }
.checkbox-row { display: flex; align-items: center; gap: 10px; margin: 12px 0; }
.checkbox-row input { width: auto; }
.checkbox-row label { margin: 0; cursor: pointer; }
.form-row { display: flex; gap: 16px; }
.form-row > div { flex: 1; }
.results { margin-top: 20px; }
.result-item { background: #141414; padding: 16px; border-radius: 4px; margin-top: 12px; border-left: 3px solid #c9a04a; }
.result-link { color: #c9a04a; font-size: 16px; text-decoration: none; font-weight: 600; }
.result-link:hover { text-decoration: underline; }
.result-meta { color: #8a8680; font-size: 12px; margin-top: 6px; }
</style></head><body>
<h1>📸 35awards References Collector</h1>
<p class="subtitle">Сбор референсов с 35awards.com — победители и финалисты 9 конкурсов (2015—2025)</p>
<form id="form">
<label>Номинация:</label>
<select id="query">
<optgroup label="— Девушки —">
<option value="девушки">Все девушки (4 номинации)</option>
<option value="женский портрет">Женский портрет</option>
<option value="fashion">Мода и гламур (Fashion & Glamour)</option>
<option value="постановка">Постановочное фото (Staged)</option>
<option value="ню">Nude 18+</option>
</optgroup>
<optgroup label="— Портреты —">
<option value="детский портрет">Детский портрет</option>
<option value="мужской портрет">Мужской портрет</option>
</optgroup>
<optgroup label="— Жанры —">
<option value="улица">Уличная фотография (Street)</option>
<option value="пейзаж">Пейзаж (дневной + ночной)</option>
<option value="макро">Макро</option>
<option value="архитектура">Архитектура / Городской пейзаж</option>
<option value="натюрморт">Натюрморт</option>
<option value="репортаж">Репортаж</option>
<option value="концепт">Концептуальная фотография</option>
</optgroup>
<optgroup label="— Специальные —">
<option value="спорт">Спорт / Движение (Motion)</option>
<option value="чб">Чёрно-белое (Black and White)</option>
<option value="подводная">Подводная фотография</option>
<option value="аэро">Аэрофотография</option>
<option value="животные">Дикий животный мир (Wildlife)</option>
<option value="питомцы">Питомцы (Pets)</option>
<option value="мобильная">Мобильная фотография</option>
</optgroup>
<optgroup label="— Всё —">
<option value="все">Все номинации</option>
</optgroup>
</select>
<div class="form-row">
<div>
<label>Максимум фото:</label>
<input type="number" id="count" value="40" min="5" max="500" step="5">
<div class="hint">До 500. Для маленького — 20-40, для полного — 200-500</div>
</div>
<div>
<label>Фото на номинацию (для "все"):</label>
<input type="number" id="per_nom" value="15" min="5" max="50">
<div class="hint">Сколько брать из каждой номинации</div>
</div>
</div>
<div class="checkbox-row">
<input type="checkbox" id="per_nomination">
<label for="per_nomination">📋 Отдельные каталоги для каждой номинации (плюс общий)</label>
</div>
<div class="hint" style="margin-left: 26px;">Каждая номинация получит свой HTML-файл со ВСЕМИ работами</div>
<label>Доп. фильтр через VLM (опционально):</label>
<input type="text" id="vlm_filter" placeholder="например: девушка в кадре? (оставьте пустым если не нужно)">
<div class="hint">Требуется z-ai CLI. Для nude фото цензурируется автоматически.</div>
<button type="submit" id="submitBtn">🚀 Собрать каталог</button>
</form>
<div class="status" id="status"></div>
<div class="results" id="results"></div>
<script>
document.getElementById('form').onsubmit = async (e) => {
    e.preventDefault();
    const q = document.getElementById('query').value;
    const c = parseInt(document.getElementById('count').value);
    const pn = parseInt(document.getElementById('per_nom').value);
    const perNom = document.getElementById('per_nomination').checked;
    const vlm = document.getElementById('vlm_filter').value;
    const status = document.getElementById('status');
    const results = document.getElementById('results');
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Сборка...';
    status.style.display = 'block';
    status.textContent = '⏳ Запускаю сборку... Это может занять несколько минут...';
    results.innerHTML = '';
    try {
        const resp = await fetch('/collect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({query: q, count: c, per_nomination: perNom, per_nom: pn, vlm_filter: vlm})
        });
        const data = await resp.json();
        if (data.success) {
            status.textContent = '✅ Готово! ' + data.message;
            let html = '';
            if (data.files && data.files.length > 0) {
                html += '<h3 style="color:#c9a04a;margin-top:20px">📂 Каталоги:</h3>';
                data.files.forEach(f => {
                    html += '<div class="result-item">';
                    html += '<a href="' + f.url + '" target="_blank" class="result-link">📄 ' + f.name + '</a>';
                    html += '<div class="result-meta">' + f.photos + ' фото · ' + f.size + '</div>';
                    html += '</div>';
                });
            }
            results.innerHTML = html;
        } else {
            status.textContent = '❌ Ошибка: ' + data.error;
        }
    } catch (err) {
        status.textContent = '❌ Ошибка сети: ' + err.message;
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Собрать каталог';
    }
};
</script>
</body></html>"""
    
    @app.route("/")
    def index():
        return INDEX_HTML
    
    @app.route("/collect", methods=["POST"])
    def collect():
        if collecting["active"]:
            return jsonify({"success": False, "error": "Уже идёт сборка, подождите"})
        data = request.json
        query = data.get("query", "").strip()
        count = int(data.get("count", 40))
        per_nom = int(data.get("per_nom", 15))
        per_nomination = data.get("per_nomination", False)
        vlm_filter = data.get("vlm_filter", "").strip()
        if not query:
            return jsonify({"success": False, "error": "Выберите номинацию"})
        collecting["active"] = True
        try:
            contests_data = fetch_all_contests()
            search_max = count if per_nomination else per_nom
            photos = search_photos(query, contests_data, max_per_nomination=search_max)
            if not photos:
                return jsonify({"success": False, "error": f"Не найдено фото по запросу '{query}'"})
            download_all_photos(photos)
            if vlm_filter:
                photos = filter_by_vlm(photos, vlm_filter)
            files = []
            timestamp = int(time.time())
            if per_nomination:
                by_nom = defaultdict(list)
                for p in photos:
                    by_nom[p.get("nomination", "Другое")].append(p)
                for nom, nom_photos in by_nom.items():
                    safe_nom = re.sub(r'[^a-zA-Z0-9]', '_', nom)
                    output_path = os.path.join(BASE_DIR, f"gallery_{timestamp}_{safe_nom}.html")
                    generate_html_gallery(nom_photos, output_path, title=f"{nom} — 35awards", query=nom)
                    if os.path.exists(output_path):
                        size_mb = os.path.getsize(output_path) / 1024 / 1024
                        files.append({"name": f"{nom} ({len(nom_photos)} фото)", "url": f"/gallery/{os.path.basename(output_path)}", "photos": len(nom_photos), "size": f"{size_mb:.1f} МБ"})
                all_path = os.path.join(BASE_DIR, f"gallery_{timestamp}_ALL.html")
                all_photos_trimmed = photos[:count]
                generate_html_gallery(all_photos_trimmed, all_path, title=f"Все: {query}", query=query)
                if os.path.exists(all_path):
                    size_mb = os.path.getsize(all_path) / 1024 / 1024
                    files.insert(0, {"name": f"Общий каталог ({len(all_photos_trimmed)} фото)", "url": f"/gallery/{os.path.basename(all_path)}", "photos": len(all_photos_trimmed), "size": f"{size_mb:.1f} МБ"})
            else:
                photos_trimmed = photos[:count]
                output_path = os.path.join(BASE_DIR, f"gallery_{timestamp}.html")
                generate_html_gallery(photos_trimmed, output_path, title=f"Референсы: {query}", query=query)
                if os.path.exists(output_path):
                    size_mb = os.path.getsize(output_path) / 1024 / 1024
                    files.append({"name": f"Каталог ({len(photos_trimmed)} фото)", "url": f"/gallery/{os.path.basename(output_path)}", "photos": len(photos_trimmed), "size": f"{size_mb:.1f} МБ"})
            return jsonify({"success": True, "message": f"Собрано {len(photos)} фото, создано {len(files)} каталогов", "files": files})
        except Exception as e:
            import traceback
            return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()[-500:]})
        finally:
            collecting["active"] = False
    
    @app.route("/gallery/<filename>")
    def gallery(filename):
        safe = os.path.basename(filename)
        path = os.path.join(BASE_DIR, safe)
        if os.path.exists(path):
            return send_file(path)
        return "File not found", 404
    
    return app


if __name__ == "__main__":
    main()
