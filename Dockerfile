# Single container for free hosting: the public Node gateway plus the private Python agent.
# The agent binds to 127.0.0.1 only, so the gateway is the sole way in.
FROM node:22-bookworm-slim AS api-deps
WORKDIR /api
COPY api/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NODE_ENV=production \
    AGENT_URL=http://127.0.0.1:8000 PORT=10000
COPY --from=api-deps /usr/local/bin/node /usr/local/bin/node
WORKDIR /srv
COPY agent/requirements.txt agent/requirements.txt
RUN pip install --no-cache-dir -r agent/requirements.txt
COPY agent/app agent/app
COPY agent/eval agent/eval
COPY --from=api-deps /api/node_modules api/node_modules
COPY api/package.json api/package.json
COPY api/src api/src
COPY deploy/start.sh start.sh
RUN chmod 755 start.sh && useradd --uid 10001 --no-create-home appuser
USER appuser
EXPOSE 10000
CMD ["./start.sh"]
