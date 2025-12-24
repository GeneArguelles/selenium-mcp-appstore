FROM python:3.12-slim

# Install Chromium + chromedriver and minimal dependencies.
# (Package names are for Debian-based images.)
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    ca-certificates \
    fonts-liberation \
    libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HOST=0.0.0.0
ENV PORT=8000

# Tell Selenium where Chrome is (Debian path for chromium)
ENV CHROME_BINARY=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

EXPOSE 8000

CMD ["python", "mcp_server_v2.py"]
