# Expenses Dashboard

A mobile-first PWA dashboard for personal expenses stored in Google Sheets.
Connect your spreadsheet, deploy the static files to any host, and get a
fast, private dashboard on your phone.

> **RU / EN**: this README is bilingual. The English section starts at
> [English](#english).

---

## Русский

### Что это

Дашборд расходов для телефона (PWA), который:

- читает вашу Google-таблицу расходов и превращает её в красивые KPI,
  графики по категориям и по месяцам;
- показывает траты за текущий месяц, за прошлый месяц и средние значения;
- работает как устанавливаемое приложение (офлайн после первого открытия);
- хранит данные только у вас: таблица остаётся вашей, секреты — ваши.

### Демо

https://quicksnapper.github.io/expenses-dashboard/

Демо работает на синтетических данных: это пример, а не чужие траты.

### Возможности

- KPI: траты за месяц, за прошлый месяц, средний чек, итого;
- график категорий (распределение за выбранный период);
- график динамики по месяцам;
- переключатель: текущий месяц / прошлый месяц / всё время / среднее;
- список транзакций с поиском по категории;
- тёмная и светлая темы;
- PWA: установка на телефон, работа офлайн;
- автоматическое обновление данных (см. GitHub Actions).

### Структура

```
expenses-dashboard/
├── mobile-expenses/          # статический PWA-сайт
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   ├── manifest.webmanifest
│   ├── sw.js
│   └── data.json             # данные (в репозитории — демо-данные)
├── scripts/
│   ├── export_expenses_dashboard.py  # экспорт из Google Sheets
│   └── make_demo_data.py             # генератор демо-данных
├── categories.py             # категории и канонизация
├── parser.py                 # парсер «продукты 850»
├── sheets.py                 # доступ к Google Sheets
├── formulas.py               # QUERY-формулы для таблицы
├── create_expenses_sheet.py  # одноразовая инициализация таблицы
├── sync_categories.py        # синхронизация категорий
└── tests/                    # pytest
```

### Быстрый старт

1. Склонируйте репозиторий.
2. Откройте демо или раздайте папку `mobile-expenses/` любым статическим
   сервером:

   ```bash
   python -m http.server 8080 --directory mobile-expenses
   ```

3. Откройте http://127.0.0.1:8080/ — вы увидите демо-дашборд.

### Подключение своей таблицы

1. Создайте Google-таблицу с листами: `Транзакции`, `Категории`,
   `По категориям`, `По месяцам`. Проще всего один раз запустить
   `create_expenses_sheet.py`.

2. Заведите сервисный аккаунт Google (Google Cloud Console → IAM →
   Service Accounts), создайте ключ JSON и **дайте адресу аккаунта доступ
   Editor к таблице**.

3. Создайте `.env` по образцу `.env.example`:

   ```bash
   GOOGLE_SHEET_ID=...
   GOOGLE_CREDENTIALS_PATH=google_credentials.json
   ```

4. Сгенерируйте `data.json`:

   ```bash
   pip install -r requirements.txt
   python -m scripts.export_expenses_dashboard
   ```

5. Раздайте `mobile-expenses/` на ваш хостинг. Автообновление можно
   настроить через GitHub Actions (см. `deploy-selfhosted.yml.example`).

### Тесты

```bash
pip install -r requirements.txt
pytest tests/ -q
```

### Лицензия

MIT (см. [LICENSE](LICENSE)).

---

## English

### What is this

A mobile-first PWA dashboard for personal expenses stored in Google Sheets.
Connect your spreadsheet, deploy static files anywhere, and get a fast,
private dashboard on your phone.

### Demo

https://quicksnapper.github.io/expenses-dashboard/

The demo runs on synthetic data: it is an example, not someone's expenses.

### Features

- KPI: this month, last month, average, total;
- category breakdown chart for a selected period;
- monthly trend chart;
- period toggle: current month / previous month / all time / average;
- transaction list with category search;
- dark and light themes;
- PWA: installable, works offline;
- automatic data refresh (see GitHub Actions).

### Quick start

```bash
git clone https://github.com/quicksnapper/expenses-dashboard.git
cd expenses-dashboard
python -m http.server 8080 --directory mobile-expenses
```

Open http://127.0.0.1:8080/ — you will see the demo dashboard.

### Connecting your own spreadsheet

1. Create a Google Sheet with sheets: `Транзакции`, `Категории`,
   `По категориям`, `По месяцам`. The easiest way is to run
   `create_expenses_sheet.py` once.

2. Create a Google service account (Google Cloud Console → IAM →
   Service Accounts), create a JSON key, and **give the account's email
   Editor access to the sheet**.

3. Create `.env` from `.env.example`:

   ```bash
   GOOGLE_SHEET_ID=...
   GOOGLE_CREDENTIALS_PATH=google_credentials.json
   ```

4. Generate `data.json`:

   ```bash
   pip install -r requirements.txt
   python -m scripts.export_expenses_dashboard
   ```

5. Serve `mobile-expenses/` from your host. For automatic updates see
   `deploy-selfhosted.yml.example`.

### Tests

```bash
pip install -r requirements.txt
pytest tests/ -q
```

### License

MIT (see [LICENSE](LICENSE)).
