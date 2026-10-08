# Live Test Classification

本目录保留需要真实进程、运行时或 Provider 边界的验证脚本。分类只决定运行时机；不会削弱脚本中的现有断言，也不会把按需脚本视为已删除的保护。

## Required guardrails

以下脚本保护当前 Candidate/Evolution 架构的稳定不变量，必须保留，并在相关实现、依赖或恢复路径变化时作为回归运行：

- `b2_crash_recovery.py`：B2 crash/restart 与持久化恢复编排。
- `b2_runtime_parent.py`：B2 runtime 子进程入口。
- `b2_provider_parent.py`：B2 真实 Provider 子进程入口。
- `b3_shadow_evolution.py`：B3 完整 Evolution mutation 与 shadow Governance 回归。

## On-demand verification

以下脚本用于 MCP、production rollout、operational closure 或 Provider 专项。它们按对应发布或运维范围运行，不作为每次 Candidate/Evolution 基线的默认 gate：

- `b4_mcp_governance.py`：B4 Gate、storage、Dashboard 与 MCP 一致性。
- `production_rollout.py`：production rollout 证据采集。
- `operational_closure.py`：rollback 与共享 EvidenceStore 运维演练。
- `provider_workload.py`：真实 bundled-provider 有界工作负载与可靠性采样。

脚本的具体前置条件和参数以各文件自身的 CLI 与环境变量检查为准。
