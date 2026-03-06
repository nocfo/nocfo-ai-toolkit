FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir "poetry>=2.0,<3.0"

COPY pyproject.toml poetry.lock* README.md /app/
COPY src /app/src

RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --only main

ENTRYPOINT ["nocfo"]
CMD ["mcp", "--transport", "http", "--auth-mode", "oauth", "--path", "/mcp", "--host", "0.0.0.0", "--port", "8000"]
