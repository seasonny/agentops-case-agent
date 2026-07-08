# 約束與不可違反規則

| | |
|---|---|
| **Purpose** | 定義改碼時不可違反的資安、治理與協作紅線 |
| **Audience** | 開發者、AI Agent（改碼前必讀） |
| **Source of truth** | 本文件是**改碼紅線**的權威來源 |
| **Related** | [operations/policy.md](policy.md)、[guides/developer.md](../guides/developer.md)、[architecture/01-principles.md](../architecture/01-principles.md) |

> 政策操作細節見 [policy.md](policy.md)；guardrail 模組對照見 [guides/developer.md](../guides/developer.md)。

本檔列出 **AI Agent 在改碼時不得違反** 的硬約束。違反這些規則可能導致資安事件或 Support Case 誤操作。

---

## 1. 機敏資料

| 規則 | 說明 |
|------|------|
| **禁止 commit secrets** | `.env`、`config/local.json`、`agent_memory.json`、`reports/` 已在 `.gitignore` |
| **禁止硬編碼憑證** | API Key、OAuth token、私鑰不可寫進程式或測試 |
| **測試用合成資料** | 一律使用 `tests/safe_test_data.py` 的假信箱、假 case ID |
| **日誌 / 持久化脫敏** | 使用 `core/redaction.py`；勿繞過 `sanitize_for_log` / `sanitize_for_storage` |

---

## 2. 安全決策歸程式，不归 LLM

以下必須以 **確定性程式** 實作，不可「只靠 prompt 提醒」：

| 領域 | 模組 |
|------|------|
| 誰的留言要處理 | `core/participants.py`、`core/trigger.py` |
| 能否呼叫 MCP | `core/mcp_policy.py`、`core/policy_compiler.py` |
| 危險指令攔截 | `core/mcp_policy.py`、`core/dangerous_command_split.py` |
| Exec argv 白名單 | policy profile + exec MCP |
| 回覆防偽 | `core/reply_grounding.py` |
| 出站敏感資訊 | `core/reply_guardrail.py` |

**Triage（理解、選工具）交給 LLM**；上表為執行前/出站前的 **enforce 層**。禁止以確定性 regex 路由取代 LLM triage。

**禁止：** 為了「讓 LLM 更聽話」而移除或繞過上述檢查。

---

## 3. MCP 與執行邊界

| 規則 | 說明 |
|------|------|
| **不在 Agent 內 subprocess shell** | 本機命令只經 exec MCP（`mcp-shell-server`） |
| **不擅自擴大 policy 能力** | 新 MCP 工具須同步更新 `policy.yaml` / `policy_capability_map.yaml` |
| **must-gather / 上傳** | 需 policy 開啟 + 對應 MCP；無能力時應 `clarify`，不可假裝已上傳 |
| **`create_case_rh_portal`** | 目前被 policy 封鎖；勿在未設計 intake 流程前解封 |

---

## 4. 回覆與 Case 操作

| 規則 | 說明 |
|------|------|
| **Grounding** | `call_mcp` 後的回覆須對應真實 `execution_results` |
| **禁止偽造輸出** | 不可在回覆中捏造 dig/DNS/oc 成功結果 |
| **Agent 標記** | 回覆保留 `【AI 運維代理自動通知】` 前綴（可配置但勿 silently 移除） |
| **dry-run 不可發留言** | `--dry-run` 路徑不得呼叫 `add_case_comment` |

---

## 5. 測試與驗證

| 規則 | 說明 |
|------|------|
| **改 core/workflow 必跑 test** | `make test` |
| **改 policy 必跑 test + policy-dump** | 確認編譯結果符合預期 |
| **整合驗證需明示** | `make check` / `make dry-run` 需要真實 API Key 與 OAuth，CI 外執行 |
| **不要 skip hooks** | 除非使用者明確要求，否則 git commit 不可加 `--no-verify` |

---

## 6. 程式碼風格（Agent 行為約束）

| 規則 | 說明 |
|------|------|
| **最小 diff** | 只改任務相關檔案 |
| **不過度抽象** | 不為一兩行邏輯新增 helper |
| **沿用模組邊界** | `core/` 業務邏輯、`bridges/` 外部整合、`workflow/` 編排 |
| **不擅自加文件** | 除非使用者要求，勿新增 README 以外的 markdown |
| **不擅自 commit** | 僅在使用者明確要求時提交 |

---

## 7. Policy Profile 速查

| Profile | 能力 |
|---------|------|
| `minimal` | 只讀寫 Case，不碰叢集 |
| `diagnostic` | **預設** — 查叢集 + 網路診斷 |
| `enterprise` | 生產白名單，需明確開啟各能力 |

變更 profile 或 capabilities 前，確認 README / POLICY 中的客戶影響。

---

## 8. 遇到不確定時

1. 查 [AGENTS.md](../../AGENTS.md) 與 [PROGRESS.md](../../PROGRESS.md)
2. 查 [guides/developer.md](../guides/developer.md) 對應模組
3. 查 [docs/README.md](../README.md) 文件索引
3. 仍不確定 → **問使用者**，不要猜測 Case 行為或資安取捨
