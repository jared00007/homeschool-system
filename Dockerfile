# Compass — container image for hosting (Render / Railway / Fly).
# Locally the app still runs the old way (start-tracker.command); this is only
# for the hosted, multi-device deployment where "local won't cut it".
FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2-binary are bundled in the wheel, so no apt needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tracker/ ./tracker/

# The host injects $PORT; Streamlit must bind it and 0.0.0.0. Headless mode
# skips the "email?" prompt. DATABASE_URL (set in the host dashboard) flips
# db_backend from SQLite to Postgres automatically.
ENV PORT=8501
EXPOSE 8501
CMD streamlit run tracker/app.py \
    --server.port ${PORT} \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
