# Exec MCP 契約（argv → text）

本文件說明 **Case Agent** 與 **可抽換的執行層 MCP**（exec provider）之間的最小介面。  
適用於：本機 / 跳板機上的 `dig`、`ping`、`nslookup`、`oc` 等除錯指令。

**重點：policy（黑白名單、能否執行）由 Case Agent 負責；exec MCP 只做啞巴執行。**

---

## 1. 分工

| 元件 | 職責 | Policy |
|------|------|--------|
| **Case Agent** | 觸發、角色、指令分類、**全部業務 policy**、撰寫回覆、防偽 | ✅ 唯一來源（`config/policy.yaml`） |
| **kubernetes-mcp**（case / cluster） | Red Hat Case CRUD、K8s API | 工具黑名單由 Agent 決定是否呼叫 |
| **exec MCP**（客戶可自備 / 第三方） | 接收 `argv` → 執行 → 回傳文字 | ❌ 不重複業務黑白名單；僅硬底線（見 §5） |

Case Agent **不**在本機 `subprocess` 跑 shell。所有執行經 MCP `tools/call`。

---

## 2. 最小工具契約

### 2.1 工具名

邏輯名稱：`exec_argv`（實作名稱可不同，由 `agent_config.json` 的 `tool_map` 映射）。

### 2.2 輸入（arguments）

```json
{
  "argv": ["dig", "google.com.tw"],
  "timeout_seconds": 30,
  "cwd": "/optional/working/dir"
}
```

| 欄位 | 必填 | 說明 |
|------|------|------|
| `argv` | 是 | 字串陣列，`argv[0]` 為程式名，其餘為參數。**禁止** shell 字串（見 §5） |
| `timeout_seconds` | 否 | 預設建議 30 |
| `cwd` | 否 | 工作目錄 |

**不支援** 下列形式：

```json
{ "command": "dig google.com.tw | bash" }
{ "shell": "sh -c '...'" }
```

### 2.3 輸出（MCP result → Agent 視為執行文字）

MCP 標準回傳即可，Agent 從 `content[].text` 取文字。建議內容格式（二擇一）：

**A. 純文字（最簡單）**

```text
; <<>> DiG 9.16.23-RH <<>> google.com.tw
...
```

**B. 含 exit code（建議，方便 Agent / LLM 判斷失敗）**

```text
exit_code: 0
--- stdout ---
; <<>> DiG 9.16.23-RH <<>> google.com.tw
...
--- stderr ---
```

或 JSON 字串：

```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": ""
}
```

Agent 將整段文字存入 `execution_results`，供解讀與回覆防偽使用。

### 2.4 錯誤

執行失敗時仍回傳文字（含 `exit_code` 與 stderr），**不要**只回空白。  
MCP 協定層錯誤使用標準 `isError` + `content` 文字說明。

---

## 3. Agent 端設定（客戶抽換 exec MCP）

`config/agent_config.json` 概念範例（多 provider 為演進方向；現階段可與 cluster 共用進程）：

```json
{
  "mcp_providers": {
    "case": {
      "command": "/path/to/kubernetes-mcp-server",
      "args": [],
      "tools": ["read_case_comments_rh_portal", "add_case_comment_rh_portal"]
    },
    "cluster": {
      "command": "/path/to/kubernetes-mcp-server",
      "args": [],
      "tools": ["resources_list", "pods_log", "pods_exec"]
    },
    "exec": {
      "command": "/path/to/customer-exec-mcp",
      "args": [],
      "tool_map": {
        "exec_argv": "run_argv"
      },
      "capability_profile": "argv_exec_v1"
    }
  }
}
```

客戶更換 exec 層時：

1. 修改 `mcp_providers.exec` 的 `command` / `args`
2. 更新 `tool_map`（若對方工具名不是 `exec_argv`）
3. 執行 `python check_mcp_tools.py` 確認工具存在且 schema 含 `argv` 陣列
4. **不必**同步修改 exec MCP 內的業務黑白名單（應關閉或設最弱）

---

## 4. Case Agent 的 Policy（單一來源）

所有「能不能跑」由 Agent 在 **呼叫 MCP 之前** 決定。使用者編輯 **`config/policy.yaml`**（見 [POLICY.md](POLICY.md)）；編譯後由 `core/mcp_policy.py` 執行檢查。

| 機制 | 說明 |
|------|------|
| Profile + Mode | 能力包 + 白/黑名單思維（`policy_compiler.py`） |
| `dangerous_commands` | 輸入留言與 `argv` 全文掃描（reboot、rm -rf…） |
| Exec binaries | `pods_exec` / `exec_argv` 允許的 `argv[0]` |
| 出站 `reply_guardrail` | 敏感資訊、危險指令提及 |
| 回覆防偽 | 回覆中的「執行結果」須對應 `execution_results`（`reply_grounding.py`） |

LLM **不**決定是否安全；只決定語意與工具規劃。安全由 `policy.yaml` 編譯後的確定性規則處理（見 [POLICY.md](POLICY.md)）。

---

## 5. Exec MCP 硬底線（非業務 policy）

Exec MCP **不**維護與 Agent 重複的黑白名單，但建議實作：

- 只接受 `argv` 陣列，拒絕 shell 一條龍字串
- `timeout_seconds` 上限（例如 ≤ 120）
- 輸出大小上限（例如 ≤ 1MB）
- 不使用 `sh -c` / `bash -c` 包裝

---

## 6. 路由原則（Agent 內）

| 請求類型 | 優先路由 | 說明 |
|----------|----------|------|
| Case 讀寫 | case provider | Portal API |
| `oc get` / K8s 查詢 | cluster provider | API 工具，不跑 shell |
| 叢集內 `dig` / `ping` | `pods_exec` | 需叢集可連線 + Pod |
| 本機 / 跳板機 `dig` / `ping` | **exec provider** `exec_argv` | 無叢集時 fallback |
| 危險 / 無法映射 | 不執行 | `dangerous_command` 或 `clarify` |

---

## 7. 驗收清單（exec provider）

- [x] 提供至少一個工具，接受 `argv: string[]`（經 `exec_argv` → `shell_execute` 映射）
- [x] 回傳可讀文字（stdout；含 `exit_code` 格式化）
- [x] 不接受 shell 字串參數（由 mcp-shell-server 強制）
- [x] `python check_mcp_tools.py` 可列出該工具
- [ ] Agent dry-run / 正式 run 日誌出現 `mcp_call` + 對應 tool，且 `execution_results` 非空
- [x] Case 回覆中的命令輸出與 `execution_results` 一致（`block_ungrounded_execution_output` + fallback）

---

## 8. 常見問題

**Q: 為什麼不直接用通用 shell MCP？**  
A: 通用 shell MCP 常自帶 policy，且接受 shell 字串，與 Agent 雙份維護、安全邊界不清。建議使用符合本契約的 `argv` 型 exec MCP。

**Q: 指令種類很多，要逐條 allowlist 嗎？**  
A: 不必。Agent 用 **危險黑名單 + argv 形狀 + binary 類別**；exec MCP 不需列舉每條指令。

**Q: Mac / Linux 差異誰處理？**  
A: Exec MCP 用 `PATH` 解析 `argv[0]`；Agent 只傳 `["dig", "target"]`。

**Q: kubernetes-mcp 要加 host exec 嗎？**  
A: **不必。** 本機執行由獨立 exec provider 負責，kubernetes-mcp 維持 Case + 叢集單一職責。

---

## 9. 推薦實作：mcp-shell-server

本專案預設使用 [tumf/mcp-shell-server](https://github.com/tumf/mcp-shell-server) 作為 exec provider。

| Agent 邏輯 | mcp-shell-server |
|------------|------------------|
| `exec_argv` | `shell_execute` |
| `argv` | `command` |
| `timeout_seconds` | `timeout` |
| `cwd` | `directory` |

### 安裝（PoC）

```bash
# 需要 Python 3.11+（Agent 本體仍可用 3.9）
/usr/local/bin/python3.11 -m pip install 'mcp-shell-server>=1.1.0'
# 或
./scripts/install_exec_mcp.sh
```

### 設定範例

見 `config/agent_config.json` 的 `mcp_providers.exec`：

```json
"exec": {
  "command": "/usr/local/bin/mcp-shell-server",
  "args": [],
  "env": {
    "ALLOW_COMMANDS": "dig,ping,nslookup,host,traceroute,curl"
  },
  "tool_map": {
    "exec_argv": "shell_execute"
  }
}
```

驗證：

```bash
python3 check_mcp_tools.py
```

### Fork vs 直接 pip 安裝？

| 情境 | 建議 |
|------|------|
| **PoC / 本機開發** | 直接 `pip install mcp-shell-server==1.1.0` 釘版本即可；搭配 Agent 的 `config/policy.yaml` |
| **企業 / Production** | **Fork 或 vendoring** 到內部 Git + 內部 PyPI/artifact registry；釘 commit/tag、做安全審查、可控更新 |
| **部署白名單** | `ALLOW_COMMANDS` = MCP 進程層粗粒度白名單；**業務 policy 仍以 Agent 為準** |

Fork 流程（建議）：

1. Fork `tumf/mcp-shell-server` 到組織 GitHub
2. 檢視 `SECURITY.md`、審計 log 行為、預設 timeout/output cap
3. 釘 release tag（例如 `v1.1.0`），必要時 cherry-pick 安全修補
4. 從 fork 安裝：`pip install git+https://github.com/YOURORG/mcp-shell-server@v1.1.0`
5. 或 vendoring 到 `vendor/mcp-shell-server` + `pip install -e vendor/mcp-shell-server`

**雙層防護：**

- **MCP 層**：`ALLOW_COMMANDS`、子進程最小 env、timeout/output cap（硬底線）
- **Agent 層**：`dangerous_commands`、`host_exec_allowed_binaries`、`reply_guardrail`（業務 policy）

---

## 10. 相關文件

- Case / Portal 串接：[mcp_case_api_integration.md](mcp_case_api_integration.md)
- Agent policy：`config/policy.yaml`（見 [POLICY.md](POLICY.md)）
- 主設定：`config/agent_config.json`
