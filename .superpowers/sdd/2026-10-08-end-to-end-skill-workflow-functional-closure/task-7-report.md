# Task 7: Candidate to runtime reuse

## Result

The new E2E test exercises the explicit Host continuation from local miss through MCP Cloud search, Codex selected Cloud ID, real Candidate acquisition, real skill-engineering inspection/validation/Codex semantic confirmation, receipt gated install, fresh Registry/SkillStore discovery, local lookup, and `SkillTool` attachment. The installed `SKILL.md` bytes match the deterministic fixture, and its marker reaches the `invoked_skill_content` attachment.

The companion protocol test stops at local miss and verifies that the response only offers `cloud_skill_discovery`: it has no installed Skill, no task replay flag, and no claim of task resumption.

Only external HTTP is replaced by a deterministic transport response. The Cloud search MCP handler and `OpenSpaceClient.search_skills` execute. The Candidate lifecycle, Governance pipeline, install, Registry, Store, discovery, and SkillTool are real code. The restart boundary is represented by closing the original Store and mapping connections and constructing fresh Registry/Store instances from the formal Skill root and persisted database, as prescribed by the implementation plan. This test does not launch a second operating system process or prove autonomous task replay.

## Test first and observed failures

The first test version was run before any production edit. It hit the external Cloud API with the fixture's placeholder key and failed with HTTP 401. That was a test harness error, so Cloud discovery was moved to the existing client/MCP path with only HTTP transport replaced. A later assertion expected raw `SKILL.md` as the `SkillTool` attachment and failed because the real tool wraps Skill content in its command context. The assertion now checks exact installed bytes separately and the marker in the actual attachment.

After those test corrections, the existing production chain passed. No missing production seam was found and no production code was changed for Task 7. Thus there was no legitimate production RED to turn GREEN; the report does not claim one.

## Verification

The task used the pinned `skill-engineering` source at commit `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c` via the existing task environment. That environment lacks some OpenSpace test dependencies, so `PYTHONPATH` exposed the global Python 3.14 site packages and Win32 module paths while keeping the pinned source first. `PYTHONUTF8=1` was set.

Focused E2E command:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\skill-engineering-pinned-e2e\skill-engineering;C:\Users\28320\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages;C:\Users\28320\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\win32;C:\Users\28320\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\win32\lib;C:\Users\28320\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\pythonwin'
& 'D:\project\OpenSpace-e2e-functional-closure\artifacts\recovery-subprocess\venv\Scripts\python.exe' -m pytest tests/cloud/test_candidate_runtime_reuse.py -v -p no:cacheprovider
```

Observed: `2 passed in 1.05s`.

Candidate and Evolution focused regression command:

```powershell
& 'D:\project\OpenSpace-e2e-functional-closure\artifacts\recovery-subprocess\venv\Scripts\python.exe' -m pytest tests/cloud/test_candidate_runtime_reuse.py tests/cloud/test_candidate_governance_integration.py tests/skill_engine/test_governance_adapter.py tests/skill_engine/test_skill_trust_lifecycle.py -v -p no:cacheprovider
```

Observed: `35 passed in 2.68s`; no failures, skips, xfails, or collection errors. This is Task 7 focused evidence, not the phase's full verification gate.

## Milestone interpretation

| Milestone | Evidence | Result |
| --- | --- | --- |
| `LOCAL_MISS_CONTINUATION_AVAILABLE` | `DiscoverSkillsTool` response metadata and attachment | Yes |
| `CLOUD_DISCOVERY_EXECUTED` | MCP `cloud_search_skills` ran the client search with deterministic HTTP | Yes in explicitly driven path |
| `CODEX_SELECTION_COMPLETED` | The exact returned `cloud_skill_id` was selected and passed to acquisition | Yes in explicitly driven path |
| `CANDIDATE_INSTALLED` | Receipt gated install reached persisted `INSTALLED` state | Yes |
| `TASK_RESUMED_WITH_SKILL` | Subsequent fresh local lookup and `SkillTool` attachment contained the marker | Yes in explicitly driven continuation |

Functional install to runtime reuse and the continuation protocol are verified. Task level automatic closure remains unverified and is not claimed: neither `execute_task` nor the local miss response automatically replays the original task with the new Skill.
