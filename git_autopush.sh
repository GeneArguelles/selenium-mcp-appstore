#!/bin/bash
# ==========================================================
# Automated Git Push Script with Timestamped Commit Message
# ==========================================================
# This script:
#   1. Detects modified/untracked files
#   2. Adds them to staging
#   3. Commits with an ISO timestamp message
#   4. Pushes to the 'main' branch
#   5. Displays a short summary of the commit
# ==========================================================

# Exit immediately on error
set -e

# Ensure we’re inside a Git repo
if [ ! -d ".git" ]; then
  echo "❌ Error: No .git directory found. Run this from inside your repo root."
  exit 1
fi

# Generate timestamp for the commit
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Check if there are any changes to commit
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
  echo "✅ No changes to commit. Repository is clean."
  exit 0
fi

echo "🧩 Staging all modified and new files..."
git add -A

# Optional: list what was staged
echo "📋 Files staged for commit:"
git status -s

# Create commit with timestamp
echo "📝 Committing changes..."
git commit -m "Auto update @ ${TIMESTAMP}"

# Push to main branch
echo "🚀 Pushing to remote 'main' branch..."
git push origin main

# Confirm success
echo "✅ Successfully pushed changes at ${TIMESTAMP}"
git log -1 --oneline

