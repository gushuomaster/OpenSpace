# Phase 7 E2E / Dogfooding

## 已执行的回归路径

- `tests/skill_engine/test_governance_adapter.py`：覆盖 Shadow 持久化、Enforced required capability 未执行阻断、Committer 发布边界、candidate digest 变更阻断，以及 `off` 模式不调用治理引擎。
- `tests/skill_engine/test_evolution_retry_idempotency.py`：保持重复 Decision / Commit 的既有幂等路径。
- `tests/skill_engine/test_skill_trust_lifecycle.py`：保持 `PROVISIONAL → TRUSTED` 的独立成功 Evidence 晋级规则。
- `tests/cloud/test_upload_trust.py`：保持 `PROVISIONAL` upload 阻断和 `TRUSTED` upload 放行。
- skill-engineering 独立回归覆盖五文档声明、仅生成 SRS 的 deliverable mismatch，并返回 Coverage INCOMPLETE、publish unauthorized。

## 模式结果

| 模式 | 结果 |
| --- | --- |
| `off` | 不调用 GovernanceEngine、不写治理结果、不改变原 Commit 流程 |
| `shadow` | 执行并写入 EvidenceStore，但不阻断原 Commit |
| `enforced` | Gate 非 PASS 或 `publish_authorized=false` 时创建 OpenSpace candidate 并阻断 Commit |

## 尚未完成的真实运行项

本轮未启动真实 MCP 服务、Dashboard 浏览器会话或外部 Provider，因此以下项目没有被宣称为通过：真实 Create/Fix/Audit Only 端到端演练、Provider Required/Missing 的实际执行证据、线上并发 source mutation、进程崩溃后的真实重启恢复，以及五文档 Skill 在 OpenSpace 真实 authoring backend 中的完整 dogfooding。

这些缺口不会被测试名称替代；在运行环境提供真实 Provider、Skill authoring 和可控恢复注入后，应继续执行并追加证据。
