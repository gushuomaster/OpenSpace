# Architecture Contract Narrowing Wave 2

日期：2026-10-08

本报告记录 Wave 2 的本地实现、跨仓库集成和受控环境验证。远端发布、PR、merge 和 release 均未执行。

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

本地新 venv 使用本地 Git exact-SHA 构建并安装 skill-engineering，再构建并安装 OpenSpace wheel；在中立工作目录、`python -I`、无 `PYTHONPATH` 条件下完成 import、14-symbol contract、PEP 610 commit provenance 和 `pip check` 验证。OpenSpace wheel：`openspace-2.0.0-py3-none-any.whl`，sha256 `f5f1bcd04d31eb969dae9c5d6c1f3355d266f57ba7cee67b7919bb80a26840fe`。

远端 `origin` 当前可见 `master=70698fd46496e0fc946e1e49b11b321de4efe34c`，未见新 SHA；因此本地集成可复现，但正式 GitHub URL 的新 revision 复现必须在发布后重新验证。

## Test Evidence

| Scope | Result |
|---|---|
| OpenSpace full suite, isolated venv | `198 passed, 2 skipped` |
| skill-engineering full suite, isolated venv | `462 passed, 2 skipped` |
| Candidate contract/runtime/visibility/continuation/recovery | `42 passed, 1 skipped` |
| Evolution/staged authoring focused | `50 passed` |
| OpenSpace wheel neutral import and PEP 610 smoke | PASS |
| `pip check` | `No broken requirements found` |
| `skill-discovery` validator | `Skill is valid!` |
| `delegate-task` validator | `Skill is valid!` |
| `skill-engineer` validator | `Skill is valid!` |

两个 skip 都是 Windows symlink privilege limitation（WinError 1314），不是功能失败或 collection error。

## Remaining Decisions

本轮没有删除 direct-mutation 子图，没有改变公共 Governance API，也没有改变双仓库 topology。现有消费者证据仍支持：保留 Evolution 公共 facade、保留双仓库和 immutable pin；direct-mutation 仅在后续弃用证据和独立消费者审计完成后再评估删除。任何 topology、公共 API 删除或长期治理所有权变化仍需用户单独决策。

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
REMOTE_DEPENDENCY_REPRODUCIBLE = PENDING
FINAL_INTEGRATION_BASELINE_READY = NO (remote publication pending)
PR_READY = NO (publication authorization pending)
USER_CHANGES_PRESERVED = YES
```
