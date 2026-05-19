# LLM Collapse Detector

Система мониторинга и обнаружения коллапса больших языковых моделей. Позволяет отслеживать качество генерации текста в динамике, сравнивать версии моделей, настраивать пороговые правила срабатывания алертов и получать уведомления при обнаружении признаков коллапса.

## Содержание

- [Обзор](#обзор)
- [Технологический стек](#технологический-стек)
- [Быстрый старт](#быстрый-старт)
- [Структура репозитория](#структура-репозитория)
- [Симуляция коллапса](#симуляция-коллапса)

---

## Обзор

Коллапс модели — явление постепенной деградации генеративной нейросети при рекуррентном обучении на синтетических данных, порождённых ею же (Shumailov et al., 2023). Система предоставляет инструментарий для:

- Бенчмаркинга — запуска воспроизводимых замеров метрик на WikiText-2 или пользовательских датасетах;
- Мониторинга промптов — сбора трасс генерации, токенных вероятностей и производных метрик по каждому запросу;
- Сравнения версий — сопоставления характеристик двух версий одной модели с подсветкой значимых изменений;
- Алертинга — гибкой настройки правил с рассылкой e-mail уведомлений;
- Аудита — ведения полного журнала всех действий пользователей.

---


## Технологический стек

| Компонент     | Технология                          |
|---------------|-------------------------------------|
| Backend       | Python 3.12, FastAPI, SQLAlchemy    |
| Frontend      | React 18, TypeScript, Recharts      |
| База данных   | PostgreSQL 14 (dev: SQLite)         |
| Очередь задач | Redis 7 + Celery                    |
| ML-инференс   | Transformers, PyTorch |
| Контейнеры    | Docker, Docker Compose              |
| Миграции      | Alembic                             |
| Тесты         | pytest                              |

---

## Быстрый старт

### Docker Compose

```bash
git clone <repo>
cd thesis
cp backend/.env.example backend/.env   # + заполнить переменные

docker compose up -d
docker compose exec backend alembic upgrade head
```

Фронтенд доступен на `http://localhost:5173`, API — на `http://localhost:8000`.

### Локальная разработка

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # для Windows: .venv\Scripts\activate
pip install -r requirements.txt

alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## Структура репозитория

```
./
├── backend/
│   ├── app/
│   │   ├── api/routes/        # FastAPI маршруты
│   │   ├── services/          # Бизнес-логика
│   │   ├── models/            # SQLAlchemy модели
│   │   ├── schemas/           # Pydantic схемы
│   │   └── core/              # Конфигурация, безопасность, crypto
│   ├── alembic/               # Миграции БД
│   ├── tests/                 # Юнит и интеграционные тесты
│   └── functional_tests/      # E2E тесты на чекпоинтах из notebooks/collapse_models/
├── frontend/
│   └── src/
│       ├── pages/             # Страницы приложения
│       ├── components/        # Переиспользуемые компоненты
│       └── api/               # HTTP-клиент (cookie-auth)
├── notebooks/
│   ├── model_collapse_distilgpt2.ipynb   # Симуляция коллапса 
│   └── collapse_models/                  # Чекпоинты gen_0..gen_5
└── docker-compose.yml
```

---

## Симуляция коллапса

Ноутбук `notebooks/model_collapse_distilgpt2.ipynb` воспроизводит рекуррентный коллапс:

1. $M_0$ — дообученная distilgpt2 на 8 000 историй TinyStories в 2 эпохи.
2. $M_1..M_5$ — $M_{i+1}$ обучается на 5 000 синтетических примеров, сгенерированных $M_i$.

Результаты:

```
Δ entropy          gen_0 → gen_5:  6.94 → 5.95  (-0.99)
Δ vocab_size       gen_0 → gen_5:  281  → 136   (-145)
Δ js_divergence    gen_0 → gen_5:  0.51 → 0.64  (+0.13)
```
