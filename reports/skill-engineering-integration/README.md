# Skill Engineering Integration Reports

本目录是 OpenSpace × skill-engineering 集成报告的单一入口。报告按当前用途分为 Active、Historical 与 On-demand；历史归档保留原文和 Git 历史，不代表当前实现状态。

## Active

当前权威报告：[`architecture-contract-narrowing-wave2.md`](architecture-contract-narrowing-wave2.md)

- [`architecture-contract-narrowing-wave2.md`](architecture-contract-narrowing-wave2.md)：Wave 2 contract narrowing、本地集成、完整回归与 publication checkpoint。
- [`integration-baseline-consolidation-and-simplification-plan.md`](integration-baseline-consolidation-and-simplification-plan.md)：当前集成基线、复杂度分类、简化进度和待决策事项。
- [`candidate-governance-lifecycle-design.md`](candidate-governance-lifecycle-design.md)：Candidate Acquisition → Quarantine → Governance → Install 的架构边界与不变量。
- [`end-to-end-functional-closure.md`](end-to-end-functional-closure.md)：显式 continuation、visibility admission、crash recovery 与 runtime reuse 的功能收口设计和证据。

## Historical

以下报告位于 [`archive/`](archive/)；它们用于追溯阶段性判断，不再作为当前完成状态或默认执行门槛：

- [`archive/phase0-architecture-audit.md`](archive/phase0-architecture-audit.md)
- [`archive/phase1-contract-mapping.md`](archive/phase1-contract-mapping.md)
- [`archive/phase2-shadow-governance.md`](archive/phase2-shadow-governance.md)
- [`archive/phase3-provider-coverage.md`](archive/phase3-provider-coverage.md)
- [`archive/phase4-enforced-gate.md`](archive/phase4-enforced-gate.md)
- [`archive/phase5-integrity-publish.md`](archive/phase5-integrity-publish.md)
- [`archive/phase6-observability.md`](archive/phase6-observability.md)
- [`archive/phase7-e2e-dogfooding.md`](archive/phase7-e2e-dogfooding.md)
- [`archive/final-integration-report.md`](archive/final-integration-report.md)
- [`archive/fork-tax-report.md`](archive/fork-tax-report.md)
- [`archive/upstream-sync-strategy.md`](archive/upstream-sync-strategy.md)

## On-demand

这些报告保留给 enforcement、production 或 release 专项；它们不是每次 Candidate/Evolution 集成基线的默认 gate：

- [`enforcement-readiness-matrix.md`](enforcement-readiness-matrix.md)
- [`enforcement-readiness-report.md`](enforcement-readiness-report.md)
- [`production-readiness-matrix.md`](production-readiness-matrix.md)
- [`production-readiness-report.md`](production-readiness-report.md)
- [`release-closure-diff-ownership.md`](release-closure-diff-ownership.md)
- [`release-closure-reproduction.md`](release-closure-reproduction.md)

如分类或权威结论发生变化，先更新本索引和当前权威报告，避免新增并行状态报告。
