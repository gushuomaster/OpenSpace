# Upstream Sync Strategy

## Remotes and branches

```text
origin   https://github.com/gushuomaster/OpenSpace.git
upstream https://github.com/HKUDS/OpenSpace.git
```

长期分支为 `integration/skill-governance`，实现分支为 `codex/integrate-skill-engineering`。禁止向 `upstream` push；所有集成提交先进入个人 fork。

## 同步策略

主要策略采用 rebase：

```powershell
git fetch upstream
git switch main
git rebase upstream/main
git push origin main
git switch integration/skill-governance
git rebase origin/main
git switch codex/integrate-skill-engineering
git rebase integration/skill-governance
```

若官方变更与集成提交需要保留明确合并上下文，才使用 merge，并在同步提交中记录原因。同步前后使用 `git diff upstream/main...integration/skill-governance` 生成 Fork Tax 记录。

## 高风险区域

`openspace/skill_engine/evolution/engine.py`、`openspace/skill_engine/evidence/store.py`、`openspace/runtime/app.py` 和 `pyproject.toml` 是优先人工审查区域。治理接入应优先保持 Adapter 与依赖注入 patch surface，避免重写 OpenSpace 生命周期。
