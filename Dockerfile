FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps: Java + curl for installing JMeter
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    openjdk-21-jre-headless \
 && rm -rf /var/lib/apt/lists/*

# Install JMeter
ARG JMETER_VERSION=5.6.3
RUN mkdir -p /opt \
 && curl -fsSL "https://downloads.apache.org/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz" -o /tmp/jmeter.tgz \
 && tar -xzf /tmp/jmeter.tgz -C /opt \
 && ln -s "/opt/apache-jmeter-${JMETER_VERSION}/bin/jmeter" /usr/local/bin/jmeter \
 && rm -f /tmp/jmeter.tgz

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

# Render sets $PORT automatically
CMD ["sh", "-lc", "uvicorn jmeter_server:app --host 0.0.0.0 --port ${PORT:-10000}"]
