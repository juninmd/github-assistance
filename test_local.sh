#!/bin/bash

# Local Test Script for Development Team Agents
# This script helps you test agents locally before deploying to GitHub Actions

set -e  # Exit on error

echo "========================================="
echo "Development Team Agents - Local Test"
echo "========================================="
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo ""
    echo "Create a .env file with the following variables:"
    echo ""
    echo "GITHUB_TOKEN=your_github_token"
    echo "JULES_API_KEY=your_jules_api_key"
    echo "GEMINI_API_KEY=your_gemini_api_key"
    echo "GITHUB_OWNER=juninmd"
    echo ""
    exit 1
fi

# Load environment variables
echo "📁 Loading environment variables..."
export $(cat .env | grep -v '^#' | xargs)

# Verify required variables
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GITHUB_TOKEN not set"
    exit 1
fi

if [ -z "$JULES_API_KEY" ]; then
    echo "❌ Error: JULES_API_KEY not set"
    exit 1
fi

echo "✅ Environment variables loaded"
echo ""

# Check if logs directory exists
if [ ! -d "logs" ]; then
    echo "📂 Creating logs directory..."
    mkdir -p logs
fi

# Function to run an agent
run_agent() {
    local agent_name=$1
    echo ""
    echo "========================================="
    echo "Running: $agent_name"
    echo "========================================="
    echo ""

    uv run run-agent $agent_name

    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ $agent_name completed successfully"
    else
        echo ""
        echo "❌ $agent_name failed"
        return 1
    fi
}

# Main menu
echo "Select agent to run:"
echo ""
echo "1) Product Manager"
echo "2) Interface Developer"
echo "3) Senior Developer"
echo "4) PR Assistant"
echo "5) All Agents (sequential)"
echo "6) Exit"
echo ""
read -p "Enter choice [1-6]: " choice

case $choice in
    1)
        run_agent "product-manager"
        ;;
    2)
        run_agent "interface-developer"
        ;;
    3)
        run_agent "senior-developer"
        ;;
    4)
        run_agent "pr-assistant"
        ;;
    5)
        run_agent "all"
        ;;
    6)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "========================================="
echo "Test Complete!"
echo "========================================="
echo ""
echo "📊 Check logs/ directory for execution results"
echo ""
