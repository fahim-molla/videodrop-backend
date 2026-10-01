FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask flask-cors gunicorn yt-dlp

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app"]
