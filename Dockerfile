FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    OUTPUT_DIR=/app/outputs

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY app.py ./
RUN pip install --no-cache-dir .

RUN mkdir -p /app/outputs
EXPOSE 7860
CMD ["python", "app.py"]
