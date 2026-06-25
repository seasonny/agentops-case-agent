# Enterprise 部署指南

Phase 2 能力：稽核、Outage 模式、人工核准、Case 診斷記憶、Secrets 注入、Health check。

---

## Production 建議設定

### 1. Policy：`enterprise` + `allowlist`

```yaml
# config/policy.yaml
profile: enterprise
mode: allowlist
dangerous_handling: skip_and_continue
```

或透過 tenant / 環境變數：

```bash
export POLICY_PROFILE=enterprise
```

`enterprise` profile 預設僅開：`case_read`、`case_write`、`cluster_read`；關閉 `cluster_exec`、`host_diag`、`must_gather`、`upload_attachments`。

### 2. 複製 Enterprise 設定範本

```bash
cp config/agent_config.enterprise.example.json config/agent_config.json
cp config/policy_profiles/enterprise.yaml   # 確認 policy.yaml 指向 enterprise
```

依需求開啟能力（在 `policy.yaml` 的 `capabilities:` 區塊覆寫）。

---

## 稽核 Trail

每次 policy 判定、MCP 呼叫、回覆發送寫入：

```
reports/{case_id}/audit.jsonl
```

```bash
python main.py --audit-report --case-id 01234567
```

每行 JSON 含：`ts`、`event`、`tenant_id`、`tool`、`arguments`、`policy_passed`、`dry_run` 等。

---

## Outage 模式

```json
"outage": {
  "enabled": true,
  "interval_seconds": 5,
  "notify_webhook_url_env": "CASE_AGENT_WEBHOOK_URL",
  "notify_on": ["reply_posted", "policy_blocked", "approval_required", "clarify"]
}
```

- 啟用後輪詢間隔改為 `outage.interval_seconds`（預設 5 秒）
- Webhook 為 JSON POST（相容 Slack Incoming Webhook / 自建中繼）

```bash
export CASE_AGENT_WEBHOOK_URL=https://hooks.example.com/agent-events
```

---

## 人工核准（HITL）

```json
"approval": {
  "enabled": true,
  "required_tools": ["oc_adm_must_gather", "pods_exec", "upload_attachment_rh_portal"]
}
```

流程：

1. Agent 規劃高風險 MCP → 寫入 `reports/{case_id}/approvals.json` pending
2. 回覆 Case 說明待核准 fingerprint
3. SRE 核准後下一輪自動重試

```bash
python main.py --pending-approvals --case-id 01234567
python main.py --approve 01234567 a1b2c3d4e5f6g7h8 --approved-by sre@corp.com
```

---

## Secrets 注入（Vault / K8s Secret）

不在 repo 放 API key；掛載檔案後由 Agent 啟動時注入：

```json
"secrets": {
  "env_from_files": {
    "GEMINI_API_KEY": "/run/secrets/gemini-api-key",
    "CASE_AGENT_WEBHOOK_URL": "/run/secrets/webhook-url"
  }
}
```

K8s 範例：Secret volume 掛到 `/run/secrets/`，與上表路徑對齊。

---

## Case 診斷記憶

`case_context.track_diagnostics: true` 時，已執行診斷寫入 `agent_memory.json` 的 `diagnostics_history`，並注入 LLM 的 case history，避免重複跑相同檢查。

---

## 可觀測性

```bash
python main.py --health
python main.py --health-json
python main.py --check
python main.py --report
```

Health 報告含：LLM、MCP providers、policy profile/mode、outage 狀態、audit 是否開啟。

---

## 多租戶 / RBAC（輕量）

建議：**一團隊一 Agent 實例**（獨立 `case_id`、`policy.yaml`、`tenant.id`）。

```json
"tenant": {
  "id": "prod-ocp-team-a",
  "label": "OCP Production Team A",
  "policy_profile": "enterprise"
}
```

`tenant.id` 會寫入 audit trail；不同團隊用不同設定檔與 process 隔離。

---

## Production 上線 Checklist

1. `policy.yaml` → `enterprise` + `allowlist`
2. `python main.py --check`
3. `python main.py --dry-run` 試跑一則 SE 留言
4. 確認 `reports/{case_id}/audit.jsonl` 有紀錄
5. 若開 approval：測試 `--pending-approvals` / `--approve` 流程
6. Outage 時啟用 `outage.enabled` + webhook
7. 正式執行 `python main.py`

---

## 相關文件

- [MCP_PROVIDERS.md](MCP_PROVIDERS.md) — 多產品 MCP 掛載
- [POLICY.md](POLICY.md) — 能力包說明
- [DEVELOPER.md](DEVELOPER.md) — 架構
