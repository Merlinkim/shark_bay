# Shark Bay Agent Orchestration Guide

This guide documents how to utilize the Openclaw agents (Merlin, Arthur, Lancelot) to achieve the goal of **1% daily return**. Use this as a reference for training and eventual migration to the production server.

## 🤖 Agent Roles

### 1. Merlin (Strategist & Researcher)
- **Primary Goal**: Strategy optimization and market analysis.
- **When to use**: 
    - "Find the best EMA parameters for the last 30 days."
    - "Analyze why the SMA Crossover failed during the recent dump."
- **Output**: Research notes and parameter recommendations in the Obsidian Vault.

### 2. Arthur (Lead Developer)
- **Primary Goal**: Infrastructure robustness and feature implementation.
- **When to use**:
    - "Add a new RSI-based indicator to the library."
    - "Optimize the DB query for faster backtesting."
- **Output**: Code changes in the `app/` directory.

### 3. Lancelot (Risk & Health Manager)
- **Primary Goal**: Capital protection and system monitoring.
- **When to use**:
    - "Check if the ingestor has any data gaps."
    - "Evaluate the MDD of Merlin's new proposed strategy."
- **Output**: System health reports and risk alerts.

## 🛠 Integration Setup (MCP)

Agents interact with the codebase via the **Model Context Protocol (MCP)**. Ensure `openclaw.json` has the following server configured:

```json
"shark-bay-code": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/merlin/code/shark_bay"]
}
```

## 📋 Training Exercises (Practice Tasks)

To practice orchestration, try the following command flow:

1. **Research**: Ask Merlin to find optimal parameters for `BTCUSDT`.
2. **Review**: Ask Lancelot to review Merlin's findings for risk.
3. **Implement**: If safe, ask Arthur to register the new strategy or parameters.

## 🚀 Migration Checklist
When moving to the new server:
1. [ ] Install Openclaw and dependencies (Node.js, Python, Docker).
2. [ ] Copy `openclaw.json` and agent instructions.
3. [ ] Update MCP paths to match the new server's directory structure.
4. [ ] Ensure the PostgreSQL database is accessible by the agents.
