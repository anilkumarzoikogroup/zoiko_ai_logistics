FROM python:3.11-slim AS base
WORKDIR /app

RUN addgroup --system zoiko && adduser --system --ingroup zoiko zoiko

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ ./services/

USER zoiko
EXPOSE 8010
CMD ["uvicorn", "services.connector_hub.app:app", "--host", "0.0.0.0", "--port", "8010"]
