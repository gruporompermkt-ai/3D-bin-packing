FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# os testes rodam no build: se falharem, a imagem não é gerada e o deploy para
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY . .
RUN MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider && touch /tmp/testes-ok

FROM base
COPY --from=test /tmp/testes-ok /tmp/testes-ok
COPY py3dbp ./py3dbp
COPY app ./app
RUN useradd -r -u 10001 app && mkdir -p /data && chown app /data
USER app
ENV DB_PATH=/data/cubagem.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
