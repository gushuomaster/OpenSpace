# Enforcement Readiness Matrix

验证基线：OpenSpace 分支 `codex/integrate-skill-engineering`，依赖锁定到 `skill-engineering@2c7019c93f6b510b199b1a20c40ce4104ee79c68`。本矩阵只记录已实际执行的命令或明确的未执行 blocker。

| ID | 场景 | Mode | Provider | Expected | Actual | Evidence | Status |
|---|---|---|---|---|---|---|---|
| ER-001 | 正常治理主链路 | enforced | real bundled Provider | PASS | 小型真实 Skill 已在 13.8s 产生 AVAILABLE structured output；大型 2.8MB/285 文件目标仍在 25s 超时，未取得完整 PASS | `engine/host_adapters.py` timing；live `adapter.invoke` | BLOCKED |
| ER-002 | Required capability FAIL | enforced | injected result | BLOCK | Governance API 返回 `BLOCKED`、不授权 | `tests/unit/test_governance_api.py` | PASS |
| ER-003 | Provider unavailable | enforced | unavailable | fail-closed | `UNAVAILABLE` / `NOT_STARTED`，无伪造 PASS | `tests/integration/test_host_provider_execution.py::test_configured_but_missing_optional_provider_uses_direct_core` | PASS |
| ER-004 | Provider crash | enforced | injected production adapter | fail-closed | 无 fallback 时 `INCOMPLETE`；有 FULL fallback 时明确记录 fallback | `tests/integration/test_host_provider_execution.py` | PASS |
| ER-005 | malformed output | enforced | injected production adapter | fail-closed | Provider execution failed，结构化结果不被接受 | `tests/integration/test_host_provider_execution.py` | PASS |
| ER-006 | shadow FAIL | shadow | injected result | record only | Adapter 级持久化且不授权通过；完整 Evolution live non-blocking 仍未完成 | `tests/skill_engine/test_governance_adapter.py` | PARTIAL |
| ER-007 | off | off | none | zero invocation | `GovernanceAdapter.evaluate()` 返回 `None`，EvidenceStore 无治理记录 | `test_off_adapter_does_not_invoke_or_persist_governance` | PASS |
| ER-008 | candidate CAS mismatch | enforced | real adapter | BLOCK | `candidate_digest_mismatch` | `test_candidate_digest_change_is_blocked_before_commit` | PASS |
| ER-009 | source digest mismatch | enforced | real adapter | BLOCK | `source_digest_mismatch` | `test_source_digest_change_is_blocked_before_commit` | PASS |
| ER-010 | interrupted run | enforced | real | no false PASS | 未执行真实进程中断点演练 | 无 | BLOCKER |
| ER-011 | restart recovery | enforced | real | recover safely | 现有 recovery/idempotency 回归 34 passed，但未执行真实 kill/restart 验证 | `tests/skill_engine/test_evolution_retry_idempotency.py`, `tests/skill_engine/evolution` | BLOCKER |
| ER-012 | Deliverable Contract FAIL | enforced | injected/provider contract | BLOCK | `deliverable_contract_failed` 硬阻断 | `test_failed_deliverable_contract_is_blocked_even_with_provider_pass` | PASS |
| ER-013 | Provider not executed | enforced | none | incomplete/block | `provider_not_selected` / `provider_not_executed`，不升级 Coverage | `tests/unit/test_governance_api.py`、OpenSpace adapter tests | PASS |
| ER-014 | capability coverage incomplete | enforced | real/injected | BLOCK/INCOMPLETE | Coverage 独立为 `INCOMPLETE` | 五文档 Golden Regression 与 Governance API tests | PASS |
| ER-015 | historical regression Skill | enforced | bundled contract | detect defect | 五文档声明但只生成 SRS 被识别为 contract incomplete | `tests/unit/test_governance_api.py`、`tests/integration/test_deliverable_contract_pipeline.py` | PASS |
| ER-016 | EvidenceStore/Dashboard live consistency | shadow | real adapter result | same source | 同一 governance_id 的 gate、candidate digest、记录数量一致 | live Flask Dashboard API + EvidenceStore probe | PASS |
| ER-017 | MCP live consistency | shadow | real adapter result | same source | 未启动真实 MCP/OpenSpace runtime，不能声称通过 | 无 | BLOCKER |

## 结论

Required 项 ER-001、ER-010、ER-011、ER-017 尚未通过；ER-006 只有 Adapter 级证据。因此当前不能升级 `ENFORCED_READY`。
