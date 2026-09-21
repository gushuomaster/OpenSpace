# Phase 6 Observability

## 已实现

- OpenSpace 继续以同一个 `EvidenceStore` 保存治理结果，结果同时生成 `governance:<id>` evidence ref 和 `governance_result_persisted` event。
- MCP 增加只读 `inspect_skill_governance`，支持按 `governance_id` 查询、按 `gate_status` 筛选和限制返回数量；不提供绕过门禁的写操作。
- Dashboard 增加 `/api/v1/evolution/governance` 列表和详情接口，Evolution 页面显示最近治理结果。
- UI 展示 `Validation`、`Coverage`、`Integrity`、`publish_authorized`、阻断原因、引擎版本和 revision，而不是压缩成单一 PASS。
- `EvolutionRunResult` 和 MCP evolution summary 保留治理结果，便于从一次生命周期运行追溯到治理证据。

## Trust / Upload 边界

治理通过只表示允许进入唯一 `EvolutionCommitter`。提交后的状态仍由 OpenSpace 的 `SkillTrustState` 控制：新修订先为 `PROVISIONAL`，只有独立成功运行证据满足现有阈值后才转为 `TRUSTED`。现有 upload trust gate 继续拒绝 `PROVISIONAL`，不接受 Governance PASS 作为绕过条件。

## 验证

- `python -m pytest tests/skill_engine tests/cloud tests/runtime -q`：85 passed。
- `npm run build`（`apps/dashboard`）：TypeScript 和 Vite 构建成功；仅报告既有 chunk size、Browserslist 和 npm audit 警告。

## 限制

Dashboard 当前是只读治理摘要，不替代 OpenSpace 原生 Decision、Candidate、Commit 或 Trust 页面；治理详情通过 evidence ref 和 MCP 查询获得。
