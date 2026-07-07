# 專案進度（AI 交接用）

> **給 Cursor / AI Agent：** 每次完成任務後更新本檔。新 session 開始時先讀這裡，再讀 [AGENTS.md](AGENTS.md)。

最後更新：**2026-07-08**

---

## 當前狀態

| 項目 | 狀態 |
|------|------|
| 產品階段 | **PoC / 內部驗證** |
| 架構對齊 | **Sprint 3 完成** — Decision Engine（`core/decision/` + `DecisionEngine`） |
| 核心流程 | `UnderstandingService` → `DecisionEngine` → LangGraph execute → MCP → 回覆 + guardrail |
| 測試 | `make test` — 144 tests OK |
| 下一 sprint | **Sprint 4 — Connector 抽象**（尚未開始） |

---

## 最近完成

- [x] **Sprint 3（2026-07-08）**：建立 `core/decision/` 與 `DecisionEngine` 統一決策入口
- [x] `workflow/graph.py` `policy` / 核准閘門改經 `DecisionEngine`
- [x] `audit_trail.record_decision()` 記錄決策結果
- [x] **Sprint 2（2026-07-08）**：`core/understanding/` + `UnderstandingService`
- [x] **Sprint 1（2026-07-07）**：`workflow/runner.py` Workflow Engine 邊界

---

## 進行中

_（目前無 — 待指派 Sprint 4）_

---

## 待辦 / 已知缺口

| 優先 | 項目 | 備註 |
|------|------|------|
| 高 | **Sprint 4：Connector 抽象** | 見 [06-architecture-alignment-plan.md](docs/architecture/06-architecture-alignment-plan.md) |
| — | Outage 自動開案 | README / DEVELOPER 標記為尚未實作 |
| — | `create_case_rh_portal` | 目前被 policy 封鎖 |
| — | 實際 Case PoC 驗證 | 需 Red Hat OAuth + 有效 `case_id` |

---

## Architecture Debt（記錄、未修）

| 項目 | 說明 | 建議處理時機 |
|------|------|--------------|
| runtime bootstrap 在 `main.py` | MCPRegistry / WorkflowDeps 組裝仍在入口 | 可選；Sprint 4 前評估 |
| `analysis_prefilled` 雙路徑 | poll 先分析、graph `analyze` 常 skip | 設計如此；可選未來簡化 |
| `comment_analyzer` facade | 向後相容薄包裝 | 測試遷移後可移除 |
| 零散 `deps.policy` 呼叫 | collection / compose 仍直接用 policy | 可選收斂 |
| Connector 未抽象 | Case 讀寫與 poll 耦合 | **Sprint 4** |

---

## 本機環境備註

| 項目 | 值 |
|------|-----|
| Python | 3.11+ |
| 測試 Case ID | 使用 `tests/safe_test_data.py` 或 config 範例 `01234567` |
| MCP OAuth | 根目錄 `agent_config.json` + 首次 `make check` |
| 回歸驗證 | `python3 main.py --case-id=04444508`（需 `.env` + OAuth） |

---

## 變更紀錄

### 2026-07-08 — Sprint 3：Decision Engine

**做了什麼：**
- 新增 `core/decision/`（`models`、`engine`）
- `DecisionEngine.evaluate_policy()` / `evaluate_approval()` 委派至 `mcp_policy`、`approval`
- `workflow/graph.py` `policy` 與核准閘門改經 `DecisionEngine`
- `audit_trail.record_decision()` 記錄決策
- 更新 `docs/architecture/04-module-map.md`
- 新增 `tests/test_decision_engine.py`

**驗證：**
- [x] `make test`（144 OK）
- [x] `make policy-dump` 輸出與 sprint 前一致
- [ ] `python3 main.py --case-id=04444508`（需本機 OAuth / API key，由開發者執行）

**留給下一個 session：**
- 開始 Sprint 4（Connector 抽象）前需架構批准

### 2026-07-08 — Sprint 2：Understanding 邊界

**做了什麼：**
- 新增 `core/understanding/`（`models`、`action_inference`、`semantic`、`service`）
- `UnderstandingService` 作為單一入口；`CommentAnalyzer` 改為向後相容 facade
- `main.py`、`workflow/runner.py`、`workflow/graph.py` 改呼叫 `UnderstandingService`
- 更新 `docs/architecture/04-module-map.md`
- 新增 `tests/test_understanding_action_inference.py`、`tests/test_understanding_service.py`

**驗證：**
- [x] `make test`（140 OK）

### 2026-07-07 — Sprint 1：Workflow Engine 邊界

**做了什麼：**
- 新增 `workflow/runner.py`（poll 週期 helper + `process_poll_cycle`）
- `main.py` 精簡為 CLI、一次性指令、runtime 組裝、poll loop 啟動
- 更新 `docs/architecture/04-module-map.md`
- 新增 `tests/test_workflow_runner.py`

**驗證：**
- [x] `make test`（135 OK）

### 2026-07-08 — 修復 `--health` CLI import

**做了什麼：**
- `main.py` 補上 `from core.observability import build_health_report, format_health_text`

**驗證：**
- [x] `python3 main.py --health` 正常輸出
- [x] `make test`（135 OK）

### 2026-06-27 — 建立 Harness Engineering 協作檔

**做了什麼：**
- 新增 AGENTS.md、PROGRESS.md、Makefile、init.sh
- 新增 docs/ARCHITECTURE.md、docs/CONSTRAINTS.md

**驗證：**
- [x] make test（129 OK）
