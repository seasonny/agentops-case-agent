# Engineering Principles

| | |
|---|---|
| **Purpose** | 定義指導每個架構決策的工程原則 |
| **Audience** | 架構師、貢獻者 |
| **Source of truth** | 本文件是**設計原則**的權威來源 |
| **Related** | [00-manifesto.md](00-manifesto.md)、[02-reference-architecture.md](02-reference-architecture.md)、[05-vocabulary.md](05-vocabulary.md) |

These principles guide every architectural decision in this project.

---

## Trust before Autonomy

Autonomy is never the primary objective.

Trust must be established before increasing automation.

---

## Governance over Intelligence

A more capable model does not automatically create a better enterprise system.

Governance enables adoption.

---

## Policy over Prompt

Business rules must be implemented through explicit policies rather than embedded inside prompts.

Policies should be:

* Version controlled
* Auditable
* Configurable
* Testable

---

## Workflow over Conversation

Enterprise work consists of workflows, not conversations.

Conversation is only the interface.

Workflow is the product.

---

## Human by Exception

The Agent should execute actions automatically whenever they comply with organizational policy.

Human involvement should occur only when:

* Policy cannot determine the correct action.
* Risk exceeds the defined threshold.
* Additional business context is required.

---

## Product Agnostic

Business logic should never depend on OpenShift, Kubernetes, or any particular vendor.

Products are integrations.

Architecture is independent.

---

## Extensible by Design

Every major component should be replaceable without redesigning the system.

Examples include:

* LLM
* Connectors
* Workflow Engine
* Decision Engine
* Tool Provider
* Policy Engine