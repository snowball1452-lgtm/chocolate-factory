#!/bin/bash
# 🏭 Chocolate Factory — One-line deploy
# Usage: curl -fsSL https://raw.githubusercontent.com/snowball1452-lgtm/chocolate-factory/main/quickstart/deploy.sh | bash
# Or:   bash quickstart/deploy.sh

set -euo pipefail
BOLD="\033[1m"
GREEN="\033[32m"
RESET="\033[0m"

echo -e "${BOLD}🏭 Chocolate Factory — Quickstart Deploy${RESET}"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Install: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check docker compose
if docker compose version &> /dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE="docker-compose"
else
    echo "❌ Docker Compose not found. Install: https://docs.docker.com/compose/install/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo .)"

# If running from curl, clone the repo first
if [ ! -f "$SCRIPT_DIR/../compiler/compiler.py" ]; then
    echo "📥 Cloning chocolate-factory..."
    git clone --depth 1 https://github.com/snowball1452-lgtm/chocolate-factory.git /tmp/chocolate-factory 2>/dev/null
    cd /tmp/chocolate-factory
    SCRIPT_DIR="$(pwd)"
else
    cd "$SCRIPT_DIR/.."
fi

echo "🏗️  Building factory container..."
$COMPOSE -f docker-compose.quickstart.yml build --quiet

echo "🚀 Starting factory (2 containers)..."
$COMPOSE -f docker-compose.quickstart.yml up -d

echo ""
sleep 3

# Health check
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Factory is live at http://localhost:8000${RESET}"
    echo ""
    echo "  API docs:  http://localhost:8000/docs"
    echo "  Ollama:    http://localhost:11434"
    echo ""
    echo "  Try it:"
    echo '  curl -X POST http://localhost:8000/compile \'
    echo '    -H "Content-Type: application/json" \'
    echo '    -d '"'"'{"sources": {"organization": "/models/allowed = [\"kimi-k2.6\"]"}}'"'"''
else
    echo "⏳ Factory still starting... check with: docker compose -f docker-compose.quickstart.yml logs"
fi

echo ""
echo -e "${BOLD}🏭 Done.${RESET} To stop: ${COMPOSE} -f docker-compose.quickstart.yml down"
