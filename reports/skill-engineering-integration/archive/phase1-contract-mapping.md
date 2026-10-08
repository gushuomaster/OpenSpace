# Phase 1 Contract Mapping

OpenSpace commit：`38277815ed44a53d757973c2bc4454c3b6426698`  
skill-engineering Public API：`e200f0a4e36d63885969cc0f5d9679f8f7d521da`

## One-way dependency

```text
OpenSpace lifecycle models
  → openspace.skill_engine.governance_adapter.mapping
  → engine.GovernanceRequest
  → engine.GovernanceEngine
  → engine.GovernanceResult
  → openspace.skill_engine.governance_adapter.persistence_bridge
  → OpenSpace EvidenceStore
```

`skill-engineering` 的 Public API 只接受中立 dataclass、字符串、路径和 Mapping，不 import OpenSpace runtime 类型。OpenSpace 只 import `engine` 的 Public API，不 import其内部 provider、rule 或 staging 模块。

## 概念映射

| OpenSpace | Governance Contract | 责任归属 |
| --- | --- | --- |
| `DecisionRationale` | `GovernanceRequest.intent`、`decision_id`、action 和 target | OpenSpace 是唯一语义 Decision source |
| `EvidencePacket`/`ResourceRef` | `GovernanceRequest.evidence_refs` | OpenSpace EvidenceStore 是 Durable State source |
| `AdmissionResult` | `admission_id`、action context、candidate context | OpenSpace Admission 保持不变 |
| `EvolutionCandidate` | Adapter 传入 candidate context；Gate 阻断时继续复用 CandidateStore | OpenSpace 是唯一 Candidate Store |
| `ValidationResult` | `validation_status`、validation refs | OpenSpace Validator 产生基础验证证据 |
| `SkillBehaviorEvalResult` | behavior evidence ref 和 validation context | OpenSpace Behavior Eval 保持独立 |
| `EvolutionCommitter` | `publish_authorized` 的唯一消费者 | OpenSpace 是唯一 Active Skill mutation owner |
| `SkillTrustState` | Commit 后继续由 OpenSpace 管理 `PROVISIONAL`/`TRUSTED` | Governance PASS 不改变 Trust |
| `SkillLineage` | parent revision context、source/candidate digest | OpenSpace 维护版本 DAG |

## Public API

`skill-engineering` 暴露：

- `GovernanceRequest`
- `GovernanceResult`
- `GovernanceEngine`
- `GovernanceError`
- `ProviderObservation`
- `CapabilityDecision`

`GovernanceRequest` 没有 OpenSpace 类型字段；`GovernanceResult` 包含 validation、coverage、integrity、capability、provider、publish authorization、reason codes 和 engine version/revision。

## 状态映射

### Action 类型

```text
FIX      → OpenSpace FIX
DERIVED  → OpenSpace DERIVED
CAPTURED → OpenSpace CAPTURED
AUDIT_ONLY → 不进入 Mutation
```

### Trust

```text
Governance PASS
  → EvolutionCommitter commit
  → SkillTrustState.PROVISIONAL
  → independent runtime success evidence
  → TRUSTED
```

### Gate

```text
Validation FAIL / Integrity FAIL / required capability FAIL → BLOCKED
Validation UNKNOWN / Coverage incomplete / provider not executed → INCOMPLETE
全部 required 条件满足 → PASS
```

`GovernanceAdapter` 的 `off`、`shadow`、`enforced` 与 OpenSpace 的 `audit_only`、`fix_only`、`autonomous` 分层；前者只控制治理门，后者继续控制 Evolution 生命周期。

## Durable Evidence

治理结果写入 OpenSpace 现有 EvidenceStore 的 `governance_results` 表，并通过 `governance_result_ref` 和 `governance_result_persisted` event 进入现有 ResourceRef/EvidenceEvent 索引。没有新增 Candidate DB、DecisionRecord、Active Skill Store 或第二个 EvidenceStore。

## 当前边界与后续缺口

- 当前 Adapter 已支持 neutral mapping、digest 计算、治理结果持久化和 Enforced pre-commit 阻断。
- ProviderObservation 的真实 Provider 注入点尚未接入 OpenSpace Provider registry；未提供 Provider 时，required capability 会 fail closed。
- Dashboard/MCP 只读治理诊断尚未完成。
- Candidate/Source digest 在 Committer 前会重新通过 Adapter 计算；需要追加并发变更测试证明阻断行为。
