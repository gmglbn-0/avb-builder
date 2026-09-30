FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    AVB_DATA_DIR=/data \
    AVB_PORT=8085 \
    AVB_HOST=0.0.0.0

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install avbroot, custota-tool, ksud, and magiskboot
RUN mkdir -p /tmp/tools && \
    curl -sL https://github.com/chenxiaolong/avbroot/releases/download/v3.34.1/avbroot-3.34.1-x86_64-unknown-linux-gnu.zip -o /tmp/tools/avbroot.zip && \
    unzip -q /tmp/tools/avbroot.zip -d /usr/local/bin && \
    curl -sL https://github.com/chenxiaolong/Custota/releases/download/v6.6/custota-tool-6.6-x86_64-unknown-linux-gnu.zip -o /tmp/tools/custota.zip && \
    unzip -q /tmp/tools/custota.zip -d /usr/local/bin && \
    curl -sL https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v3.4.0/ksud-x86_64-unknown-linux-musl -o /usr/local/bin/ksud && \
    curl -sL https://github.com/topjohnwu/Magisk/releases/download/v28.1/Magisk-v28.1.apk -o /tmp/tools/magisk.apk && \
    unzip -p /tmp/tools/magisk.apk lib/x86_64/libmagiskboot.so > /usr/local/bin/magiskboot && \
    chmod +x /usr/local/bin/avbroot /usr/local/bin/custota-tool /usr/local/bin/ksud /usr/local/bin/magiskboot && \
    rm -rf /tmp/tools

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and default config
COPY src/ ./src/
COPY config.example.yaml ./config.yaml

EXPOSE 8085
VOLUME ["/data"]

CMD ["python3", "-m", "src.main", "serve"]
