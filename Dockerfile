FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backup_restore.py .
RUN mkdir -p /app/backups
ENV AWS_DEFAULT_REGION=us-east-2
CMD ["python", "backup_restore.py"]
