<!--
Sync Impact Report
- Version change: unratified template → 1.0.0
- Modified principles:
  - Template Principle 1 → I. Evidence-Grounded and Traceable Answers
  - Template Principle 2 → II. End-to-End Authorization
  - Template Principle 3 → III. Agent Decision and Controlled Execution Separation
  - Template Principle 4 → IV. Modular and Progressive Retrieval
  - Template Principle 5 → V. Observable, Evaluated, and Tested Quality
- Added sections:
  - Enterprise Data and Operational Safety
  - Development Workflow and Quality Gates
- Removed sections:
  - Placeholder-only additional constraints and workflow sections
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md
  - ✅ .specify/templates/spec-template.md
  - ✅ .specify/templates/tasks-template.md
  - ✅ .specify/templates/commands/ (directory absent; no command templates to update)
- Runtime guidance reviewed:
  - ✅ AGENTS.md (already compatible; no change required)
  - ✅ README.md (contains no governance references; no change required)
- Follow-up TODOs: None
-->
# AtlasMind Constitution

## Core Principles

### I. Evidence-Grounded and Traceable Answers

Every answer derived from enterprise knowledge MUST be supported by evidence the requesting
user is authorized to inspect. The system MUST distinguish sourced facts, reasoned inferences,
conflicting evidence, and unknowns. It MUST NOT present unsupported content as established fact.
Every retrievable segment, entity, relationship, and material tool result MUST remain traceable
to its source, location, version, and applicable knowledge scope. Citations MUST resolve to the
evidence that supports the associated claim, or the answer MUST state that evidence is
insufficient.

Rationale: Enterprise users must be able to verify important conclusions and identify stale,
conflicting, or incomplete knowledge without trusting an opaque model response.

### II. End-to-End Authorization

Every knowledge request MUST use the caller's current authenticated identity, role, and
knowledge scope. Authorization MUST be enforced before and during document retrieval,
structured-data queries, graph traversal, external tool use, answer construction, citation
display, evaluation, and access to operational records. Unknown, stale, or inconsistent
authorization state MUST fail closed. Restricted content MUST NOT leak through answer text,
metadata, citations, summaries, error messages, traces, evaluation artifacts, or inferred graph
paths. Agent planning MUST NOT weaken, replace, or bypass these controls.

Rationale: A correct answer delivered across a permission boundary is a security failure, not a
successful retrieval.

### III. Agent Decision and Controlled Execution Separation

The Agent layer MUST be limited to understanding intent, deciding whether retrieval is needed,
planning bounded steps, and selecting approved capabilities. Retrieval and Tool services MUST
own input validation, authorization, data access, execution limits, failure isolation, and output
normalization. A language model MUST NOT directly execute database operations, decide access
rights, or invoke unregistered capabilities. Any operation that can mutate enterprise or external
system state MUST retain the existing human confirmation or approval mechanism and MUST create
an auditable decision record.

Rationale: Separating probabilistic planning from deterministic controls keeps tool use
reviewable and prevents natural-language instructions from becoming unbounded authority.

### IV. Modular and Progressive Retrieval

Document, structured-data, graph, and external-system retrieval MUST expose bounded,
replaceable capabilities with consistent authorization, provenance, error, and observability
contracts. Optional retrieval strategies MUST be selected by explicit policy and task need; the
system MUST NOT execute every available strategy for every query. Delivery MUST progress in
independently testable stages: enterprise retrieval and citation, Agent workflow and tools,
graph retrieval, then advanced retrieval and evaluation. Later stages MUST preserve the
security and traceability guarantees of earlier stages.

Rationale: Policy-driven modularity limits complexity, permits safe replacement of retrieval
backends, and allows each phase to deliver verifiable value.

### V. Observable, Evaluated, and Tested Quality

Every Agent interaction MUST have a correlation identity and record the user query, material
decisions, retrieval and tool activity, timing, usage, final status, answer, and citations at the
minimum detail needed for authorized diagnosis. Sensitive content in operational records MUST
remain subject to authorization and data-governance controls. Retrieval quality, context
relevance, answer faithfulness, and citation accuracy MUST be measured with repeatable datasets
before release and after material retrieval, prompt, model, policy, or workflow changes.
Automated tests MUST cover authorization, data isolation, high-risk tools, data writes or
migrations, complex state transitions, and important defect regressions. Other changes MUST
receive verification proportional to risk.

Rationale: An enterprise knowledge Agent cannot be operated safely without reproducible quality
signals, diagnosable executions, and tests at its highest-risk boundaries.

## Enterprise Data and Operational Safety

- Knowledge objects MUST retain source ownership, version, lifecycle state, metadata, and
  knowledge scope from ingestion through retrieval, graph construction, citation, and deletion.
- Duplicate, superseded, revoked, failed, or partially processed content MUST have an explicit
  state and MUST NOT silently participate as current authoritative knowledge.
- Automatically extracted metadata, entities, and relationships MUST preserve their evidence
  and MUST allow authorized correction when they influence user-visible conclusions.
- Retrieval or tool failures MUST be isolated. Partial results MAY be returned only when their
  limitations and impact are disclosed; failed or unverified outputs MUST NOT be treated as facts.
- Data retention, redaction, export, and deletion MUST follow the enterprise's approved data
  governance policy. A missing required policy is a release blocker, not an implicit default.
- Prompts, documents, and tool outputs MUST be treated as untrusted input. Instructions embedded
  in retrieved content MUST NOT override authorization, approval, or capability boundaries.
- External capabilities MUST use least privilege, bounded inputs, timeouts, and auditable
  outcomes. High-risk side effects MUST remain unavailable until the required human approval is
  recorded.

## Development Workflow and Quality Gates

- Every feature specification MUST define prioritized independent user journeys, acceptance
  scenarios, edge cases, measurable technology-agnostic outcomes, assumptions, dependencies,
  and explicit scope boundaries.
- Features affecting Agent, Prompt, Context, Tool, Workflow, Memory, RAG, permissions, or data
  isolation MUST specify evidence handling, authorization boundaries, failure behavior,
  observability, evaluation, and approval requirements before planning.
- Every implementation plan MUST pass the Constitution Check before research and again after
  design. Any violation MUST be recorded with a concrete necessity and rejected simpler
  alternative; authorization and human-approval guarantees are non-waivable.
- Tasks MUST trace to user stories or cross-cutting constitutional requirements. Required
  security tests, permission-isolation tests, high-risk tool tests, audit/observability work, and
  RAG evaluation work MUST be explicit tasks rather than implicit completion criteria.
- Implementation MUST reuse existing project modules and approved technology choices unless a
  reviewed plan justifies a change. Unrelated refactoring MUST NOT be bundled with feature work.
- Completion claims MUST cite actually executed tests or evaluations. Failing checks MUST NOT be
  hidden, removed, or weakened to obtain a passing result.
- Each delivery phase MUST be independently demonstrable and MUST retain all previously accepted
  permission, evidence, approval, and audit guarantees.

## Governance

This constitution is the highest project-level engineering and delivery authority. Specifications,
plans, tasks, templates, reviews, and implementation decisions MUST comply with it. Where another
project document conflicts, the stricter constitutional rule applies until the conflict is resolved.

Amendments require a documented proposal stating the affected principles, compatibility impact,
template changes, validation or migration needs, and rollback considerations. Project maintainers
MUST review and approve amendments before they take effect. Dependent templates and active plans
MUST be updated in the same change or explicitly listed as pending blockers.

Versions follow semantic versioning: MAJOR for incompatible principle or governance changes,
MINOR for new principles or materially expanded obligations, and PATCH for non-semantic
clarifications. The ratification date remains the original adoption date; the last-amended date
changes whenever constitutional meaning or wording changes.

Compliance MUST be checked during specification, planning, task generation, code review, and
release readiness. Deviations MUST be visible in the plan's Complexity Tracking section and
approved before implementation. No deviation may waive end-to-end authorization or required human
approval for high-risk actions. Runtime behavior and executed validation results take precedence
over unsupported completion claims.

**Version**: 1.0.0 | **Ratified**: 2026-08-22 | **Last Amended**: 2026-08-22
