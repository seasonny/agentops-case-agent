# MCP Provider 擴充指南

Case Agent 遵循 **Agent 薄、MCP 厚**：新產品能力 = 新 MCP provider + `policy_capability_map.yaml` 條目。

---

## 預設 Stack（OpenShift / Case）

| Provider | 用途 | 預設 |
|----------|------|------|
| `platform` | Case 讀寫、K8s API | `npx rh-tam-kubernetes-mcp-server` |
| `exec` | 本機 dig/ping 等 | `mcp-shell-server` |

---

## 合併額外 Provider

將範本合併進 `config/local.json`：

```bash
# 純 RHEL / 本機 sosreport（exec MCP）
# 見 config/mcp_providers/rhel-exec.example.json

# 多產品並存
# 見 config/mcp_providers/multi-product.example.json
```

`config/local.json` 範例：

```json
{
  "mcp_providers": {
    "platform": { "command": "npx", "args": ["-y", "rh-tam-kubernetes-mcp-server@latest"] },
    "exec": {
      "command": "mcp-shell-server",
      "tool_map": { "exec_argv": "shell_execute" }
    },
    "rhel": {
      "command": "/opt/mcp/rhel-diagnostics-mcp",
      "args": [],
      "tools": ["sosreport_collect", "subscription_status"]
    }
  }
}
```

---

## 新增工具到 Policy

編輯 `config/policy_capability_map.yaml`：

```yaml
capabilities:
  rhel_diag:
    label: RHEL 診斷
    tools:
      - sosreport_collect
      - subscription_status
```

在 `config/policy_profiles/diagnostic.yaml`（或 enterprise 覆寫）開啟：

```yaml
capabilities:
  rhel_diag: true
```

---

## 非 OCP 環境

| 場景 | 建議 |
|------|------|
| 純 RHEL | `exec` MCP + sosreport；或專用 RHEL MCP |
| 跳板機 | SSH MCP（需自行部署）→ 映射為 `exec_argv` 等價工具 |
| 無 K8s API | 關閉 `cluster_*` 能力；SE 留言走 clarify + exec |

無 K8s 時 `platform` provider 可僅保留 Case 讀寫工具（若 MCP 支援）。

---

## SSH / 跳板機（契約）

外部 SSH MCP 應暴露與 `mcp-shell-server` 相容的 argv 介面，或透過 `tool_map` 映射：

```json
"tool_map": {
  "exec_argv": "remote_shell_execute"
}
```

Agent 不內建 SSH；由 MCP 負責連線與執行邊界。

---

## 驗證

```bash
python check_mcp_tools.py
python main.py --check
python main.py --health
```

確認新工具出現在 catalog，且 `policy.yaml` 允許後再試 `--dry-run`。
