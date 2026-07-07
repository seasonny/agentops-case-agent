> **ARCHIVED** — 2026-07 文件整併審查報告。執行結果見 [docs/README.md](../README.md)。

# Documentation Consolidation Review

> **目的：** 在 [00-manifesto.md](00-manifesto.md)–[06-architecture-alignment-plan.md](06-architecture-alignment-plan.md) 成為架構基礎後，審查既有文件的去留。  
> **原則：** 建立單一真相來源（single source of truth），保留有價值的獨特知識，不遺失操作與契約細節。  
> **本文件僅為審查報告，不修改任何既有檔案。**

---

## 執行摘要

### 建議的文件層級（目標狀態）

| 層級 | 角色 | 文件 |
|------|------|------|
| **L0 — 哲學與架構** | 為什麼、是什麼、往哪走 | `00`–`06`（新基礎） |
| **L1 — 操作與約束** | 怎麼安全地跑、改、部署 | `CONSTRAINTS.md`、`POLICY.md`、`ENTERPRISE.md` |
| **L2 — 實作手冊** | 怎麼擴充、除錯、整合 | `DEVELOPER.md`（精簡後）、`MCP_PROVIDERS.md`、MCP 契約 |
| **L3 — 對外敘事** | 客戶 / workshop 簡報 | `PITCH.md`（需更新或歸檔） |
| **L4 — 入口導覽** | 冷啟動與快速連結 | `README.md`、`AGENTS.md`（需更新連結，不在本次審查範圍） |

### 審查結果一覽

| 文件 | 建議 |
|------|------|
| `ARCHITECTURE.md` | **MERGE** |
| `CONSTRAINTS.md` | **KEEP** |
| `DEVELOPER.md` | **SPLIT** |
| `ENTERPRISE.md` | **KEEP** |
| `MCP_PROVIDERS.md` | **KEEP** |
| `PITCH.md` | **ARCHIVE** |
| `POLICY.md` | **KEEP** |
| `mcp_case_api_integration.md` | **KEEP** |
| `mcp_exec_contract.md` | **KEEP** |

**無 DELETE 建議。** 所有文件均含值得保留的知識，或具歷史／對外價值。

---

## 逐份審查

---

### `ARCHITECTURE.md`

#### 1. Primary purpose

AI / 開發者**冷啟動速覽**：以實作導向方式說明 Case Agent 的資料流、目錄結構、設定載入、workflow 節點、MCP provider 與執行時產物。定位是「5 分鐘看懂 repo 怎麼跑」。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [04-module-map.md](04-module-map.md) | 目錄結構、模組職責、workflow 角色、設定與 runtime 產物 |
| [02-reference-architecture.md](02-reference-architecture.md) | 高層資料流（但抽象層級不同） |
| [05-vocabulary.md](05-vocabulary.md) | Workflow Engine、Tool Provider 等概念（ARCHITECTURE 用實作名稱描述） |
| [06-architecture-alignment-plan.md](06-architecture-alignment-plan.md) | `main.py` 職責過廣等備註，與 ARCHITECTURE 的「單一入口」敘述呼應 |

#### 3. Unique knowledge worth preserving

- **設定載入順序**的精簡一覽（含根目錄 `agent_config.json` vs `config/agent_config.json` 區分）
- **Workflow 節點表**（analyze → policy → execute …）與 `analysis_prefilled` 行為說明
- **實作級 mermaid 圖**（LangGraph、MCP Registry、具體 provider 名稱）
- **延伸閱讀索引**（連結至 DEVELOPER、POLICY、契約文件）

#### 4. Conflicting architectural concepts

| 衝突 | 說明 |
|------|------|
| 架構 vs 實作混雜 | 標題為「架構速覽」，內容綁定 LangGraph、Gemini、具體檔名，與 [02-reference-architecture.md](02-reference-architecture.md) 的產品無關、概念穩定原則不一致 |
| 元件命名 | 使用 `policy` 節點、MCP Registry，未使用 Understanding / Decision Engine / Connector 詞彙 |
| 輪詢中心 | 資料流暗示 poll 驅動，與 [02-reference-architecture.md](02-reference-architecture.md) 的 event-driven 敘事不完全對齊（實作現況如此，但文件未區分「現況」與「目標」） |

無**原則性**衝突（如「LLM 決定安全」），主要是**抽象層級與詞彙**與新基礎不一致。

#### 5. Recommendation: **MERGE**

**Destination：** [04-module-map.md](04-module-map.md)

**應移入的章節：**

| `ARCHITECTURE.md` 章節 | 移入 `04-module-map.md` 的位置 |
|------------------------|-------------------------------|
| 設定載入順序 | 擴充現有 `config/` 小節，或新增「Operational Quick Reference」附錄 |
| Workflow 節點（`workflow/graph.py`） | 擴充 `workflow/` 小節：節點表 + `analysis_prefilled` 說明 |
| MCP Providers 表 | 擴充 `bridges/` 小節，或附錄「Default Provider Stack」 |
| 狀態與報告 | 併入現有「執行時產物」小節（已有部分內容） |
| 系統概覽 mermaid | 附錄「Implementation Diagram」（標明為**現況實作**，非參考架構圖） |
| 目錄結構 | **不重複移入** — `04-module-map.md` 已更完整；合併後刪除 ARCHITECTURE 中的樹狀圖 |
| 延伸閱讀表 | 分散至 `04` 文末與各新文件交叉連結 |

**合併後 `ARCHITECTURE.md` 的處置：** 改為 **≤20 行的 redirect stub**，指向 `04-module-map.md` 與 `00`–`06`，避免 `AGENTS.md` 等既有連結失效。此為後續文件工作，不在本審查執行。

---

### `CONSTRAINTS.md`

#### 1. Primary purpose

**AI Agent 與開發者的硬約束清單**：改碼時不可違反的資安、治理、測試與協作規則。定位是「紅線」，不是教學文件。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [01-principles.md](01-principles.md) | Policy over Prompt、Human by Exception、確定性規則 |
| [05-vocabulary.md](05-vocabulary.md) | Policy、Guardrail、Audit 概念 |
| [docs/.ai/definition-of-done.md](.ai/definition-of-done.md) | 變更品質標準、不 over-engineer |
| [POLICY.md](POLICY.md) | Profile 速查（§7） |

#### 3. Unique knowledge worth preserving

- **模組級紅線對照表**（哪個安全領域對應哪個 `core/` 模組）
- **禁止 commit / 測試資料 / redaction** 的具體規則
- **MCP 執行邊界**（不 subprocess、`create_case_rh_portal` 封鎖等）
- **AI 協作行為約束**（最小 diff、不擅自 commit、不擅自加文件）
- **驗證命令對照**（`make test`、`policy-dump`）

#### 4. Conflicting architectural concepts

| 衝突 | 說明 |
|------|------|
| 模組邊界描述 | §6 寫死 `core/` / `bridges/` / `workflow/` 三分法；[06-architecture-alignment-plan.md](06-architecture-alignment-plan.md) 規劃 `understanding/`、`domain/`、`decision_engine` — 演進後需更新 CONSTRAINTS，但目前非錯誤 |
| Policy 節點 vs Decision Engine | 將 `mcp_policy` 列為決策模組，與目標 Decision Engine 概念尚未對齊 — **術語滯後**，非原則衝突 |

#### 5. Recommendation: **KEEP**

**理由：** 這是**可執行的約束清單**，不是架構哲學。新文件定義「應然」；CONSTRAINTS 定義「改碼時不得做什麼」。兩者互補。

**建議後續（非本次）：** 在文件頂部加入「架構詞彙見 [05-vocabulary.md](05-vocabulary.md)」；Sprint 3 完成後更新模組對照表中的 Decision Engine 名稱。

---

### `DEVELOPER.md`

#### 1. Primary purpose

**開發者深度手冊**：觸發規則、workflow 行為、L0–L5 Guardrail、policy 編譯流程、擴充指南、日誌事件、常見問題。定位是「如何改對、如何除錯」。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [04-module-map.md](04-module-map.md) | 專案結構、模組職責、MCP provider、workflow 概覽 |
| [01-principles.md](01-principles.md) | 開頭「設計原則」三欄表（程式 vs LLM vs MCP） |
| [05-vocabulary.md](05-vocabulary.md) | Guardrail、Policy、Understanding 相關行為描述 |
| [POLICY.md](POLICY.md) | MCP Policy、profile/mode、shell 路由 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架構圖、設定載入、workflow 節點 |
| [CONSTRAINTS.md](CONSTRAINTS.md) | 安全與機敏資料章節 |

#### 3. Unique knowledge worth preserving

- **L1/L2 觸發規則**完整說明（production vs demo、`[SE]` 前綴、`require_explicit_request_in_demo`）
- **L0–L5 Guardrail 對照表**（對外敘事與模組映射）
- **Workflow investigate loop** 現況描述、`action_type` 行為表
- **防無窮迴圈**機制（cooldown、loop guard、handled keys）
- **結構化日誌 event 表**
- **擴充指南**（改哪個 prompt、policy、graph）
- **常見開發問題 FAQ**（`comment_skipped` reason、Hydra JSON）
- **MCP 工具速查表**

#### 4. Conflicting architectural concepts

| 衝突 | 說明 |
|------|------|
| 「設計原則」表 | 與 [01-principles.md](01-principles.md) 層級不同（實作分工 vs 企業原則），並存可接受，但易造成「有兩套原則」印象 |
| `policy` 節點 = Guardrail | [05-vocabulary.md](05-vocabulary.md) 區分 Policy（組織規則）與 Guardrail（安全底線）；DEVELOPER 將 workflow `policy` 節點標為 Guardrail — **術語需對齊** |
| 引用 `note.md` | 外部心智模型文件，不在新文件體系內；連結可能斷裂或與 00-manifesto 敘事重疊 |

#### 5. Recommendation: **SPLIT**

**保留於 `DEVELOPER.md`（L2 實作手冊）：**

| 章節 | 理由 |
|------|------|
| 觸發與角色（L1 + L2） | 操作細節，無替代文件 |
| Workflow 節點行為、investigate loop、`action_type` | 實作行為規格 |
| 三層觸發 + 五層 Guardrail | 對外與對內 guardrail 敘事核心 |
| 回覆防偽、Shell 診斷路由 | 實作行為說明 |
| 防無窮迴圈 | 運維參數 |
| 日誌 event 表 | 除錯必備 |
| 擴充指南 | 貢獻者入口 |
| 常見開發問題 | FAQ |
| MCP 工具速查 | 開發參考 |

**移出或改為連結（不重複維護）：**

| 章節 | Destination | 處置 |
|------|-------------|------|
| 開頭「設計原則」表 | [01-principles.md](01-principles.md) + [05-vocabulary.md](05-vocabulary.md) | 改為 2–3 句 + 連結 |
| 「架構」mermaid + MCP Providers 表 | [04-module-map.md](04-module-map.md)（MERGE 後） | 刪除重複，留連結 |
| 設定載入順序 + 環境變數表 | [04-module-map.md](04-module-map.md) 附錄或 README | 刪除重複，留連結 |
| 專案結構樹 | [04-module-map.md](04-module-map.md) | 刪除 |
| MCP Policy 編譯流程圖 + profile 說明 | [POLICY.md](POLICY.md) | 精簡為「見 POLICY.md」 |
| 安全與機敏資料 | [CONSTRAINTS.md](CONSTRAINTS.md) | 精簡為連結 |

**Split 後 `DEVELOPER.md` 的定位：** 「Case Agent 實作與除錯手冊」，不再自稱架構文件。

---

### `ENTERPRISE.md`

#### 1. Primary purpose

**Enterprise 部署與運維指南**：production policy 建議、audit trail、outage webhook、人工核准、secrets 注入、health check、多租戶、上線 checklist。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [05-vocabulary.md](05-vocabulary.md) | Audit、Human Escalation、Policy |
| [01-principles.md](01-principles.md) | Human by Exception、Governance |
| [POLICY.md](POLICY.md) | `enterprise` profile + `allowlist` |
| [04-module-map.md](04-module-map.md) | `enterprise.py`、`approval.py`、`observability.py` 模組說明 |

#### 3. Unique knowledge worth preserving

- **可複製的 JSON / YAML 設定範例**
- **CLI 命令**（`--audit-report`、`--approve`、`--health`）
- **Webhook 事件類型**與 outage 輪詢行為
- **Approval 流程**三步驟與 fingerprint 機制
- **Secrets 掛載路徑**與 K8s 範例
- **Production 上線 Checklist**（7 步）
- **多租戶輕量模型**（一團隊一實例）

#### 4. Conflicting architectural concepts

無實質衝突。ENTERPRISE 描述**已實作的 Phase 2 企業能力**，與 [03-evolution-roadmap.md](03-evolution-roadmap.md) Phase 3（Decision Engine）為不同維度 — 可並存。

#### 5. Recommendation: **KEEP**

**理由：** 獨特的**部署與運維知識**，新文件體系未涵蓋操作層細節。屬 L1 操作文件。

**建議後續：** 在開頭加入「架構背景見 [02-reference-architecture.md](02-reference-architecture.md)；詞彙見 [05-vocabulary.md](05-vocabulary.md)」。

---

### `MCP_PROVIDERS.md`

#### 1. Primary purpose

**Tool Provider 擴充指南**：如何新增 MCP provider、合併 `local.json`、註冊 policy capability、非 OCP 環境建議、SSH 跳板機契約、驗證步驟。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [05-vocabulary.md](05-vocabulary.md) | Tool Provider、Integration、Capability |
| [04-module-map.md](04-module-map.md) | `bridges/mcp_*`、`mcp_discovery` |
| [DEVELOPER.md](DEVELOPER.md) | MCP Providers 章節 |
| [mcp_exec_contract.md](mcp_exec_contract.md) | exec provider、tool_map |

#### 3. Unique knowledge worth preserving

- **「Agent 薄、MCP 厚」**擴充心智模型（與原則一致）
- **`config/mcp_providers/*.example.json` 使用方式**
- **新增 capability 到 `policy_capability_map.yaml` 的步驟**
- **非 OCP / 純 RHEL / 無 K8s 場景建議**
- **SSH MCP 與 `tool_map` 映射範例**

#### 4. Conflicting architectural concepts

無衝突。與 [05-vocabulary.md](05-vocabulary.md) Tool Provider 定義一致。

#### 5. Recommendation: **KEEP**

**理由：** 聚焦**整合擴充**的操作指南，內容比 module map 更具體，比 DEVELOPER 更專注。屬 L2 整合手冊。

**建議後續：** DEVELOPER 的 MCP 章節改為連結本文件；[06-architecture-alignment-plan.md](06-architecture-alignment-plan.md) Sprint 4 完成後更新「Connector vs Tool Provider」交叉連結。

---

### `PITCH.md`

#### 1. Primary purpose

**對內 / 對客戶 PoC 電梯簡報**（約 10 張 slide）：問題陳述、產品定位、Guardrailed ReAct 敘事、與 Cursor 對比、PoC 成功指標、下一步建議。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [00-manifesto.md](00-manifesto.md) | 信任優於自動化、非 chatbot、企業採用 |
| [01-principles.md](01-principles.md) | Guardrail-first、LLM 不做閘門 |
| [03-evolution-roadmap.md](03-evolution-roadmap.md) | 路線圖（但 Phase 編號不同） |
| [DEVELOPER.md](DEVELOPER.md) | L0–L5 Guardrail 敘事 |

#### 3. Unique knowledge worth preserving

- **Slide 格式**的客戶溝通敘事
- **Outage 場景**問題陳述（業務動機）
- **與 Cursor / Coding Agent 對比表**
- **PoC 成功指標**（回應時效、來回次數、漏跑率）
- **建議 PoC 範圍**（2 週、1 Case、SE 訪談）

#### 4. Conflicting architectural concepts

| 衝突 | 說明 |
|------|------|
| **Phase 編號** | Slide 9：「Phase 1 PoC / Phase 2 Enterprise」— 與 [03-evolution-roadmap.md](03-evolution-roadmap.md) 的 Phase 1（Architecture Understanding）… Phase 5（Workshop）**完全不同語意** |
| **產品定位** | 強調「Case Agent」與 Red Hat Support — 正確為 Reference Implementation，但未明確區分於 Reference Architecture |
| **路線圖時效** | 「Phase 2 Enterprise」描述的能力（audit、approval）**已實作** — 簡報內容可能過時 |

#### 5. Recommendation: **ARCHIVE**

**理由：**

- 架構與哲學敘事已由 `00`–`06` 取代，不應再作為技術真相來源
- Phase 編號與新路線圖衝突，繼續放在 `docs/` 主目錄易誤導貢獻者
- 仍具**對客戶簡報**價值，不應刪除

**歸檔方式（建議後續執行）：**

- 移至 `docs/archive/PITCH.md` 或在檔首加 **ARCHIVED — 僅供銷售參考，架構以 00–06 為準** 橫幅
- Slide 9 路線圖改連結 [03-evolution-roadmap.md](03-evolution-roadmap.md)
- PoC 成功指標與 Slide 10 下一步 — 待 Phase 5 Workshop 時擷取至新 `docs/workshop/` 教材

---

### `POLICY.md`

#### 1. Primary purpose

**安全政策操作手冊**（面向 SRE / 客戶 / 資安審計）：如何編輯 `policy.yaml`、profile/mode 心智模型、能力表、確定性路由、危險指令處理、設定範例、FAQ。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [01-principles.md](01-principles.md) | Policy over Prompt |
| [05-vocabulary.md](05-vocabulary.md) | Policy、Capability、Guardrail、Decision |
| [DEVELOPER.md](DEVELOPER.md) | Policy 編譯、mcp_policy |
| [CONSTRAINTS.md](CONSTRAINTS.md) | Profile 速查、確定性決策 |

#### 3. Unique knowledge worth preserving

- **30 秒快速開始**與客戶友善語氣
- **全流程 mermaid**（Support 留言 → 檢查鏈）
- **Capability 完整對照表**（含典型工具名 — 操作參考）
- **denylist / allowlist 心智模型圖**
- **確定性路由決策樹**（dig/ping → pods_exec vs exec_argv）
- **設定範例**（關閉 host_diag、enterprise allowlist、overrides）
- **混合指令** `dangerous_handling` 行為表
- **bundle_output / must-gather 協作路徑**說明
- **與 agent_config / guardrails / exec MCP 的關係表**

#### 4. Conflicting architectural concepts

| 衝突 | 說明 |
|------|------|
| Policy vs Guardrail 混用 | 流程圖步驟 H「回覆有捏造輸出」屬 Guardrail（[05-vocabulary.md](05-vocabulary.md)），但整體文件標題為 Policy — **術語可更精確**，非原則錯誤 |
| Capability = 政策單元 | 與 [05-vocabulary.md](05-vocabulary.md) 一致；文件中 capability 綁定具體工具名，屬 Reference Implementation 層細節，可接受 |

#### 5. Recommendation: **KEEP**

**理由：** 這是 **`policy.yaml` 的權威操作文件**。新文件定義 Policy **概念**；POLICY.md 定義 Policy **怎麼配**。客戶與 workshop 仍需此文件。

**建議後續：** 開頭加入「概念定義見 [05-vocabulary.md](05-vocabulary.md) § Policy / Capability / Guardrail」；Sprint 3 後補充 Decision Engine 如何消費 policy 編譯結果。

---

### `mcp_case_api_integration.md`

#### 1. Primary purpose

**MCP Server 團隊與 Case Agent 之間的整合契約**：Red Hat Case Management API 對照、MCP 工具 ↔ REST 映射、Hydra JSON 回傳格式、角色映射、驗收清單。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [04-module-map.md](04-module-map.md) | `case_api_models.py`、`case_portal.py` 職責 |
| [05-vocabulary.md](05-vocabulary.md) | Connector、Integration |
| [06-architecture-alignment-plan.md](06-architecture-alignment-plan.md) | Sprint 4 Connector 演進 |

#### 3. Unique knowledge worth preserving

- **REST API 路徑**（含 `/v1/` vs 非 `v1` attachments 差異）
- **MCP 工具 Phase 1/2/3 優先級**
- **JSON 契約 §4**（comments、case、attachments、errors）
- **`createdByType` → role 映射表**（含待實測 enum）
- **Agent 端串接步驟與驗收清單**
- **Swagger / operationId 對照**

#### 4. Conflicting architectural concepts

無衝突。這是 **Integration 契約**，位於 Reference Implementation 的 Connector 層，與參考架構的 Product Agnostic 原則一致（契約針對 Red Hat Portal，架構不綁定）。

#### 5. Recommendation: **KEEP**

**理由：** 獨特的**跨團隊 API 契約**，無其他文件可替代。屬 L2 整合規格。

**建議後續：** Sprint 4 可選將路徑改為 `docs/contracts/mcp_case_api_integration.md`；更新 [04-module-map.md](04-module-map.md) 連結。非必須。

---

### `mcp_exec_contract.md`

#### 1. Primary purpose

**Exec Tool Provider 整合契約**：Agent 與 exec MCP 的分工、argv 輸入輸出格式、policy 單一來源原則、exec MCP 硬底線、路由原則、`mcp-shell-server` 安裝與 fork 建議。

#### 2. Overlap with new documents

| 新文件 | 重疊內容 |
|--------|----------|
| [05-vocabulary.md](05-vocabulary.md) | Tool Provider、Policy、Guardrail |
| [01-principles.md](01-principles.md) | 確定性規則、Policy over Prompt |
| [CONSTRAINTS.md](CONSTRAINTS.md) | 不 subprocess、exec 邊界 |
| [POLICY.md](POLICY.md) | exec binaries、路由 |
| [MCP_PROVIDERS.md](MCP_PROVIDERS.md) | tool_map、provider 設定 |

#### 3. Unique knowledge worth preserving

- **三方分工表**（Agent / kubernetes-mcp / exec MCP）
- **argv schema**與禁止 shell 字串的明確規範
- **輸出格式 A/B**（純文字 vs exit_code 結構）
- **Exec MCP 硬底線**（timeout 上限、輸出上限、禁止 `sh -c`）
- **路由原則表**（Case / cluster / pods_exec / exec_argv）
- **mcp-shell-server 映射表**與企業 fork 流程
- **雙層防護**（MCP 層 vs Agent 層）說明

#### 4. Conflicting architectural concepts

無衝突。契約明確寫「policy 由 Agent 負責」，與 [01-principles.md](01-principles.md) 及 [05-vocabulary.md](05-vocabulary.md) 一致。

#### 5. Recommendation: **KEEP**

**理由：** 獨特的 **Tool Provider 實作契約**，供 MCP 實作者與企業客戶替換 exec 層時使用。

**建議後續：** 可與 `mcp_case_api_integration.md` 同置 `docs/contracts/`；在 [05-vocabulary.md](05-vocabulary.md) Tool Provider 章節加入連結。

---

## 跨文件議題

### 1. Phase 編號衝突

| 來源 | Phase 語意 |
|------|------------|
| [PITCH.md](PITCH.md) Slide 9 | Phase 1 = PoC；Phase 2 = Enterprise |
| [03-evolution-roadmap.md](03-evolution-roadmap.md) | Phase 1 = Architecture Understanding；… Phase 5 = Workshop |
| [DEVELOPER.md](DEVELOPER.md) | 「現況 Phase 3」指 workflow investigate loop（第三版 workflow，非 roadmap phase） |

**建議：** 以 [03-evolution-roadmap.md](03-evolution-roadmap.md) 為 **Phase 編號的單一來源**。其他文件避免使用「Phase N」或明確標註語境（如「Workflow Phase 3」）。

### 2. Policy vs Guardrail 術語漂移

多份舊文件將 workflow `policy` 節點、grounding、出站掃描統稱為 guardrail 或 policy。  
[05-vocabulary.md](05-vocabulary.md) 已區分兩者。後續 SPLIT/MERGE 時應對齊詞彙，不需改變行為。

### 3. `AGENTS.md` 與 `README.md` 連結債務

`AGENTS.md` 冷啟動五問仍指向 `ARCHITECTURE.md` 為架構入口。ARCHITECTURE MERGE 後需更新為：

```
架構：docs/00-manifesto.md → 04-module-map.md
約束：docs/CONSTRAINTS.md
操作：docs/POLICY.md、docs/DEVELOPER.md
```

此為後續文件工作，列入 Phase 5 Workshop 或 MERGE 執行清單。

### 4. 契約文件分散

兩份 MCP 契約目前與架構文件同層。長期可選 `docs/contracts/` 子目錄，但不影響內容正確性 — **非緊急**。

---

## 建議的單一真相來源（SSOT）矩陣

| 問題 | 去哪裡找答案 |
|------|--------------|
| 為什麼做這個專案？ | [00-manifesto.md](00-manifesto.md) |
| 設計原則是什麼？ | [01-principles.md](01-principles.md) |
| 概念架構長什麼樣？ | [02-reference-architecture.md](02-reference-architecture.md) |
| 怎麼演進？ | [03-evolution-roadmap.md](03-evolution-roadmap.md) + [06-architecture-alignment-plan.md](06-architecture-alignment-plan.md) |
| 每個模組擁有什麼？ | [04-module-map.md](04-module-map.md) |
| 術語是什麼意思？ | [05-vocabulary.md](05-vocabulary.md) |
| 改碼紅線？ | [CONSTRAINTS.md](CONSTRAINTS.md) |
| 怎麼配 policy.yaml？ | [POLICY.md](POLICY.md) |
| 怎麼部署 production？ | [ENTERPRISE.md](ENTERPRISE.md) |
| 怎麼擴充 / 除錯？ | [DEVELOPER.md](DEVELOPER.md)（split 後） |
| 怎麼加 MCP provider？ | [MCP_PROVIDERS.md](MCP_PROVIDERS.md) |
| Case API 契約？ | [mcp_case_api_integration.md](mcp_case_api_integration.md) |
| Exec MCP 契約？ | [mcp_exec_contract.md](mcp_exec_contract.md) |
| 客戶簡報？ | `docs/archive/PITCH.md`（歸檔後） |

---

## 建議執行順序（僅文件工作）

以下對應 [03-evolution-roadmap.md](03-evolution-roadmap.md) Phase 5 的一部分，**不改程式**：

| 順序 | 動作 | 涉及文件 |
|------|------|----------|
| 1 | MERGE `ARCHITECTURE.md` → `04-module-map.md`；ARCHITECTURE 改 stub | ARCHITECTURE, 04 |
| 2 | SPLIT `DEVELOPER.md`；移除與 00–06 / POLICY / CONSTRAINTS 重複章節 | DEVELOPER |
| 3 | ARCHIVE `PITCH.md`；加橫幅與路線圖連結 | PITCH |
| 4 | 更新 `AGENTS.md`、`README.md` 文件索引 | AGENTS, README |
| 5 | 在 KEEP 文件開頭加入 SSOT 交叉連結 | CONSTRAINTS, POLICY, ENTERPRISE, MCP_PROVIDERS, 契約 |
| 6 | 可選：建立 `docs/contracts/` 並移動兩份 MCP 契約 | 契約文件 |

---

## 結論

新文件體系（`00`–`06`）應成為**架構與哲學的單一來源**。舊文件中：

- **無一份應 DELETE** — 均含獨特操作、契約或歷史價值
- **一份應 MERGE**（`ARCHITECTURE.md`）— 消除與 `04-module-map.md` 的重複
- **一份應 SPLIT**（`DEVELOPER.md`）— 分離架構敘事與實作手冊
- **一份應 ARCHIVE**（`PITCH.md`）— 避免過時 Phase 編號誤導技術讀者
- **六份應 KEEP** — 作為約束、政策、部署、整合、契約的權威來源

此 consolidation 不改變任何程式行為，僅釐清「讀哪一份才是對的答案」。
