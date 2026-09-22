# Enforcement Readiness Report

## A. Final Status

```text
NOT_READY
```

本轮验证没有满足 `ENFORCED_READY` 的全部 Required 条件。Provider 适配器已增加真实 timing、隔离 Codex 配置和结构化输出完成判定；小型真实 Skill 可完成，但大型真实目标仍超时。真实 crash-point/restart recovery、Shadow full Evolution 和 MCP live consistency 尚未完成。

## B. Readiness Matrix

详见 [`enforcement-readiness-matrix.md`](enforcement-readiness-matrix.md)。矩阵中的每一项都区分了真实 Provider、生产 Adapter 故障注入、单元回归和未执行 blocker。

## C. Architecture Changes

本轮没有重构 Governance Adapter、Evolution Pipeline、EvidenceStore 或 ownership 边界。发现并修复一处阻断性实现缺陷：

1. **Symptom**：真实 `CodexSkillProviderAdapter` 调用被 Codex structured-output API 拒绝，先后报告 `allOf`、外部 `$ref`、`uniqueItems`、缺少 `type` 和 required-key 不完整。
2. **Root cause**：`schemas/provider-result.schema.json` 使用了目标 response-format 子集不支持的 JSON Schema 关键字，并把嵌套 contract 作为外部引用。
3. **Minimal fix**：将 Provider response schema 改为本地 `$defs`、显式 `type`、无 `allOf`/`uniqueItems`，并让可选嵌套结果以 `null` 明确出现在 structured-output required 集合中；`normalize_provider_result()` 始终以相同形状校验。
4. **Regression**：新增 schema compatibility 测试；`skill-engineering` 全量回归保持通过。
5. **Live completion fix**：`engine/host_adapters.py` 采用隔离 Codex 配置、stdout/stderr 并发 drain、结构化输出稳定完成判定和 Provider timing 快照；新增子进程延迟清理回归。

## D. Real Provider Evidence

- Provider：`bundled.deliverable-contract`
- Discovery：`build_default_provider_adapters()` 返回 `AVAILABLE`，资源为 `providers/capability-contract-provider`
- Selection：Adapter 按 `DELIVERABLE_CONTRACT` 选择
- Execution：真实 `codex exec --ephemeral --ignore-user-config --ignore-rules --sandbox read-only` 已启动
- Result：小型目标在约 13.8 秒写出 `AVAILABLE` structured output，适配器在子进程清理未结束时安全消费；大型 2.8MB/285 文件目标在 25 秒仍超时
- Evidence：timing 记录了 `spawned_ms`、`first_output_ms`、`parsed_ms`、`schema_validated_ms`、`pid`、stdout/stderr bytes、target bytes/file count 和 timeout reason；真实大型目标的 stderr 显示 Codex 工具调用被宿主 policy 拒绝后未完成检查
- Gate：应为 `INCOMPLETE/BLOCKED`，不能 PASS

因此，Provider 的“小型真实执行完成”已通过，但目标 Skill 的完整 PASS/FAIL 与大型目标运行仍未通过；不能把小型 fixture 或生产 Adapter 注入式测试替代为真实目标外部执行通过。

## E. Fault Injection

生产 `CodexSkillProviderAdapter` 的注入式回归已覆盖：

- unavailable：`ProviderExecution.NOT_STARTED`，无伪造执行证据
- crash：无 FULL fallback 时 Gate `INCOMPLETE`
- malformed response：normalize/schema 拒绝，execution failed
- semantic finding：required Provider finding 进入 Gate FAIL
- timeout：大型真实 bundled Provider 仍超时；另有 Adapter timeout 转换测试路径
- completion：真实小型目标在子进程退出码非零但结构化输出稳定时被正确消费；不接受不完整/不稳定输出

本轮没有把 Provider crash/timeout 当成成功；shadow/enforced 的完整 live external run 仍是 blocker。

## F. CAS Results

- Candidate mutation：`candidate_digest_mismatch`，commit 前阻断
- Source mutation：`source_digest_mismatch`，commit 前阻断
- Stale GovernanceResult replay：旧 result 对新 candidate 的 integrity verification 返回 `candidate_digest_mismatch`

对应 OpenSpace 回归为 `tests/skill_engine/test_governance_adapter.py`。

## G. Crash Recovery

以下真实 crash points 尚未完成 kill/restart 演练：candidate created、governance started、provider started/completed、result persisted、before apply、during apply。现有 OpenSpace recovery 代码仍保留，但没有用本轮实际进程证据证明这些点全部可恢复，因此列为 Required blocker。

已运行 OpenSpace recovery/idempotency 回归：`34 passed`；这不是对真实进程 kill/restart 的替代证据。

## H. Dogfooding

本轮没有声称完成真实 Codex/Agent 五案例 dogfooding。缺少可复现的真实 authoring session、Provider 成功结果和可控 crash harness；五文档 mismatch 仅有独立 Governance regression 证据。

## I. Regression

```text
skill-engineering full suite: 448 passed, 2 skipped
skill-engineering focused Provider/contract: 69 passed; host/fallback: 11 passed; manifest/deliverable: 18 passed
OpenSpace focused governance/skill/cloud/runtime: 88 passed
OpenSpace non-benchmark suite: 110 passed, 1 failed
Dashboard build: PASS
Skill validation: PASS
New regression failures: 0
```

OpenSpace 唯一失败为 `WINDOWS_PATH_COMPAT_001`：Windows 下既有测试将 `/etc/mailman3/mailman.cfg` 解析成 `C:\etc\mailman3\mailman.cfg`。该断言已存在于 `upstream/main`，当前集成未修改相关 grounding 代码；因此为 known baseline failure，不是新回归。

## J. Known Debt / Blockers

1. `ER-001`：大型真实 bundled Provider execution timeout，尚未取得目标 Skill 的真实 PASS/FAIL 闭环。
2. `ER-010/ER-011`：没有真实进程中断和重启恢复证据。
3. `ER-006`：shadow FAIL 的“不阻断完整 Evolution”尚未通过 live runtime 证明。
4. Dashboard 与 EvidenceStore 的同一 governance_id live consistency 已通过；MCP/OpenSpace runtime live consistency 尚未启动服务验证。
5. OpenSpace 保留 1 个既有 Windows baseline failure；benchmarks 仍受可选 `harbor` 依赖影响。

## K. Final Decision

由于真实 Provider 主链路和 crash/restart Required 项未通过，最终状态保持：

```text
NOT_READY
```

## L. Live Runtime Closure

| Blocker | Root cause / action | Live status |
|---|---|---|
| B1 Real Provider | Isolated Codex startup and structured-output completion detection fixed; small fixture completes, large target remains blocked by tool-policy retries and timeout | BLOCKED |
| B2 Crash / restart | Existing recovery/idempotency tests pass, but no real process kill/restart evidence | BLOCKED |
| B3 Shadow full Evolution | Adapter-level shadow persistence exists; full live Evolution non-blocking run not executed | BLOCKED |
| B4 Surface consistency | EvidenceStore ↔ Dashboard same-run probe passes; MCP/OpenSpace runtime probe not executed | PARTIAL |

The current evidence therefore remains `NOT_READY`; no Required blocker is silently promoted from unit or adapter evidence to live readiness.

下一步只能在可用的 Codex Provider 服务、真实 OpenSpace 运行实例和可控 crash/restart harness 中继续验证；不得通过降低 Gate、伪造 Provider evidence 或把注入式测试改称真实 E2E 来升级状态。
