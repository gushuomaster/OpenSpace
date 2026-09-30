# Skill Candidate Governance Lifecycle Design

设计日期：2026-09-30
状态：待用户复核
范围：OpenSpace 远程 Skill Candidate 的 Acquisition、Quarantine、Governance、Install/Register

## 1. 目标

本设计只补齐一条真实链路：

```text
Codex / Agent
  -> OpenSpace Discovery
  -> Candidate Selection
  -> Acquisition
  -> Quarantine
  -> skill-engineering Governance
  -> Codex semantic confirmation
  -> candidate-bound receipt
  -> Install
  -> Registry / SkillStore
  -> Runtime Use
```

核心不变量：

1. Governance PASS 前，远程 Candidate 不得位于正式 Skill 根目录，不得进入正式 Registry 或 SkillStore。
2. Governance 检查、Codex semantic confirmation、receipt 和最终安装必须绑定同一份 Candidate bytes。
3. `BLOCKED`、`INCOMPLETE`、`INTEGRITY_MISMATCH` 或 Governance/Install error 均不得留下正式可用 Skill。
4. OpenSpace 继续拥有 Discovery、Acquisition、Quarantine、Install、Registry、SkillStore 和 Runtime state。
5. skill-engineering 继续拥有 Inspection、Provider、Evidence、Coverage、Integrity、Quality Gate 和 Managed Completion Receipt。
6. 本设计不合并 Repository，不扩展 Production Rollout，不修改现有 Evolution Governance 的职责。

## 2. 当前问题

当前单 Skill 云导入链为：

```text
cloud_browse_skills(action="import_skill")
  -> cloud_import_skill()
  -> _do_import_cloud_skill()
  -> OpenSpaceClient.import_skill()
  -> download + temporary extraction
  -> copy into a formal Skill root
  -> registry.register_skill_dir()
  -> SkillStore.sync_from_registry()
```

临时解压目录不是治理 quarantine。候选被复制到正式目录后立即注册，现有 `GovernanceAdapter` 没有参与这条路径。

另外存在两条旁路：

- `openspace-download-skill` 调用同一个直接导入实现；
- `import_package_bundle` 下载完成后会扫描包目录并把其中 Skill 注册到 Registry/SkillStore。

因此仅修改 MCP 的一个 action 不足以建立可靠安全边界。

## 3. 方案比较

### 3.1 推荐方案：OpenSpace 两阶段 lifecycle + 窄 Governance verifier

OpenSpace 将远程内容先物化为完整、不可作为正式 Skill 使用的 quarantine Candidate。Codex 针对该目录运行现有 skill-engineering phased workflow。安装边界通过一个面向真实 OpenSpace 消费者的窄 verifier 重新验证 confirmed outcome、receipt 和当前 Candidate digest，然后由 OpenSpace 完成安装与注册。

收益：

- 复用现有完整 Governance Pipeline；
- 保留 Codex semantic confirmation；
- 不把安装职责移入 skill-engineering；
- OpenSpace 不需要理解 skill-engineering 内部所有 bundle 类型；
- 不新增第二套 Gate 或 receipt。

代价：

- OpenSpace 需要一份最小 Candidate durable state；
- skill-engineering package boundary 需要暴露一个窄的验证能力，或等价地稳定导出现有验证函数；
- 现有 `import_skill` 的“立即可用”语义不能继续保持。

### 3.2 不推荐：OpenSpace 直接编排 skill-engineering 内部模块

OpenSpace 可以直接 import `PipelineOrchestrator`、serialization、`completion_receipt()` 和 `managed_status()`。

该方案不增加 wrapper，但会让 OpenSpace 依赖多个内部模型、序列化格式和 Gate 实现细节。任何 skill-engineering 内部调整都会扩大跨仓库兼容成本，因此不采用。

### 3.3 拒绝：单次 import 内自动完成治理

单次调用内完成下载、Provider、Gate 和安装，需要新增 LLM 决策层，或由程序替 Codex 生成 semantic confirmation。两者均改变现有治理权责，且无法证明是用户认可的语义判断，因此拒绝。

## 4. 责任边界

### 4.1 OpenSpace

OpenSpace 负责：

- 搜索并返回远程候选元数据；
- 记录 Agent/Codex 选择的远程 Candidate；
- 下载、解压和安全检查；
- 构造 quarantine 中的最终安装镜像；
- 保存 Candidate immutable manifest 和 mutable lifecycle state；
- 在安装边界调用 receipt verifier；
- 原子物化正式目录；
- 写入 Cloud/local binding；
- 更新 SkillStore 和 Registry；
- 同步失败时补偿回滚；
- 返回用户可见的 lifecycle status 和 next action。

### 4.2 skill-engineering

skill-engineering 负责：

- 对 quarantine payload 执行正式 `AUDIT`；
- 执行 Codex 明确选择的 Provider；
- 生成 Inspection、Validation、Coverage、Integrity 和 Gate evidence；
- 要求 Codex 对精确 artifact digest 做 semantic confirmation；
- 生成 `ManagedCompletionReceipt`；
- 在安装前重新验证 confirmed outcome、receipt 和 Candidate 当前 digest；
- 保持现有 Gate verdict 的语义：只返回 `PASS`、`FAIL`、`INCOMPLETE` 或 `ERROR`；
- 不执行安装。`BLOCKED`、`INTEGRITY_MISMATCH` 等是 OpenSpace Candidate lifecycle 对 Gate/完整性结果的映射，不是新的 Gate verdict。

### 4.3 Codex / Agent

Codex / Agent 负责：

- 判断是否需要远程 Skill；
- 选择一个具体候选和本地 placement；
- 选择适用的专业 Provider 和 deliverable applicability；
- 编写 Governance decision records；
- 查看 Validation evidence；
- 仅对精确 digest 提交 `confirmed_by=CODEX` 的 semantic confirmation；
- 将 confirmed Governance output 提交到 OpenSpace 安装边界。

## 5. Quarantine 与 Candidate 数据布局

Quarantine 必须位于 OpenSpace 管理的数据根目录，且不在任何已配置、默认或动态注册的 Skill root 下。调用方传入的 `target_dir` 只能表示预期正式安装父目录，不能控制 quarantine 位置。

逻辑布局：

```text
<openspace-state>/candidates/quarantine/<candidate-id>/
  candidate-manifest.json
  state.json
  governance/
    confirmed-outcome.json       # 收到后保存
    candidate-binding.json       # verifier PASS 后原子写入
  payload/
    <final-skill-directory>/
      SKILL.md
      ...
```

具体目录名不是 Public API；实现可以根据现有 OpenSpace state root 调整，但必须满足：

- quarantine root 不会被 Registry 自动扫描；
- payload 与 lifecycle metadata 分离；
- Governance target 仅为 `payload/<final-skill-directory>`；
- 修改 `state.json` 或保存 Governance output 不会改变 Candidate content digest；
- 所有记录使用 UTF-8 和原子替换写入。

### 5.1 最终安装镜像

Governance 前，OpenSpace 必须完成所有会改变 Skill 目录 bytes 的准备工作，包括：

- 安全 ZIP 解压；
- 确认存在唯一 Skill root 和 `SKILL.md`；
- 路径逃逸和符号链接检查；
- 本地 Skill ID 的确定；
- 本地分类/placement 的确定；
- 需要随 Skill 安装的稳定 sidecar 文件。

Governance 后不得再向 payload 增加 `.skill_id`、Cloud binding sidecar、分类文件或其他内容。运行时 binding 中会变化的字段应保存在 Candidate manifest 或 mapping store，不得在 PASS 后改写已治理 payload。

## 6. Candidate Identity

Candidate identity 使用 manifest identity、content digest 和 Governance binding 三层绑定。

### 6.1 Immutable Candidate Manifest

Immutable manifest 至少包含：

```text
schema_version
candidate_id
source_type
cloud_skill_id
authoritative_revision_or_manifest_hash
source_integrity_status
candidate_digest
final_skill_id
final_directory_name
intended_install_parent
local_category_path
acquired_at
```

`candidate_id` 从 manifest 的 canonical identity projection 计算。该 projection 只包含来源身份、来源完整性声明、`candidate_digest`、最终 Skill identity 和 placement；明确排除 `candidate_id` 自身、`acquired_at`、文件路径表示差异以及 mutable lifecycle status，避免循环或非确定性 identity。manifest 写入后不得原地修改；来源、payload 或 placement 发生变化时产生新的 Candidate。

### 6.2 Content Digest

`candidate_digest` 必须使用与 skill-engineering artifact inventory 相同的目录 digest 语义计算。安装边界不得维护一个近似或平行 hash 算法。

### 6.3 Candidate Governance Binding

现有 `ManagedCompletionReceipt` 已可靠绑定 artifact bytes、validation bundle 和 semantic confirmation，但不直接携带 OpenSpace 的 `candidate_id` 或 placement。为避免把 Candidate A 的 receipt 重用于相同 bytes、不同 identity/placement 的 Candidate B，OpenSpace 在 verifier PASS 后原子写入一份 immutable binding record，至少包含：

```text
schema_version
candidate_id
candidate_manifest_digest
canonical_payload_path
candidate_digest
inspection_id
validation_id
managed_completion_receipt_digest
bound_at
```

该记录不是第二套 Quality Gate 或第二种 receipt；它只把既有 `ManagedCompletionReceipt` 绑定到 OpenSpace-owned Candidate context。它不能单独授权安装，安装时仍必须重新验证完整 confirmed outcome、原 receipt 和当前 payload。

完整绑定关系为：

```text
candidate_id
  -> immutable candidate manifest
  -> candidate_digest

ManagedCompletionReceipt
  -> inspection_id
  -> validation bundle digest
  -> semantic confirmation digest
  -> candidate_digest

install request
  -> candidate_id
  -> immutable candidate manifest digest
  -> candidate-governance binding
  -> confirmed Governance output
  -> recomputed ManagedCompletionReceipt
```

只有 manifest identity、binding record、receipt、Governance outcome 和当前 payload 全部一致时才允许安装。Candidate directory 或 canonical payload path 变化也使旧 binding 失效。

## 7. Lifecycle 状态

OpenSpace 只维护 Candidate acquisition/install 状态，不复制 skill-engineering 内部 inspection state machine。

```text
ACQUIRING
  -> QUARANTINED
  -> GOVERNANCE_PENDING
  -> GOVERNANCE_PASSED
  -> INSTALLING
  -> INSTALLED
```

终止或可诊断状态：

```text
ACQUISITION_FAILED
GOVERNANCE_BLOCKED
GOVERNANCE_INCOMPLETE
GOVERNANCE_ERROR
INTEGRITY_MISMATCH
INSTALL_FAILED
```

状态规则：

| Current | Event | Next | Formal install/registration allowed |
|---|---|---|---|
| `ACQUIRING` | download/extract/normalize succeeds | `QUARANTINED` | no |
| `QUARANTINED` | Governance work is handed to Codex | `GOVERNANCE_PENDING` | no |
| `QUARANTINED` / `GOVERNANCE_PENDING` | verified Gate PASS + valid receipt | `GOVERNANCE_PASSED` | not yet |
| `QUARANTINED` / `GOVERNANCE_PENDING` | Gate `FAIL` | `GOVERNANCE_BLOCKED` | no |
| `QUARANTINED` / `GOVERNANCE_PENDING` | missing Provider/evidence/source proof | `GOVERNANCE_INCOMPLETE` | no |
| `QUARANTINED` / `GOVERNANCE_PENDING` | Gate/framework `ERROR` | `GOVERNANCE_ERROR` | no |
| any pre-install state | manifest/receipt/current digest mismatch | `INTEGRITY_MISMATCH` | no |
| `GOVERNANCE_PASSED` | install transaction starts | `INSTALLING` | no runtime use yet |
| `INSTALLING` | filesystem, binding, SkillStore and Registry complete | `INSTALLED` | yes |
| `INSTALLING` | any step fails and compensation completes | `INSTALL_FAILED` | no |

`BLOCKED` 或 `INCOMPLETE` Candidate 保留在 quarantine 供诊断，不自动删除，也不会被 Registry 扫描。

## 8. Governance Protocol

### 8.1 Audit target

治理目标是 quarantine 中的完整最终安装镜像。使用现有 phased workflow：

```text
inspect --mode AUDIT --target <candidate-payload>
  -> Codex decisions
validate --inspection <inspection-bundle>
  -> Codex semantic confirmation for exact validation.artifact_digest
confirm
  -> PASS / FAIL / INCOMPLETE / ERROR
  -> ManagedCompletionReceipt when formally complete
```

这里的 `AUDIT` 是针对 Candidate payload 的只读治理；因此 `validate` 不把 Candidate 当作 repair candidate 重新 staging。只有现有的 `AUDIT_REPAIR` / `TARGETED_REPAIR` 场景才使用 `--candidate`，本设计不把远程安装转化为修复流程。

本轮不调用 skill-engineering `apply`。`apply` 用于修复现有 Skill 的原子替换，不是远程 Candidate 安装器。

正式可安装结果必须同时满足：

- Gate verdict 为 `PASS`；
- Gate outcome 为 `AUDIT_COMPLETE_VALID`；
- Coverage 为 `FULL`；
- Capability preservation 为 `CAPABILITY_PRESERVED`；
- semantic confirmation 的 `confirmed_by` 为 `CODEX`；
- receipt 为 formal completion；
- receipt candidate digest 等于当前 quarantine payload digest；
- Candidate source integrity 为 `PROVEN`。

### 8.2 窄 verifier contract

skill-engineering package boundary 增加或稳定导出一个仅服务实际安装边界的 verifier。具体函数/class 名称不在本设计中冻结，但语义必须是：

输入：

- 当前 quarantine payload path；
- `confirm` 阶段的完整 serialized outcome；
- outcome 中的 Managed Completion Receipt。

行为：

1. 使用现有 schemas/deserializers 解析 Validation、SemanticConfirmation 和 Receipt；
2. 根据 serialized validation 与 semantic confirmation 重新执行现有 `confirm` adjudication，而不是信任调用方提交的 verdict 字符串；
3. 用重建的 outcome 重新计算 completion receipt，并要求与提交 receipt 完全相等；
4. 调用现有 `validate_completion_receipt()`；
5. 调用现有 `managed_status(candidate_path, receipt)` 重验当前 bytes；
6. 要求 Validation 中的 `source_path` 和 `artifact_path` 均解析为本次传入的 canonical quarantine payload path，拒绝把另一 Candidate 的相同 bytes outcome 重用于当前 Candidate；
7. 返回安装边界所需的最小分类和规范化 receipt，不持久化、不安装、不注册。

该 verifier 是当前真实 OpenSpace 消费者需要的窄边界，不扩展为通用 Governance Service。

OpenSpace 收到 verifier PASS 后，重新计算 Candidate manifest digest 和 `candidate_id`，再写入 `candidate-binding.json`。只有该写入成功，Candidate 才从 `QUARANTINED` / `GOVERNANCE_PENDING` 进入 `GOVERNANCE_PASSED`。

### 8.3 Source integrity

`cloud_skill_id` 只是远程对象引用，不能自动视为 immutable revision。只有 OpenSpace Cloud contract 明确定义为不可变的 revision、snapshot 或 manifest hash 才能使 `source_integrity_status=PROVEN`。

缺少该证明时：

- Candidate 仍可下载到 quarantine 供检查；
- byte-level Governance 可以执行；
- lifecycle 最终结果必须是 `GOVERNANCE_INCOMPLETE`；
- 不得因内容 hash 当前可重复而把来源证明升级为 PASS。

## 9. Install Transaction

OpenSpace 的 Candidate install boundary 是正式 Skill mutation owner。步骤如下：

1. 根据 `candidate_id` 加载 immutable manifest、state 和 Candidate Governance binding；
2. 拒绝不处于可治理状态或已安装的 Candidate；
3. 验证 quarantine 和正式 Skill roots 不重叠；
4. 重新计算 `candidate_id`、manifest digest 和 payload digest，并调用窄 Governance verifier；
5. 将 `BLOCKED`、`INCOMPLETE` 或 mismatch 写入 state 后返回，不触碰正式环境；
6. 对预期目标获取按 target/skill ID 隔离的安装锁，并创建 durable install journal；
7. 拒绝已存在的 target、Skill ID 或 binding 冲突；
8. 要求 binding 中的 candidate identity、manifest digest、canonical payload path、receipt digest 和 inspection/validation identity 与本次输入完全一致；
9. 将 payload 复制到正式父目录下的 sibling temporary directory；
10. 验证 temporary directory digest 等于 receipt candidate digest；
11. 以同文件系统 atomic rename 物化最终目录；
12. 验证最终目录 digest 仍等于 receipt；
13. 写入 Cloud/local binding 和 SkillStore；
14. 进入最终 visibility critical section：提交 Registry 可见性并将 Candidate state 原子更新为 `INSTALLED`，记录 installed path、receipt digest 和 installed digest；Registry-backed readers 在该临界区结束前不得观察新条目；
15. 标记 install journal complete 并清理 journal。

Registry 在 transaction 的最后阶段才可见，避免 SkillStore 失败后仍被 Runtime 选择。实现应把现有 `register_skill_dir()` 内的“解析/安全检查”和“写入 Registry”拆成可复用的 prepare/commit 两步，或提供等价的非可见预检；不得复制一份独立 Skill parser。

文件系统、SQLite、Candidate state 和内存 Registry 无法依赖单一底层原子事务，因此 durable journal 是必要的恢复边界。进程启动时必须先恢复未完成 install journal，再扫描或暴露正式 Skill roots：删除或回滚仅由该 journal 证明为本次 transaction 创建且 identity/digest 匹配的 binding、SkillStore record 和目录；不得根据路径猜测删除。这样异常补偿和进程中断都不会把未完成 Candidate 留给自动发现流程。

### 9.1 补偿回滚

安装步骤发生异常时，按反向顺序补偿：

```text
Registry entry
  -> SkillStore record
  -> Cloud/local binding
  -> formal filesystem directory
```

回滚只处理本次 transaction 创建且 identity/digest 匹配的对象。不得覆盖或删除预先存在的 Skill。quarantine payload 和 Governance evidence 保留，Candidate state 记录 `INSTALL_FAILED` 与非敏感失败原因。

如果补偿本身失败，Candidate 仍不得标记为 `INSTALLED`；返回明确的 recovery-required error，并保留足够 ownership/digest 信息供受控恢复。

## 10. 失败语义

### 10.1 BLOCKED

条件包括已知结构、行为、Provider evidence、deliverable contract 或其他 required check 失败。

结果：

- state=`GOVERNANCE_BLOCKED`；
- quarantine 保留；
- formal target 不创建；
- binding、SkillStore、Registry 不变。

### 10.2 INCOMPLETE

条件包括 required Provider 未执行、Coverage 不完整、缺少 Codex confirmation、receipt 非 formal completion、缺少 authoritative source revision 或其他必需 evidence。

结果与 BLOCKED 相同，但保留可补齐依赖后重新治理的语义。

### 10.3 INTEGRITY_MISMATCH

以下任一不一致都产生该状态：

- Candidate manifest 中记录的 `candidate_digest` 与当前 payload digest 不同；
- Candidate Governance binding 中的 candidate ID、manifest digest、canonical payload path、inspection/validation identity 或 receipt digest 与当前输入不同；
- receipt candidate digest 与 manifest 不同；
- Governance outcome 重建后的 receipt 与提交 receipt 不同；
- sibling temporary copy 或最终安装目录 digest 不同；
- Candidate identity、Skill ID 或目标 placement 与 manifest 不同。

发生 mismatch 后不得继续使用旧 receipt；内容变化必须产生新 Candidate 或重新进行完整 Governance。

### 10.4 Error

解析错误、framework error、下载错误和 install error 不得被归一化为 PASS。Governance Gate/framework error 映射为 `GOVERNANCE_ERROR`；下载错误映射为 `ACQUISITION_FAILED`；安装错误映射为 `INSTALL_FAILED` 或 recovery-required error。错误响应不得包含 token、authorization header 或原始 credential-bearing stderr。

## 11. API 兼容策略

本设计冻结行为，不冻结最终 action、函数或 class 名称。

### 11.1 真实消费者兼容矩阵

当前 Repository 内已确认的 direct-import 消费者如下。这里的“兼容”只能保留入口发现性、选择/placement 参数和结构化响应能力；不能保留“调用后立即正式可用”，因为该旧语义正是本轮要关闭的安全缺口。

| 真实消费者 / 调用链 | 当前成功契约 | 两阶段后的兼容策略 | 必须迁移的假设 |
|---|---|---|---|
| MCP `cloud_browse_skills(action="import_skill")` → `cloud_import_skill()` → `_do_import_cloud_skill()` | 返回正式 `local_path`，随后 Registry/SkillStore 可见 | 保留 action 和 selection/placement 输入；返回 acquisition result、Candidate identity/digest、`governance_required` 和下一步；不返回正式 `local_path` | “import success = 可检索/可运行”改为“acquisition success = 等待治理” |
| `OpenSpaceClient.import_skill()` / `import_cloud_skill()` | 下载、写 `.skill_id`、分类物化、binding、正式落盘一次完成 | 复用 transport、解压、root discovery、ID/placement 计算；将 mutation 延迟到 receipt-verified install boundary | 任何直接 Python 调用都不能再无 receipt 写正式 Skill root |
| `openspace-download-skill` → `OpenSpaceClient.import_skill()` | `--output-dir` 是直接解压目标，并输出“Skill downloaded to” | 保留命令选择参数；输出 quarantine Candidate 信息；拒绝正式 root；帮助文本明确后续 Governance/Install | `--force` 不得成为覆盖正式 Skill 或绕过 receipt 的能力；其保留/收窄在实现计划中按 quarantine 冲突语义决定 |
| MCP `import_package_bundle` → client bundle import → `_bind_imported_package_skills()` → Registry discovery | package 内 Skill 会获得 binding，并可能自动进入 Registry/SkillStore | package 仅作为 inspection artifact 下载；包内 Skill 必须显式选取并逐个形成 Candidate | “下载 package = 导入所有内含 Skill”被移除 |
| `execute_task` cloud search result | 只返回候选并提示后续 import | 保持 discovery-only；把 next action 文案改为 acquisition → governance → install | 不得提示一次 `import_skill` 后即可参与 retrieval |

Repository 外部是否存在直接 Python 消费者，当前代码库没有可验证证据。因此设计不承诺维持旧的 direct-install side effect；实现计划需要通过 changelog/deprecation note 明确这一安全性 breaking change，而不是留下隐藏 bypass。

### 11.2 MCP `cloud_browse_skills`

保留现有 `import_skill` action 作为兼容入口，但将其行为改为 acquisition-only：

- 下载并创建 quarantine Candidate；
- 返回 `governance_required`、candidate ID、candidate path、digest 和下一步；
- `registered=false`；
- 不返回容易被旧客户端误认为正式 Skill 的 `local_path`；
- 不注册、不写 SkillStore。

这是有意的安全语义收缩。旧客户端仍能识别 action，但不能继续依赖“一次调用后立即可用”。

新增的第二阶段 action 名称和参数在实现计划中根据 MCP schema 约束确定。无论名称如何，它都必须要求 candidate identity 和完整 confirmed Governance output，不能只接受调用方提供的 `gate_status=PASS`。

### 11.3 Python Cloud client

当前 `OpenSpaceClient.import_skill()` 同时承担下载、分类、正式落盘和 binding，必须拆分责任：

- 下载/解压能力复用于 acquisition；
- 正式物化能力只能由 install boundary 在 verifier PASS 后调用；
- 不保留一个无 receipt 即可写入正式 Skill root 的 public path。

具体方法名可以保留并标记为 acquisition 兼容入口，也可以由现有调用点迁移后收窄；实现计划应根据外部 API 稳定性选择，但安全不变量优先于旧的 direct-import 语义。

### 11.4 `openspace-download-skill`

保留命令和主要参数，语义明确为下载到 quarantine/acquisition root：

- 不注册 Registry/SkillStore；
- 不生成正式 binding；
- 输出 Candidate identity/path/digest 和 Governance-required 状态；
- 当可识别 `output-dir` 与正式 Skill root 重叠时必须拒绝。

该命令不能成为绕过 MCP lifecycle 的直接安装入口。

### 11.5 Package bundle

`import_package_bundle` 只下载供检查的 package artifact：

- 使用非正式、非扫描目录；
- 不调用当前 `_bind_imported_package_skills()`，不写 `.skill_id`、Cloud/local binding 或正式 Skill sidecar；
- 删除当前自动 `discover_from_dirs()` 和 `sync_from_registry()` 行为；
- 包内 Skill 必须被单独选为 Candidate，经过相同 Governance lifecycle 后才能安装。

### 11.6 `execute_task`

保持现有 discovery-only 行为。Cloud hits 可以作为候选返回，但不得自动下载或注册。

## 12. 复用现有能力

### OpenSpace

- Cloud search、metadata fetch 和 bundle download；
- 安全 ZIP extraction 与 path traversal 检查；
- Local taxonomy / classification；
- CloudLocalMappingStore；
- SkillRegistry 的解析、安全检查和注册；
- SkillStore 持久化；
- runtime state root 和 Evidence read-root 管理；
- MCP structured response 和 secret redaction。

### skill-engineering

- `inspect -> validate -> confirm` phased workflow；
- Artifact manifest、snapshot 和 directory digest；
- Provider Gateway 和 provider evidence；
- deliverable applicability、Coverage 和 Integrity；
- Quality Gate；
- Codex semantic confirmation digest binding；
- `ManagedCompletionReceipt`；
- `completion_receipt()`、`validate_completion_receipt()` 和 `managed_status()`。

现有 `GovernanceEngine` / Evolution `GovernanceAdapter` 不替代上述 phased workflow。Evolution pipeline 保持原样。

## 13. 新增复杂度

本设计只引入以下不可避免的复杂度：

1. 一个 OpenSpace-owned Candidate lifecycle orchestration boundary，用于跨调用保存 acquisition/install 状态；
2. 一份 immutable Candidate manifest、一份 mutable state record，以及一份 verifier PASS 后生成的 immutable Candidate Governance binding；
3. 一个不位于正式 Skill roots 下的 quarantine root resolver；
4. 一个基于现有 skill-engineering primitives 的窄 receipt verifier；
5. 一个按 target/Skill identity 隔离、带 durable journal 和启动恢复的 install transaction；
6. Registry 的非可见 prepare、最终 visibility critical section 与补偿路径，避免同步失败或进程中断时提前暴露 Skill。

不新增：

- 独立 Service；
- 新 Governance Pipeline；
- 第二套 Quality Gate；
- 第二种 receipt；
- 跨机器 Receipt Registry；
- Production Rollout 或 B1-B4 harness；
- 面向未知消费者的通用平台 API。

## 14. 测试设计

实现按 TDD 进行，每个行为先观察到针对当前 direct-import 路径的失败。

### 14.1 Unit

- acquisition 只写 quarantine，正式 root/Registry/SkillStore 不变；
- Candidate manifest identity 和 digest 稳定；
- quarantine root 与正式 roots 重叠时拒绝；
- verifier 拒绝伪造 verdict、非 Codex confirmation、非 formal receipt 和错误 digest；
- state transition 拒绝越级和重复安装；
- package bundle 不自动注册。

### 14.2 Integration

- 远程 fixture Candidate 完成 `Acquisition -> Quarantine -> real inspect/validate/confirm -> Install -> SkillStore -> Registry`；
- BLOCKED outcome 不创建 target、不写 binding/store/registry；
- INCOMPLETE outcome 不创建 target、不写 binding/store/registry；
- Governance 后修改 payload，安装得到 `INTEGRITY_MISMATCH`；
- copy 后篡改或 digest mismatch，安装补偿且不注册；
- SkillStore/Registry 注入失败触发补偿，不留下可选择 Skill；
- 未完成 install journal 在下一次启动、正式 root 扫描前完成受控恢复；
- 最终安装 digest 等于 receipt candidate digest；
- 旧 `import_skill` action 返回 governance-required，而不是 `local_path`/registered success；
- CLI downloader 和 package bundle 无法绕过治理。

### 14.3 Regression

- 现有 Evolution Governance focused tests；
- Cloud search 和 explicit selection tests；
- Registry/SkillStore 正常本地 Skill 注册；
- existing upload trust 与 lineage 行为；
- skill-engineering focused unit/integration tests 和 Skill quick validation。

测试不得使用 mock Gate status 作为主成功证据。外部 Cloud transport 可以 fixture 化，但 Governance、digest、receipt、正式 filesystem placement、Registry 和 SkillStore 必须运行真实实现。

## 15. 实施边界

实施预计只涉及：

- OpenSpace Cloud acquisition/import orchestration；
- OpenSpace Candidate quarantine/state；
- MCP/CLI 兼容入口；
- OpenSpace install/register transaction；
- skill-engineering 的窄 outcome/receipt verifier boundary；
- Candidate lifecycle focused tests；
- host Skill 文档中 import 后立即可用的旧说明。

不修改：

- EvolutionEngine 的治理顺序；
- EvolutionCommitter 的 ownership；
- Production readiness reports/harness；
- Repository ownership 或发布模式；
- skill-engineering 是否长期独立。

## 16. 完成判定

只有真实 integration evidence 同时证明以下条件时，实施阶段才能报告完成：

```text
CANDIDATE_QUARANTINE_IMPLEMENTED
CANDIDATE_GOVERNANCE_CONNECTED
FAIL_CLOSED_BEFORE_INSTALL
RECEIPT_BOUND_TO_INSTALLED_CANDIDATE
REGISTER_ONLY_AFTER_GOVERNANCE_PASS
EVOLUTION_GOVERNANCE_PRESERVED
NO_NEW_PLATFORMIZATION
```

## 17. 保留的高影响决策

本轮不决定 `skill-engineering` 是否长期保持独立 Repository。当前设计在双仓库结构下建立最小、窄且可删除的边界；未来若治理能力内聚到 OpenSpace，Candidate manifest、receipt/digest 不变量和安装 transaction 仍可保留，只有 verifier 的物理调用边界需要改变。
