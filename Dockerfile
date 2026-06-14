FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    FRONTEND_DIST=/frontend/dist

WORKDIR /backend

RUN apt-get update \
  && apt-get install -y --no-install-recommends libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY app/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/backend/ ./
COPY --from=frontend-build /frontend/dist /frontend/dist

RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
