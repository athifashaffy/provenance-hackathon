# Render web service: AEGIS provenance backend + built React frontend.
# Self-contained — SQLite (no external DB), vendored reference_lib, static UI baked in.
FROM python:3.11-slim

WORKDIR /app

# Dependencies. aegis_deploy/requirements.txt covers the app; uvicorn is the
# ASGI server Render runs the FastAPI app under (no a2wsgi/Passenger bridge here).
COPY aegis_deploy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "uvicorn[standard]==0.32.1"

# Application code (main.py, vendored libs, data/, built frontend in static/).
COPY aegis_deploy/ .

# SQLite lives on the container's ephemeral disk; fine for a stateless /verify demo.
ENV PYTHONUNBUFFERED=1 \
    AEGIS_DB_PATH=/app/data/aegis.db

# Render injects $PORT at runtime; default to 10000 for local `docker run`.
EXPOSE 10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
