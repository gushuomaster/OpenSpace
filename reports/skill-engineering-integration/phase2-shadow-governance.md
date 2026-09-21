# Phase 2 Shadow Governance

## 已实现

- `OPENSPACE_GOVERNANCE_MODE=shadow` 是默认模式。
- Runtime 初始化时创建 `GovernanceAdapter`，并注入 `EvolutionEngine` 与 `EvolutionCommitter`。
- Governance 调用发生在 Behavior Eval 成功之后、正式 Commit 之前。
- Shadow 模式持久化 `GovernanceResult`，但不阻止 OpenSpace 原有 Commit。
- `EvolutionRunResult` 和 MCP evolution summary 暴露 governance results。
- `EvidenceStore` 使用现有 SQLite DB 的 `governance_results` 表和 `governance_result_ref`，没有第二个 Evidence DB。

## 阻断差异记录

当前每个治理结果会记录：

- `gate_status`
- `publish_authorized`
- `validation_status`
- `coverage_status`
- `integrity_status`
- capability/provider reason codes
- source/candidate digest
- engine name/version/revision

因此可以直接查询原流程仍然提交、但 Governance 判定 `BLOCKED` 或 `INCOMPLETE` 的差异，而不改变原始提交行为。

## 当前默认行为

没有声明 required capabilities 的历史 Decision 会得到兼容性的完整 coverage；声明了 required capability 但未提供 ProviderObservation 时，结果为 `INCOMPLETE`。这使 Shadow 能观察缺口，同时不影响已有 OpenSpace 任务。

## 验证

- `tests/skill_engine/test_governance_adapter.py` 覆盖 Shadow persistence、required Provider 未执行和 Committer boundary。
- `tests/skill_engine/test_evolution_retry_idempotency.py` 保持通过。

## 进入 Enforced 的条件

在 Provider coverage、deliverable contract 和 digest CAS 回归稳定前，不能将默认模式改为 Enforced。切换只通过 `OPENSPACE_GOVERNANCE_MODE=enforced` 完成，不增加 capability-specific feature flags。
