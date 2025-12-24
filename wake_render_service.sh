#!/bin/bash
# Wake Render web service (keep-alive / pre-deploy warmup)
SERVICE_URL="https://selenium-mcp.onrender.com"

echo "🚀 Waking up Render service at $SERVICE_URL..."
for i in {1..10}; do
  echo "⏱️  Ping $i/10"
  curl -s -o /dev/null "$SERVICE_URL/health"
  curl -s -o /dev/null "$SERVICE_URL/mcp/schema"
  sleep 1
done
echo "✅ Service should now be warm and responsive."
