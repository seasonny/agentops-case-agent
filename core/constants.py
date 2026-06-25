AGENT_REPLY_PREFIX = "【AI 運維代理自動通知】"

TURN_WAITING = "WAITING_FOR_SUPPORT"
TURN_WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
TURN_PROCESSING = "PROCESSING"
TURN_COOLDOWN = "COOLDOWN"

TURN_OWNER_SUPPORT = "SUPPORT"
TURN_OWNER_CUSTOMER = "CUSTOMER"

DEFAULT_MCP_CONFIG = {
    "mcpServers": {
        "kubernetes": {
            "command": "npx",
            "args": ["-y", "rh-tam-kubernetes-mcp-server@latest"],
        }
    }
}
