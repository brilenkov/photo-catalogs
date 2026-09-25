# 35awards References Collector

Универсальный инструмент для сбора референсов с **35awards.com** — победителей и финалистов 9 конкурсов (2015—2025).

## 🚀 Быстрый старт (локально)

```bash
pip install -r requirements.txt

# CLI
python awards_refs.py -q "женский портрет" -c 40
python awards_refs.py -q "девушки" -c 100 --per-nomination

# Веб-интерфейс
python awards_refs.py --web
# → откроется http://localhost:5000

# Интерактивный режим
python awards_refs.py
```

## 📋 Режимы работы

### 1. CLI с параметрами
```bash
python awards_refs.py -q "ню" -c 40 -o my_gallery.html
python awards_refs.py -q "улица" -c 20 --per-nomination
python awards_refs.py -q "девушки" -c 200 --per-nomination
```

### 2. Веб-интерфейс
```bash
python awards_refs.py --web
```
Откроется форма с:
- Dropdown выбора номинации (сгруппированы по категориям)
- Полем "максимум фото" (до 500)
- Чекбоксом "отдельные каталоги по номинациям"
- VLM-фильтром (опционально)

### 3. Интерактивный режим
```bash
python awards_refs.py
```

## 📂 Отдельные каталоги по номинациям

Флаг `--per-nomination` создаёт отдельный HTML для каждой номинации:

```bash
python awards_refs.py -q "девушки" -c 100 --per-nomination
```

Результат:
```
gallery_Female_portrait.html     ← все фото Female portrait
gallery_Fashion___Glamour.html   ← все фото Fashion & Glamour
gallery_Staged_photo.html        ← все фото Staged photo
gallery_Nude_18_.html            ← все фото Nude 18+
gallery_ALL.html                 ← общий каталог (100 фото)
```

Каждый файл содержит ВСЕ найденные работы из этой номинации со ВСЕХ 9 конкурсов.

## 🌐 Хостинг (бесплатно)

### Render.com (рекомендуется)

1. Зарегистрируйтесь на [render.com](https://render.com)
2. New → Web Service → подключите GitHub репозиторий
3. Настройки:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:application --bind 0.0.0.0:$PORT --timeout 300`
   - **Plan**: Free
4. Deploy!

Или используйте `render.yaml` для автоматического деплоя.

### PythonAnywhere

1. Зарегистрируйтесь на [pythonanywhere.com](https://pythonanywhere.com)
2. Создайте Flask web app
3. Загрузите файлы
4. В WSGI файле: `from wsgi import application`
5. ⚠️ Free tier имеет ограничения на внешние запросы

### Replit

1. Создайте Repl на [replit.com](https://replit.com)
2. Загрузите файлы
3. `pip install -r requirements.txt`
4. Run: `python wsgi.py`

### Hugging Face Spaces

1. Создайте Space на [huggingface.co](https://huggingface.co/spaces)
2. SDK: Gradio или Streamlit
3. Загрузите файлы
4. ⚠️ Требует адаптации под Gradio

## ⚠️ Ограничения бесплатного хостинга

- **Render Free**: app "засыпает" через 15 мин бездействия; первый запрос может занять 30+ сек
- **PythonAnywhere Free**: ограничения на внешние HTTP-запросы; 100 сек CPU/день
- **Replit Free**: app засыпает; ограничения на память
- **Сборка больших каталогов** (200+ фото) может занять 5-10 минут — возможны таймауты

**Рекомендация**: для больших каталогов используйте локальный запуск. Веб-версия удобна для быстрого подбора 20-50 фото.

## 📦 Файлы

| Файл | Описание |
|------|----------|
| `awards_refs.py` | Основной скрипт (CLI + веб + WSGI) |
| `wsgi.py` | WSGI entry point для хостинга |
| `requirements.txt` | Python зависимости |
| `Procfile` | Для Heroku |
| `render.yaml` | Для Render.com |

## 🔍 Номинации (ключевые слова)

**Девушки**: `женский портрет`, `fashion`, `постановка`, `ню`, `девушки` (все 4)
**Портреты**: `детский портрет`, `мужской портрет`
**Жанры**: `улица`, `пейзаж`, `макро`, `архитектура`, `натюрморт`, `репортаж`, `концепт`
**Спец**: `спорт`, `чб`, `подводная`, `аэро`, `животные`, `питомцы`, `мобильная`
**Все**: `все`

## 🎨 Возможности готового каталога

- **Два размера фото**: превью (400px) для сетки + полные (1400px) для модалки
- **Полноэкранный режим**: двойной клик или клавиша F
- **Скачивание оригинала**: кнопка в модалке
- **Метаданные**: место, номинация, год, конкурс
- **Ссылки**: на профиль автора и страницу работы на 35awards
- **Навигация**: стрелки ← →, Esc
- **Офлайн**: все фото встроены в HTML (base64)

## 📝 Лицензия

MIT — используйте свободно. Фото принадлежат их авторам.
