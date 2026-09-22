# Enforcement Readiness Report

## A. Final Status

```text
NOT_READY
```

本轮验证没有满足 `ENFORCED_READY` 的全部 Required 条件。真实 bundled Provider 已被发现并启动，但结构化请求在 schema 修复后仍于 120 秒超时；真实 crash-point/restart recovery、MCP live consistency 和 Agent dogfooding 尚未完成。

## B. Readiness Matrix

详见 [`enforcement-readiness-matrix.md`](enforcement-readiness-matrix.md)。矩阵中的每一项都区分了真实 Provider、生产 Adapter 故障注入、单元回归和未执行 blocker。

## C. Architecture Changes

本轮没有重构 Governance Adapter、Evolution Pipeline、EvidenceStore 或 ownership 边界。发现并修复一处阻断性实现缺陷：

1. **Symptom**：真实 `CodexSkillProviderAdapter` 调用被 Codex structured-output API 拒绝，先后报告 `allOf`、外部 `$ref`、`uniqueItems`、缺少 `type` 和 required-key 不完整。
2. **Root cause**：`schemas/provider-result.schema.json` 使用了目标 response-format 子集不支持的 JSON Schema 关键字，并把嵌套 contract 作为外部引用。
3. **Minimal fix**：将 Provider response schema 改为本地 `$defs`、显式 `type`、无 `allOf`/`uniqueItems`，并让可选嵌套结果以 `null` 明确出现在 structured-output required 集合中；`normalize_provider_result()` 始终以相同形状校验。
4. **Regression**：新增 schema compatibility 测试；`skill-engineering` 全量回归保持通过。

## D. Real Provider Evidence

- Provider：`bundled.deliverable-contract`
- Discovery：`build_default_provider_adapters()` 返回 `AVAILABLE`，资源为 `providers/capability-contract-provider`
- Selection：Adapter 按 `DELIVERABLE_CONTRACT` 选择
- Execution：真实 `codex exec --ephemeral --sandbox read-only` 已启动
- Result：实际执行超时（120 秒），未生成可接受 ProviderResult
- Evidence：Codex CLI 输出的 structured-output schema 错误已在第一次执行中暴露并修复；第二次执行越过 schema 错误后以 `TimeoutError` 结束
- Gate：应为 `INCOMPLETE/BLOCKED`，不能 PASS

因此，Provider 的“真实执行成功”尚未通过；不能把生产 Adapter 的注入式测试替代为真实外部执行通过。

## E. Fault Injection

生产 `CodexSkillProviderAdapter` 的注入式回归已覆盖：

- unavailable：`ProviderExecution.NOT_STARTED`，无伪造执行证据
- crash：无 FULL fallback 时 Gate `INCOMPLETE`
- malformed response：normalize/schema 拒绝，execution failed
- semantic finding：required Provider finding 进入 Gate FAIL
- timeout：真实 bundled Provider 120 秒超时；另有 Adapter timeout 转换测试路径

本轮没有把 Provider crash/timeout 当成成功；shadow/enforced 的完整 live external run 仍是 blocker。

## F. CAS Results

- Candidate mutation：`candidate_digest_mismatch`，commit 前阻断
- Source mutation：`source_digest_mismatch`，commit 前阻断
- Stale GovernanceResult replay：旧 result 对新 candidate 的 integrity verification 返回 `candidate_digest_mismatch`

对应 OpenSpace 回归为 `tests/skill_engine/test_governance_adapter.py`。

## G. Crash Recovery

以下真实 crash points 尚未完成 kill/restart 演练：candidate created、governance started、provider started/completed、result persisted、before apply、during apply。现有 OpenSpace recovery 代码仍保留，但没有用本轮实际进程证据证明这些点全部可恢复，因此列为 Required blocker。

## H. Dogfooding

本轮没有声称完成真实 Codex/Agent 五案例 dogfooding。缺少可复现的真实 authoring session、Provider 成功结果和可控 crash harness；五文档 mismatch 仅有独立 Governance regression 证据。

## I. Regression

```text
skill-engineering full suite: 446 passed, 2 skipped
skill-engineering focused Provider/contract: 69 passed; host/fallback: 11 passed; manifest/deliverable: 18 passed
OpenSpace focused governance/skill/cloud/runtime: 88 passed
OpenSpace non-benchmark suite: 110 passed, 1 failed
Dashboard build: PASS
Skill validation: PASS
New regression failures: 0
```

OpenSpace 唯一失败为 `WINDOWS_PATH_COMPAT_001`：Windows 下既有测试将 `/etc/mailman3/mailman.cfg` 解析成 `C:\etc\mailman3\mailman.cfg`。该断言已存在于 `upstream/main`，当前集成未修改相关 grounding 代码；因此为 known baseline failure，不是新回归。

## J. Known Debt / Blockers

1. `ER-001`：真实 bundled Provider execution timeout，尚未取得真实 PASS 结果。
2. `ER-010/ER-011`：没有真实进程中断和重启恢复证据。
3. `ER-006`：shadow FAIL 的“不阻断完整 Evolution”尚未通过 live runtime 证明。
4. MCP 与 Dashboard 的 live response consistency 未启动服务验证；静态接口和 focused build/test 通过不等于 live E2E 通过。
5. OpenSpace 保留 1 个既有 Windows baseline failure；benchmarks 仍受可选 `harbor` 依赖影响。

## K. Final Decision

由于真实 Provider 主链路和 crash/restart Required 项未通过，最终状态保持：

```text
NOT_READY
```

下一步只能在可用的 Codex Provider 服务、真实 OpenSpace 运行实例和可控 crash/restart harness 中继续验证；不得通过降低 Gate、伪造 Provider evidence 或把注入式测试改称真实 E2E 来升级状态。
