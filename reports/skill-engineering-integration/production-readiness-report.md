# Production Readiness Report

## Final Status

```text
NOT_READY
```

本报告是独立的 Production Rollout 结论，不回滚此前已经完成的 `ENFORCED_READY`。当前状态为：

```text
ENFORCED_READY
        ↓
Production Rollout evidence collected
        ↓
NOT_READY for PRODUCTION_READY
```

原因不是已验证的 Governance 合约失效；独立 rollback 已通过，但真实持续 workload、off 全链路和真实 Provider reliability/timeout 分布仍不足，shared EvidenceStore 也尚未与真实 Provider workload 对齐。

## Immutable Revisions

```text
OpenSpace rollout baseline=90478ec39b52d4d478a341cc62eddfec07119e99
skill-engineering=0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c
engine_version=1.0.3
```

## Rollout Stages

### Stage 0 — off baseline

受控 harness 在 `off` 下验证：Governance invocation=0、Provider invocation=0、Evidence persistence=0，且不改变治理结果。该证据只覆盖 GovernanceAdapter 及其输入对象，尚未覆盖真实 OpenSpace Create、Modify、Fix、Evolution、Apply 全链路，因此 Stage 0 为 `PARTIAL`。

### Stage 1 — shadow rollout

已执行完整 B3 shadow Evolution、B4 MCP/Evidence/Dashboard 一致性和受控 invalid/provider-error workload：

- `PASS` 继续执行并持久化；
- `BLOCKED`、`INCOMPLETE` 继续执行但不授权；
- provider error 被记录，不静默降级；
- 五文档历史 mismatch、required capability 未执行和 coverage incomplete 均未出现 false PASS。

Stage 1 为 `PASS_WITH_WARNINGS`，因为真实长期 workload 样本还不足。

### Stage 2 — enforced opt-in

受控 enforced valid/invalid/provider failure 已验证；真实 B2 KR-03 证明 Governance PASS、CAS 重校验通过后才可授权，B2 KR-04 证明中断恢复为 `failed_needs_review`。Stage 2 暂不扩大为全局默认，结论为 `PASS_WITH_WARNINGS`。

### Stage 3 — default-mode evaluation

本轮不修改默认模式。基于当前样本，推荐默认保持：

```text
shadow
```

理由：shadow 已具备可观测性和 fail-closed 语义；rollback compatibility 已通过，但真实 Provider 稳定性、持续 workload p95/p99 和与真实 workload 对齐的 Evidence retention 尚未完成生产级验证。

## Operational Closure

### O1 — Off Full Lifecycle

`off` 模式的 adapter 级检查仍满足 invocation=0、provider invocation=0、persistence=0；但本轮尚未在真实 OpenSpace entrypoint 中完整跑通 Create、Modify、Fix、Apply（以及独立 Evolution）全链路。因此 `O1=BLOCKED`，不能把局部 off 证据升级为 full lifecycle PASS。

### O2 — Sustained Real Provider Workload

本轮执行了 3 个真实 bundled Provider runs，目标为 OpenSpace `remember` Skill（2 files，3469 bytes）：

```text
runs=3
completed=2
semantic PASS=2
Provider ERROR=1
Provider UNAVAILABLE=1
timeout=0
completion rate=66.7%
error rate=33.3%
orphan process delta=0
```

Provider duration preliminary distribution：

```text
p50=88.581426s
p95=128.550179s
max=128.550179s
```

其中两次成功耗时约 `48.613s`、`76.028s`，一次 `UNAVAILABLE` 耗时约 `128.550s`。这已经暴露出生产可靠性风险，但样本不足 20、未覆盖 medium/large/invalid/multi-file workload，因此 `O2=BLOCKED`，`POC-03=PARTIAL`、`POC-04=BLOCKED`。

### O3 — Independent Rollback-to-Pinned-Release

在独立 worktree 中执行：

```text
current release: 90478ec
rollback target: d990347
skill-engineering: 0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c
```

rollback 后保留原 EvidenceStore，不清库、不重建历史状态，并验证：

- historical GovernanceResult 可读；
- Dashboard 查询返回 `200`；
- MCP `inspect_skill_governance` 返回同一 historical governance id；
- 新 valid case 为 `PASS` + authorized；
- 新 invalid case 为 `BLOCKED` + unauthorized；
- source integrity 为 `PASS`。

因此 `O3=PASS`，证据为 `D:/project/operational-rollback/verify.json`。

### O4 — Shared EvidenceStore Long-Term Growth

同一个 `EvidenceStore` 连续执行 24 次 Governance run：

```text
initial records=0
final records=24
initial size=4096 bytes
final size=4096 bytes
average growth/run=0 bytes (SQLite page allocation remained stable)
early/middle/latest readable=true
query p50=0.011672s
```

没有清空数据库或删除旧记录，也没有发现重复 GovernanceResult。由于该 24-run workload 是 synthetic Governance evaluation 而不是 O2 的真实 Provider workload，`O4=PARTIAL`，不能单独关闭长期生产存储 blocker。

## Reliability and Quality

真实 B2 结果：

- Provider 完成、持久化前 kill：`governance_count=0`、`action_count=0`、false pass/apply/stale replay 均为 0；
- Governance 持久化、apply 前 kill：Governance PASS 保留，source/candidate digest 重校验通过，无 apply；
- commit 中断：恢复为 `failed_needs_review`，target digest 未变化；
- Windows Provider child cleanup：相关 engine regression `2 passed`。

受控 quality cases：

- known invalid：`BLOCKED` 或 `INCOMPLETE`，无 false PASS；
- shadow invalid/provider error：继续运行且结果持久化；
- enforced invalid/provider error：不授权；
- `AUDIT_ONLY`：`publish_authorized=false`，不进入 mutation。

未完成项：尚未对真实 workload 样本完成系统化 false-positive review，也未完成足够长的 Provider timeout/error 分布采样。

## Performance

受控 20-run Governance 调用延迟（秒）：

| Mode | p50 | p95 | max | 说明 |
|---|---:|---:|---:|---|
| off | 0.000002 | 0.000003 | 0.000007 | 不调用治理引擎 |
| shadow | 0.008164 | 0.010507 | 0.010805 | synthetic contract evaluation + persistence |
| enforced | 0.002813 | 0.005985 | 0.006256 | synthetic contract evaluation + persistence |

受控 Governance 数字不代表真实 Provider 端到端延迟；本轮真实 Provider 3-run preliminary 分布已单独记录，但此前真实大型 Provider 约 `142s` 的结果仍需和 medium/large workload 一起纳入正式分布。由于真实持续 workload 分布尚未完成，`performance_profile_complete=BLOCKED`。

## Concurrency and Idempotency

- 2 路并发：2 个 unique governance_id，两个 EvidenceStore 各 1 条记录；
- 4 路并发：4 个 unique governance_id，四个 EvidenceStore 各 1 条记录；
- duplicate request：同一 identity 重试复用同一 governance_id，记录数保持 1；
- OpenSpace Evolution retry/idempotency 回归：通过。

## Evidence Growth

受控 harness 连续执行 10 次，每次独立 EvidenceStore 为 4096 bytes，未写入 repository snapshot；这证明受控路径没有无界复制，但没有替代共享生产 DB 的长期 retention、deduplication 和磁盘增长验证，因此标记 `PARTIAL`。

## Rollback and Operational Safety

已覆盖：CAS、replay protection、crash recovery、Job Object cleanup、MCP/Dashboard/Evidence 一致性。

独立 rollback drill 已完成：从 `90478ec` 回到隔离 worktree `d990347`，历史 Evidence/Governance、Dashboard、MCP 和新 valid/invalid case 均通过。剩余风险是 O1/O2/O4，而不是 rollback compatibility。

## Regression

```text
skill-engineering full suite: 459 passed, 2 skipped
skill-engineering quick validation: Skill is valid!
OpenSpace governance/cloud: 86 passed
OpenSpace runtime: 2 passed
OpenSpace non-benchmark: 111 passed, 1 known baseline failure
Dashboard build: PASS
Provider cleanup regression: 2 passed
New rollout regression: 0
```

Known baseline 仍为 OpenSpace Windows `/etc/...` path mapping；本轮未修改相关 grounding 逻辑。

## Production Blockers

1. `O1/POC-01`：真实 OpenSpace entrypoint 的 off Create/Modify/Fix/Apply 全链路尚未完成。
2. `O2/POC-02/POC-04`：真实 Provider 只有 3 runs，出现 1 次 `UNAVAILABLE`，尚未完成 20-run、多规模、invalid/multi-file workload。
3. `POC-03`：真实 Provider latency 只有 preliminary p50/p95/max，不能代表稳定生产分布。
4. `O4/POC-07`：shared store 24-run 仍是 synthetic Governance workload，尚未与真实 Provider workload 对齐。

因此当前最终结论为：

```text
NOT_READY
recommended_default_mode=shadow
PRODUCTION_READY=false
```

本轮不修改默认 mode，不向 `upstream` push，不启动全局 enforced rollout。下一步应只针对上述 blocker 补真实 workload、timeout 分布和 rollback 证据。
