# AI Engineering Agreement

| | |
|---|---|
| **Purpose** | 定義人與 AI 的分工，以及實作前後必須遵守的工程規則 |
| **Audience** | AI Agent（每次實作前必讀） |
| **Source of truth** | 本文件是 **AI 工程協作方法** 的權威來源 |
| **Related** | [docs/README.md](../README.md)、[README.md](README.md)、[working-agreement.md](working-agreement.md)、[definition-of-done.md](definition-of-done.md) |

> Start from [docs/README.md](../README.md). Continue via [AI Collaboration Guide](README.md) after architecture phase 1.

## Role

Human owns:

- Product vision
- Architecture
- Design decisions
- Sprint approval

AI owns:

- Analysis
- Implementation
- Refactoring
- Testing
- Documentation updates

---

## Engineering Rules

When architecture is unclear:

1. Do not invent architecture.
2. Explain the uncertainty.
3. Propose alternatives.
4. Explain trade-offs.
5. Wait for approval.

---

## Implementation Rules

- One architecture concept per sprint.
- Preserve behavior.
- Keep repository runnable.
- Small reviewable commits.
- Prefer evolution over replacement.

---

## Decision Principle

Architecture decisions belong to humans.

Implementation belongs to AI.