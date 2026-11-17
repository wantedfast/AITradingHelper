FROM python:3.11-slim-bookworm

LABEL com.aitrading.managed="true"

ARG PIP_INDEX_URL=https://pypi.org/simple/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/work/api_uploads /app/outputs/api_reports

EXPOSE 8600

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/api/health', timeout=5).read()" || exit 1

CMD ["python", "-m", "trade_review_agent.api.simple_api"]
