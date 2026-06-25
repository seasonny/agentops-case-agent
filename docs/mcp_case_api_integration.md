# MCP Server × Case Agent 串接規格

本文件供 **MCP Server 團隊**實作，並作為 **Case Agent** 端 JSON 解析的契約依據。  
API 來源：[Red Hat Case Management API](https://access.redhat.com/management/api/case_management#/)（Swagger：`CaseManagement-API_v1.json`）。

- **Base URL**：`https://api.access.redhat.com/support`
- **Auth**：`Authorization: Bearer <token>`

---

## 1. 設計原則

1. **工具名向後相容**：保留現有 `*_rh_portal` 名稱，Agent 無需改 CLI。
2. **回傳 JSON 契約**：MCP 回傳結構化 JSON（見 §4），Agent 透過 `core/case_api_models.py` 解析。
3. **路徑差異由 MCP 吸收**：Case API 用 `/v1/cases/...`，Attachments 用 `/cases/...`（無 `v1`）。
4. **過渡期**：若暫時無法 JSON 化，可繼續回傳 legacy 文字；Agent 會 fallback 至 regex parser。

---

## 2. MCP 工具 ↔ REST API 對照表

### Phase 1（必做）

| MCP 工具名 | HTTP | operationId | 說明 |
|------------|------|-------------|------|
| `read_case_comments_rh_portal` | `GET /v1/cases/{caseNumber}/comments` | `getCaseComments` | 回傳 §4.1 JSON（**不要**再回傳 `[1] Author...` 文字） |
| `read_case_rh_portal` | `GET /v1/cases/{caseNumber}` | `getCase` | 回傳 §4.2 JSON |
| `add_case_comment_rh_portal` | `POST /v1/cases/{caseNumber}/comments` | `createCaseComment` | 見 §3.1 |

**`read_case_comments_rh_portal` 建議參數：**

| MCP 參數 | API 參數 | 必填 | 說明 |
|----------|----------|------|------|
| `case-number` | `caseNumber` (path) | 是 | Case 編號 |
| `start-date` | `startDate` (query) | 否 | ISO 8601，增量輪詢 |
| `end-date` | `endDate` (query) | 否 | ISO 8601 |
| `sort-field` | `sortField` (query) | 否 | 建議 `createdDate` |
| `sort-order` | `sortOrder` (query) | 否 | 建議 `asc`（Agent 內部 oldest→newest） |

**`add_case_comment_rh_portal` 參數映射：**

| MCP 參數 | API `CaseComment` 欄位 | 說明 |
|----------|------------------------|------|
| `case-number` | path `caseNumber` | |
| `text` | `commentBody` | |
| `public` | （待實測） | Swagger 無 `isPublic`；請實測並文件化 |
| — | `doNotChangeStatus` | 建議可選 `true`，避免 Agent 回覆改變 Case 狀態 |

---

### Phase 2（建議）

| MCP 工具名 | HTTP | 說明 |
|------------|------|------|
| `list_case_attachments_rh_portal` | `GET /cases/{caseNumber}/attachments/` | 回傳 §4.3 |
| `upload_attachment_rh_portal` | `POST /cases/{caseNumber}/attachments/` | `multipart/form-data` |
| `get_case_comment_rh_portal` | `GET /v1/cases/{caseNumber}/comments/{commentId}` | 單則留言 debug |

**Attachment 上傳狀態（大檔）：**

- `GET /cases/{caseNumber}/attachments/status`
- `GET /cases/{caseNumber}/attachments/{attachmentId}/status`

---

### Phase 3（企業擴充，Agent policy 預設擋）

| MCP 工具名 | HTTP | Agent 用途 | Policy |
|------------|------|------------|--------|
| `filter_cases_rh_portal` | `POST /v1/cases/filter` | 多 Case 佇列 | 可選 |
| `update_case_rh_portal` | `PUT /v1/cases/{caseNumber}` | 同步 Portal `status` | **建議預設 block** |
| `create_case_rh_portal` | `POST /v1/cases` | — | Agent 已 block |

**不建議暴露**：`DELETE` attachment、任意修改 severity/product。

---

## 3. Hydra Schema 重點欄位

### 3.1 `CaseComment`

| API 欄位 | Agent 內部欄位 | 用途 |
|----------|----------------|------|
| `id` | `portal_comment_id` | 穩定去重（`pid:{id}:{hash}`） |
| `commentBody` | `content` | 留言正文 |
| `createdDate` / `publishedDate` | `timestamp` | 排序、去重 |
| `createdBy` | `author` | 顯示 |
| `createdByType` | `created_by_type` → `api_role` | **角色辨識主依據** |
| `isDraft` | — | `true` 時跳過 |
| `contentType` | `content_type` | 輔助 |
| `doNotChangeStatus` | — | 建議 POST 時可設 |

### 3.2 `createdByType` → 角色（待實測補齊）

Agent 目前映射（`core/case_api_models.py`）：

| `createdByType` | Agent `resolved_role` |
|-----------------|------------------------|
| `ASSOCIATE`, `REDHAT`, `SUPPORT`, `ENGINEER`, `RHN_SUPPORT` | `support` |
| `CUSTOMER`, `CONTACT`, `USER`, `CUSTOMER_CONTACT` | `customer` |
| `SYSTEM`, `AUTOMATED`, `BOT` | `ignored` |

**請 MCP 團隊實測後回報完整 enum，我們會更新映射表。**

### 3.3 `Case`（getCase）

Agent 使用欄位：`status`, `severity`, `summary`, `description`, `product`, `version`, `openshiftClusterID`, `openshiftClusterVersion`, `lastModifiedDate`, `resolutionDescription`

### 3.4 `CaseAttachment`

Agent 使用欄位：`id`, `fileName`, `sizeKB`, `createdDate`, `createdBy`, `isPrivate`, `downloadRestricted`, `link`

---

## 4. MCP 回傳 JSON 契約

### 4.1 Comments — `read_case_comments_rh_portal`

```json
{
  "comments": [
    {
      "id": "127",
      "caseNumber": "01234567",
      "commentBody": "請執行 oc get node",
      "createdDate": "2026-06-24T10:00:00Z",
      "publishedDate": "2026-06-24T10:00:00Z",
      "createdBy": "Jane Doe",
      "createdByType": "ASSOCIATE",
      "contentType": "TEXT",
      "isDraft": false,
      "doNotChangeStatus": false
    }
  ],
  "source": "hydra:getCaseComments"
}
```

也可直接回傳 `CaseComment[]` 陣列（Agent 皆支援）。

### 4.2 Case — `read_case_rh_portal`

```json
{
  "caseNumber": "01234567",
  "status": "Waiting on Customer",
  "severity": "3",
  "summary": "節點 NotReady",
  "product": "Red Hat OpenShift Container Platform",
  "version": "4.16",
  "openshiftClusterID": "xxxxxxxx",
  "openshiftClusterVersion": "4.16.12",
  "lastModifiedDate": "2026-06-24T09:00:00Z",
  "resolutionDescription": null
}
```

### 4.3 Attachments — `list_case_attachments_rh_portal`

```json
{
  "attachments": [
    {
      "id": "att-123",
      "fileName": "must-gather.tar.gz",
      "sizeKB": 512000,
      "createdDate": "2026-06-24T08:00:00Z",
      "createdBy": "customer@example.com",
      "isPrivate": false,
      "downloadRestricted": false,
      "link": "https://..."
    }
  ]
}
```

### 4.4 錯誤格式

```json
{
  "isError": true,
  "content": [{ "type": "text", "text": "HTTP 403: Account mismatch" }],
  "httpStatus": 403,
  "operationId": "getCaseComments"
}
```

---

## 5. Agent 端已準備的程式

| 檔案 | 職責 |
|------|------|
| `core/case_api_models.py` | API JSON → 內部 comment/case/attachment 結構 |
| `bridges/case_portal.py` | 自動偵測 JSON / legacy；`query_case_detail`、`list_attachments` stub |
| `core/participants.py` | 優先使用 `createdByType` 映射角色 |
| `core/comments.py` | 去重 key 支援 `pid:{portal_comment_id}:{hash}` |

**MCP Phase 1 完成後 Agent 串接步驟：**

1. 確認 `read_case_comments` 回傳 §4.1 → 日誌出現 `comments_parsed_api_json`
2. 確認 `createdByType` 映射正確 → 日誌 `resolved_role=support`
3. 啟用 `read_case_rh_portal` 注入 case context（後續 PR）
4. 更新 `participants` config 或自動填充

---

## 6. 驗收清單

- [ ] `python check_mcp_tools.py` 列出 Phase 1 工具
- [ ] `read_case_comments_rh_portal` 回傳 §4.1 JSON（非 legacy 文字）
- [ ] `add_case_comment_rh_portal` 成功建立留言並回傳 `CaseComment`（含 `id`）
- [ ] `read_case_rh_portal` 回傳 §4.2 JSON
- [ ] 提供 `createdByType` 實測對照表
- [ ] 提供 `public` 留言實測結果
- [ ] （P2）`list_case_attachments_rh_portal` 回傳 §4.3

---

## 7. 參考：API 路徑不一致提醒

```
GET  /support/v1/cases/{caseNumber}/comments     ← Case / Comments
GET  /support/cases/{caseNumber}/attachments/    ← Attachments（無 v1）
POST /support/v1/cases/filter                    ← 多 Case 查詢
```

MCP 實作時請統一封裝，勿讓 Agent 處理路徑差異。
