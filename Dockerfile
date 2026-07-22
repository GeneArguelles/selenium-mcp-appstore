FROM python:3.12-slim
ENV CHROME_BINARY=/usr/bin/chromium
ENV CHROMEDRIVER_BINARY=/usr/bin/chromedriver
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    openjdk-21-jre-headless \
    chromium chromium-driver \
    fonts-liberation \
    libnss3 libnspr4 \
    libgbm1 \
    libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 \
    libgtk-3-0 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
    libxshmfence1 libdrm2 libxkbcommon0 \
 && rm -rf /var/lib/apt/lists/*

 RUN which chromium && chromium --version \
 && which chromedriver && chromedriver --version

# Install JMeter
ARG JMETER_VERSION=5.6.3
ARG JMETER_SHA512=5978a1a35edb5a7d428e270564ff49d2b1b257a65e17a759d259a9283fc17093e522fe46f474a043864aea6910683486340706d745fcdf3db1505fd71e689083
RUN mkdir -p /opt \
 && curl -fsSL "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz" -o /tmp/jmeter.tgz \
 && echo "${JMETER_SHA512}  /tmp/jmeter.tgz" | sha512sum -c - \
 && tar -xzf /tmp/jmeter.tgz -C /opt \
 && ln -s "/opt/apache-jmeter-${JMETER_VERSION}/bin/jmeter" /usr/local/bin/jmeter \
 && rm -f /tmp/jmeter.tgz

WORKDIR /app
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Build-time sanity check (optional but recommended)
RUN python -c "import mcp_server; print('mcp_server import OK')"

# Render sets $PORT automatically
CMD ["sh", "-lc", "uvicorn mcp_server:app --host 0.0.0.0 --port ${PORT:-10000}"]
