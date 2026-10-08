# Phase 4 Enforced Gate

## Gate 条件

当 `OPENSPACE_GOVERNANCE_MODE=enforced` 时，`EvolutionEngine` 在调用 `EvolutionCommitter` 前要求：

```text
validation_status = PASS
coverage_status = COMPLETE
integrity_status = PASS
所有 required capability = PASS
gate_status = PASS
publish_authorized = true
```

任何 `FAIL` 或 `UNKNOWN`/`NOT_RUN` 都不会进入正式发布；被阻断的演化继续进入 OpenSpace 唯一 `EvolutionCandidateStore`，而不是由治理引擎创建第二个候选库。

## Committer 二次门禁

`EvolutionCommitter` 接收可选 Governance Adapter。Enforced 模式下它在任何 backup、active copy、SkillStore 写入或 Registry refresh 之前重新验证治理结果，并拒绝未授权发布。

治理授权与正式 publication 仍然是两个步骤：

```text
GovernanceResult.publish_authorized
  → EvolutionCommitter
  → Active Skill mutation
```

## 模式兼容

- `off`：不执行治理，不持久化，不影响旧流程。
- `shadow`：执行和持久化，但保留旧 Commit 行为。
- `enforced`：治理结果 fail closed。

这三个值不改变 OpenSpace 原生 `audit_only/fix_only/autonomous` Evolution mode。
