FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY services ./services
RUN pip install .

ARG APP_MODULE
ENV APP_MODULE=${APP_MODULE}
EXPOSE 8000

CMD ["sh", "-c", "uvicorn ${APP_MODULE}:app --host 0.0.0.0 --port 8000"]

