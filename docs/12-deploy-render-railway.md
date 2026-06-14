# Deploy Hi Jack LMS — Render / Railway

**Date:** 2026-06-10  
**Stack:** Docker → Django + Vue (single container) + PostgreSQL

---

## Что получится

| | |
|---|---|
| URL | `https://hijack-lms-xxxx.onrender.com` или `*.up.railway.app` |
| Ярлык на телефоне | Стабильный HTTPS-адрес, IP не нужен |
| База | PostgreSQL (не SQLite) |
| Free tier | Сервер «засыпает» без трафика (~50 сек первый заход) |

---

## Render vs Railway — что выбрать

| | **Render** | **Railway** |
|---|------------|-------------|
| Free tier | ✅ Web + Postgres | ⚠️ $5 credit/мес, потом платно |
| Blueprint (1 клик) | ✅ `render.yaml` в репо | Вручную |
| Регион ближе к UZ | Frankfurt | Можно выбрать |
| **Рекомендация** | **Начать здесь** | Если нужен быстрый UI и есть credit |

---

## Вариант A — Render (рекомендуется)

### 1. Подготовка

1. Код на **GitHub** (приватный или публичный репозиторий).
2. Аккаунт [render.com](https://render.com).

### 2. Деплой через Blueprint

1. Render → **New** → **Blueprint**
2. Подключи репозиторий `Hijack-mme`
3. Render прочитает `render.yaml` и создаст:
   - **Web Service** (Docker)
   - **PostgreSQL** (free)
4. **Apply**

### 3. После первого деплоя

1. Открой URL вида `https://hijack-lms-xxxx.onrender.com`
2. Войди: CEO `903708242` / `50608991Zz!` (если `SEED_DEMO=1`)
3. На телефоне: Chrome → адрес → **Добавить на главный экран**

### 4. Переменные (Dashboard → Environment)

| Key | Value |
|-----|-------|
| `ALLOWED_HOSTS` | `.onrender.com,lms.company.uz` |
| `CSRF_TRUSTED_ORIGINS` | `https://hijack-lms-xxxx.onrender.com,https://lms.company.uz` |
| `SEED_DEMO` | `0` после первого успешного деплоя |

`SECRET_KEY` и `DATABASE_URL` Render задаёт сам.

### 5. Свой домен `lms.company.uz`

1. Render → Service → **Settings** → **Custom Domains**
2. Добавь `lms.company.uz`
3. У регистратора домена — CNAME на адрес Render
4. Обнови `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`

---

## Вариант B — Railway

### 1. Подготовка

1. Код на GitHub
2. Аккаунт [railway.app](https://railway.app)

### 2. Деплой

1. **New Project** → **Deploy from GitHub repo**
2. Выбери `Hijack-mme`
3. Railway найдёт `Dockerfile` и `railway.toml`
4. **Add service** → **Database** → **PostgreSQL**
5. В web-сервисе → **Variables** → **Add reference** → `DATABASE_URL` из Postgres

### 3. Environment variables

```
DEBUG=false
SECRET_KEY=<случайная длинная строка>
ALLOWED_HOSTS=.up.railway.app,lms.company.uz
DATABASE_SSL=true
SEED_DEMO=1
```

`RAILWAY_PUBLIC_DOMAIN` Railway подставляет сам — CSRF подхватится в `settings.py`.

### 4. Домен

Railway → **Settings** → **Networking** → **Generate Domain**  
Потом **Custom Domain** для `lms.company.uz`.

---

## Локальная проверка Docker (перед облаком)

```powershell
cd D:\projects\Hijack-mme
docker build -t hijack-lms .
docker run --rm -p 8000:8000 -e DEBUG=true -e ALLOWED_HOSTS=* -e SEED_DEMO=1 hijack-lms
```

Открой http://127.0.0.1:8000

С Postgres локально:

```powershell
docker run --rm -p 8000:8000 `
  -e DATABASE_URL=postgresql://... `
  -e SECRET_KEY=local-test-key `
  -e DEBUG=true `
  -e ALLOWED_HOSTS=* `
  -e SEED_DEMO=1 `
  hijack-lms
```

---

## Файлы деплоя в репозитории

| Файл | Назначение |
|------|------------|
| `Dockerfile` | Сборка frontend + backend |
| `render.yaml` | Blueprint для Render |
| `railway.toml` | Настройки Railway |
| `app/backend/start.sh` | migrate + gunicorn |
| `.env.example` | Список переменных |

---

## Free tier — ограничения

- **Render free web:** засыпает через ~15 мин без запросов; cold start 30–60 сек
- **Render free Postgres:** 1 GB, expires через 90 дней (продлевать или мигрировать)
- **Railway:** trial credit, потом ~$5+/мес

Для офиса 5–20 человек free Render обычно хватает на старт.

---

## Следующий шаг

1. Залить код на GitHub (если ещё нет)
2. Выбрать **Render Blueprint** — быстрее всего
3. После деплоя — прислать URL, проверим login и телефон

**Альтернатива без облака:** закрепить IP в роутере (вариант 2 из прошлого обсуждения) — остаётся бесплатно, но ПК должен быть включён.
