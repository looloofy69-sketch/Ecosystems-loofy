FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

# Install the algorithm library, then the shared MCP runner, then the HTTP bridge.
# The bridge and MCP adapter intentionally reuse the same fixed capability runner.
COPY modules/decision-infrastructure/ /app/modules/decision-infrastructure/
RUN python -m pip install --no-cache-dir /app/modules/decision-infrastructure

COPY adapters/decision-mcp/ /app/adapters/decision-mcp/
RUN python -m pip install --no-cache-dir /app/adapters/decision-mcp

COPY adapters/decision-api/ /app/adapters/decision-api/
RUN python -m pip install --no-cache-dir /app/adapters/decision-api

EXPOSE 8080

CMD ["uvicorn", "ecosystem_decision_api.server:app", "--host", "0.0.0.0", "--port", "8080"]
