# Bootstrap Prompt

| | |
|---|---|
| **Purpose** | 所有 AI coding assistant 共用的標準啟動提示 |
| **Audience** | Cursor、ChatGPT、Claude Code、Codex 等 |
| **Source of truth** | Repository 文件與程式碼 — **不是**本提示 |

本檔案是 **boot loader**。不教架構；只指示 AI 從 repository 自行學習。

---

## 使用方式

將下方 **Prompt** 區塊整段貼到新 session 的第一則訊息。  
若 assistant 支援 `@` 或檔案引用，可附加 `docs/README.md`。

---

## Prompt

```
You are working in the AgentOps Case Agent repository.

Before doing anything:
1. Open and follow docs/README.md — the single entry point and reading order.
2. Learn architecture, constraints, and collaboration rules from the repository docs — do not assume or invent them.
3. Read PROGRESS.md for current state.
4. Do not modify code until you have completed the required reading steps in docs/README.md.

The repository is the source of truth. Ask only if the docs are unclear.

My task:
[PASTE YOUR TASK HERE]
```

---

## 備註

- 將 `[PASTE YOUR TASK HERE]` 替換為實際任務。
- 若 session 已載入 `AGENTS.md`（如 Cursor），仍應從 `docs/README.md` 開始，依閱讀順序執行。
- 不要在本提示中追加架構說明 — 變更應發生在 repository 文件，而非 bootstrap prompt。
