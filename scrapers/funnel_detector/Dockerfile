FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8094
HEALTHCHECK --interval=60s --timeout=10s CMD curl -f http://localhost:8094/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8094"]
