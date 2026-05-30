# Cloud Run image for the AEGIS backend (self-contained: SQLite, no external DB).
FROM python:3.12-slim

WORKDIR /app

# uvicorn isn't in the cPanel requirements (that host uses Passenger/a2wsgi);
# Cloud Run runs the ASGI app directly, so add it here.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "uvicorn[standard]==0.32.1"

COPY . .

# Ephemeral but always-writable DB location; demo products are re-seeded on
# startup so printed QR codes survive instance recycles.
ENV AEGIS_DB_PATH=/tmp/aegis.db

# Cloud Run injects $PORT (default 8080). Bind to it.
ENV PORT=8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
