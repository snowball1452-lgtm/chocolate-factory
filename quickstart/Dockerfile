FROM python:3.11-slim

LABEL org.opencontainers.image.title="Chocolate Factory — Quickstart"
LABEL org.opencontainers.image.description="Single-container policy compiler + taste engine API"
LABEL org.opencontainers.image.source="https://github.com/snowball1452-lgtm/chocolate-factory"

WORKDIR /factory

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Copy the compiler and taste engine
COPY compiler/ ./compiler/
COPY adapters/__init__.py ./adapters/__init__.py
COPY adapters/taste_engine.py ./adapters/taste_engine.py
COPY quickstart/server.py ./server.py

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
