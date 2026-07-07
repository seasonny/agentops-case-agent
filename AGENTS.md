# AgentOps Case Agent — AI 協作指南

本檔案供 **Cursor / AI Agent** 在每次新 session 使用。目標：讓 Agent 在**不猜測**的前提下完成任務，並在結束時留下可交接的狀態。

> **從 [docs/README.md](docs/README.md) 開始**，依該頁「建議閱讀順序」執行。完成 architecture 第一階段後，繼續 [docs/.ai/README.md](docs/.ai/README.md)（AI Collaboration Guide）。

**在理解閱讀順序中的必要步驟前，不要修改程式碼。**

---

## 這是什麼？

**AgentOps Case Agent** 是與 Red Hat Support Case 協作的 AI 運維助手：

1. 輪詢 Case 留言 → 辨識 Support 請求
2. 經 MCP 執行診斷（`oc`、Pod log、dig/ping 等）
3. 撰寫繁中回覆 → 出站 guardrail → 發回 Case

**設計原則**（程式 vs LLM vs MCP）：

| 負責方 | 職責 |
|--------|------|
| **Agent 程式** | 觸發規則、MCP 政策、出站安全、防偽 |
| **LLM** | 理解留言、選工具、撰寫回覆 |
| **MCP Server** | 叢集 / Case API 操作 |

Agent **不在本機 subprocess 跑 shell**；本機 `dig`/`ping` 走 **exec MCP**（`mcp-shell-server`）。

---

## 冷啟動五問（Harness Core Workflow）

新 session 開始時，應能從 repo 直接回答：

| 問題 | 去哪找 |
|------|--------|
| 1. 這是什麼系統？ | 本檔 + [docs/README.md](docs/README.md) |
| 2. 專案怎麼組織？ | [docs/architecture/04-module-map.md](docs/architecture/04-module-map.md) |
| 3. 怎麼跑？ | `make init` → `make check` → `make dry-run`；詳見 [README.md](README.md) |
| 4. 怎麼驗證？ | `make test` + `make check`；見下方「驗證清單」 |
| 5. 現在進度？ | [PROGRESS.md](PROGRESS.md) |

若任一問題需要**猜測**，先補文件或問使用者，再動手改碼。

---

## 協作閉環（Harness Core Cycle）

每次被指派任務時，依序：

```
1. 讀 PROGRESS.md → 確認當前狀態與未完成項
2. 執行 make init（首次）或 make check（確認環境）
3. 實作 / 修 bug（小 diff、沿用既有慣例）
4. 驗證：make test && make check
5. 更新 PROGRESS.md（做了什麼、待辦、已知問題）
6. 僅在使用者明確要求時才 git commit
```

---

## 驗證清單

```bash
make test          # 129+ unittest，不需 LLM / MCP / Case
make check         # LLM key、MCP、Case 讀取（需 .env 與 OAuth）
make dry-run       # 試跑一輪，不發回覆
make policy-dump   # 輸出編譯後安全政策
```

改動範圍與建議驗證：

| 改動類型 | 最低驗證 |
|----------|----------|
| `core/`、`workflow/` | `make test` |
| `config/policy*` | `make test` + `make policy-dump` |
| MCP / 設定載入 | `make test` + `make check` |
| Prompt 文案 | `make test` + `make dry-run`（若可） |

---

## 必讀約束

改碼前請讀 [docs/operations/constraints.md](docs/operations/constraints.md)。重點：

- **不要**提交 `.env`、`config/local.json`、`agent_memory.json`、`reports/`
- **不要**在測試或 commit 中嵌入真實 Case ID、客戶內容、API Key
- 測試資料用 `tests/safe_test_data.py`
- 安全 / 觸發 / guardrail 邏輯用**確定性程式**實作，不要只靠 prompt
- 回覆須 **grounding**（`core/reply_grounding.py`），不可偽造 MCP 輸出

---

## 關鍵目錄

```
main.py              # CLI 入口
workflow/graph.py    # LangGraph workflow
core/                # 設定、觸發、policy、guardrail、LLM
bridges/             # MCP registry、Case portal
config/              # agent_config.json、policy.yaml、prompts
tests/               # unittest
docs/                # 架構、政策、MCP 契約
```

詳細架構：[docs/architecture/04-module-map.md](docs/architecture/04-module-map.md)  
開發者指南：[docs/guides/developer.md](docs/guides/developer.md)  
文件入口：[docs/README.md](docs/README.md)

---

## 編碼慣例

- Python 3.11+；沿用現有模組邊界（`core/` vs `bridges/` vs `workflow/`）
- **最小 diff**：只改任務相關檔案，不重構無關程式
- 新預設值放 `core/config.py` → `default_config()`；客戶可調項放 `config/agent_config.json`
- 註解只解釋非顯而易見的業務邏輯
- 回覆使用者用**繁體中文**（程式 / 變數名維持英文）

---

## 常用擴充入口

| 目標 | 檔案 |
|------|------|
| 調整 triage | `config/prompts/analyze_comment.txt` |
| 調整回覆語氣 | `config/prompts/compose_reply.txt` |
| 新增 MCP 能力 | `config/policy.yaml` + `policy_capability_map.yaml` |
| 新增 workflow 節點 | `workflow/graph.py` |
| 觸發 / 角色規則 | `core/trigger.py`、`core/participants.py` |

---

## 文件索引

完整文件地圖見 **[docs/README.md](../README.md)**。快速連結：

| 文件 | 用途 |
|------|------|
| [docs/README.md](docs/README.md) | **Repository 唯一文件入口** |
| [docs/.ai/README.md](docs/.ai/README.md) | AI Collaboration Guide（接續 architecture 之後） |
| [README.md](README.md) | 安裝、設定、使用者操作 |
| [PROGRESS.md](PROGRESS.md) | 當前進度與交接 |
| [docs/architecture/](docs/architecture/) | 架構參考（哲學、概念、模組、詞彙） |
| [docs/guides/developer.md](docs/guides/developer.md) | 實作、Guardrail、擴充、除錯 |
| [docs/operations/constraints.md](docs/operations/constraints.md) | 改碼紅線 |
| [docs/operations/policy.md](docs/operations/policy.md) | 安全政策 profile |
| [docs/operations/enterprise.md](docs/operations/enterprise.md) | Enterprise 部署 |
