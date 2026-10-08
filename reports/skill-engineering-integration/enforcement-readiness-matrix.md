# Enforcement Readiness Matrix

验证基线：OpenSpace 分支 `codex/integrate-skill-engineering`，最终 pin commit `8a4c402308fbcd2df22d79cd08033837b73c36dd`。OpenSpace 依赖锁定到 `skill-engineering@0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c`，运行时加载 revision 与 pin 一致。

| ID | 场景 | Mode | Expected | Actual | Evidence | Status |
|---|---|---|---|---|---|---|
| ER-001 | 大型真实五文档治理主链路 | enforced | PASS / ALLOW | Provider 完成；`declared=5`、`verified=5`、`missing=0`；Deliverable Contract `PASS`；Governance `PASS`；`publish_authorized=true` | `D:/project/release-closure-worktrees/openspace-b2-live-23751005c1/kr02/kr02-provider-result.json` | PASS |
| ER-002 | Required capability FAIL | enforced | BLOCK | Governance 返回 `BLOCKED`、不授权 | `tests/unit/test_governance_api.py` | PASS |
| ER-003 | Provider unavailable | enforced | fail closed | `UNAVAILABLE` / `NOT_STARTED`，无伪造 PASS | `tests/integration/test_host_provider_execution.py` | PASS |
| ER-004 | Provider crash / malformed output | enforced | fail closed | 无 FULL fallback 时 `INCOMPLETE`；无效结构不被接受 | `tests/integration/test_host_provider_execution.py` | PASS |
| ER-005 | Provider available / selected / executed 分离 | enforced | 未执行不得 PASS | availability、selection、execution 与 evidence validity 独立记录 | Governance API、Host Provider 回归 | PASS |
| ER-006 | Shadow full Evolution | shadow | 记录但不阻断 | `PASS`、`BLOCKED`、`INCOMPLETE` 均持久化；三案仍由唯一 Committer 提交且进入 `provisional` | `D:/project/release-closure-worktrees/openspace-b3-shadow-7036f8150c/b3-shadow-results.json` | PASS |
| ER-007 | off | off | zero invocation | 不执行、不持久化、不影响 Commit | `test_off_adapter_does_not_invoke_or_persist_governance` | PASS |
| ER-008 | candidate CAS mismatch | enforced | BLOCK | `candidate_digest_mismatch` | `test_candidate_digest_change_is_blocked_before_commit` | PASS |
| ER-009 | source digest / revision mismatch | enforced | BLOCK | source 变化在 Commit 前阻断 | Governance Adapter 回归 | PASS |
| ER-010 | Provider 完成、Governance 持久化前 kill | enforced | no false PASS / apply | `governance_count=0`、`action_count=0`、`false_pass=0`、`false_apply=0`、`stale_replay=0` | `D:/project/release-closure-worktrees/openspace-b2-live-23751005c1/b2-live-results.json` | PASS |
| ER-011 | Governance 持久化后、apply 前 kill | enforced | recover safely | `PASS` 结果保留；source/candidate digest 重校验通过；无 apply 或 stale replay | `D:/project/release-closure-worktrees/openspace-b2-live-23751005c1/b2-live-results.json` | PASS |
| ER-012 | Commit 中途 kill | enforced | recover safely | restart 标记 `failed_needs_review`；target digest 未变化；无 false apply | `D:/project/release-closure-worktrees/openspace-b2-live-23751005c1/b2-live-results.json` | PASS |
| ER-013 | Deliverable Contract FAIL / missing | enforced | BLOCK / INCOMPLETE | FAIL 硬阻断；缺失产生 Coverage `INCOMPLETE` | Governance API 与五文档 Golden Regression | PASS |
| ER-014 | Provider child orphan | enforced | orphan=0 | Windows Job Object 回归证明宿主被 kill 后子进程退出 | `test_provider_child_exits_when_host_process_is_killed` | PASS |
| ER-015 | EvidenceStore / Dashboard consistency | shadow | same source | 同一 `governance_id` 的 gate、digest、reason、engine version 一致 | B4 live artifact | PASS |
| ER-016 | MCP transport/session consistency | shadow | same source | 真实 MCP stdio 两次独立 session 与 Evolution Gate、EvidenceStore、Dashboard API 完全一致 | `D:/project/release-closure-worktrees/openspace-b4-mcp-e757ca8803/b4-mcp-results.json` | PASS |
| ER-017 | Governance engine release provenance | release | immutable revision | OpenSpace pin、PEP 610 direct URL、loaded module 和 `engine_revision` 均为 `0c83c8e...` | `release-closure-reproduction.md`; B4 final artifact | PASS |
| RC-01 | Diff ownership | release | classified | ownership report records repo, owner, commit boundary and evidence | `release-closure-diff-ownership.md` | PASS |
| RC-02 | Task changes committed | release | immutable | engine packaging/revision fixes and OpenSpace pin are separate audited commits | git history | PASS |
| RC-03 | Immutable engine SHA | release | fixed | `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c` | engine origin/master | PASS |
| RC-04 | Dependency pin updated | release | same SHA | OpenSpace requires exact engine SHA | `pyproject.toml` | PASS |
| RC-05 | Runtime SHA matches pin | release | same SHA | direct URL and runtime revision match | final venv metadata | PASS |
| RC-06 | Clean checkout reproduction | release | reproducible | clean detached worktrees and non-editable venv | closure report | PASS |
| RC-07 | B1 pinned reproduction | enforced | PASS | five deliverables declared/verified, Governance PASS and authorized | B2 KR-02 artifact | PASS |
| RC-08 | B2 pinned reproduction | enforced | PASS | kill/restart and recovery scenarios pass | B2 final artifact | PASS |
| RC-09 | B3 pinned reproduction | shadow | PASS | shadow outcomes persist without blocking Committer | B3 final artifact | PASS |
| RC-10 | B4 pinned reproduction | shadow | PASS | MCP/DB/dashboard/evolution consistency and revision match | B4 final artifact | PASS |
| RC-11 | Regression closure | release | zero new | engine 459/2; OpenSpace 88 focused and 110+baseline; target four parent baselines | closure report | PASS_WITH_BASELINE |

## B1 关闭证据

- 原始真实缺陷不是 timeout：STP 缺少公开入口端到端行为证据，且 Registry 与公开 selector 存在重复声明漂移。
- 目标 Skill 已补公开 STP 请求到生成、结构、artifact 与 validation 的行为测试，并让 selector 从 Registry 的 `implemented + public` 状态派生；`registered_only` 明确不进入公开选择范围。
- 同一大型目标重新运行后，Provider 识别 `SRS`、`SDD_DETAIL`、`STP`、`STD`、`STR` 五项均已声明、可达、实现且有行为证据；`scope_conflicts` 仅剩显式 `blocking=false` 的信息项。
- KR-02 从启动到安全 kill/restart 验证结束的窗口约 `142.2s`；治理结果为 `PASS`，不是通过过滤、降级或忽略 Required finding 获得。

## 结论

B1、B2、B3、B4 的 clean/pinned live runtime closure 均为 `PASS`。所有 Required release closure 项通过；四个目标 Skill 测试失败均已在父提交复现并标识为已知基线。最终状态为 `ENFORCED_READY`，仅表示具备进入下一独立 Production Rollout 阶段的资格。
