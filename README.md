# AgentOps Case Agent

與 Red Hat Support Case 協作的 AI 運維助手。  
讀取 Support 留言 → 規劃診斷 → 透過 MCP 執行 → 回覆 Case。

**您只需要：** Case 編號 + LLM API Key。其餘由產品預設處理。

---

## 快速開始（5 分鐘）

### 1. 安裝

需要 **Python 3.11+**（含本機 shell exec MCP）與 **Node.js**（npx 自動拉取 kubernetes MCP）。

```bash
pip install -r requirements.txt
```

MCP 無需另外安裝腳本：kubernetes MCP 預設用 `npx` 首次執行時自動下載；shell MCP 隨 `pip install` 一併安裝。

### 2. 設定

```bash
cp config/agent_config.minimal.json config/agent_config.json
cp .env.example .env
```

編輯兩個檔案：

| 檔案 | 填什麼 |
|------|--------|
| `.env` | `GEMINI_API_KEY=...`（或 `OPENAI_API_KEY`） |
| `config/agent_config.json` | `case_id`、LLM `provider` / `model` |

（可選）若要用本機編譯的 MCP 而非 npx 預設：

```bash
cp config/local.json.example config/local.json   # 改 platform.command 路徑
```

`config/agent_config.json` 最小範例：

```json
{
  "case_id": "01234567",
  "llm": {
    "provider": "gemini",
    "model": "gemini-3.1-flash-lite",
    "api_key_env": "GEMINI_API_KEY"
  }
}
```

也可用環境變數覆寫：`CASE_ID`、`LLM_PROVIDER`、`LLM_MODEL`。

### 3. MCP OAuth（首次使用）

Case 讀寫需 **Red Hat 帳號授權**，由 `rh-tam-kubernetes-mcp-server` 處理（非 Agent 本體）：

1. 確認根目錄 `agent_config.json` 含 `"selectedAuthType": "oauth-personal"`（repo 已附範本）
2. 執行 `python main.py --check`
3. 若 MCP 提示登入，用瀏覽器完成 Red Hat OAuth（通常只需一次，token 由 MCP 本機保存）

### 4. 檢查與啟動

```bash
python main.py --check          # 檢查 LLM、MCP、Case 讀取
python main.py --dry-run        # 試跑（不發回覆）
python main.py                  # 正式運行
```

其他常用參數：

```bash
python main.py --case-id 01234567
python main.py --reset-memory   # 清除處理紀錄，從頭開始
python main.py --report         # PoC 量測摘要
python check_mcp_tools.py       # 列出 MCP 工具
```

---

## 它會做什麼？

| 步驟 | 說明 |
|------|------|
| 輪詢 Case | 讀取新留言 |
| 辨識 Support 請求 | 依 API 角色與內容（不需您設定 trigger） |
| 執行診斷 | `oc get`、Pod 日誌、dig/ping 等（經 MCP） |
| 撰寫回覆 | 繁中回覆 Support，出站前安全檢查 |
| 防造假 | 回覆須對應真實執行結果 |
| PoC 量測 | 每次處理寫入 `reports/{case_id}/`（`--report` 查看摘要） |

### 典型情境

| Support 留言 | Agent 行為 |
|--------------|------------|
| 「請執行 oc get node」 | 經 MCP 執行 → 結果寫回 Case |
| 「請跑 dig / ping」 | 經 exec MCP 執行 → 回覆 |
| 「請上傳 must-gather / sosreport」 | **有** MCP + policy → 收集→上傳→驗證附件清單；**否則** `clarify`（含模板問題） |
| 危險指令（reboot、rm -rf） | 攔截並說明；其餘可執行指令照常（`skip_and_continue`） |

> must-gather / 大型收集包需 `config/policy.yaml` 開啟對應能力，且環境有對應 MCP。沒有時 Agent 會在 Case 上向 Support 請教，這是設計上的正常路徑。

### SRE 可見性

```bash
python main.py --dry-run          # 試跑；stdout 會印出本輪 Run 摘要
python main.py --report           # 查看 PoC 累計指標（回應時效、clarify 次數等）
python main.py --report-json      # 同上，JSON 格式
```

Run 詳情：`reports/{case_id}/runs/run-*.json` · 累計指標：`reports/{case_id}/metrics.json` · 稽核：`reports/{case_id}/audit.jsonl`

### Enterprise（Production）

```bash
python main.py --health              # 健康檢查
python main.py --audit-report        # 稽核摘要
python main.py --pending-approvals   # 待核准 MCP 操作
python main.py --approve <case> <fingerprint> --approved-by sre@corp.com
```

設定範例：`config/agent_config.enterprise.example.json` · 完整指南：[docs/ENTERPRISE.md](docs/ENTERPRISE.md)

---

## 設定檔一覽

| 檔案 | 誰該編輯 | 用途 |
|------|----------|------|
| `config/agent_config.json` | **您** | Case、LLM、輪詢、測試模式等（**大部分調整都在這**） |
| `.env` | **您** | API Key、環境變數覆寫 |
| `config/local.json` | 可選 | 覆寫 MCP 執行檔路徑 |
| 根目錄 `agent_config.json` | 通常不用改 | MCP OAuth 設定（Red Hat 登入） |
| `config/policy.yaml` | **資安 / 進階** | 安全政策（選 profile） |
| `agent_memory.json` | 自動產生 | 執行狀態（`--reset-memory` 可清除） |
| `reports/{case_id}/` | 自動產生 | PoC run 報告與量測（`--report`） |

> **MCP 預設行為**（無需 `local.json`）：`platform` → `npx -y rh-tam-kubernetes-mcp-server@latest`；`exec` → 同 venv 的 `mcp-shell-server`（或 PATH）。可用 `MCP_PLATFORM_COMMAND` / `MCP_EXEC_COMMAND` 覆寫。

---

## 可調整設定（依檔案）

下面列出「想改什麼行為 → 改哪個檔案 → 怎麼寫」。  
未寫進 `agent_config.json` 的欄位會用程式內建預設值（見 `core/config.py`）。

### 1. `config/agent_config.json` — 主力設定檔

路徑：**`config/agent_config.json`**（從 `config/agent_config.minimal.json` 複製後編輯）

#### 必填（第一次使用）

```json
{
  "case_id": "01234567",
  "llm": {
    "provider": "gemini",
    "model": "gemini-3.1-flash-lite",
    "api_key_env": "GEMINI_API_KEY"
  }
}
```

| 欄位 | 說明 | 範例 |
|------|------|------|
| `case_id` | Red Hat Case 編號 | `"01234567"` |
| `llm.provider` | LLM 供應商 | `"gemini"` 或 `"openai"` |
| `llm.model` | 模型名稱 | `"gemini-3.1-flash-lite"` |
| `llm.api_key_env` | 讀哪個環境變數當 API Key | `"GEMINI_API_KEY"` |
| `llm.temperature` | 可選，預設 `0` | `0` |

#### 輪詢頻率（不耗 LLM token，只影響多久讀一次 Case）

```json
{
  "polling": {
    "interval_seconds": 30,
    "cooldown_after_reply_seconds": 60
  }
}
```

| 欄位 | 預設 | 說明 |
|------|------|------|
| `polling.interval_seconds` | `10` | 每輪結束後等幾秒再讀留言 |
| `polling.cooldown_after_reply_seconds` | `45` | Agent 回覆後冷卻幾秒（防連發） |

#### 一人測試（假扮 Support 留言）

**步驟 1：** 在 **`.env`** 或執行前 export：

```bash
AGENT_DEV_MODE=1
```

**步驟 2（可選）：** 在 **`config/agent_config.json`** 改測試前綴（預設 `[SE] `）：

```json
{
  "participants": {
    "demo_trigger_prefix": "[SE] "
  }
}
```

用法：在 Case 留言開頭打 `[SE] 請執行 oc get node`，Agent 會把這則當成 Support 請求。  
`demo_trigger_prefix` **只在** `AGENT_DEV_MODE=1` 時生效。

進階觸發規則（仍寫在 **`config/agent_config.json`** 的 `trigger` 區塊）：

```json
{
  "trigger": {
    "mode": "demo",
    "require_explicit_request_in_demo": true
  }
}
```

| 欄位 | 說明 |
|------|------|
| `trigger.mode` | `"production"`（只處理 Support）或 `"demo"`（測試）；設了 `AGENT_DEV_MODE=1` 且未指定時自動為 `demo` |
| `require_explicit_request_in_demo` | `true` 時 customer 留言須含「請執行」、code block 等才觸發 |

#### 誰算 Support / Customer（正式環境通常不用改）

API 的 `createdByType` 優先；必要時在 **`config/agent_config.json`** 加：

```json
{
  "participants": {
    "support_author_patterns": ["*@redhat.com", "Red Hat*"],
    "support_authors": ["alice@example.com"],
    "customer_authors": ["bob@example.com"],
    "ignore_authors": ["Automated Support"]
  }
}
```

#### 叢集內 dig/ping（走 Pod 而非本機）

在 **`config/agent_config.json`**：

```json
{
  "diagnostics": {
    "pods_exec": {
      "namespace": "openshift-console",
      "pod": "console-abc123"
    }
  }
}
```

有填 `namespace` + `pod` 時，`dig`/`ping` 會優先進 Pod；否則走本機 exec MCP。

#### 回覆與安全上限

```json
{
  "limits": {
    "max_replies_per_session": 20,
    "max_reply_chars": 4000
  },
  "agent": {
    "reply_prefix": "【AI 運維代理自動通知】",
    "loop_guard_seconds": 1800
  },
  "case": {
    "comment_public": true
  },
  "guardrails": {
    "reply": {
      "block_ungrounded_execution_output": true
    }
  }
}
```

| 欄位 | 說明 |
|------|------|
| `limits.max_replies_per_session` | 單次啟動最多回幾則 |
| `agent.reply_prefix` | Agent 回覆開頭標記（用來辨識自己的留言） |
| `agent.loop_guard_seconds` | 相同失敗指令冷卻秒數 |
| `case.comment_public` | `true` = 回覆為公開留言 |
| `guardrails.reply.block_ungrounded_execution_output` | 擋下 LLM 偽造執行結果 |

#### 完整範例（合併多區塊）

```json
{
  "case_id": "01234567",
  "polling": {
    "interval_seconds": 30,
    "cooldown_after_reply_seconds": 60
  },
  "llm": {
    "provider": "gemini",
    "model": "gemini-3.1-flash-lite",
    "api_key_env": "GEMINI_API_KEY"
  },
  "participants": {
    "demo_trigger_prefix": "[SE] "
  },
  "diagnostics": {
    "pods_exec": {
      "namespace": "",
      "pod": ""
    }
  }
}
```

---

### 2. `.env` — API Key 與快速覆寫

路徑：**專案根目錄 `.env`**（從 `.env.example` 複製）

```bash
GEMINI_API_KEY=your-key-here
CASE_ID=01234567
AGENT_DEV_MODE=1
```

| 變數 | 對應設定 | 說明 |
|------|----------|------|
| `GEMINI_API_KEY` | `llm.api_key_env` | LLM API Key |
| `OPENAI_API_KEY` | 同上 | 若 provider 為 openai |
| `CASE_ID` | `case_id` | 覆寫 Case 編號 |
| `LLM_PROVIDER` | `llm.provider` | 覆寫 LLM 供應商 |
| `LLM_MODEL` | `llm.model` | 覆寫模型 |
| `AGENT_DEV_MODE=1` | `trigger.mode` | 啟用測試模式 |
| `MCP_PLATFORM_COMMAND` | `config/local.json` | 覆寫 kubernetes MCP 路徑 |
| `MCP_EXEC_COMMAND` | 同上 | 覆寫 shell MCP 路徑 |

程式啟動時會讀 `.env` 載入環境變數（見 `core/config.py` 的 `load_dotenv`）。已 export 的變數優先於 `.env`。

---

### 3. `config/local.json` — MCP 執行檔路徑（可選）

路徑：**`config/local.json`**（從 `config/local.json.example` 複製，**不進版控**）

只有當你不想用 npx 預設、或要用本機編譯的 MCP 時才需要：

```json
{
  "mcp_providers": {
    "platform": {
      "command": "/path/to/rh-tam-kubernetes-mcp-server",
      "args": []
    },
    "exec": {
      "command": "/usr/local/bin/mcp-shell-server",
      "env": {
        "ALLOW_COMMANDS": "dig,ping,nslookup,host,traceroute,curl"
      },
      "tool_map": {
        "exec_argv": "shell_execute"
      }
    }
  }
}
```

---

### 4. 根目錄 `agent_config.json` — MCP OAuth

路徑：**專案根目錄 `agent_config.json`**（不是 `config/agent_config.json`）

這是 **kubernetes MCP server** 的 OAuth 設定，不是 Agent 的 Case/LLM 設定：

```json
{
  "mcpServers": {
    "kubernetes": {
      "command": "npx",
      "args": ["-y", "rh-tam-kubernetes-mcp-server@latest"]
    }
  },
  "selectedAuthType": "oauth-personal"
}
```

首次 `--check` 時依 MCP 提示完成 Red Hat 登入即可。

---

### 5. `config/policy.yaml` — 安全政策

路徑：**`config/policy.yaml`**（詳見 [docs/POLICY.md](docs/POLICY.md)）

大多數情況只改一行：

```yaml
profile: diagnostic   # minimal | diagnostic | enterprise
```

| Profile | 用途 |
|---------|------|
| `minimal` | 只讀寫 Case，不碰叢集 |
| `diagnostic` | **預設** — 查叢集 + 網路診斷（dig/ping 等） |
| `enterprise` | 生產白名單，只允許明確開啟的能力 |

```bash
python main.py --check        # 查看政策摘要
python main.py --policy-dump  # 輸出完整編譯結果（資安審計）
```

進階：在 `policy.yaml` 用 `capabilities` 覆寫單項能力，或用 `overrides` 微調工具清單。

---

### 6. 命令列參數（不改檔案）

```bash
python main.py --case-id 01234567      # 覆寫 case_id
python main.py --dry-run               # 試跑，不真的執行 MCP / 發回覆
python main.py --check                 # 檢查 LLM、MCP、Case、Policy
python main.py --policy-dump           # 輸出編譯後的安全政策 JSON
python main.py --reset-memory          # 清除 agent_memory.json
```

---

### 7. 開發者專用（改程式行為）

| 想調整 | 檔案 |
|--------|------|
| LLM 分析 / 回覆語氣 | `config/prompts/analyze_comment.txt`、`compose_reply.txt` 等 |
| Workflow 流程 | `workflow/graph.py` |
| 預設值原始碼 | `core/config.py` 的 `default_config()` |

詳見 [docs/DEVELOPER.md](docs/DEVELOPER.md)。

---

## 常見問題

**`--check` 失敗？**

- LLM：確認 `.env` 有 API Key
- MCP platform：確認已安裝 Node.js / npx；或設 `MCP_PLATFORM_COMMAND` / `config/local.json`
- MCP shell exec：需 Python 3.11+ 且 `pip install -r requirements.txt` 成功
- Case：確認 `case_id` 正確且 MCP OAuth 已設定（見根目錄 `agent_config.json`）

**Agent 沒回覆我的測試留言？**

- 正式模式只處理 **Support** 留言（Red Hat 工程師或 API 辨識為 support）
- 內部同事討論（customer 角色）會自動略過

**一人測試（假扮 Support）？**

1. 在 **`.env`** 加一行 `AGENT_DEV_MODE=1`（或 `export AGENT_DEV_MODE=1`）
2. 在 Case 留言開頭打 **`[SE] `**（預設前綴；要改請編輯 **`config/agent_config.json`**）：

```json
{
  "participants": {
    "demo_trigger_prefix": "[SE] "
  }
}
```

3. 範例留言：`[SE] 請執行 oc get node`

完整可調參數見上方 [可調整設定（依檔案）](#可調整設定依檔案)。

**想先看不真的發送？** → `python main.py --dry-run`

---

## 進階文件

| 文件 | 內容 |
|------|------|
| [docs/POLICY.md](docs/POLICY.md) | 安全政策（profile / 能力包） |
| [docs/DEVELOPER.md](docs/DEVELOPER.md) | 架構、Guardrail、觸發規則、擴充指南 |
| [docs/mcp_case_api_integration.md](docs/mcp_case_api_integration.md) | MCP Case API 串接規格 |
| [docs/mcp_exec_contract.md](docs/mcp_exec_contract.md) | 本機 exec MCP（dig/ping）契約 |

---

## 授權

PoC / 內部使用。MCP Server 與 Red Hat Case API 需另行設定 OAuth。
