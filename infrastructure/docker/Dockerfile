# Web pages are built first, so the final image needs no Node.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY agent_engine ./agent_engine
COPY backend ./backend
COPY knowledge_engine ./knowledge_engine
COPY llm_engine ./llm_engine
COPY voice_engine ./voice_engine
COPY scripts ./scripts
COPY models/manifests ./models/manifests
COPY --from=web /web/dist ./frontend/dist
RUN useradd --create-home --uid 10001 voice && mkdir -p /app/data && chown -R voice /app/data /app/models
USER voice
ENV VAP_HOST=0.0.0.0
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "scripts/serve.py"]
