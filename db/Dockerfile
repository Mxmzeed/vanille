FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache
COPY src/vanille_db ./src/vanille_db
RUN uv sync --frozen --no-dev --no-editable --no-cache

RUN useradd --create-home --uid 10001 vanille
USER vanille
EXPOSE 9003
CMD ["uvicorn", "vanille_db.main:app", "--host", "0.0.0.0", "--port", "9003"]
