FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip install --no-cache-dir \
    paddlepaddle==3.3.0 \
    paddleocr>=3.4.0 \
    flask>=3.0.0

# Pre-download PP-StructureV3 models at build time
RUN python -c "from paddleocr import PPStructureV3; PPStructureV3()" || true

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8080

ENV PADDLE_DEVICE=cpu

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["serve"]
