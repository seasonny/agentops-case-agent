.PHONY: help init install check test dry-run run report policy-dump mcp-tools clean approve deny pending audit

PYTHON ?= python3
CASE_ID ?=
BY ?= operator
REASON ?=

help: ## 顯示可用指令
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-14s %s\n", $$1, $$2}'

init: install ## 首次設定：安裝依賴 + 複製設定範本
	@./init.sh

install: ## 安裝 Python 依賴
	$(PYTHON) -m pip install -r requirements.txt

check: ## 檢查 LLM、MCP、Case 讀取
	$(PYTHON) main.py --check $(if $(CASE_ID),--case-id $(CASE_ID),)

test: ## 執行單元測試（不需 LLM / Case）
	$(PYTHON) -m unittest discover -s tests -v

dry-run: ## 試跑一輪，不發回覆
	$(PYTHON) main.py --dry-run $(if $(CASE_ID),--case-id $(CASE_ID),)

run: ## 正式運行
	$(PYTHON) main.py $(if $(CASE_ID),--case-id $(CASE_ID),)

report: ## PoC 量測摘要
	$(PYTHON) main.py --report

policy-dump: ## 輸出編譯後安全政策 JSON
	$(PYTHON) main.py --policy-dump

pending: ## 列出待核准 MCP 操作
	$(PYTHON) main.py --pending-approvals $(if $(CASE_ID),--case-id $(CASE_ID),)

approve: ## 核准最新 pending（BY=核准者名稱）
	$(PYTHON) main.py --approve-latest $(if $(CASE_ID),--case-id $(CASE_ID),) --approved-by $(BY)

deny: ## 拒絕最新 pending（BY=拒絕者, REASON=原因）
	$(PYTHON) main.py --deny-latest $(if $(CASE_ID),--case-id $(CASE_ID),) --denied-by $(BY) --deny-reason "$(REASON)"

audit: ## 輸出 audit 摘要
	$(PYTHON) main.py --audit-report $(if $(CASE_ID),--case-id $(CASE_ID),)

mcp-tools: ## 列出 MCP 工具
	$(PYTHON) check_mcp_tools.py

clean: ## 清除 Python cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
