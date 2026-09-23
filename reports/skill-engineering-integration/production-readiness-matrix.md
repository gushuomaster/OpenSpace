# Production Readiness Matrix

## 验证基线

- OpenSpace integration revision：`d99034791ea5b7c2ee2c661735e18ee39c3b961d`
- skill-engineering pin：`0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c`
- Runtime engine revision：`0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c`
- 受控 rollout artifact：`D:/project/production-rollout-live-3/production-rollout-results.json`
- 真实 crash/restart artifact：`D:/project/production-rollout-b2/b2-live-results.json`

## Matrix

| ID | 场景 | Expected | Actual | Evidence | Status |
|---|---|---|---|---|---|
| PR-001 | off baseline | zero governance/provider invocation | 受控 workload 中 invocation=0、persisted=0；尚未覆盖真实 Create/Modify/Fix/Apply 全链路 | `production-rollout-results.json`; `test_off_adapter_does_not_invoke_or_persist_governance` | PARTIAL |
| PR-002 | shadow valid | observe + continue | PASS 持久化，shadow 不授权；B3 valid 继续 commit | B3 artifact；rollout harness | PASS |
| PR-003 | shadow invalid | FAIL + continue | BLOCKED 持久化，Evolution 继续；B3 required_fail 通过 | B3 artifact；rollout harness | PASS |
| PR-004 | shadow provider error | error recorded + continue | INCOMPLETE 持久化，shadow 不阻断；provider error 语义可见 | B4 provider_error；rollout harness | PASS |
| PR-005 | enforced valid | allow | 受控 enforced valid 为 PASS/authorized；真实 B2 KR-03 重校验通过 | rollout harness；B2 KR-03 | PASS |
| PR-006 | enforced invalid | block | 受控 enforced invalid 为 BLOCKED/no authorization；尚未完成完整 Evolution invalid live case | rollout harness；`test_enforced_adapter_blocks_required_unexecuted_capability` | PARTIAL |
| PR-007 | provider unavailable | safe semantics | `available=false`/`selected=false` 在 off 不调用、shadow 记录 INCOMPLETE、enforced 不授权 | rollout harness `provider_unavailable` | PASS |
| PR-008 | provider timeout | safe semantics | 合成 timeout observation 在 shadow/enforced 均不授权；真实长期 timeout 分布未测 | rollout harness | PARTIAL |
| PR-009 | concurrent governance | isolated | 2 路、4 路各自 unique governance_id，EvidenceStore count=1 | rollout harness | PASS |
| PR-010 | duplicate request | idempotent/safe | 相同 identity 重试复用同一 governance_id，持久化记录仍为 1；Evolution 幂等回归通过 | rollout harness；`test_evolution_retry_idempotency.py` | PASS |
| PR-011 | restart recovery | safe | KR-02/KR-03/KR-04 真实 kill/restart 通过；无 false pass/apply/stale replay | `D:/project/production-rollout-b2/b2-live-results.json` | PASS |
| PR-012 | Evidence growth | bounded/understood | 10 次受控运行 DB=4096 bytes；未覆盖共享生产 DB 长期增长、压缩和 retention | rollout harness | PARTIAL |
| PR-013 | process cleanup | no orphan | engine Windows Job Object regression 2 passed；B2 OpenSpace cleanup complete | `test_host_provider_execution.py`; B2 logs | PASS |
| PR-014 | sustained workload | stable | 仅完成 20 次受控 Governance 调用；真实 Provider/多 Skill 长时间 workload 未完成 | rollout performance artifact | BLOCKED |
| PR-015 | rollback | reproducible | 已验证 crash recovery/backup safety，但未完成独立 rollback-to-pinned-release 演练 | B2 recovery artifact；无独立 rollback artifact | BLOCKED |

## Gate Status

- `off_baseline`：PARTIAL
- `shadow_rollout`：PASS_WITH_WARNINGS
- `known_invalid_detection`：PASS（已知五文档 mismatch 与 required/provider 缺陷均未被误放行）
- `false_positive_review`：PARTIAL（受控案例完成，真实 workload 样本不足）
- `false_negative_review`：PASS_WITH_WARNINGS（历史案例已覆盖，生产 workload 分布尚未覆盖）
- `enforced_opt_in`：PASS_WITH_WARNINGS
- `concurrency_isolation`：PASS
- `idempotency`：PASS
- `provider_reliability`：PARTIAL
- `performance_profile_complete`：BLOCKED
- `dependency_failure_semantics`：PASS_WITH_WARNINGS
- `restart_recovery`：PASS
- `process_cleanup`：PASS
- `evidence_growth_review`：PARTIAL
- `rollback`：BLOCKED
- `new_regression_failures`：PASS（仅既有 baseline）

结论：Production Readiness Gate 未满足，当前不能声明 `PRODUCTION_READY`。
