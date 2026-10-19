# AgentGateWay — Multi-stage Docker build
FROM python:3.13-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY mock_servers/ mock_servers/

RUN pip install --no-cache-dir .

# Runtime stage
FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ src/
COPY mock_servers/ mock_servers/
COPY config/ config/

ENV PYTHONPATH="/app/src:/app"

EXPOSE 8000

CMD ["uvicorn", "agentgateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
