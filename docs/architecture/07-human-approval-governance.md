# Human Approval & Governance

| | |
|---|---|
| **Purpose** | 定義 Enterprise 場景下 **Human-in-the-Loop（HITL）核准** 的概念模型、稽核要求、整合方式與 Case Agent 對照 |
| **Audience** | 架構師、SRE、平台工程、workshop 提案者、接手的 Enterprise 團隊 |
| **Source of truth** | 本文件是 **人工核准治理** 的權威來源 |
| **Related** | [01-principles.md](01-principles.md)、[02-reference-architecture.md](02-reference-architecture.md)、[05-vocabulary.md](05-vocabulary.md)、[operations/enterprise.md](../operations/enterprise.md)、[operations/policy.md](../operations/policy.md) |

> **核心共識：** **Approval 是組織治理閘門** — 卡在 Decision 與 Execute 之間，決定高風險計畫能否執行。  
> 核准發生在 **治理通道**（Slack / AWX / ITSM / CLI…），**不是** 對話裡的「OK / Pass / 好的」。  
> 全程 **Audit 可回放** — 這是 Trusted AI 上 Production 的關鍵。

---

## 為什麼需要這份文件

Production 上客戶關心的不是「模型多聰明」，而是：

1. **誰** 在 **何時** 因 **何規則** 允許或拒絕執行？
2. 高風險操作是否 **必經人工核准**？
3. 核准鏈是否 **可稽核、可問責**（Trusted Governance）？

本文件以 **Approval** 為主角，定調其在 Enterprise AI Agent Reference 中的位置，並保留與 Ansible、Slack、ITSM 等整合的彈性——**不綁死單一產品或單一 trigger 來源**。

---

## Approval 是什麼：治理閘門

```
Understanding → 建議計畫
       │
       ▼
Decision Engine → allowed | denied | requires_approval
       │
       ├── denied ──────────→ 說明原因（Response）
       │
       └── requires_approval
                │
                ▼
         ┌──────────────┐
         │ APPROVAL GATE │  ← 本文件主角
         └──────┬───────┘
                │ grant（治理通道）
                ▼
            Execute → Interpret → Response
```

| 問題 | 答案 |
|------|------|
| Approval 卡在哪？ | **Decision 之後、Execute 之前** |
| 誰決定「要不要核准」？ | **Policy + approval 規則**（Decision Engine），不是 LLM |
| 誰執行「核准」動作？ | **Approver**（組織角色），透過 ApprovalProvider |
| Trigger 從哪來？ | **任意合法事件**（見下文）；trigger ≠ approval |

---

## 三角色模型（敘事主軸）

用 **Requester / Approver / Agent** 描述，不以特定職稱（如 Support）為軸。

| 角色 | 職責 | 典型例子 |
|------|------|----------|
| **Requester** | 觸發一次「待執行計畫」的來源 | Case 留言、告警、排程、上游 workflow |
| **Approver** | 在治理通道 **顯式 grant/deny** | SRE on-call、Change 委員、AWX approval node |
| **Agent** | 保存 Pending、等核准、**resume** 執行、寫 audit | Case Agent |

**重點：**

- **Approver ≠ Requester** — 開 ticket 的人通常 **不能** 自己批高風險操作。
- **Requester 說幾次話不是重點** — trigger 可以是一次或多次；Approval 關心的是 **計畫 + 組織裁決**。
- **Connector（Case）** 負責對外協作；**ApprovalProvider** 負責對內治理 — 兩個平面。

---

## 典型 Approval 時間軸（trigger 無關）

```
T0  Trigger            某事件產生「待執行計畫」（例：工單留言、webhook）
T1  Agent              Understanding → Decision: requires_approval
T2  Agent              Pending Action Store 持久化 intent + fingerprint
T3  Agent              Response（可選）: 對外可讀狀態 — 「待內部核准」
T4  ApprovalProvider   approval_requested → Slack / AWX / ITSM / …
T5  Approver           在 **治理通道** grant（非對話裡的 OK）
T6  Workflow Engine    resume(pending_id) — **不需新 trigger 留言**
T7  Agent              Execute → Interpret → Response（grounded 結果）
```

**設計約束（為何不能靠對話核准）：**

- 核准 **不得** 依賴「有人在 Case 再說 please proceed / OK」— 對話與治理是不同事件源。
- 核准 **不得** 依賴 LLM 解讀「好的」— 無身份綁定、無 audit 對應。
- 核准後 **必須 resume 已保存的計畫** — 而非賭下一輪 poll 撿到相同 trigger。

---

## 架構邊界：三個平面

```
┌─────────────────────────────────────────────────────────────┐
│  Connector 平面（對外協作 — Case / Jira / …）                 │
│  狀態說明、診斷結果 — 面向使用方                              │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Agent 平面（Workflow + Decision Engine）                    │
│  理解 → 裁決 → Pending → Resume → 執行 → 回應              │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Governance 平面（ApprovalProvider + Audit）                 │
│  approval_requested → granted/denied → 可問責                │
└─────────────────────────────────────────────────────────────┘
```

| 平面 | 做什麼 | 不做什麼 |
|------|--------|----------|
| **Connector** | 客戶／使用方可讀的狀態與結果 | 不當核准 UI |
| **Agent** | Pending、等 grant、resume | 不自批、不用 LLM 當核准 |
| **Governance** | Approver、Provider、Audit | 規則不寫在 prompt 裡 |

對應 [01-principles.md](01-principles.md)：**Human by Exception**、**Policy over Prompt**、**Governance over Intelligence**。

---

## 概念元件

### Decision Engine（裁決是否需 Approval）

- 輸入：Understanding 的 **建議計畫**
- 輸出：`DecisionResult.requires_approval`
- 規則來自 **policy + approval config**

### Pending Action Store

`requires_approval` 時 **必須持久化** 待執行 intent（與 trigger 解耦）：

| 欄位 | 用途 |
|------|------|
| `pending_id` / `workflow_id` | Resume |
| `fingerprint` | tool + arguments 雜湊 |
| `actions` | grant 後執行的 MCP 計畫 |
| `correlation_id` | Audit 串鏈 |
| `expires_at` | TTL |

### ApprovalProvider（可替換）

```
DecisionEngine → requires_approval
       ▼
ApprovalProvider.submit(ApprovalRequest)
       ▼  async
grant | deny | expire
       ▼
WorkflowEngine.resume(pending_id)
```

**Reference 不規定** Slack 或 AWX；只規定 **契約 + audit 事件**。

### Workflow Engine（Resume）

Approval 是 **Workflow 中斷後恢復** 的第一類場景（見 [02-reference-architecture.md](02-reference-architecture.md)）。

---

## 刻意不採用的反模式

| 反模式 | 為何不符合 Enterprise |
|--------|------------------------|
| 對話裡「OK / 好的」= 核准 | 無 Approver 身份、無 audit |
| 等 Requester 再 trigger 一次 | 核准與 trigger 綁死 |
| 把 fingerprint 寫給 **終端使用者** | 治理細節應在 ops 通道 |
| poll 賭重試、無 Pending Store | intent 丟失、不可問責 |

**核准的權威來源：** ApprovalProvider 的 **grant 事件**（signed callback / queue message）。

---

## Enterprise 整合（ApprovalProvider 實作）

| Provider | 適用 | Audit `approved_via` 例 |
|----------|------|-------------------------|
| **Slack / Teams** | On-call 快速批 | `slack:channel/C123` |
| **ServiceNow / Jira Change** | 正式變更紀錄 | `servicenow:CHG001234` |
| **Ansible AWX / Automation Controller** | 既有 job approval node | `awx:job_template/42` |
| **自建 API / Event Bus** | 企業核准中台 | `api:approval-svc` |
| **CLI / 檔案** | Reference PoC | `cli:operator` |

Case Agent PoC 使用 CLI + `approvals.json` — 證明 **契約與 audit**，非 Production 唯一形态。

---

## 設定模型（概念固定、配置可調）

```yaml
approval:
  enabled: true
  rules:
    - match:
        tools: ["oc_adm_must_gather", "pods_exec"]
      approver_group: "ocp-sre-oncall"
      provider: slack
      ttl_hours: 24
  connector_reply:
    mode: customer_status   # customer_status | ops_detail | silent
```

| 欄位 | 說明 |
|------|------|
| `approver_group` | **Approver** 角色，通常 ≠ Requester |
| `provider` | ApprovalProvider 選型 |
| `connector_reply.mode` | 對外（Connector）狀態說明方式 |

---

## Audit：Trusted Governance 核心

### 必備事件鏈

| 順序 | event |
|------|-------|
| 1 | `decision`（含 `requires_approval`） |
| 2 | `approval_requested` |
| 3 | `approval_granted` / `approval_denied` / `approval_expired` |
| 4 | `workflow_resumed` |
| 5 | `mcp_executed` |
| 6 | `reply_posted` |

**Correlation：** `correlation_id` 或 `pending_id` 串起全鏈。

Case Agent：`reports/{case_id}/audit.jsonl` · `python main.py --audit-report --case-id <id>`

Enterprise：同一事件轉發 SIEM / 資料湖。

---

## Approval 事件契約（整合用）

### `approval_requested`

```json
{
  "event": "approval_requested",
  "version": "1",
  "correlation_id": "01234567:229:a1b2c3d4e5f6g7h8",
  "pending_id": "pend-uuid",
  "fingerprint": "a1b2c3d4e5f6g7h8",
  "tool": "oc_adm_must_gather",
  "approver_group": "ocp-sre-oncall",
  "requested_at": "2026-07-09T12:00:00Z",
  "expires_at": "2026-07-10T12:00:00Z"
}
```

### `approval_granted`

```json
{
  "event": "approval_granted",
  "correlation_id": "01234567:229:a1b2c3d4e5f6g7h8",
  "pending_id": "pend-uuid",
  "approved_by": "sre@corp.com",
  "approved_via": "slack:channel/C123"
}
```

### `approval_denied`

```json
{
  "event": "approval_denied",
  "correlation_id": "01234567:229:a1b2c3d4e5f6g7h8",
  "pending_id": "pend-uuid",
  "fingerprint": "a1b2c3d4e5f6g7h8",
  "tool": "oc_adm_must_gather",
  "denied_by": "sre@corp.com",
  "denied_via": "cli:operator",
  "deny_reason": "叢集已下線，不需 must-gather"
}
```

> **Deny** = Approver 明確拒絕執行；pending 關閉，Agent **不 resume**。與 `approval_expired`（逾時無人處理）語意不同。

---

## 與 Policy 的關係

| 層次 | 職責 |
|------|------|
| **Policy** | 工具是否 **允許出現在計畫中** |
| **Approval** | 在允許集合內，哪些仍須 **Approver 顯式 grant** |

兩層都進 audit；Decision Engine 單次 `evaluate()` 輸出統一結果。

---

## Reference 範例：Case Agent + 工單留言

> **僅為 Case Agent 的一種 trigger 示例**，不是 Approval 架構的前提。

1. **Requester：** 工單上一則診斷請求（Case Agent production 下通常只處理特定角色留言 — 屬 **trigger 規則**，見 `core/trigger.py`）
2. **Agent：** `requires_approval` → Pending → 可選 Connector 回覆「待內部核准」
3. **Approver：** SRE 經 Slack / CLI grant
4. **Agent：** resume → must-gather → 結果回工單

**Trigger 規則**（誰的留言會啟動 Agent）與 **Approval 治理**（誰能放行執行）請分開配置、分開敘事。

---

## Case Agent 現況 vs 目標

| 能力 | 目標 | 現況（2026-07） |
|------|------|----------------|
| Decision → `requires_approval` | ✅ | ✅ |
| Pending + resume | ✅ | ✅ Phase B |
| Resume 去重（同 correlation 只 resume 一次） | ✅ | ✅ |
| CLI：`--approve-latest` / `pending_id` | ✅ | ✅ |
| ApprovalProvider 抽象 | ✅ | ⚠️ CLI only（Phase D） |
| Audit 核准鏈 | ✅ | ✅ |
| `customer_status` 對外回覆 | ✅ | ✅ Phase C |
| `approval_denied` | ✅ | ✅ CLI `--deny` / `--deny-latest` |

---

## Production 檢查清單

- [ ] 高風險 tools 由 config 定義
- [ ] **Approver ≠ Requester**
- [ ] 核准在 **Governance 平面**，非對話 OK
- [ ] grant 後 **resume Pending**，非賭 poll
- [ ] audit 可串 `requested → granted → executed`
- [ ] Pending TTL + 過期處理
- [ ] ApprovalProvider 可替換

---

## 演進路徑

| 階段 | 交付 |
|------|------|
| **A** | Decision 合一 + CLI + audit |
| **B** | Pending Store + Workflow resume |
| **C** | `customer_status` Connector 回覆 |
| **B.2** | Resume 去重 + CLI 簡化（`--approve-latest`、`pend-` token） |
| **D** | Slack / AWX / ITSM Provider |
| **E** | 多 tenant + SIEM |

---

## 相關文件

| 文件 | 用途 |
|------|------|
| [02-reference-architecture.md](02-reference-architecture.md) | Human Escalation |
| [operations/enterprise.md](../operations/enterprise.md) | 部署與 PoC CLI |
| [guides/workshop.md](../guides/workshop.md) | Workshop |

---

## 一句話（Workshop / 提案）

> **高風險操作必經 Approval 閘門；核准在治理通道完成，全程 Audit 可問責。**  
> Agent 保存計畫、grant 後 resume — 這才是敢上 Production 的 Trusted Governance。
