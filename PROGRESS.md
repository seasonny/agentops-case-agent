# 專案進度（AI 交接用）

> **給 Cursor / AI Agent：** 每次完成任務後更新本檔。新 session 開始時先讀這裡，再讀 [AGENTS.md](AGENTS.md)。

最後更新：**2026-06-27**

---

## 當前狀態

| 項目 | 狀態 |
|------|------|
| 產品階段 | **PoC / 內部驗證**（Initial commit 已就緒） |
| 核心流程 | 輪詢 → 觸發 → LangGraph workflow → MCP 執行 → 回覆 + guardrail |
| 測試 | `make test` — 129 tests OK |
| Harness 協作 | **剛建立** AGENTS.md、PROGRESS.md、Makefile、init.sh、docs/ARCHITECTURE.md、docs/CONSTRAINTS.md |

---

## 最近完成

- [x] 初始 repo：Case Agent 完整 PoC（workflow、policy、guardrail、enterprise hooks）
- [x] 文件：README、DEVELOPER、POLICY、MCP 契約等
- [x] Harness Engineering 協作檔（本輪）

---

## 進行中

_（目前無明確進行中任務 — 由下一個 session 填入）_

---

## 待辦 / 已知缺口

| 優先 | 項目 | 備註 |
|------|------|------|
| — | Outage 自動開案 | README / DEVELOPER 標記為尚未實作 |
| — | `create_case_rh_portal` | 目前被 policy 封鎖 |
| — | 實際 Case PoC 驗證 | 需 Red Hat OAuth + 有效 `case_id` |

---

## 本機環境備註

_（由開發者 / Agent 填入，勿寫入 secrets）_

| 項目 | 值 |
|------|-----|
| Python | 3.11+ |
| 測試 Case ID | 使用 `tests/safe_test_data.py` 或 config 範例 `01234567` |
| MCP OAuth | 根目錄 `agent_config.json` + 首次 `make check` |

---

## Session 交接模板

完成一輪工作後，複製以下區塊並更新：

```markdown
### YYYY-MM-DD — [簡短標題]

**做了什麼：**
- ...

**驗證：**
- [ ] make test
- [ ] make check（若動到 MCP/設定）

**留給下一個 session：**
- ...
```

---

## 變更紀錄

### 2026-06-27 — 建立 Harness Engineering 協作檔

**做了什麼：**
- 新增 AGENTS.md、PROGRESS.md、Makefile、init.sh
- 新增 docs/ARCHITECTURE.md、docs/CONSTRAINTS.md

**驗證：**
- [x] make test（129 OK）

**留給下一個 session：**
- 依實際開發任務更新「進行中」與「待辦」
- 若新增 Cursor Rules，可放在 `.cursor/rules/`（目前 gitignore）
