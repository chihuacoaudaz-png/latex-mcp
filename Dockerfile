FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgraphite2-3 \
    libfontconfig1 \
    libharfbuzz0b \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh && \
    mv tectonic /usr/local/bin/

RUN pip install --no-cache-dir "mcp[cli]<2" uvicorn starlette

WORKDIR /app
COPY server.py .

ENV PORT=10000
EXPOSE 10000

CMD ["python", "server.py"]
