# Fork Tax Report

## 统计口径

本报告以 `upstream/main` 为基线，统计集成分支上的文件和 Adapter patch surface。提交集成改动后重新运行：

```powershell
git diff --stat upstream/main...integration/skill-governance
git diff --name-status upstream/main...integration/skill-governance
```

## 集成 patch surface

截至 `integration/skill-governance` 的 `6daa9594c198f1e952db1a79fa0dabb95cf9ddde`，相对 `upstream/main` 的统计为：

- 修改/新增文件：29
- 新增文件：16
- 修改文件：13
- 代码和报告新增：1306 行，删除：3 行
- Adapter 新增目录：5 个 Python 文件
- 冲突文件：0（本次未执行 upstream 同步合并）

治理改动集中在：

- `openspace/skill_engine/governance_adapter/`
- `openspace/skill_engine/evidence/store.py` 与 `types.py`
- `openspace/skill_engine/evolution/engine.py`
- `openspace/runtime/app.py`、MCP、Dashboard
- `pyproject.toml` 的锁定 Git 依赖
- `reports/skill-engineering-integration/`

没有复制 `skill-engineering` 源码，没有 subtree/vendor，没有第二套 Evidence/Candidate DB，也没有修改 OpenSpace 的 Trust/Upload 所有权。

## 风险结论

Evolution Engine 和 EvidenceStore 是不可避免的高风险冲突点；Adapter 本身是新增目录，适合在 upstream 同步时独立解决。每次 upstream 同步必须重新统计文件数、Adapter 行数、冲突文件和高风险区域，不以“能 rebase”替代行为回归。
