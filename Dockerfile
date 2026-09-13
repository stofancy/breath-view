FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libopengl0 libgl1 libglib2.0-0 libdbus-1-3 libxkbcommon0 fontconfig fonts-droid-fallback && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py storage.py reader.py analysis_report.py patient_summary.py portable_report.py ./
COPY web ./web
ENV QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1
EXPOSE 8080
USER 1000:1000
CMD ["python", "app.py", "--serve", "--host", "0.0.0.0", "--port", "8080", "--home", "/data"]
