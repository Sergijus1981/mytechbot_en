FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-rus poppler-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip uninstall -y opencv-python opencv-python-headless && pip install --no-cache-dir opencv-python-headless==4.10.0.84

COPY . .

CMD ["python", "bot.py"]