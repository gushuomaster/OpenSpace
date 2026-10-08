# OpenSpace + skill-engineering 集成基线收口与架构简化规划

日期：2026-10-08

审计基线：`codex/e2e-skill-functional-closure@76262da82c4bd2fca553f323c67913d0e44e96eb`
skill-engineering 本地修复候选：`codex/baseline-wheel-policy-package@1c1c44225ba46efc96add761a30c7c9b04aa5270`

## 结论先行

统一代码候选已经识别：`codex/e2e-skill-functional-closure` 是 `codex/integrate-skill-engineering` 的严格后继，包含全部 12 个 End-to-End Functional Closure 提交；本轮新增的第 13 个提交只补齐了已证实的 wheel packaging 缺失，并把依赖 contract test 扩展为真实默认 Gate policy smoke。

在同一受控、非 editable 的本地 exact-SHA 安装中，Candidate lifecycle、Local miss 显式 continuation、Candidate visibility、crash reconciliation、restart/runtime reuse、Evolution Governance 以及默认 Gate policy 均已通过新鲜验证。正式交付基线仍不能标记 COMPLETE：修复 SHA `1c1c442…` 尚未出现在 `https://github.com/gushuomaster/skill-engineering.git`，因此 OpenSpace 当前写入的 GitHub URL 在干净外部环境中尚不能解析该 revision。按照本阶段禁止 push/release 的边界，这个外部发布缺口保留为唯一未闭合项。

本轮未 merge、push、PR、release、Repository 合并或历史复杂度清理；OpenSpace 原始工作区的 4 个用户修改保持原样。

## A. Git Integration Baseline Report

### 分支关系

| 项目 | Integration branch | E2E branch | 结论 |
|---|---|---|---|
| HEAD | `1bbde7e` | `76262da` | E2E 是统一候选 |
| merge-base | `1bbde7e` | `1bbde7e` | 两分支从同一 Integration HEAD 分叉 |
| `rev-list --left-right --count` | 0 | 13 | Integration 是 E2E 的祖先；E2E 多 13 个提交 |
| Candidate lifecycle | 已包含 | 已包含 | 无缺失 |
| Governance integration | 已包含 | 已包含 | Evolution adapter 与 Candidate 窄路径共存 |
| Cloud continuation | 未包含 | 已包含 | `7e0871b` 新增显式 continuation |
| Visibility admission | 未包含 | 已包含 | `5f67904`/`ec7a1e6` |
| Crash reconciliation | 未包含 | 已包含 | `797fe53`/`e2d7af3`/`d9a8281` |
| Runtime reuse | 未包含 | 已包含 | `3efe735` |
| Evolution compatibility | 已包含 | 已包含 | E2E 没有删除或旁路 Evolution |
| Dependency alignment | 已包含旧 pin | 已包含新本地修复 pin | 新 pin 需要发布后才具备远端可复现性 |

E2E 相对 Integration 的提交为：

```text
08f0176 docs: design end-to-end skill workflow closure
219d6f6 docs: refine skill workflow closure boundaries
5f67904 test: define managed skill visibility admission
ec7a1e6 fix: close managed skill visibility bypasses
7e0871b feat: expose truthful cloud discovery continuation
4b6a8f8 fix: align skill-engineering dependency contract
797fe53 test: prove candidate install kill point
e2d7af3 fix: reconcile interrupted candidate installs
d9a8281 fix: fail closed after candidate terminal write
3efe735 test: prove candidate runtime reuse after restart
e3e6638 docs: record end-to-end skill closure evidence
ab2507b docs: normalize closure report formatting
76262da fix: bind reproducible governance dependency
```

没有发现“一个分支只有 Candidate、另一个分支才有 Evolution 修复”的缺失关系。`76262da` 的改动范围只有 `pyproject.toml`、`requirements.txt` 和 dependency contract test；没有 cherry-pick、rebase 或整体 merge。

### 用户修改保护

原始 `D:\project\OpenSpace` 仍只包含以下 4 个既有未提交修改，未被读取之外的操作触碰：

- `reports/skill-engineering-integration/enforcement-readiness-matrix.md`
- `reports/skill-engineering-integration/production-readiness-matrix.md`
- `reports/skill-engineering-integration/production-readiness-report.md`
- `tests/live/provider_workload.py`

所有修改均位于隔离 worktree；OpenSpace E2E worktree 与 skill-engineering 修复 worktree 均干净。

## B. Functional Coverage Matrix

| Function | Code evidence | Test evidence | Status |
|---|---|---|---|
| Candidate Acquisition → Quarantine | `openspace/cloud/candidate_lifecycle.py`; MCP acquisition entrypoints | `tests/cloud/test_candidate_acquisition.py`, `test_candidate_lifecycle.py` | COMPLETE |
| Candidate identity/digest/receipt binding | `engine.inventory`, `engine.managed_completion`, `engine.serialization` consumers | Candidate governance/install negative tests | COMPLETE |
| Governance against final Candidate bytes | `openspace/cloud/candidate_governance.py` | `tests/cloud/test_candidate_governance.py`, `test_candidate_governance_integration.py` | COMPLETE |
| Real Codex semantic confirmation | serialized Governance outcome required before install | candidate governance integration and install tests | COMPLETE |
| PASS + valid receipt → Install | MCP install entrypoint and lifecycle checks | `tests/cloud/test_candidate_install.py` | COMPLETE |
| Quarantine/inspection/non-installed visibility admission | `CandidateVisibilityPolicy`; runtime and MCP registry paths | `test_candidate_visibility.py`, `test_candidate_visibility_entrypoints.py` | COMPLETE |
| Fail closed for BLOCKED/INCOMPLETE/ERROR/tamper | receipt and digest validation before install | governance/install negative cases | COMPLETE |
| Kill-point recovery and startup reconciliation | `reconcile_installing_candidates`; runtime startup hook | `test_candidate_recovery.py`, kill-point regression | COMPLETE |
| Restart → local lookup → SkillTool reuse | runtime registry/store and `SkillTool` | `test_candidate_runtime_reuse.py` | COMPLETE |
| Local miss semantics | explicit continuation payload; no implicit task replay | `test_cloud_discovery_continuation.py`, `test_skill_discovery_continuation.py` | COMPLETE |
| Cloud selection continuation | host/MCP continuation handoff | cloud continuation tests | COMPLETE |
| Existing Evolution Governance | `GovernanceAdapter` in `runtime/app.py`; Evolution engine before Committer | `tests/skill_engine/test_governance_adapter.py`, `tests/skill_engine/evolution/*`, retry regression | COMPLETE |
| Ordinary local Skill compatibility | existing Registry/SkillStore/SkillTool paths | full OpenSpace suite | COMPLETE |
| Default Gate policy in installed wheel | `engine.quality_gate.POLICY_PATH` plus package data | new wheel build/install test; dependency smoke | COMPLETE locally |
| Immutable GitHub dependency reproducibility | OpenSpace declarations use one SHA and PEP 610 is checked | local exact-SHA passes; `git ls-remote` reports SHA absent | PARTIAL |
| Task-level automatic replay | explicitly outside approved scope | no test claimed | MISSING by design |

本轮新鲜验证结果：

- OpenSpace full suite：`192 passed, 2 skipped, 0 failed, 0 collection errors`。
- OpenSpace focused Candidate/Evolution/dependency suite：`131 passed, 1 skipped`。
- skill-engineering full suite：`460 passed, 2 skipped, 0 failed, 0 collection errors`。
- 3 个 Skill validators（`skill-discovery`、`delegate-task`、`skill-engineer`）：全部 `Skill is valid!`。
- 本地 exact-SHA non-editable dependency smoke：PEP 610=`1c1c442…`，`policy=v1`，Candidate/Evolution imports PASS。
- 2 个 skip 都是 Windows symlink privilege limitation，不是功能失败。

## C. Historical Complexity Matrix

| Component | Real consumer | Classification | Recommendation | Risk |
|---|---|---|---|---|
| `GovernanceAdapter` | Evolution engine 在 Committer 前调用 | KEEP / NARROW | 明确文档为 Evolution-only cross-repo adapter；不接管 Candidate governance | 删除会绕过 Evolution Governance |
| `GovernanceRequest/Result` 与 public facade | OpenSpace Evolution 真实跨 repo 消费 | KEEP | 保留最小请求/结果契约和 Codex semantic boundary | 破坏 Evolution adapter contract |
| Candidate internal engine imports | Candidate governance 真实消费 inventory/receipt/serialization | KEEP / future NARROW | 当前不删；未来可在有 consumer contract 后缩小 public surface | 当前删除会破坏 Candidate lifecycle |
| immutable Git SHA pin | 双 repo 安装、receipt provenance、PEP 610 | KEEP | 保持单一 pin；发布前不得把本地 SHA 宣称为远端可复现 | pin 漂移会破坏闭环证据 |
| PEP 610 provenance | dependency contract test | NARROW | 保留为 cross-repo contract 证据，不把它扩展成产品运行时能力 | 过度扩大只增加安装测试维护 |
| Candidate identity/digest/receipt/integrity | Candidate install/recovery | KEEP | 作为 fail-closed 核心机制 | 删除会允许错 Candidate 安装 |
| B2 crash/restart | Candidate install kill-point 与 recovery | KEEP | 继续作为重点回归 | 删除会重新引入持久化断点 |
| B3 shadow full Evolution regression | Evolution 真实行为 | KEEP | 保留，和 Candidate 套件分开报告 | 删除会失去 Evolution 保护 |
| Production Readiness umbrella | 主要是旧独立产品交付证明 | ARCHIVE / NARROW | 保留历史报告；移出默认 Candidate 完成定义 | 继续作为默认 gate 会制造错误完成信号 |
| B1 provider dogfood | 大型 provider workload，非 Candidate 闭环 | ARCHIVE / NARROW | 只在 provider/production 专项运行 | 高耗时且与当前闭环弱相关 |
| B4 MCP/dashboard harness | MCP/dashboard consistency | ARCHIVE / NARROW | 保留按需验证，不作为每次基线必要条件 | 默认运行成本高 |
| rollback-to-pin / independent release closure | 独立 package/release 假设 | ARCHIVE / NARROW | 作为发布专项证据，不作为 Candidate lifecycle 必需件 | 会把发布拓扑误当运行时不变量 |
| generic `SkillSource` exports（仅 master） | 目前只有 Local exact-resolution 真实消费者 | REMOVE_CANDIDATE / NARROW | 当前 pinned baseline 不适用；未来保留 exact resolver，收窄 generic search/export | 过早删除 master future consumer |
| legacy `SkillEvolver` direct mutation branch | 未发现独立生产 direct consumer；authoring backend 复用私有 primitive | REMOVE_CANDIDATE（未来） | 先建立 consumer contract 与回归，再删遗留 public branch | 误删会影响 focused tests/未知消费者 |

## D. Minimal Simplification Plan

### P0：无需用户决策、可安全做的收窄

1. 把 Production Readiness、B1、B4、rollback/release closure 从默认“统一 Candidate 完成定义”中移到按需发布/专项验证；保留原始报告和可复现命令。
2. 将 `GovernanceAdapter` 文档、模块说明和 contract test 明确为 Evolution-only；Candidate 继续使用 skill-engineering 的窄治理入口，不建立第二套 pipeline。
3. 保留当前最小 dependency contract：两个声明同一 immutable SHA、PEP 610、Candidate/Evolution imports、默认 Gate policy load。不要再增加全局 PYTHONPATH 或手工 config copy accommodation。
4. 继续保留 B2/B3、Candidate digest/receipt/integrity/recovery 和 visibility admission；这些直接保护安全与 fail-closed 不变量。

### P1：需要后续真实消费者证据后再做

- 收窄 master-only generic `SkillSource` exports。
- 删除 legacy direct-mutation public branch。
- 合并重复的旧发布证明测试，但每项删除前先迁移其稳定不变量到 focused regression。

### 不能在本轮做的事项

- 不删除 GovernanceAdapter、Candidate lifecycle、Evolution Governance 或 recovery/integrity primitives。
- 不建立第二套 Governance Pipeline、journal、公共治理平台或 Agent 自治 replay。
- 不把手工复制 policy、editable install 或 PYTHONPATH 当成修复。
- 不在未发布 `1c1c442…` 前宣称远端 dependency contract COMPLETE。

## E. Repository Topology Comparison

| 维度 | A：继续双仓库并缩小边界 | B：将 Governance implementation 内聚到 OpenSpace |
|---|---|---|
| 真实消费者 | OpenSpace Evolution 直接消费 adapter/facade；Candidate 消费 engine primitives | 可减少跨 repo import，但需迁移 Evolution 与全部 skill-engineering tests |
| 迁移成本 | 当前已完成，主要是 contract 与发布协调 | 高：治理、schemas、providers、validators、receipt、测试和文档整体迁移 |
| 依赖维护 | 需要 immutable pin、wheel packaging、PEP 610 contract | 少一条 pin，但 OpenSpace 需承接完整治理 release surface |
| 测试成本 | 两套 authoritative suite + 少量 cross-repo contract | 单仓库 suite 更集中，但迁移期需双轨回归 |
| 发布成本 | 两 repo 发布与 pin 更新 | 单 repo 发布更简单，治理与运行时 release 耦合 |
| 后续升级影响 | skill-engineering 可独立演进，受 pin 控制 | OpenSpace runtime 变更会直接影响治理实现 |
| 当前建议 | **维持；只收窄公开边界** | 仅作为长期用户决策，不在本轮实施 |

本轮没有证据证明必须改变 Repository topology。是否长期独立属于用户决策，不由当前代码自动反推。

## F. Final Classification

```text
INTEGRATION_BASELINE_IDENTIFIED = YES
INTEGRATION_BASELINE_COMPLETE = NO
CANDIDATE_LIFECYCLE_PRESENT = YES
E2E_CONTINUATION_PRESENT = YES
RUNTIME_REUSE_PRESENT = YES
EVOLUTION_GOVERNANCE_PRESENT = YES
DEPENDENCY_CONTRACT_REPRODUCIBLE = NO
GOVERNANCE_INVARIANTS_VERIFIED = YES
SIMPLIFICATION_PLAN_READY = YES
HIGH_IMPACT_DECISIONS_PENDING = 3
USER_CHANGES_PRESERVED = YES
```

`DEPENDENCY_CONTRACT_REPRODUCIBLE=NO` 的唯一原因是修复提交尚未发布到正式 GitHub remote；本地 exact-SHA wheel 安装与全部功能验证已经通过。3 个待决策项是：

1. skill-engineering 是否长期保持独立 repository；
2. 独立 package/release 是否继续作为长期交付边界；
3. 面向未知外部消费者的 public API 与 Production Readiness harness 保留范围。

停止条件已满足：完成统一基线核对、证实的最小 packaging 修复、真实功能与负向验证、架构复杂度复核和简化计划；未进入 merge、push、PR、release 或历史代码清理。
