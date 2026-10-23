# One service: FastAPI (auth, rate limits, agent) also serves the built React app. Runs on Cloud Run ($PORT).
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 WEB_DIST=/srv/web
WORKDIR /srv/agent
COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/app ./app
COPY agent/eval ./eval
COPY --from=web /web/dist /srv/web
RUN useradd --uid 10001 --no-create-home appuser
USER appuser
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-server-header --proxy-headers --forwarded-allow-ips='*'
