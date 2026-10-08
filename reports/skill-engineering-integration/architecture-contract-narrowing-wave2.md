# Architecture Contract Narrowing Wave 2

日期：2026-10-08

本报告记录 Wave 2 的实现、dependency publication checkpoint 与 Phase 3 最终集成验证。仅 skill-engineering 授权提交被推送；OpenSpace push、PR、merge 和 release 均未执行。

## Architecture Changes

- `skill-engineering` 新增 `engine.candidate_contract`，仅 re-export Candidate 当前需要的 14 个既有符号；没有复制业务逻辑、Adapter、Service、Registry 或第二套 Governance Pipeline。
- OpenSpace 五个 Candidate 生产模块统一从该 contract 导入，Candidate 对 engine 内部模块的直接导入由 5 个模块收窄为 1 个稳定入口。
- staged authoring 通过 `SkillEvolver.run_staged_authoring_loop` 和 `apply_staged_authoring_with_retry` 进入共享算法；`_run_evolution_loop`、`_apply_with_retry`、构造参数和默认关闭的 direct-mutation guard 均保留。
- GovernanceAdapter、Candidate lifecycle、receipt、digest、integrity、visibility 和 crash recovery 的职责与实现未改变。

实现提交：

- skill-engineering：`c0d455054f8525d0a881d4e689e36ecfe287bde4`，`feat: expose narrow candidate governance contract`
- OpenSpace：`3dba5a68ca3f27d2838d056b4b93859550c75b69`，`refactor: narrow candidate and staged authoring contracts`

## Compatibility and Failure Evidence

- Legacy direct-mutation guard 默认关闭，原有入口和参数仍可用；staged authoring 不调用 legacy 私有 entrypoint。
- 新增回归覆盖真实 staging retry 成功、retry exhaustion、staging 清理和正式目录哨兵保持不变。
- Candidate contract 测试验证 14 个对象身份、精确 `__all__`、原始导入兼容性和 installed wheel 可用性。
- Candidate 的 BLOCKED/INCOMPLETE/ERROR、digest/receipt mismatch、visibility admission、recovery 和 runtime reuse 回归保持通过。

## Dependency Status

OpenSpace 的 `pyproject.toml` 与 `requirements.txt` 均指向：

`skill-engineering @ git+https://github.com/gushuomaster/skill-engineering.git@c0d455054f8525d0a881d4e689e36ecfe287bde4`

全新 Python 3.14.3 venv 从正式 GitHub URL 和精确 SHA、禁用 pip cache 构建并安装 skill-engineering，再构建并安装 OpenSpace wheel；在中立工作目录、`python -I`、无 `PYTHONPATH` 条件下完成 import、14-symbol contract、PEP 610 provenance 和 `pip check` 验证。

远端 `origin/codex/architecture-contract-narrowing-wave2` 已重新读取并 fetch 为 `c0d455054f8525d0a881d4e689e36ecfe287bde4`。发布 diff 仅含 `engine/candidate_contract.py`、`tests/unit/test_candidate_contract.py`、`tests/integration/test_distribution_packaging.py`。

Phase 3 wheels：

- `skill_engineering-1.0.3-py3-none-any.whl`：sha256 `2114b70fc31f2588483fc76f5fb763d21048d27cd3f9c4957c4360dbecffa433`
- `openspace-2.0.0-py3-none-any.whl`：sha256 `dc88ca2fd6014ab206ea4cbb96d0a24a908c98ae61533720a06d872dc9be8945`

## Test Evidence

| Scope | Result |
|---|---|
| OpenSpace full suite, isolated venv | `198 passed, 2 skipped` |
| skill-engineering full suite, isolated venv | `462 passed, 2 skipped` |
| Candidate focused (`tests/cloud`) | `84 passed, 1 skipped` |
| Cross-repository dependency contract | `5 passed` |
| Evolution/staged authoring/continuation focused | `52 passed` |
| OpenSpace wheel neutral import and PEP 610 smoke | PASS |
| `pip check` | `No broken requirements found` |
| `skill-discovery` validator | `Skill is valid!` |
| `delegate-task` validator | `Skill is valid!` |
| `skill-engineer` validator | `Skill is valid!` |

OpenSpace full 的 2 个 skip 分别是可选 Harbor/Terminal-Bench 环境未安装，以及 Windows directory symlink privilege limitation（WinError 1314）；Candidate focused 的 1 个 skip 与后者重叠。skill-engineering full 的 2 个 skip 都是 Windows symlink privilege limitation。没有失败、xfail 或 collection error。

## Unified Candidate Baseline

`git merge-base --is-ancestor` 已逐项证明 Integration 基线 `1bbde7e`、continuation `7e0871b`、crash fail-closed `d9a8281`、runtime reuse `3efe735`、旧 dependency pin `76262da`、Dependency Publication Closure `30b30f6`、Wave 1 `b757efc` 与 Wave 2 implementation `3dba5a6` 全部位于当前 OpenSpace 本地候选 ancestry。没有使用 cherry-pick、rebase 或覆盖用户工作区完成整合。

## Remaining Decisions

本轮没有删除 direct-mutation 子图，没有改变公共 Governance API，也没有改变双仓库 topology。现有消费者证据仍支持：保留 Evolution 公共 facade、保留双仓库和 immutable pin；direct-mutation 仅在后续弃用证据和独立消费者审计完成后再评估删除。任何 topology、公共 API 删除或长期治理所有权变化仍需用户单独决策。

残余风险仅包括：当前 Windows 主机无法执行 3 个独立 symlink 测试实例，可选 Harbor/Terminal-Bench gate 未运行；任务级自动重放仍明确不在范围内；3 个长期高影响架构决策仍待用户决定。这些事项不阻塞当前 PR 候选，但需要在对应平台或后续专项继续跟踪。

## Final Status

```text
WAVE2_IMPLEMENTATION_COMPLETE = YES
STAGED_AUTHORING_DECOUPLED = YES
LEGACY_COMPATIBILITY_PRESERVED = YES
CANDIDATE_CONTRACT_COMPLETE = YES
CANDIDATE_INTERNAL_IMPORTS_REDUCED = YES
CANDIDATE_GOVERNANCE_PRESERVED = YES
EVOLUTION_GOVERNANCE_PRESERVED = YES
LOCAL_INTEGRATION_VERIFIED = YES
REMOTE_DEPENDENCY_REPRODUCIBLE = YES
FINAL_INTEGRATION_BASELINE_READY = YES
PR_READY = YES (PR not created; authorization pending)
USER_CHANGES_PRESERVED = YES
```
