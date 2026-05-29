FROM python:3.11-slim

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements-docker.txt

COPY . .

RUN mkdir -p logs ml/models

CMD ["python", "main.py"]
