# Phase 5 Integrity and Publish

## Digest CAS

初次治理结果绑定：

- source digest
- candidate digest
- staging descriptor
- request/decision/authoring/validation IDs

Committer 在正式发布前把初次 GovernanceResult 的两个 digest 与当前 source/candidate 目录比较。发现任一变化时抛出 `GovernanceBlockedError`，reason code 为：

```text
source_digest_mismatch
candidate_digest_mismatch
```

随后 Enforced 模式再执行一次 Adapter governance evaluation，确保当前 evidence 和 gate 仍然有效。

## 唯一发布器

只有 `EvolutionCommitter` 可以执行：

- FIX backup
- proposed directory apply
- SkillStore revision 写入
- skill id sidecar 写入
- Registry refresh
- Evidence action finalize

Governance Engine 不直接写 Active Skill；Adapter 也不拥有任何 mutation API。

## Recovery / Idempotency

OpenSpace 现有 `evolution_actions`、idempotency key、committing recovery 和 FIX backup 机制继续复用。新增治理结果通过 `governance_id` 和 `governance_result:<id>` 保证重复持久化幂等。

## 回归

`tests/skill_engine/test_governance_adapter.py` 覆盖：

- Enforced required capability 未执行阻断
- Committer publication boundary
- Governance 后 candidate digest 变化阻断
