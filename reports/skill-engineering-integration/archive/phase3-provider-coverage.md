# Phase 3 Provider / Coverage / Deliverable Contract

## Provider 状态

`GovernanceRequest` 和 `ProviderObservation` 明确区分：

```text
available
selected
executed
evidence_valid
```

Adapter 只翻译 Decision proposal contract 中声明的 Provider observation；Provider 的发现、选择和实际执行仍属于调用方/Provider 层，Adapter 不复制 Provider Engine。

以下状态不能生成 required capability PASS：

- available but not selected
- selected but not executed
- executed but evidence invalid
- selected provider identity 不匹配
- executed 但没有 evidence refs

## Coverage

`Validation PASS` 与 `Coverage COMPLETE` 在 Public API 中是独立字段。required capability 未执行时返回 `INCOMPLETE`，不会因为 Validation PASS 自动升级 coverage。

## Deliverable Contract

当 proposal contract 标记：

```json
{
  "required_capabilities": ["DELIVERABLE_CONTRACT"],
  "applicability": {"deliverable_contract": "required"}
}
```

Adapter 要求相应 deliverable contract 和 executed/evidence-valid Provider。契约缺失或状态为 `INCOMPLETE` 时，治理结果不会授权发布。

## 五文档 Golden Regression

`skill-engineering` Public API 的回归覆盖“声明五份文档但实际只生成 SRS”的形态：Provider/contract 结果不完整时，`coverage_status=INCOMPLETE`，`publish_authorized=false`。该检测属于独立 Governance 证据，不改变 OpenSpace 的文档生成实现。

## 当前限制

OpenSpace 目前没有把自身 grounding Provider registry 自动转换为 Governance ProviderObservation；正式 Provider 适配需要一个明确的 provider execution evidence source。现阶段可通过 proposal contract 的中立 Provider observation 注入，缺失时 Enforced 必须 fail closed。
