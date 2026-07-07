# Definition of Done

> Start from [docs/README.md](../README.md). AI guide: [README.md](README.md) · [engineering-method.md](engineering-method.md)

This document defines the quality standard for every architectural change, refactoring, and feature implementation in this repository.

A task is **not complete** simply because the code works.

A task is complete only when it improves the project while remaining aligned with the documented philosophy.

---

# Design Alignment

Every change must align with the following documents:

* docs/architecture/00-manifesto.md
* docs/architecture/01-principles.md
* docs/architecture/02-reference-architecture.md

Document index: [docs/README.md](../README.md)

If a proposed implementation conflicts with these documents, the implementation should be reconsidered.

Architecture has higher priority than implementation.

---

# Simplicity

The preferred solution is the simplest solution that satisfies the requirements.

Avoid introducing:

* unnecessary abstractions
* additional frameworks
* excessive configuration
* generic code without a clear use case

Favor clarity over cleverness.

---

# Extensibility

Every new feature should increase, or at least preserve, the project's extensibility.

New functionality should avoid tight coupling with:

* specific vendors
* specific products
* specific AI models
* specific deployment environments

Reference implementations should remain reusable.

---

# Governance

Every execution path should clearly answer:

* Why is this action allowed?
* Which policy applies?
* Can the decision be explained?
* Can the action be audited?

Enterprise AI requires governance before autonomy.

---

# Human by Exception

Human interaction should occur only when:

* policy cannot determine an outcome
* business approval is required
* confidence is below an acceptable threshold
* risk exceeds organizational policy

Do not introduce unnecessary approval steps.

Automation should remain the default for trusted operations.

---

# Workshop Value

Every change should improve at least one of the following:

* architectural clarity
* educational value
* maintainability
* extensibility
* governance
* usability

Avoid adding features that make demonstrations more complicated without improving understanding.

---

# AI Collaboration

When proposing changes, always explain:

1. Why is this change necessary?
2. Which design principle does it support?
3. Which architectural problem does it solve?
4. What are the trade-offs?
5. Is there a simpler alternative?

Do not generate code before answering these questions.

---

# Pull Request Checklist

Before considering a task complete, verify the following:

* Architecture remains consistent.
* Design principles are respected.
* No unnecessary coupling has been introduced.
* Existing workflows remain understandable.
* Policies remain externalized.
* Components remain replaceable.
* Workshop storytelling is improved or preserved.

---

# Success

Success is not measured by the amount of code added.

Success is measured by whether the repository becomes a better reference for Enterprise AI Agent design.

Code is temporary.

Architecture evolves.

Principles endure.