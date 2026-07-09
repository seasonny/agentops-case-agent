# Documentation

> **Repository 唯一入口。** 人類貢獻者與 AI Assistant 都從本頁開始。  
> 在理解下方「建議閱讀順序」中的必要步驟前，**不要修改程式碼**。

---

## 這是什麼？

**Enterprise AI Agent Reference** 的第一個參考實作：**Case Agent**（自動協助 Red Hat Support Case）。

**安裝與執行**（非文件職責）→ [../README.md](../README.md)

---

## 建議閱讀順序

以下為 repository **唯一的**建議閱讀順序。依序閱讀；標有「依需要」的步驟可在任務需要時再讀。

### 第一階段 — 架構理解（所有人必讀）

| # | 文件 | 目的 |
|---|------|------|
| 1 | **本頁** `docs/README.md` | 文件地圖與閱讀順序 |
| 2 | [architecture/00-manifesto.md](architecture/00-manifesto.md) | 專案為什麼存在 |
| 3 | [architecture/01-principles.md](architecture/01-principles.md) | 設計原則 |
| 4 | [architecture/02-reference-architecture.md](architecture/02-reference-architecture.md) | 概念架構 |
| 5 | [architecture/04-module-map.md](architecture/04-module-map.md) | 模組責任 |
| 6 | [architecture/05-vocabulary.md](architecture/05-vocabulary.md) | 架構術語 |

### 第二階段 — AI 協作（AI Assistant 必讀）

> **AI Assistant：** 完成第一階段後，繼續閱讀 [.ai/README.md](.ai/README.md)（AI Collaboration Guide），並依該指南完成 `.ai/` 下的必讀文件。  
> **人類貢獻者**可跳過本階段。

| # | 文件 | 目的 |
|---|------|------|
| 7 | [.ai/README.md](.ai/README.md) | AI 協作指南（非獨立入口） |
| 8 | [.ai/project-context.md](.ai/project-context.md) | 專案脈絡 |
| 9 | [.ai/working-agreement.md](.ai/working-agreement.md) | 架構師角色與提案規則 |
| 10 | [.ai/engineering-method.md](.ai/engineering-method.md) | 人機分工與實作規則 |
| 11 | [.ai/definition-of-done.md](.ai/definition-of-done.md) | 完成標準 |
| 12 | [../AGENTS.md](../AGENTS.md) | Session 協作閉環與驗證 |

### 第三階段 — 實作前準備（改碼前必讀）

| # | 文件 | 目的 |
|---|------|------|
| 13 | [operations/constraints.md](operations/constraints.md) | 改碼紅線 |
| 14 | [../PROGRESS.md](../PROGRESS.md) | 當前進度與待辦 |

### 第四階段 — 依任務閱讀（依需要）

| 任務 | 文件 |
|------|------|
| Workshop / PoC 提案、敘事、邊界 | [guides/workshop.md](guides/workshop.md) |
| 改程式、除錯、擴充 | [guides/developer.md](guides/developer.md) |
| 配置 `policy.yaml` | [operations/policy.md](operations/policy.md) |
| Production 部署 | [operations/enterprise.md](operations/enterprise.md) |
| 人工核准 / HITL 治理 | [architecture/07-human-approval-governance.md](architecture/07-human-approval-governance.md) |
| 新增 MCP provider | [guides/mcp-providers.md](guides/mcp-providers.md) |
| Case API 契約 | [contracts/case-api.md](contracts/case-api.md) |
| Exec MCP 契約 | [contracts/exec-mcp.md](contracts/exec-mcp.md) |
| 架構演進規劃 | [architecture/03-evolution-roadmap.md](architecture/03-evolution-roadmap.md)、[architecture/06-architecture-alignment-plan.md](architecture/06-architecture-alignment-plan.md) |

---

## 文件分類

### Architecture — 架構參考（概念層）

技術無關。不描述 Python、LangGraph 或 MCP 實作。

| 文件 | 回答的問題 |
|------|------------|
| [architecture/00-manifesto.md](architecture/00-manifesto.md) | 為什麼做這個專案？ |
| [architecture/01-principles.md](architecture/01-principles.md) | 設計原則是什麼？ |
| [architecture/02-reference-architecture.md](architecture/02-reference-architecture.md) | 概念架構元件與職責？ |
| [architecture/03-evolution-roadmap.md](architecture/03-evolution-roadmap.md) | 長期演進策略？ |
| [architecture/04-module-map.md](architecture/04-module-map.md) | 程式碼模組擁有什麼？ |
| [architecture/05-vocabulary.md](architecture/05-vocabulary.md) | 架構術語是什麼意思？ |
| [architecture/06-architecture-alignment-plan.md](architecture/06-architecture-alignment-plan.md) | 如何漸進對齊架構？ |
| [architecture/07-human-approval-governance.md](architecture/07-human-approval-governance.md) | 人工核准與 Enterprise 治理？ |

**架構層 SSOT：** [02-reference-architecture.md](architecture/02-reference-architecture.md) + [01-principles.md](architecture/01-principles.md)

---

### Guides — 實作指南（程式層）

| 文件 | 回答的問題 |
|------|------------|
| [guides/workshop.md](guides/workshop.md) | Workshop 敘事、縱深防禦、PoC 邊界、寫死項目？ |
| [guides/developer.md](guides/developer.md) | 觸發、workflow、guardrail、擴充、除錯？ |
| [guides/mcp-providers.md](guides/mcp-providers.md) | 怎麼加 MCP provider？ |

---

### Operations — 運維參考（操作層）

| 文件 | 回答的問題 |
|------|------------|
| [operations/constraints.md](operations/constraints.md) | 改碼時哪些紅線不能碰？ |
| [operations/policy.md](operations/policy.md) | 怎麼配 `policy.yaml`？ |
| [operations/enterprise.md](operations/enterprise.md) | 怎麼部署 production？ |
| [architecture/07-human-approval-governance.md](architecture/07-human-approval-governance.md) | 人工核准 / HITL 怎麼設計？ |

**政策 SSOT：** [operations/policy.md](operations/policy.md) · **改碼紅線 SSOT：** [operations/constraints.md](operations/constraints.md)

---

### Contracts — 整合契約

| 文件 | 回答的問題 |
|------|------------|
| [contracts/case-api.md](contracts/case-api.md) | Case Portal MCP JSON 契約？ |
| [contracts/exec-mcp.md](contracts/exec-mcp.md) | Exec MCP argv 契約？ |

---

### AI Collaboration — AI 協作指引

| 文件 | 回答的問題 |
|------|------------|
| [.ai/README.md](.ai/README.md) | AI 協作指南（接續第一階段架構文件之後） |
| [.ai/project-context.md](.ai/project-context.md) | 專案脈絡摘要？ |
| [.ai/working-agreement.md](.ai/working-agreement.md) | 架構師角色與工作方式？ |
| [.ai/engineering-method.md](.ai/engineering-method.md) | 人與 AI 分工、實作規則？ |
| [.ai/definition-of-done.md](.ai/definition-of-done.md) | 變更完成的品質標準？ |
| [../AGENTS.md](../AGENTS.md) | Session 協作閉環？ |

---

### Archive — 歷史文件

| 文件 | 說明 |
|------|------|
| [archive/pitch.md](archive/pitch.md) | 客戶 PoC 簡報（非架構 SSOT） |
| [archive/documentation-consolidation-review.md](archive/documentation-consolidation-review.md) | 2026-07 文件整併審查報告 |

---

## 單一來源速查

| 問題 | 去哪裡 |
|------|--------|
| **從哪開始？** | **本頁** |
| 為什麼做這個專案？ | [architecture/00-manifesto.md](architecture/00-manifesto.md) |
| 設計原則？ | [architecture/01-principles.md](architecture/01-principles.md) |
| 概念架構？ | [architecture/02-reference-architecture.md](architecture/02-reference-architecture.md) |
| 模組責任？ | [architecture/04-module-map.md](architecture/04-module-map.md) |
| 術語定義？ | [architecture/05-vocabulary.md](architecture/05-vocabulary.md) |
| AI 協作指南？ | [.ai/README.md](.ai/README.md) |
| AI 工程方法？ | [.ai/engineering-method.md](.ai/engineering-method.md) |
| 改碼紅線？ | [operations/constraints.md](operations/constraints.md) |
| 配 policy.yaml？ | [operations/policy.md](operations/policy.md) |
| 人工核准 / HITL？ | [architecture/07-human-approval-governance.md](architecture/07-human-approval-governance.md) |
| Workshop / PoC？ | [guides/workshop.md](guides/workshop.md) |
| 擴充 / 除錯？ | [guides/developer.md](guides/developer.md) |
| 安裝與執行？ | [../README.md](../README.md) |
| 當前進度？ | [../PROGRESS.md](../PROGRESS.md) |

---

## 目錄結構

```
docs/
├── README.md                 ← 唯一入口（你在這裡）
├── architecture/
├── guides/
├── operations/
├── contracts/
├── archive/
└── .ai/                      # AI Collaboration Guide（非獨立入口）
```

根目錄 `docs/*.md` 舊路徑保留為 **redirect stub**。
