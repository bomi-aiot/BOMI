FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY contract.py mapping.py translator.py main.py ./
COPY config/device.example.yaml ./config/device.example.yaml

CMD ["python", "main.py"]

