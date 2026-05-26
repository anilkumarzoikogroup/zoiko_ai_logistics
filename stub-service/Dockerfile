FROM python:3.11-slim AS base
WORKDIR /app

RUN addgroup --system zoiko && adduser --system --ingroup zoiko zoiko

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ ./services/

USER zoiko
EXPOSE 8013
CMD ["uvicorn", "services.stub_svc.app:app", "--host", "0.0.0.0", "--port", "8013"]
