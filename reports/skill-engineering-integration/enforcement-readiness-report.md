# Enforcement Readiness Report

## A. Final Status

```text
ENFORCED_READY
```

B1–B4 已在 clean checkout 和 immutable dependency pin 上重现通过。`ENFORCED_READY` 仅表示满足集成验收门禁，不自动开始 Production Rollout。

## B. B1 Root Cause

旧的 Provider timeout 已关闭。真实 Governance 随后正确发现目标 Skill 的两个 Required 缺陷：

1. `STP` 被声明为 implemented，但缺少从公开请求到 selector、dispatch、generation、artifact 和 validation 的直接端到端行为证据。
2. Registry 与公开 selector 各自维护范围，导致 `implemented` 能力与可公开选择能力发生漂移。

这两个 finding 是目标缺陷，不是 Governance false positive；本轮没有降低 evidence、coverage 或 fail-closed 要求。

## C. B1 Target Fix

- 新增公开 STP 请求的真实行为回归，验证正确 selector、生成路径、`STP.docx`、测试计划结构、Required sections 和 validation PASS。
- 以 Registry 为公开 selector 的单一能力来源：只有 `status=implemented` 且 `selection_scope=public` 的 profile 可公开选择。
- `registered_only` profile 显式使用 `selection_scope=none`，不再依赖硬编码白名单。
- 五文档公开范围固定为 `SRS`、`SDD_DETAIL`、`STP`、`STD`、`STR`；`STD` 语义统一为 `test-description`。
- 新增 Registry / selector 一致性与 capability consistency 回归，没有采用取并集或文件名关键词推断。

目标 focused 回归为 `19 passed`。最终目标全量为 `263 passed, 1 skipped, 4 failed`；四项均在目标父提交 `affc52a...` 逐项复现，为已知基线。

## D. Governance Hardening Found During B1

真实复核额外暴露并修正了两处治理契约缺陷：

- Provider 曾可提交 63 位 `target_digest`；Provider 与 Deliverable Contract schema 现要求小写十六进制 SHA-256：`^[a-f0-9]{64}$`。
- `scope_conflicts` 从自由文本改为 typed `DeliverableScopeConflict(summary, blocking, evidence_refs)`；只有 `blocking=true` 会 fail closed，已删除依赖 `no blocking conflict` 等文字的关键词推断。

这些修复已有回归，且最终 clean `skill-engineering` 全量为 `459 passed, 2 skipped`。

## E. B1 Revalidation

- Provider：`bundled.deliverable-contract`
- 目标：同一大型 `gjb438c-document-engineering` Skill
- Provider execution：`EXECUTED`
- Provider evidence：valid
- Deliverable coverage：`declared=5`、`verified=5`、`missing=0`
- Deliverable Contract：`PASS`
- Governance：`PASS`
- Publish authorization：`true`
- Governance ID：`gov_9a1900ac02a0b1a01412`
- KR-02 live window：约 `142.2s`
- Evidence：`D:/project/openspace-b2-live-a133a12e0e/kr02/kr02-provider-result.json`

之前两个 finding 均通过真实能力补齐而消失，不是被忽略、过滤或降级。

## F. B2 Kill / Restart

| Crash point | Result |
|---|---|
| Provider 完成、Governance 持久化前 | Governance 与 action 均不存在；`false_pass=0`、`false_apply=0`、`stale_replay=0` |
| Governance 持久化后、apply 前 | `PASS` 结果保留；source/candidate digest 重校验通过；无 apply 或 stale replay |
| `commit_status=committing` | restart 标记 `failed_needs_review`；target digest 未变化；无 false apply |
| Windows host kill | Job Object 回归证明 Provider child 不成为 orphan |

Evidence：

- `D:/project/openspace-b2-live-a133a12e0e/b2-live-results.json`
- `D:/project/openspace-b2-live-9707259318/b2-live-results.json`
- `D:/project/openspace-b2-live-2fd99ecacd/b2-live-results.json`

B2：`PASS`。

## G. B3 Shadow Full Evolution

三种案例均通过完整 `EvolutionEngine.process_job`：

| Case | Governance | Persisted | Commit | Trust |
|---|---|---|---|---|
| valid | `PASS` | 1 | committed | provisional |
| required_fail | `BLOCKED` | 1 | committed | provisional |
| provider_incomplete | `INCOMPLETE` | 1 | committed | provisional |

三案 `publish_authorized=false`，证明 shadow 模式保留真实 Gate 语义、持久化治理结果，但不阻断唯一 `EvolutionCommitter`。Evidence：`D:/project/openspace-b3-shadow-63d36f25db/b3-shadow-results.json`。

B3：`PASS`。

## H. B4 MCP Live Consistency

真实 MCP stdio transport 覆盖 `PASS`、Required `FAIL`、Shadow validation `FAIL` 和 Provider `ERROR/INCOMPLETE`。每个案例均以同一 `governance_id` 比较：

```text
Evolution Gate
EvidenceStore
Dashboard API
MCP stdio session 1
MCP stdio session 2
```

所有表面对 validation、coverage、integrity、gate、digests、reason codes、engine name/version/revision 和 evidence refs 的结果一致。Evidence：`D:/project/openspace-b4-mcp-af1dca2c85/b4-mcp-results.json`。

B4：`PASS`。

## I. Regression

```text
skill-engineering full: 459 passed, 2 skipped
skill-engineering quick validation: PASS
OpenSpace focused governance/runtime/cloud: 88 passed
OpenSpace non-benchmark: 110 passed, 1 known baseline failure
Dashboard npm run build: PASS
Target Skill full: 263 passed, 1 skipped, 4 known baseline failures
New regression failures: 0
```

Known baselines：

- OpenSpace：`test_bypass_mode_allows_ordinary_path_outside_workspace` 在 Windows path mapping 下将 `/etc/...` 映射到 `C:/etc/...`；相关文件本轮无 diff。
- Target Skill：`test_code_scope` fixture 缺失、merged-cover-header 和两项 CPython license hash bootstrap 失败；父提交逐项复现。
- Dashboard build 只有 Browserslist、chunk size 和 npm config warning。

## J. Release Closure

最终 immutable revisions：

```text
skill-engineering=0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c
OpenSpace=8a4c402308fbcd2df22d79cd08033837b73c36dd
dependency_pin=0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c
runtime_revision=0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c
```

Pin closure 使用非 editable Git 安装；PEP 610 `direct_url.json`、imported module path 和 `GovernanceEngine.engine_revision` 全部一致。安装 wheel 同时包含 runtime contract schemas。

## K. Final Decision

```text
B1=PASS
B2=PASS
B3=PASS
B4=PASS
Final Status=ENFORCED_READY
```

Next phase：Eligible for Production Rollout；本轮不自动执行 rollout。
