# Vocabulary

| | |
|---|---|
| **Purpose** | 定義 repository 使用的架構語言與術語 |
| **Audience** | 所有人（文件、程式註解、workshop 應使用相同術語） |
| **Source of truth** | 本文件是**架構術語**的權威來源 |
| **Related** | [02-reference-architecture.md](02-reference-architecture.md)、[04-module-map.md](04-module-map.md) |

> 文件入口：[README.md](../README.md)

---

## 如何使用本詞彙表

- **術語名稱**（英文）為架構語言的正式用語，應在設計討論與文件中保持一致。
- **Owned by** 指哪個架構元件對該概念負有主要責任，不是指某個原始碼檔案。
- 若兩個術語看似重疊，請以本文件的定義為準，而非日常口語。

---

## 核心流程術語

### Event

| | |
|---|---|
| **Definition** | 觸發 Agent 行為的外部信號。例如：新工單、新留言、工具執行完成、人工回覆、逾時、workflow 恢復。 |
| **Why it exists** | Enterprise 營運是事件驅動的。Agent 應對明確的業務事件反應，而非無目的地持續運轉。 |
| **Owned by** | Connector（產生或接收事件）；Workflow Engine（消費事件並啟動處理） |
| **Related concepts** | Workflow、Connector、Workflow Engine、State |

---

### Workflow

| | |
|---|---|
| **Definition** | 為完成一項企業營運任務而編排的一系列步驟。包含理解輸入、做出決策、執行動作、產生回應，以及必要時等待人工介入。 |
| **Why it exists** | 企業工作本質是流程，不是單次對話。Workflow 是 Agent 的產品；對話只是介面。 |
| **Owned by** | Workflow Engine（編排）；Domain（定義業務步驟的語意） |
| **Related concepts** | Event、Workflow Engine、Domain、State、Decision |

---

### Workflow Engine

| | |
|---|---|
| **Definition** | 協調 workflow 執行的元件。負責接收事件、追蹤狀態、依序呼叫其他元件、支援長時間運行與中斷後恢復。 |
| **Why it exists** | 將「做什麼」與「怎麼編排」分離。編排邏輯不應與業務政策或外部系統細節混在一起。 |
| **Owned by** | Workflow Engine 本身（作為架構元件） |
| **Related concepts** | Event、Workflow、State、Understanding、Decision Engine、Tool Provider、Response |

> Workflow Engine **不擁有**業務政策。它編排決策與執行，但不定義組織規則。

---

## 認知與決策術語

### Understanding

| | |
|---|---|
| **Definition** | 解讀外部輸入的過程。辨識意圖、脈絡、建議動作與缺失資訊。產出結構化的理解結果，供後續決策使用。 |
| **Why it exists** | 企業輸入形式多樣（工單、郵件、訊息）。Agent 必須先理解「對方要什麼」，才能決定下一步。 |
| **Owned by** | Understanding 元件（架構層）；語意推理通常由模型輔助，但觸發與角色規則由確定性邏輯負責 |
| **Related concepts** | Event、Decision、Response、Domain |

> Understanding **不執行**工具，**不做**最終的組織決策（是否允許執行）。

---

### Decision

| | |
|---|---|
| **Definition** | 對「下一步應發生什麼」的判斷。包含：是否允許執行、是否需要人工介入、適用哪條政策、風險與信心是否可接受。 |
| **Why it exists** | 企業採用 AI 的前提是決策可預測、可解釋、可審計。每個動作都應能回答「為何允許或拒絕」。 |
| **Owned by** | Decision Engine |
| **Related concepts** | Decision Engine、Policy、Risk、Confidence、Human Escalation、Audit |

---

### Decision Engine

| | |
|---|---|
| **Definition** | 負責組織決策邏輯的元件。評估政策、衡量風險、判斷信心水準、決定是否允許執行、決定是否升級人工。 |
| **Why it exists** | 治理優於智力。決策邏輯必須集中、可測試、可審計，不能散落在提示詞或各處 heuristics 中。 |
| **Owned by** | Decision Engine 本身（作為架構元件） |
| **Related concepts** | Policy、Capability、Risk、Confidence、Human Escalation、Guardrail、Audit |

> Policy evaluation 是 Decision Engine 的一項能力，但 Decision Engine 的職責不限於政策檢查。

---

## 治理術語

### Policy

| | |
|---|---|
| **Definition** | 描述組織允許與禁止行為的外部化規則。以可版本化、可審計、可設定的資料形式存在，而非嵌入在提示詞或程式邏輯深處。 |
| **Why it exists** | Policy over Prompt。企業必須能自主定義、調整與審查 Agent 的行為邊界，而不依賴模型行為。 |
| **Owned by** | 組織（定義內容）；Decision Engine（評估與套用） |
| **Related concepts** | Capability、Risk、Decision Engine、Guardrail、Audit |

> Policy is data. Policy is not application logic.

---

### Capability

| | |
|---|---|
| **Definition** | 一組相關操作能力的邏輯分組。例如：讀取工單、寫入回覆、叢集唯讀查詢、執行診斷、上傳附件。政策通常以 capability 為單位開關，而非逐條指令列舉。 |
| **Why it exists** | 降低政策管理複雜度。管理者思考「允許哪類操作」，而非「允許哪一條 shell 指令」。 |
| **Owned by** | Policy（定義哪些 capability 啟用）；Decision Engine（依 capability 判斷是否允許） |
| **Related concepts** | Policy、Tool Provider、Integration、Risk |

---

### Risk

| | |
|---|---|
| **Definition** | 某項操作可能造成的營運、安全或業務衝擊的評估。風險可來自操作類型、目標環境、影響範圍或組織閾值。 |
| **Why it exists** | 並非所有技術上可執行的操作都應被允許。風險評估是 Human by Exception 的判斷依據之一。 |
| **Owned by** | Decision Engine（評估）；Policy（定義風險閾值與規則） |
| **Related concepts** | Policy、Confidence、Human Escalation、Decision、Guardrail |

---

### Confidence

| | |
|---|---|
| **Definition** | Agent 對某項理解或建議行動正確性的信心程度。信心不足時，系統應傾向澄清、延後執行或升級人工，而非貿然行動。 |
| **Why it exists** | 企業環境中，「不確定」是常態。信心是決策的輸入之一，用於平衡自動化與安全。 |
| **Owned by** | Decision Engine（納入決策）；Understanding（可提供信心相關信號） |
| **Related concepts** | Risk、Human Escalation、Decision、Understanding |

---

### Human Escalation

| | |
|---|---|
| **Definition** | 將控制權移交給人類的機制。僅在政策無法判定、風險超標、信心不足、或業務明確要求核准時觸發。 |
| **Why it exists** | Human by Exception。自動化是預設；人工介入是例外，用於處理邊界情況與高風險決策。 |
| **Owned by** | Decision Engine（判定是否需要）；Response（通知人類）；Workflow Engine（暫停並等待恢復） |
| **Related concepts** | Decision、Risk、Confidence、Policy、Workflow、[07-human-approval-governance.md](07-human-approval-governance.md) |

---

### Guardrail

| | |
|---|---|
| **Definition** | 防止有害或不可接受結果的確定性安全邊界。在理解、決策、執行或回應的關鍵路徑上強制執行，不受模型輸出影響。 |
| **Why it exists** | 信任需要可預測行為。Guardrail 確保即使理解或生成內容有誤，系統仍不會執行危險操作或洩漏敏感資訊。 |
| **Owned by** | Agent 程式（確定性實作）；Decision Engine 與 Response 路徑（套用時機） |
| **Related concepts** | Policy、Risk、Response、Audit |

> **Policy** 定義組織規則；**Guardrail** 強制執行安全底線。兩者互補，不可互換。

---

### Audit

| | |
|---|---|
| **Definition** | 對決策、執行與回應的持久化記錄。使事後能回答：誰觸發、做了什麼、依據哪條政策、結果如何。 |
| **Why it exists** | 企業合規與信任要求行為可追溯。Audit 是治理可見性的基礎。 |
| **Owned by** | Agent 程式（記錄）；Decision Engine 與 Workflow Engine（提供決策與執行脈絡） |
| **Related concepts** | Decision、Policy、Guardrail、Response |

---

## 執行與整合術語

### Tool Provider

| | |
|---|---|
| **Definition** | 抽象外部執行能力的元件。將「執行某項操作」的請求轉換為對底層系統的呼叫，並回傳結果。 |
| **Why it exists** | Workflow Engine 不應直接依賴特定 API、協定或廠商。Tool Provider 隔離執行細節，使工具可替換。 |
| **Owned by** | Tool Provider 本身（作為架構元件） |
| **Related concepts** | Integration、Capability、Workflow Engine、Decision |

> Workflow Engine 透過 Tool Provider 執行動作，不直接呼叫實作細節。

---

### Connector

| | |
|---|---|
| **Definition** | 連接 Agent 與外部營運系統的元件。負責接收事件（讀取輸入）與傳遞回應（寫回輸出）。每個外部系統通常對應一個 Connector。 |
| **Why it exists** | 企業系統各異（工單平台、ITSM、協作工具）。Connector 隔離資料來源與格式，使架構與產品無關。 |
| **Owned by** | Connector 本身（作為架構元件）；Domain 定義該 Connector 的業務語意 |
| **Related concepts** | Event、Integration、Response、Domain、Reference Implementation |

---

### Integration

| | |
|---|---|
| **Definition** | Agent 與外部企業系統之間的連接方式與契約。包含資料格式、認證、事件來源與回應通道。 |
| **Why it exists** | Agent 必須參與既有營運流程，而非要求企業遷就 Agent。Integration 是可替換的適配層。 |
| **Owned by** | Connector 與 Tool Provider（各自負責不同方向的整合） |
| **Related concepts** | Connector、Tool Provider、Capability、Domain |

> **Connector** 處理「進出營運系統的對話」；**Integration** 是更廣義的連接概念，涵蓋 Connector 與 Tool Provider 與外部世界的所有適配。

---

### Response

| | |
|---|---|
| **Definition** | Agent 對外溝通的產出。包含撰寫回覆、更新工單、產生摘要、通知使用者。回應應能說明重要的決策理由。 |
| **Why it exists** | Agent 的價值在於參與營運流程，而非僅在內部完成推理。Response 是 Agent 對組織與人的可見輸出。 |
| **Owned by** | Response 元件（架構層）；Connector（傳遞至外部系統） |
| **Related concepts** | Decision、Guardrail、Connector、Audit、Understanding |

---

## 領域與狀態術語

### Domain

| | |
|---|---|
| **Definition** | 特定企業營運領域的業務語意與流程。例如：技術支援 Case、變更管理、內部 IT 服務。Domain 定義「這個 Agent 在什麼業務場景中運作」。 |
| **Why it exists** | 通用架構需適配不同營運場景。Domain 是 Reference Implementation 與通用架構之間的分界。 |
| **Owned by** | Reference Implementation（具體領域邏輯）；組織（定義業務需求） |
| **Related concepts** | Workflow、Connector、Reference Implementation、Policy |

> 通用架構元件（Workflow Engine、Decision Engine）應與 Domain 無關；領域專屬步驟屬於 Reference Implementation 層。

---

### Memory

| | |
|---|---|
| **Definition** | Agent 跨時間保留的脈絡資訊。包含已處理事件、歷史理解、診斷累積、假設與協作脈絡。 |
| **Why it exists** | 企業任務常跨多次互動。Memory 使 Agent 能延續先前理解，而非每次從零開始。 |
| **Owned by** | Agent 程式（持久化）；Understanding 與 Domain 邏輯（讀寫語意） |
| **Related concepts** | State、Workflow、Domain、Event |

---

### State

| | |
|---|---|
| **Definition** | 某個 workflow 實例在特定時刻的執行狀態。包含進行到哪一步、等待什麼、已完成的決策與執行結果。 |
| **Why it exists** | 長時間運行與中斷恢復需要可追蹤的狀態。State 使 Workflow Engine 能暫停、恢復與重試。 |
| **Owned by** | Workflow Engine |
| **Related concepts** | Workflow、Event、Memory、Human Escalation |

> **State** 是單次 workflow 的執行快照；**Memory** 是跨多次互動的累積脈絡。兩者相關但職責不同。

---

## 專案結構術語

### Reference Architecture

| | |
|---|---|
| **Definition** | 描述 Enterprise AI Agent 應如何設計的概念架構。定義元件職責、互動方式與設計原則，不綁定特定技術或產品。 |
| **Why it exists** | 組織需要可重複採用、可長期演進的設計藍圖，而非一次性的專案實作。 |
| **Owned by** | 本 repository 的文件（[02-reference-architecture.md](02-reference-architecture.md) 為權威來源） |
| **Related concepts** | Reference Implementation、Domain、Policy、Workflow Engine |

---

### Reference Implementation

| | |
|---|---|
| **Definition** | Reference Architecture 的一個具體、可運行的實例。展示架構如何落地於特定 Domain，供學習、workshop 與組織適配。 |
| **Why it exists** | 抽象架構需要可觸摸的範例。Reference Implementation 證明設計可行，但不定義架構本身。 |
| **Owned by** | 本 repository 的程式與設定（Case Agent 為第一個 Reference Implementation） |
| **Related concepts** | Reference Architecture、Domain、Connector、Workflow |

> 更換 Connector、Workflow 或 Policy 以支援新 Domain，不應要求更換 Reference Architecture。

---

## 術語關係一覽

```
External System
      │
      ▼
  Connector ──► Event
                    │
                    ▼
            Workflow Engine ◄── State
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
Understanding   Decision      Response
      │         Engine              │
      │             │               │
      └──────┬──────┘               │
             ▼                      │
      Tool Provider                 │
             │                      │
             ▼                      ▼
      Integration              Connector
      (execution)              (delivery)

Decision Engine 使用：Policy、Capability、Risk、Confidence
關鍵路徑強制：Guardrail
事後追溯：Audit
跨時間脈絡：Memory
業務場景：Domain
```

---

## 常見混淆

| 容易混淆 | 區分方式 |
|----------|----------|
| **Policy vs Guardrail** | Policy 是組織規則（可設定）；Guardrail 是安全底線（確定性強制） |
| **Decision vs Understanding** | Understanding 解讀「是什麼」；Decision 判斷「能不能做」 |
| **Connector vs Tool Provider** | Connector 處理營運系統的讀寫與事件；Tool Provider 處理操作執行 |
| **Integration vs Connector** | Integration 是連接概念；Connector 是其在一個方向上的元件實作 |
| **Workflow vs Domain** | Workflow 是編排；Domain 是業務場景語意 |
| **State vs Memory** | State 是單次執行狀態；Memory 是跨互動累積 |
| **Reference Architecture vs Reference Implementation** | 前者是藍圖；後者是範例 |
| **Capability vs Tool** | Capability 是政策分組；Tool 是 Tool Provider 中的具體執行單元 |

---

## 延伸閱讀

| 目的 | 文件 |
|------|------|
| 設計原則 | [01-principles.md](01-principles.md) |
| 概念架構 | [02-reference-architecture.md](02-reference-architecture.md) |
| 模組對照 | [04-module-map.md](04-module-map.md) |
| 演進策略 | [03-evolution-roadmap.md](03-evolution-roadmap.md) |
