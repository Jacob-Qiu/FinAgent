#!/bin/bash

echo "========================================"
echo "Starting FinAgent Services"
echo "========================================"
echo ""

echo "[1/2] Starting FinanceMCP Server..."
npx -y finance-mcp-http &
MCP_PID=$!
echo "FinanceMCP Server started with PID: $MCP_PID"
echo "Waiting 5 seconds for server initialization..."
sleep 5
echo ""

echo "[2/2] Starting FinAgent..."
echo ""
uv run python agent.py

echo ""
echo "========================================"
echo "FinAgent has stopped."
echo "Stopping FinanceMCP Server..."
kill $MCP_PID
echo "========================================"
