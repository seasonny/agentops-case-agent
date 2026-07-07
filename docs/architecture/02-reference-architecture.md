# Enterprise AI Agent Reference Architecture

| | |
|---|---|
| **Purpose** | 定義概念架構：元件職責與互動方式（技術無關） |
| **Audience** | 架構師、貢獻者、workshop 參與者 |
| **Source of truth** | 本文件是**概念架構**的權威來源 |
| **Related** | [04-module-map.md](04-module-map.md)（現況對照）、[05-vocabulary.md](05-vocabulary.md) |

## Purpose

This document defines the conceptual architecture of the Enterprise AI Agent Reference.

It intentionally focuses on responsibilities rather than implementation details.

Frameworks, programming languages, and deployment environments are implementation choices and may evolve over time.

The architecture should remain stable.

---

# High-Level Architecture

```
                    External Event
                           │
                           ▼
                  Workflow Engine
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     Understanding   Decision Engine   Response
            │              │
            └──────┬───────┘
                   ▼
            Tool Provider
                   │
     ┌─────────────┼─────────────┐
     │             │             │
     ▼             ▼             ▼
  REST API      CLI / SSH       MCP
                   │
                   ▼
             Enterprise Systems
```

---

# Design Goals

The architecture is designed around the following principles:

* Product Agnostic
* Policy Driven
* Human by Exception
* Extensible
* Observable
* Replaceable

Every component has a single responsibility.

---

# Core Components

## Workflow Engine

The Workflow Engine coordinates the execution of an enterprise workflow.

Responsibilities:

* Receive events
* Track workflow state
* Invoke appropriate components
* Resume interrupted workflows
* Support long-running operations

The Workflow Engine should never contain business policies.

---

## Understanding

The Understanding component interprets external requests.

Examples:

* Customer Portal Case
* Support Engineer reply
* Email
* Jira comment
* Slack message

Its responsibility is to identify:

* Intent
* Context
* Required actions
* Missing information

It does not execute tools.

It does not make business decisions.

---

## Decision Engine

The Decision Engine determines what should happen next.

Responsibilities:

* Evaluate organizational policies
* Assess operational risk
* Determine confidence level
* Decide whether execution is allowed
* Decide whether human escalation is required

The Decision Engine owns organizational decision logic.

Policy evaluation is one capability of the Decision Engine.

---

## Tool Provider

The Tool Provider abstracts external execution.

Supported examples:

* SSH
* REST API
* CLI
* MCP
* Python
* Ansible

The Workflow Engine should never directly call implementation-specific tools.

---

## Response

The Response component communicates with external systems.

Examples:

* Draft a reply
* Update a Case
* Generate a summary
* Notify a user

Responses should always explain important decisions made by the Decision Engine.

---

# Human Escalation

Human involvement is exception-based.

The Agent should execute actions automatically when:

* Organizational policy allows it.
* Risk is acceptable.
* Confidence is sufficient.

Escalation should occur only when:

* Policies cannot determine the correct action.
* Risk exceeds acceptable thresholds.
* Required information is missing.
* Business approval is explicitly required.

---

# Policy Model

Policies are external configuration.

Policies should never be hardcoded inside prompts.

Examples include:

* Allowed tools
* Forbidden operations
* Risk thresholds
* Approval requirements
* Organization-specific constraints

Policy is data.

Policy is not application logic.

---

# Event-Driven Workflow

The architecture is event driven.

Typical events include:

* New Case
* New Comment
* Tool Completed
* Human Response
* Timeout
* Workflow Resumed

The Workflow Engine reacts to events instead of continuously polling for work.

---

# Extensibility

The architecture is designed to evolve.

Examples of replaceable components include:

* LLM Provider
* Workflow Engine
* Tool Provider
* Connector
* Policy Store
* Memory Implementation

Replacing one component should not require redesigning the entire system.

---

# Reference Implementation

Case Agent is the first reference implementation of this architecture.

Future implementations may include:

* Jira Agent
* ServiceNow Agent
* Cloud Operations Agent
* Change Management Agent
* Internal IT Support Agent

The architecture remains unchanged.

Only connectors, workflows, and policies evolve.