#!/usr/bin/env bash
# Harness Engineering — 初始化檢查
# 用法：./init.sh  或  make init

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "==> AgentOps Case Agent — init"

# Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: 需要 Python 3.11+" >&2
  exit 1
fi

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "    Python $PY_VER"

# Node.js（kubernetes MCP 預設用 npx）
if command -v node >/dev/null 2>&1; then
  echo "    Node $(node --version)"
else
  echo "WARN: 未偵測到 Node.js；kubernetes MCP 預設需要 npx" >&2
fi

# 設定範本
if [[ ! -f config/agent_config.json ]]; then
  cp config/agent_config.minimal.json config/agent_config.json
  echo "    已建立 config/agent_config.json（請編輯 case_id 與 LLM）"
else
  echo "    config/agent_config.json 已存在，略過"
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "    已建立 .env（請填入 API Key）"
else
  echo "    .env 已存在，略過"
fi

if [[ ! -f config/local.json ]] && [[ -f config/local.json.example ]]; then
  echo "    提示：可選複製 config/local.json.example → config/local.json（自訂 MCP 路徑）"
fi

# 依賴
echo "==> 安裝 Python 依賴"
python3 -m pip install -r requirements.txt

echo ""
echo "==> 下一步"
echo "  1. 編輯 .env（GEMINI_API_KEY 或 OPENAI_API_KEY）"
echo "  2. 編輯 config/agent_config.json（case_id）"
echo "  3. make check          # 含 MCP OAuth（首次可能需瀏覽器登入）"
echo "  4. make test           # 單元測試"
echo "  5. make dry-run        # 試跑"
echo ""
echo "AI 協作：請先讀 AGENTS.md 與 PROGRESS.md"
