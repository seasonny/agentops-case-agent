# Workshop & PoC 指南

| | |
|---|---|
| **Purpose** | Workshop / PoC 敘事、縱深防禦模型、擴充接點、PoC 寫死項目清單 |
| **Audience** | 提案者、workshop 講者、PoC 負責人、接手的 Enterprise 團隊 |
| **Source of truth** | 本文件是 **Workshop 敘事與 PoC 邊界** 的權威來源 |
| **Related** | [architecture/00-manifesto.md](../architecture/00-manifesto.md)、[architecture/01-principles.md](../architecture/01-principles.md)、[guides/developer.md](developer.md)、[operations/policy.md](../operations/policy.md) |

---

## 這是什麼？（一句話）

**Enterprise AI Agent Reference** 的第一個參考實作——示範 **LLM 負責理解與推理，程式負責治理與執行邊界** 的可信任 Agent 模式。

不是「會解某類 ticket 的產品」，而是 **可複製到你們場景的架構樣板**。

---

## 核心命題：Prompt 不是治理

對 Enterprise 而言，只在 prompt 裡寫「請不要執行危險指令」「請不要捏造結果」**沒有約束力**，也上不了 production。

正確模式是 **縱深防禦（Defense in Depth）**：

```
┌─────────────────────────────────────────────────────────────┐
│  LLM 理解意圖 → 提出計畫（action_type、MCP 呼叫、回覆草稿）   │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  確定性治理層：能不能做、要不要人核准、能不能發、留不留痕    │
│  （policy / approval / grounding / guardrail / audit）       │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
                         允許才執行 / 發送
```

| 層次 | 負責方 | 職責 | 能否只靠 Prompt？ |
|------|--------|------|-------------------|
| **理解** | LLM | 讀 Case、判斷意圖、規劃 MCP 或協作回覆 | —（這層本來就是 LLM） |
| **決策** | Decision Engine | policy 允許/拒絕、風險核准 | ❌ 必須確定性 |
| **執行** | MCP / Tool Provider | 實際操作（argv 白名單等） | ❌ 必須確定性 |
| **解讀** | LLM | 綜合 MCP 輸出、規劃 next steps | — |
| **回應** | LLM + Guardrail | 撰稿 + **防偽/掃描/長度限制** | ❌ 出站必須確定性 |
| **稽核** | Agent 程式 | audit.jsonl、run report | ❌ 必須確定性 |

**原則**：LLM **先理解**，再 **提出**；組織用 **policy 與 guardrail 裁決**。  
Prompt 引導行為；**程式 enforce 邊界**。兩者缺一不可，但不能互相取代。

詳細模組對照見 [developer.md — Guardrail](developer.md#四層-guardraill0l4--audit)。

---

## 縱深防禦一覽（L0–L4 + Audit）

```
事件進入
  │
  ▼
L0  Trigger / Participants     誰的留言值得處理？（production：Support only）
  │
  ▼
    Understanding（LLM）         意圖、action_type、MCP 計畫、clarify
  │
  ▼
L1  Dangerous keywords          shutdown / rm -rf 等（執行前）
  │
  ▼
L2  policy.yaml / DecisionEngine  能力包、工具白黑名單、tenant profile
  │
  ▼
L3  Exec MCP argv 白名單          實際 shell 只能跑允許的二進位
  │
  ▼
    Execute → Interpret（LLM）
  │
  ▼
L4  reply_grounding + guardrail  不可偽造 MCP 輸出；敏感資訊；echo/最短長度
  │
  ▼
    Audit / Webhook / Run Report  可回放、可通知、可量測
```

**Workshop 要強調**：客戶敢用，是因為 **每一層都可設定、可測試、可稽核**，不是因為模型很聰明。

---

## Workshop 三幕劇（不綁特定故障類型）

### 第一幕 — Trust：為什麼不是 Chatbot

**展示**

- `make policy-dump` → 編譯後能力與限制
- `reports/{case_id}/audit.jsonl` → 決策與 MCP 軌跡
- Guardrail 擋下偽造執行結果（grounding fallback）

**訊息**

> Enterprise 要的是 **可預期行為**，不是更會聊。  
> Prompt 建議「不要亂跑」；**policy 決定能不能跑**。

---

### 第二幕 — Teammate：Agent 在既有 Workflow 裡幹活

**展示同一 Case 的兩種路徑**（不必同一故障；重點是 **LLM 依上下文選路**）：

| 路徑 | action_type | 價值 |
|------|-------------|------|
| **A — 需要證據** | `call_mcp` | 經 policy 跑允許的工具 → 帶 **grounded** 結果回覆 |
| **B — 需要對齊** | `reply_only` | Support 給診斷/建議 → 客戶視角 **有理解、有行動** 的協作回覆 |

**訊息**

> Agent 是 **Guardrailed ReAct**：Reason → Act → Observe → Reply。  
> 路徑由 **LLM 理解** 決定，不是 repo 內建「DNS 流程」「dig 流程」。

---

### 第三幕 — Reference：PoC 結束後你們帶走什麼

**展示擴充接點**（見下節），明確說：

> 我們交付 **模式 + 治理 + 一個能跑的 Connector 範例**。  
> Case Portal 是第一個整合；**場景、工具、政策由你們接上去**。

**收尾句**

> PoC 成功 ≠ 功能做完。  
> PoC 成功 = 團隊相信 **這套縱深防禦可以安全地接到你們的運維 workflow**。

---

## PoC 真正要證明的價值

| 指標 | 意義 |
|------|------|
| **治理可見** | 被 policy 擋、需 approval 時，SE 與 SRE 看得懂原因 |
| **回覆可稽核** | 宣稱的執行結果對得上 MCP 輸出（grounding） |
| **協作品質** | `reply_only` 不是空洞「收到了」，而是可推進 Case 的對齊 |
| **可擴充** | 換 Connector / 加 MCP / 調 policy 不需改核心 workflow |
| **Human by Exception** | 高風險等人核准；不確定就 clarify |

❌ 成功 ≠ 自動結案、≠ 解完所有 ticket 類型  
✅ 成功 = **受控協作** 可縮短排查、且組織願意繼續投資

---

## 擴充接點（PoC 後由使用者自行延伸）

| 接點 | 設定 / 模組 | 你可以做什麼 |
|------|-------------|--------------|
| **Connector** | `connectors/` | 接 Jira、ServiceNow、Slack、Email（Case Portal 只是範例） |
| **Policy** | `config/policy.yaml`、`policy_capability_map.yaml` | 開關能力包、工具 allowlist、enterprise profile |
| **MCP 工具** | `config/local.json`、MCP providers | 接自家叢集、CMDB、自動化平台 |
| **Prompts** | `config/prompts/*.txt` | 語氣、語言、領域詞彙（**不**取代 policy） |
| **Trigger** | `config/agent_config.json` → `trigger` | production / demo、角色規則 |
| **Webhook** | `outage.notify_webhook_url_env` | Slack / PagerDuty / 工單系統通知 |
| **Approval** | `reports/{case_id}/approvals.json` | 高風險 MCP 人工核准後重試 |
| **Domain hooks** | `domain/case/hooks.py` | 產品特定收集、bundle、investigation 步驟 |

**刻意不做死在 reference 裡的**：特定故障閉環（例如「DNS 修完 → 自動 dig → 回 Case」）。  
外部人工作業完成後的 **下一輪事件**，應由 **Connector / Webhook / 新留言** 注入，再由 **LLM + 治理層** 決定下一步。

---

## PoC 寫死項目清單

以下為 **加速 PoC 而加的確定性捷徑**。它們 **不是** Enterprise 治理核心；長期應 **弱化或移除**，改由 **LLM 看 MCP catalog 選工具 + L2 policy 裁決**。

## 已移除的 PoC 確定性捷徑（2026-07-08）

以下模組已自 codebase **移除**；triage 改由 LLM + MCP catalog，治理仍靠 policy / guardrail / audit。

| 原項目 | 原位置 | 現況 |
|--------|--------|------|
| Shell 診斷路由 | `core/shell_diagnostics.py` | **已刪除** |
| Shell 路由 override | `action_inference.apply_shell_diag_override` | **已刪除** |
| Cluster read 路由 | `core/cluster_read_routing.py` | **已刪除** |
| 確定性 triage 優先 | `action_inference.try_deterministic_route` | **已刪除** |
| Clarify 場景偵測 | `core/clarify_templates.py` + YAML | **已刪除** |

Demo 觸發用 `looks_like_explicit_support_request` 保留於 `core/explicit_request.py`（**非 triage 路由**）。

## 刻意保留的確定性邏輯（治理核心，非 triage）

| 項目 | 位置 | 為何保留 |
|------|------|----------|
| Trigger / Participants | `trigger.py`、`participants.py` | **誰**能啟動 Agent — 組織規則，不可交 LLM |
| Dangerous command | `dangerous_command_split.py`、`mcp_policy.py` | 執行前硬擋 — **Policy over Prompt** |
| Policy / Decision / Approval | `decision/`、`mcp_policy.py` | 能不能跑 MCP — 可稽核、可測 |
| Exec argv 白名單 | Exec MCP 契約 | 執行面最後一道 |
| Reply grounding | `reply_grounding.py` | 回覆須對得上 **真實** MCP 輸出（重疊檢查 + 通用 tool output 標記） |
| Reply guardrail | `reply_guardrail.py` | 敏感資訊、危險指令提及、長度 |
| Echo 檢查 | `collaboration_reply.py` | 結構性防轉述（非場景、非關鍵字路由） |
| 協作最短長度 | `collaboration_reply.py` | 僅擋過短空回覆；**品質靠 collaborate LLM + prompt** |
| Demo 觸發 heuristic | `explicit_request.py` | 僅 demo 模式 / LLM 不可用；**不做 MCP 路由** |
| must-gather 產物解析 | `collection_flow.extract_must_gather_artifact_path` | **MCP 執行後**解析 stdout 路徑，非 comment triage |
| 附件驗證 | `collection_flow.verify_attachment_on_case` | 上傳後對 Case API 做確定性確認 |
| Audit / redaction / loop guard | 各模組 | 可稽核、防洩漏、防迴圈 |

## 設計決策（2026-07-08，已確認）

### 協作回覆品質 — 單一 LLM，不加第二 pass

- 舊版以程式片語表擋「空洞回覆」；已移除，改由 `collaborate_support.txt` + `CollaborationReasoner` 負責。
- **不**再加第二個 LLM 做品質審查（避免補洞式維護）。
- 程式僅保留結構性底線：echo 檢查、最短長度；其餘預期 LLM 產出可發佈的 `customer_voice`。

### must-gather 上傳閉環 — 現況保留，標技術債

- `extract_must_gather_artifact_path` 從 MCP **執行後** stdout 解析 tarball 路徑 → 自動上傳 → 驗證附件。
- 非 comment triage；PoC 階段保留。待 MCP 回傳 structured path 時可移除 regex（見 `PROGRESS.md` Architecture Debt）。

## 已移除（本輪 + 前輪）

- Triage 路由：`shell_diagnostics`、`cluster_read_routing`、`action_inference`、`clarify_templates`
- Collection **triage** infer：`infer_must_gather_analysis`、`infer_explicit_upload_*`、comment 關鍵字偵測
- 空洞回覆中文片語表：改由 **collaborate LLM** 負責品質
- Grounding 的 dig/ping 專用 regex：改為通用 `exit_code` / stdout 標記 + 結果重疊

### 📋 狀態摘要

```
理解與推理     → LLM（應擴展到各種情境，不寫 if-else 場景）
能不能做       → Policy / Decision Engine（確定性，不可省）
做了什麼       → MCP + Audit（確定性）
回覆真不真     → Grounding + Guardrail（確定性）
PoC 捷徑       → 已移除；LLM triage + policy 裁決
```

---

## Demo 建議腳本（10–15 分鐘）

1. **Policy dump**（30 秒）— 「我們先講邊界，再講智能」
2. **Dry-run 一輪 call_mcp**（3 分鐘）— SE 要叢集資訊 → MCP → grounded 回覆
3. **Dry-run 一輪 reply_only**（3 分鐘）— SE 給診斷/建議 → 協作回覆（非轉述）
4. **故意展示被擋**（2 分鐘）— policy blocked 或 grounding fallback + audit 一行
5. **擴充接點 slide**（2 分鐘）— Connector / Policy / MCP / Webhook
6. **收尾**（1 分鐘）— Reference 交付物 + 你們下一步

不必綁 DNS、dig、must-gather；選 **當下 Case 真實出現的兩種 action_type** 即可。

---

## 與其他文件的關係

| 想深入了解 | 文件 |
|------------|------|
| 為什麼做這個專案 | [architecture/00-manifesto.md](../architecture/00-manifesto.md) |
| Policy over Prompt | [architecture/01-principles.md](../architecture/01-principles.md) |
| Guardrail 實作細節 | [guides/developer.md](developer.md) |
| policy.yaml 怎麼配 | [operations/policy.md](../operations/policy.md) |
| Production 部署 | [operations/enterprise.md](../operations/enterprise.md) |
| 改碼紅線 | [operations/constraints.md](../operations/constraints.md) |
| 舊版投影片草稿 | [archive/pitch.md](../archive/pitch.md)（**非 SSOT**；以本文件為準） |

---

## 常見問題

### 「既然有 LLM，為什麼還要 L3 確定性路由？」

PoC 時 LLM 偶爾選錯 MCP 工具（例如 dig 請求選成 `namespaces_list`），確定性路由是 **暫時止血**。  
Enterprise 目標是 **LLM 理解 + policy 裁決**；L3 應逐步降級為 fallback，而非越堆越多場景。

### 「外部團隊做完事，Agent 會自動知道嗎？」

**不會**，也不應在 reference 裡為特定場景寫死閉環。  
Agent 每輪留下 hypothesis / audit；**下一事件**（Support 留言、Webhook、其他 Connector）進來後，再由 LLM 理解 + 治理層處理。

### 「這能上 production 嗎？」

**治理層（L0–L2、L4–L5、Audit）是 production 必要條件。**  
PoC 捷徑（L3 場景路由）應在正式化前收斂；其餘透過 enterprise profile、approval、webhook 補齊運維需求。

---

*Case Agent · LLM 理解 · 程式治理 · 縱深防禦 · 可擴充 Reference*
