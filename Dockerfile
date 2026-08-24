FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN addgroup --system atlasmind && adduser --system --ingroup atlasmind atlasmind

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN pip install --no-cache-dir .

USER atlasmind
EXPOSE 8000
CMD ["uvicorn", "atlasmind.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
