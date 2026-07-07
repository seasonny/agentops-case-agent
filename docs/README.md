# Documentation

> **從這裡開始。** 本頁是 repository 文件的入口與地圖。

---

## 五分鐘導覽

這個 repository 是 **Enterprise AI Agent Reference** 的第一個參考實作：**Case Agent**（自動協助 Red Hat Support Case）。

| 你是誰 | 先讀什麼 | 然後讀什麼 |
|--------|----------|------------|
| **新貢獻者** | 本頁 → [architecture/00-manifesto.md](architecture/00-manifesto.md) | [architecture/04-module-map.md](architecture/04-module-map.md) |
| **要改程式的人** | [operations/constraints.md](operations/constraints.md) | [guides/developer.md](guides/developer.md) |
| **要配政策的人** | [operations/policy.md](operations/policy.md) | [operations/enterprise.md](operations/enterprise.md) |
| **要接 MCP 的人** | [guides/mcp-providers.md](guides/mcp-providers.md) | [contracts/](contracts/) |
| **AI Agent（Cursor）** | [../AGENTS.md](../AGENTS.md) | [operations/constraints.md](operations/constraints.md) |

**安裝與執行**（非文件職責）→ [../README.md](../README.md)

---

## 文件分類

### Architecture — 架構參考（概念層）

回答：**為什麼存在、原則是什麼、目標架構長什麼樣、怎麼演進。**

技術無關。不描述 Python、LangGraph 或 MCP 實作。

| 文件 | 回答的問題 | 讀者 |
|------|------------|------|
| [architecture/00-manifesto.md](architecture/00-manifesto.md) | 為什麼做這個專案？ | 所有人 |
| [architecture/01-principles.md](architecture/01-principles.md) | 設計原則是什麼？ | 架構師、貢獻者 |
| [architecture/02-reference-architecture.md](architecture/02-reference-architecture.md) | 概念架構元件與職責？ | 架構師、貢獻者 |
| [architecture/03-evolution-roadmap.md](architecture/03-evolution-roadmap.md) | 長期演進策略？ | 架構師、維護者 |
| [architecture/04-module-map.md](architecture/04-module-map.md) | 程式碼模組擁有什麼？ | 貢獻者 |
| [architecture/05-vocabulary.md](architecture/05-vocabulary.md) | 架構術語是什麼意思？ | 所有人 |
| [architecture/06-architecture-alignment-plan.md](architecture/06-architecture-alignment-plan.md) | 如何漸進對齊架構？ | 架構師、維護者 |

**架構層的單一來源：** `architecture/02-reference-architecture.md`（概念）+ `architecture/01-principles.md`（原則）

---

### Guides — 實作指南（程式層）

回答：**怎麼擴充、除錯、整合 MCP。**

| 文件 | 回答的問題 | 讀者 |
|------|------------|------|
| [guides/developer.md](guides/developer.md) | 觸發、workflow、guardrail、擴充、除錯？ | 開發者 |
| [guides/mcp-providers.md](guides/mcp-providers.md) | 怎麼加 MCP provider？ | 整合工程師 |

---

### Operations — 運維參考（操作層）

回答：**怎麼安全地配置、部署、審計。**

| 文件 | 回答的問題 | 讀者 |
|------|------------|------|
| [operations/constraints.md](operations/constraints.md) | 改碼時哪些紅線不能碰？ | 開發者、AI Agent |
| [operations/policy.md](operations/policy.md) | 怎麼配 `policy.yaml`？ | SRE、客戶、資安 |
| [operations/enterprise.md](operations/enterprise.md) | 怎麼部署 production？ | SRE、平台工程師 |

**政策操作的單一來源：** `operations/policy.md`

**改碼紅線的單一來源：** `operations/constraints.md`

---

### Contracts — 整合契約（跨團隊層）

回答：**MCP Server 與 Agent 之間的 API 契約是什麼？**

| 文件 | 回答的問題 | 讀者 |
|------|------------|------|
| [contracts/case-api.md](contracts/case-api.md) | Case Portal MCP 回傳什麼 JSON？ | MCP 團隊、整合工程師 |
| [contracts/exec-mcp.md](contracts/exec-mcp.md) | Exec MCP 的 argv 契約？ | MCP 實作者、客戶 |

---

### AI Collaboration — AI 協作指引

| 文件 | 回答的問題 | 讀者 |
|------|------------|------|
| [../AGENTS.md](../AGENTS.md) | AI session 怎麼協作？ | Cursor / AI Agent |
| [.ai/working-agreement.md](.ai/working-agreement.md) | 架構師角色與工作方式？ | AI Agent |
| [.ai/definition-of-done.md](.ai/definition-of-done.md) | 變更完成的品質標準？ | AI Agent、貢獻者 |
| [.ai/project-context.md](.ai/project-context.md) | 專案脈絡摘要？ | AI Agent |

---

### Archive — 歷史文件

保留供參考，**不是**技術真相來源。

| 文件 | 說明 |
|------|------|
| [archive/pitch.md](archive/pitch.md) | 客戶 PoC 電梯簡報（Phase 編號已過時） |
| [archive/documentation-consolidation-review.md](archive/documentation-consolidation-review.md) | 2026-07 文件整併審查報告 |

---

## 建議閱讀順序

### 路徑 A — 我想理解這個專案（貢獻者）

```
docs/README.md（本頁）
  → architecture/00-manifesto.md
  → architecture/01-principles.md
  → architecture/02-reference-architecture.md
  → architecture/04-module-map.md
  → architecture/05-vocabulary.md
  → operations/constraints.md
  → guides/developer.md
```

### 路徑 B — 我要部署到 production（SRE）

```
../README.md（安裝）
  → operations/policy.md
  → operations/enterprise.md
  → operations/constraints.md
```

### 路徑 C — 我要實作 MCP Server（整合）

```
contracts/case-api.md  或  contracts/exec-mcp.md
  → guides/mcp-providers.md
  → operations/policy.md
```

### 路徑 D — 我要規劃架構演進（架構師）

```
architecture/02-reference-architecture.md
  → architecture/03-evolution-roadmap.md
  → architecture/06-architecture-alignment-plan.md
  → architecture/04-module-map.md
```

---

## 單一來源速查

| 問題 | 去哪裡 |
|------|--------|
| 為什麼做這個專案？ | [architecture/00-manifesto.md](architecture/00-manifesto.md) |
| 設計原則？ | [architecture/01-principles.md](architecture/01-principles.md) |
| 概念架構？ | [architecture/02-reference-architecture.md](architecture/02-reference-architecture.md) |
| 模組責任？ | [architecture/04-module-map.md](architecture/04-module-map.md) |
| 術語定義？ | [architecture/05-vocabulary.md](architecture/05-vocabulary.md) |
| 演進計畫？ | [architecture/06-architecture-alignment-plan.md](architecture/06-architecture-alignment-plan.md) |
| 改碼紅線？ | [operations/constraints.md](operations/constraints.md) |
| 配 policy.yaml？ | [operations/policy.md](operations/policy.md) |
| 部署 production？ | [operations/enterprise.md](operations/enterprise.md) |
| 擴充 / 除錯？ | [guides/developer.md](guides/developer.md) |
| 加 MCP provider？ | [guides/mcp-providers.md](guides/mcp-providers.md) |
| Case API 契約？ | [contracts/case-api.md](contracts/case-api.md) |
| Exec MCP 契約？ | [contracts/exec-mcp.md](contracts/exec-mcp.md) |
| 安裝與執行？ | [../README.md](../README.md) |
| 當前進度？ | [../PROGRESS.md](../PROGRESS.md) |
| AI 協作？ | [../AGENTS.md](../AGENTS.md) |

---

## 目錄結構

```
docs/
├── README.md                 ← 你在這裡
├── architecture/             # 架構參考（概念層）
├── guides/                   # 實作指南
├── operations/               # 運維與政策
├── contracts/                # MCP 整合契約
├── archive/                  # 歷史文件
└── .ai/                      # AI 協作指引
```

根目錄的 `docs/*.md` 舊路徑保留為 **redirect stub**，避免書籤與外部連結失效。
