# 專案進度（AI 交接用）

> **給 Cursor / AI Agent：** 每次完成任務後更新本檔。新 session 開始時先讀這裡，再讀 [AGENTS.md](AGENTS.md)。

最後更新：**2026-07-09**

---

## 當前狀態

| 項目 | 狀態 |
|------|------|
| 產品階段 | **PoC / 內部驗證** |
| 架構對齊 | **Approval Phase B（2026-07-09）** — Pending Store + Workflow resume 閉環 |
| 核心流程 | Connector poll → Understanding → Decision → Execute → Interpret → Response；grant 後 **resume**（不需新 trigger） |
| 測試 | `make test` — 156 tests OK |
| 下一 sprint | **Milestone B** — 真實 Case dry-run / workshop demo（見 [guides/workshop.md](docs/guides/workshop.md)） |

---

## 最近完成

- [x] **approval_denied（2026-07-09）**：`--deny` / `--deny-latest` / `make deny`；寫入 `denied[]` + audit；取消同計畫 resumable grant
- [x] **Approval B.2（2026-07-09）**：Resume 去重（`correlation_id`）；`--approve-latest` / `--approve pend-xxx`；`make approve|pending|audit`
- [x] **resume approval 閉環修正（2026-07-09）**：`workflow_resume` + `pending_id` 時 Decision Engine 跳過重複 approval
- [x] **Approval Phase B（2026-07-09）**：Pending Action 持久化（`pending_id` / `correlation_id` / `workflow_context`）；grant 後 `try_resume_approved_workflows`；audit 鏈 `approval_requested` → `approval_granted` → `workflow_resumed` → `mcp_executed`；可選 `connector_reply.mode: customer_status`
- [x] **HITL 治理定調文件（2026-07-09）**：新增 [docs/architecture/07-human-approval-governance.md](docs/architecture/07-human-approval-governance.md)；更新 enterprise.md / docs 索引
- [x] **Decision 合一（2026-07-09）**：`DecisionEngine.evaluate()` 整合 dangerous split / policy / approval；Understanding 只產出建議；governance deck 新增 2 張
- [x] **Milestone A — LLM-first 簡化（2026-07-08）**：移除 PoC 確定性 triage；新增 `workshop.md`；同步 module-map
- [x] **Sprint 5（2026-07-08）**：建立 `domain/case/`；移動 `collection_flow`、`diag_bundle`、`investigation`
- [x] `CaseDomainHooks` 編排掛鉤注入 `WorkflowDeps`；`graph.py` 不再直接 import 領域模組
- [x] **Sprint 4（2026-07-08）**：建立 `connectors/` 與 `Connector` 介面；`CasePortalConnector` 為首個實作
- [x] **Sprint 3（2026-07-08）**：`core/decision/` + `DecisionEngine`
- [x] **Sprint 2（2026-07-08）**：`core/understanding/` + `UnderstandingService`
- [x] **Sprint 1（2026-07-07）**：`workflow/runner.py` Workflow Engine 邊界

---

## 進行中

- [x] **Milestone B — Case 04444508**：治理閉環已驗證（pending → approve → resume → mcp_executed）；must-gather 因叢集未開而執行失敗屬預期

---

## 待辦 / 已知缺口

| 優先 | 項目 | 備註 |
|------|------|------|
| — | **Approval Phase D** | Slack / AWX / ITSM ApprovalProvider |
| — | Outage 自動開案 | README / DEVELOPER 標記為尚未實作 |
| — | `create_case_rh_portal` | 目前被 policy 封鎖 |
| — | 實際 Case PoC 驗證 | 需 Red Hat OAuth + 有效 `case_id`；04444508 需新 SE 留言才能觸發 dry-run |

---

## 變更紀錄

### 2026-07-09 — 治理可發現性 + 一次一批 Approval

**做了什麼：**
- `make policy-dump` 新增 `block_sources`（內建永封 / 能力關閉 / policy.yaml overrides）與 `dangerous_command_sources`
- `make check` Policy 摘要標示阻擋來源
- Approval 改為**一次一批**：`is_action_approved` 不再永久記住 fingerprint；每次新請求需重新 approve（grant 只服務 resume）

**驗證：**
- [x] `make test`（145 OK）

### 2026-07-09 — Approval Phase B（Pending Store + Workflow resume）

**做了什麼：**
- `core/approval.py`：Pending 持久化 `pending_id` / `correlation_id` / `expires_at` / `workflow_context`；`list_resumable_approved` / `mark_pending_resumed` / `expire_stale_pending`
- `workflow/runner.py`：`try_resume_approved_workflows` — grant 後下一輪 poll 自動 resume（不依賴 Case 新留言、不受 agent reply tail 阻擋）
- Audit：`approval_requested`（graph policy）、`approval_granted`（CLI `--approve`）、`workflow_resumed`、`mcp_executed`（executor 正式執行）
- Phase B.1：`approval.connector_reply.mode: customer_status` — 對外回覆不暴露 fingerprint
- 新增 `tests/test_approval_resume.py`

**驗證：**
- [x] `make test`（140 OK）

### 2026-07-09 — HITL 治理定調文件

**做了什麼：**
- 新增 `docs/architecture/07-human-approval-governance.md`（Approval Gate 為主角；Requester/Approver/Agent；Slack/AWX/ITSM；Audit 鏈）
- 修訂：弱化 Support/SE 敘事；Case 留言降為 Reference 範例；trigger ≠ approval
- 更新 governance deck（Approval Gate + Reference 範例 slides）
- 更新 `docs/README.md`、`operations/enterprise.md`、架構交叉引用

**驗證：**
- [x] 文件交叉引用一致

### 2026-07-09 — Decision 合一

**做了什麼：**
- `DecisionEngine.evaluate()`：危險指令 split、MCP 過濾、policy、approval 單次裁決
- `UnderstandingService` 移除 `_filter_dangerous_mcp_calls` / `_evaluate_dangerous_split`
- `workflow/graph.py`：`policy` 節點改呼叫 `evaluate()`；`execute` 移除 approval 閘門
- Governance deck 新增「Decision 合一」「三個情境」slides；`make test` 135 OK

**驗證：**
- [x] `make test`（135 OK）
- [x] `node docs/guides/generate-governance-deck.js`

---


**做了什麼：**
- 執行 `make check CASE_ID=04444508`、`make dry-run CASE_ID=04444508`
- 修復 `pid:` handled key 被誤判為 legacy → 每次啟動強制 re-bootstrap
- `Makefile` `check` 支援 `CASE_ID=`（與 `dry-run` 一致）
- 新增 `tests/test_memory_legacy_keys.py`

**驗證：**
- [x] `make test`（133 OK）
- [x] `make check CASE_ID=04444508`
- [x] dry-run 輪詢正常；Case 229 則留言可讀
- [ ] dry-run 完整一輪 workflow（待 Case 有新 Support 留言）

### 2026-07-08 — Milestone A：LLM-first 簡化

**做了什麼：**
- 移除 PoC 確定性 triage（`shell_diagnostics`、`cluster_read_routing`、`action_inference`、`clarify_templates`）
- Triage 改 LLM + MCP catalog；保留 policy / grounding / guardrail / audit
- 協作品質交 `collaborate_support` LLM；移除空洞片語表
- 新增 `docs/guides/workshop.md`、`core/explicit_request.py`
- 同步 `04-module-map.md`、`developer.md`、`constraints.md`

**驗證：**
- [x] `make test`（131 OK）

### 2026-07-08 — Sprint 5：Domain 分離

**做了什麼：**
- 新增 `domain/case/`（`collection_flow`、`diag_bundle`、`investigation`、`hooks`）
- `CaseDomainHooks` 封裝 collection / bundle / investigate 編排步驟
- `workflow/graph.py` 經 `deps.domain_hooks` 呼叫領域步驟，移除直接 import
- 從 `core/` 移除已搬移模組；更新 import
- 更新 `docs/architecture/04-module-map.md`

**驗證：**
- [x] `make test`（148 OK）
- [x] `python3 main.py --case-id=04444508`（2026-07-09 Milestone B check OK；dry-run 待新 SE 留言）

---

## Architecture Debt（記錄、未修）

| 項目 | 說明 | 建議處理時機 |
|------|------|--------------|
| runtime bootstrap 在 `main.py` | MCPRegistry / WorkflowDeps 組裝仍在入口 | 可選 |
| `analysis_prefilled` 雙路徑 | poll 先分析、graph `analyze` 常 skip | 設計如此；可選未來簡化 |
| `comment_analyzer` facade | 向後相容薄包裝 | 測試遷移後可移除 |
| 零散 `deps.policy` 呼叫 | domain collection / compose 仍直接用 policy | 可選收斂 |
| must-gather stdout 路徑解析 | `collection_flow.extract_must_gather_artifact_path` 用 regex 從 MCP 文字輸出抓 tarball 路徑 | MCP / must-gather 契約改回傳 structured `artifact_path` 時 |

---

## 本機環境備註

| 項目 | 值 |
|------|-----|
| Python | 3.11+ |
| 測試 Case ID | 使用 `tests/safe_test_data.py` 或 config 範例 `01234567` |
| MCP OAuth | 根目錄 `agent_config.json` + 首次 `make check` |
| 回歸驗證 | `make check CASE_ID=04444508`；`make dry-run CASE_ID=04444508` |

---

## 變更紀錄（歷史）

### 2026-06-27 — 建立 Harness Engineering 協作檔

**做了什麼：**
- 新增 AGENTS.md、PROGRESS.md、Makefile、init.sh

**驗證：**
- [x] make test（129 OK）
