FROM python:3.10-slim

WORKDIR /app

# FFmpeg — yt-dlp 提取/转换音频强依赖
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
