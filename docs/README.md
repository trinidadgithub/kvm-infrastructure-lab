# Documentation index

- **[Engineering continuity](ENGINEERING-CONTINUITY.md)** — authoritative current handoff, ownership, operational evidence, PTY issue, P0 Makefile findings, state recovery and next decisions. Start here.
- [Operation controller](OPERATION-CONTROLLER.md) — Phase 2 executable manifest, exact approvals, trust limitations and isolated stub tests.
- [Ubuntu environment runbook](../environments/ubuntu-servers/README.md) — configuration inputs, target-host preflight and environment-specific operations.
- [Packer image workflow](../packer/README.md) — build, seal, validate and publish new image versions.
- [Repository refactor design](REPOSITORY-REFACTOR-DESIGN.md) — historical proposal, including work that has since been implemented or superseded.
- [K3s lab notes](lab-plan.md), [prior implementation plan](implementation-plan.md), [prior review](review-findings.md) — historical records. Do not use their old rebuild, `make up`, or destroy instructions as current safety guidance.

Live infrastructure facts in the continuity document are operator-reported unless explicitly labeled independently verified. No documentation update changes Terraform state or infrastructure.
