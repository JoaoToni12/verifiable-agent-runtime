FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENT_RUNTIME_DATABASE=/data/runtime.sqlite3

WORKDIR /app

RUN addgroup --system runtime && adduser --system --ingroup runtime runtime

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir /data && chown runtime:runtime /data
USER runtime

EXPOSE 8000
CMD ["uvicorn", "verifiable_agent_runtime.api:app", "--host", "0.0.0.0", "--port", "8000"]
