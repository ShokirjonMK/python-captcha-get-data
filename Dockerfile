FROM python:3.10-slim

# Tesseract uchun kerakli kutubxonalar
RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
