FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV EMBEDDING_CACHE_DIR=/app/model-cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-zh-v1.5', cache_dir='/app/model-cache')"
COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x docker-entrypoint.sh && mkdir -p /app/data /app/uploads
EXPOSE 8080
CMD ["./docker-entrypoint.sh"]
