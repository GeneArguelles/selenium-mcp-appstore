#!/bin/bash
set -e

SERVICE="selenium-mcp"

echo "=========================================================="
echo "[INFO] Forcing full cache clear and redeploy for $SERVICE"
echo "=========================================================="

# Clear Render build cache through API (replace RENDER_API_KEY)
curl -s -X POST "https://api.render.com/v1/services/${SERVICE}/clear-cache" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $RENDER_API_KEY"

# Push a dummy commit so Render notices a new deployment
echo "[INFO] Touching timestamp file to trigger redeploy..."
echo "# Auto redeploy $(date)" > redeploy_marker.txt
git add redeploy_marker.txt
git commit -m "Force rebuild $(date +%Y-%m-%d_%H:%M:%S)" || true
git push origin main

echo "[INFO] ✅ Redeploy triggered."
