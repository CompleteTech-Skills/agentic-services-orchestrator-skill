# Services specialists and domain workflows

The services domain retains Discovery → Proposal → Contract → Delivery → Customer
Success, support outputs, parallel tracks, backward loops, and change-order work.
The [services adapter](completetech-services-workflow.yaml) owns that policy. See
[architecture](orchestration-architecture.md) for the single shared authority,
execution, and recovery rules.

## Artifact ownership

| Specialist | Inputs and owned outputs | Boundary |
|---|---|---|
| `agentic-discovery-skill` | Verified opportunity/workflow facts, stakeholder map, readiness, success criteria, proposal handoff | No final commercial/legal artifacts |
| `agentic-proposal-skill` | Discovery facts; buyer-facing proposal, SOW, evaluation plan, assumptions, exclusions, change order | No invented price, proof, legal terms, billing, or scope authority |
| `agentic-contract-skill` | Approved commercial facts, parties, signatories, terms source; agreement package | No commercial negotiation or signature authority |
| `agentic-delivery-skill` | Approved scope, owners, timeline, criteria; kickoff, project controls, evaluations, runbook, handoff, closeout | Services delivery specialist; does not supervise agent runtimes or approve scope expansion |
| `agentic-customer-success-skill` | Contacts, commitments, delivery/support evidence; account health, renewal, escalation, advocacy plan | Internal account records are not public proof |
| `agentic-invoice-skill` | Verified contract/SOW, amounts, billing trigger, terms; invoice/credit/receipt/payment-request drafts | No invented tax, payment instructions, acceptance, or billing authority |
| `agentic-certificate-skill` | Verified recipient and training/attendance facts; certificate PDF | A certificate does not establish attendance, delivery acceptance, or public-use approval |
| `agentic-case-study-skill` | Verified outcomes, quote/attribution consent, confidentiality limits; proof assets | No invented metrics or permission; anonymization is not consent |
| `agentic-email-skill` | Supplied artifact summary, audience, recipient, CTA; message copy and sequences | Copy does not replace underlying artifacts or authorize sending |
| `agentic-envelope-skill` | Existing artifacts, sender/recipient and packaging facts; envelope, manifest, readiness notes | Packaging does not author content or authorize delivery |
| `agentic-security-review-skill` | Data, tools, permissions, external actions, logs, rollback; risks, controls, blockers, signoff evidence | Security review does not replace commercial/legal/billing approval or formal certification |

Specialists receive only the facts and artifact versions their task requires, plus
relevant approval references. Preserve approved identity, local logo path, palette,
confidentiality, audience, assumptions, conflicts, and source attribution. Unknown
facts remain `TBD`; they cannot satisfy executable gates.

## Original routes remain supported

| Requested work | Specialist route and gate |
|---|---|
| Lead to proposal | Discovery → proposal; email recap as needed; verify discovery acceptance before the executable proposal transition |
| Signed kickoff | Proposal → contract → invoice draft → envelope/email preparation → services delivery; preserve commercial, signature, billing, and kickoff gates |
| Launch readiness | Services delivery evaluation/runbook → relevant security review → authorized launch decision → customer success handoff |
| Support/renewal | Services delivery support evidence → customer success → proposal or invoice only within approved scope |
| Proof | Delivery evidence → customer success approver/timing → case study → applicable confidentiality/public-use approval |
| Training certificate | Verified training facts → certificate → envelope/email preparation if requested |
| Billing dispute | Hold invoice send; services delivery supplies acceptance evidence; customer success routes the decision; revise billing only after resolution |
| Scope change | Keep existing delivery bounded; open discovery/proposal change track, assess relevant risk, then update contract/billing only after approval |

Commercial, legal, billing, recipient, public-proof, and client-authority gates stay
with their appropriate owners. Security review applies when sensitive data,
credentials, permissions, security-sensitive tools, production impact, incidents, or
confidentiality risk warrant it. Routine billing does not automatically require a
security review.

Services delivery, security review, technical discovery, proposal drafting, billing
preparation, and communication can run in parallel when their dependencies, owner,
output limits, and approval scope permit it. Downstream drafting never implies that
an approval gate passed. The legacy worked scenario remains in
[full-workflow-variables.md](full-workflow-variables.md); it is illustrative input,
not an executable or approved real engagement.
