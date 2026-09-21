# Phase 0 Architecture Audit

审查日期：2026-09-21  
OpenSpace repository：`https://github.com/gushuomaster/OpenSpace.git`  
OpenSpace commit：`38277815ed44a53d757973c2bc4454c3b6426698`  
skill-engineering repository：`https://github.com/gushuomaster/skill-engineering.git`  
skill-engineering integration commit：`bc964a0`  

## 审查范围

本次审查覆盖 OpenSpace 的 `openspace/skill_engine/`、runtime、MCP entrypoint、Dashboard evolution 页面及 skill-engineering 相关测试。Phase 0 只读取和运行检查，没有改变 OpenSpace runtime 行为。

## 真实调用链

当前实际链路为：

```text
TriggerStore/TriggerJob
  → EvolutionEngine.process_job
  → EvidencePacketBuilder
  → DecisionEngine
  → EvolutionAdmission
  → EvolutionCandidateStore（candidate/reject 分支）
  → SkillEvolverAuthoringBackend（staged authoring）
  → EvolutionValidator
  → SkillBehaviorEvaluator
  → EvolutionCommitter
  → EvidenceStore / SkillStore / Registry
  → SkillTrustState / SkillLineage
```

`EvolutionEngine` 在 `openspace/skill_engine/evolution/engine.py` 中编排流程。`EvolutionCommitter` 是唯一被该流程调用的正式 Active Skill mutation owner；它先建立 `evolution_actions` 的 `committing` 记录，再执行备份、应用 staged 目录、磁盘结构验证、SkillStore 写入、Registry 刷新和 Evidence finalize。

## 关键数据模型

- `DecisionRationale` 是 OpenSpace 当前唯一语义决策记录，包含 action、target skill、理由、风险、evidence claims 和 proposal contract。
- `EvidencePacket` 与 `ResourceRef` 是运行时证据输入；`EvidenceStore` 将 packet、decision、admission、validation、behavior 和 action 写入同一个 SQLite 数据库。
- `AdmissionResult` 决定 `direct`、`candidate`、`noop` 或 `reject`。
- `EvolutionCandidateStore` 使用 `evolution_candidates` 表保存未直接提交的候选，不存在第二个候选数据库。
- `ValidationResult` 与 `SkillBehaviorEvalResult` 是提交前检查证据。
- `SkillRecord` 使用 `SkillTrustState.PROVISIONAL`/`TRUSTED` 和 `SkillLineage` 表示发布后的运行时信任与版本关系。

## 状态与现有安全机制

- OpenSpace 原生 Evolution mode 是 `audit_only`、`fix_only` 和 `autonomous`，它控制是否允许 evolution action，不应与治理 Adapter 的 `off`、`shadow`、`enforced` 混用。
- `AUDIT_ONLY` 在 EvolutionEngine 中不会进入 authoring 或 commit。
- Validator 对 staged status、目标目录、证据引用、action contract、重复 authoring 和行为评估进行 fail-closed 检查。
- Committer 对 staged、validation approve、admission direct 和已批准 behavior eval 进行前置检查。
- EvidenceStore 对 decision、validation、behavior 和 commit 使用持久 idempotency key；EvolutionEngine 可复用已 committed action，避免同一 decision 重复 authoring。
- Commit 失败时会记录 phase 和 failure status，并尝试从 FIX backup 回滚；恢复逻辑处理 `committing` action。
- 当前 Committer 没有治理结果前置门，也没有在 mutation 前重新比较 candidate/source digest 的 CAS 检查。

## 当前缺失能力

当前没有：

1. 与 OpenSpace 无依赖的 skill-engineering Public Governance API。
2. `GovernanceRequest`/`GovernanceResult` 中立契约和引擎版本记录。
3. OpenSpace 内部 Thin Governance Adapter。
4. GovernanceResult 在现有 EvidenceStore 中的持久化表和 evidence ref。
5. `Validation PASS`、`Coverage COMPLETE`、`Integrity PASS` 的独立治理门。
6. Provider `available`、`selected`、`executed` 三态在 OpenSpace 生命周期中的映射。
7. Candidate/source digest 的 commit-time CAS 校验。
8. Shadow 与 Enforced 模式的治理差异记录。

## 重叠能力与边界

OpenSpace 已拥有 lifecycle、evidence、decision、admission、candidate、trust、lineage 和 commit。skill-engineering 已拥有治理模型、Provider contract、capability applicability、deliverable contract 和 quality gate。集成时不得把这些 OpenSpace 能力复制到 skill-engineering，也不得让 Adapter 重新实现 skill-engineering 的内部规则。

推荐边界：

```text
OpenSpace model
  → governance_adapter.mapping
  → neutral GovernanceRequest
  → skill-engineering Public API
  → neutral GovernanceResult
  → governance_adapter.persistence_bridge
  → OpenSpace EvidenceStore
```

## 推荐插入点

治理调用点位于 `EvolutionEngine._author_validate_commit` 的 Behavior Eval 成功之后、调用 `EvolutionCommitter.commit` 之前。Enforced 模式在此阻止未授权发布；Shadow 模式只持久化结果并允许原流程继续。

Committer 仍需在真正 mutation 前再次确认治理结果和 digest，以防止 Adapter 检查与正式发布之间发生候选或源文件变更。

## 上游同步风险

- `openspace/skill_engine/evolution/engine.py` 是高风险冲突文件，集成应优先通过注入 Adapter，避免大范围重写。
- `evidence/store.py` 是持久化扩展点，新增治理表和 ref 时必须保持同一 SQLite EvidenceStore。
- `pyproject.toml` 是依赖锁定点，必须使用 `skill-engineering` 的 tag 或 commit SHA。
- Dashboard 和 MCP 当前有 evolution API，但治理状态尚未进入其响应模型；应在 Adapter 稳定后以只读字段扩展。
- 当前 OpenSpace 环境缺少 `pydantic`，相关测试在收集阶段失败；这属于环境前置缺口，不是治理实现通过证据。

## 基线验证

- skill-engineering：`python -m pytest tests/unit -q`：287 passed，2 skipped。
- OpenSpace skill/evolution/cloud focused tests：因缺少 `pydantic`，9 个模块在 collection 阶段失败，未形成有效行为通过证据。

## Phase 0 结论

OpenSpace 已提供唯一 Evolution Pipeline、Candidate Store、EvidenceStore 和 EvolutionCommitter，适合集成独立 Governance Engine。实现应采用单向依赖和 Thin Adapter，先在 Shadow 模式持久化治理证据，再通过 Enforced gate 保护现有 Committer；不应创建第二套 lifecycle、decision、candidate、evidence 或 mutation owner。
