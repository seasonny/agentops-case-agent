# Developer Guide

| | |
|---|---|
| **Purpose** | 說明 Case Agent 的實作行為：觸發、workflow、guardrail、擴充與除錯 |
| **Audience** | 修改程式碼的開發者 |
| **Source of truth** | 本文件是**實作行為**的權威來源 |
| **Related** | [architecture/04-module-map.md](../architecture/04-module-map.md)、[operations/policy.md](../operations/policy.md)、[operations/constraints.md](../operations/constraints.md) |

> 客戶安裝與操作見 [README.md](../../README.md)。架構概念見 [architecture/](../architecture/)。政策設定見 [operations/policy.md](../operations/policy.md)。

---

## 責任分工

程式、LLM、MCP 的分工見 [architecture/01-principles.md](../architecture/01-principles.md)。實作對照：

| 負責方 | 職責 |
|--------|------|
| **Agent 程式** | 觸發、政策、guardrail、防偽、審計 |
| **LLM** | 理解留言、解讀結果、撰寫回覆 |
| **MCP Server** | 叢集 / Case API 操作 |

Agent **不在本機 subprocess 跑 shell**；本機 `dig`/`ping` 經 **exec MCP**（`mcp-shell-server`）。見 [contracts/exec-mcp.md](../contracts/exec-mcp.md)。

---

## 觸發與角色（L0）

### Production（預設）

無需設定 `trigger` 區塊：

- `trigger.mode = production`
- 只處理 **Support** 留言（`createdByType` API 優先，fallback `*@redhat.com`）
- 略過 Customer 內部討論
- 跳過 Agent 自己的回覆（`【AI 運維代理自動通知】` 前綴）

### Demo 測試

在 `.env` 設 `AGENT_DEV_MODE=1`，或在 `config/agent_config.json` 設 `"trigger": { "mode": "demo" }`。

| 機制 | 設定位置 | 說明 |
|------|----------|------|
| `trigger.mode` | `config/agent_config.json` | `AGENT_DEV_MODE=1` 且未指定時自動為 `demo` |
| `[SE] ` 前綴 | `participants.demo_trigger_prefix` | 留言以此開頭 → 視為 Support（僅 dev mode） |
| Customer 明確請求 | `trigger.require_explicit_request_in_demo` | code block、「請執行」等也可觸發 |

### L1：ParticipantResolver（`core/participants.py`）

辨識順序：

1. Agent 回覆前綴 → `agent`
2.（dev only）`demo_trigger_prefix` → `support`
3. API `createdByType` / `api_role`
4. `ignore_authors`、`support_author_patterns` 等
5. Fallback → `customer`

### L2：TriggerConfig（`core/trigger.py`）

從最新留言往回掃 `find_latest_unanswered_trigger_comment`：

- 最新是 Agent 回覆 → 不觸發
- production + customer → 略過
- 符合 Support 請求 → LLM triage

---

## Workflow（`workflow/graph.py`）

**心智模型**：Guardrailed ReAct — Reason → Act → Observe → 再 Reason，不是傳聲筒。

**現況（單輪內 investigate loop）**：

```
analyze → policy → [execute | compose]
execute → interpret ⇄ investigate_prepare → policy → execute → …
interpret → collection → bundle → convergence → compose → post
```

`investigation.enabled`（預設 true）與 `max_follow_up_steps`（預設 2）見 `config/agent_config.json`。

`main.py` 在進 workflow 前已完成 LLM triage，並設定 `analysis_prefilled=True`；workflow 的 `analyze` 節點常 skip。

| 節點 | ReAct 角色 | 職責 |
|------|------------|------|
| `analyze` | **Reason** | 理解 SE 留言、規劃 MCP / clarify |
| `policy` | **Decision** | 能不能 act（LLM 不決定） |
| `execute` | **Act** | MCP 呼叫 |
| `interpret` | **Observe → Reason** | 綜合 MCP 輸出、next_steps |
| `convergence` | **Reason** | 是否收斂 |
| `compose` | **Reply** | 帶判斷寫回 Case（須 grounding） |
| `post` | **Guardrail** | 出站掃描 + 防偽 |

`policy` 短路：`call_mcp` 被擋 → 直接 `compose`。

PoC 報告：`python main.py --report`。上傳閉環見 `core/collection_flow.py`。

### action_type

| 值 | 行為 |
|----|------|
| `call_mcp` | 執行 MCP 並回覆 |
| `reply_only` / `clarify` | 僅文字 |
| `dangerous_command` | 攔截說明 |
| `no_action` | 略過 |

---

## 五層 Guardrail（L0–L5）

術語定義見 [architecture/05-vocabulary.md](../architecture/05-vocabulary.md) § Policy / Guardrail。

| 層 | 模組 | 內容 |
|----|------|------|
| L0 | `trigger` + `participants` | 誰的留言、是否該處理 |
| L1 | `mcp_policy`（dangerous keywords） | 危險關鍵字 |
| L2 | `policy.yaml` / `mcp_policy` | 能力包、工具白黑名單 |
| L3 | `shell_diagnostics` + `comment_analyzer` | 確定性路由 |
| L4 | Exec MCP（`exec_argv`） | argv 白名單 |
| L5 | `reply_guardrail` + `reply_grounding` | 回覆防偽、出站掃描 |

政策設定完整說明：[operations/policy.md](../operations/policy.md)

### 回覆防偽（`core/reply_grounding.py`）

`call_mcp` 後若 LLM 回覆含偽造輸出，但 `execution_results` 為失敗 → 擋下並改用原始 MCP 輸出 fallback。

開關：`guardrails.reply.block_ungrounded_execution_output`（預設 true）。

### Shell 診斷路由

- `is_shell_only_request` → 確定性 `exec_argv`，不讓 LLM 選 `namespaces_list`
- LLM 選錯工具時 → `shell_diag_routing_override`

---

## 防無窮迴圈

| 機制 | 設定 |
|------|------|
| Cooldown | `polling.cooldown_after_reply_seconds`（45） |
| Session 上限 | `limits.max_replies_per_session`（20） |
| Loop guard | `agent.loop_guard_seconds`（1800） |
| 去重 | `processed_handled_keys`（timestamp + hash） |

---

## 日誌

JSON 一行一筆到 stdout。常見 `event`：

| event | 意義 |
|-------|------|
| `trigger_candidate` | 找到待處理 Support 留言 |
| `comment_analyzed` | LLM / 確定性 triage 完成 |
| `shell_diag_deterministic_route` | dig/ping 走 exec_argv |
| `mcp_call` | MCP 執行 |
| `reply_grounding_fallback` | 防偽擋下 |
| `reply_guardrail_blocked` | 出站被擋 |
| `case_comment_added` | 回覆成功 |

---

## 測試

```bash
make test
make check    # 需 .env 與 OAuth
```

改碼紅線見 [operations/constraints.md](../operations/constraints.md)。

---

## 擴充指南

| 目標 | 檔案 |
|------|------|
| 調整 triage 提示詞 | `config/prompts/analyze_comment.txt` |
| 調整回覆語氣 | `config/prompts/compose_reply.txt` |
| 調整結果解讀 | `config/prompts/interpret_results.txt` |
| 新增 MCP 政策 | `config/policy.yaml` + `policy_capability_map.yaml` |
| 新增 workflow 步驟 | `workflow/graph.py` |
| 更換 exec 層 | `config/local.json` → `mcp_providers.exec` |
| 新增 MCP provider | [mcp-providers.md](mcp-providers.md) |
| 修改產品預設值 | `core/config.py` → `default_config()` |

使用者可調設定見 [README.md — 可調整設定](../../README.md#可調整設定依檔案)。

---

## MCP 工具速查

`make mcp-tools` 列出完整清單。常用：

| 工具 | 用途 |
|------|------|
| `read_case_comments_rh_portal` | 讀留言 |
| `add_case_comment_rh_portal` | 發回覆 |
| `upload_attachment_rh_portal` | 上傳附件 |
| `oc_adm_must_gather` | 收集 must-gather |
| `resources_list` / `pods_log` | K8s 診斷 |
| `pods_exec` | Pod 內 dig/ping |
| `shell_execute`（exec MCP） | 本機 dig/ping |

---

## 常見問題

**comment_skipped reason**

| reason | 意義 |
|--------|------|
| `customer_internal` | production 略過 customer 留言 |
| `customer_no_explicit_request` | demo 模式下 customer 閒聊 |
| `loop_guard_same_request_blocker` | 相同失敗指令冷卻中 |
| `no_mcp_actions` | 無法映射到 MCP |

**Hydra JSON** — 規格見 [contracts/case-api.md](../contracts/case-api.md)

**Legacy** — 根目錄 `agent_config.json` 僅 MCP OAuth；Case/LLM 設定用 `config/agent_config.json`
