# NavCode-MA v1.2 — Multi-Agent Evidence-Grounded Code-as-Policies for VLN

> 后续实测更新（2026-10-31）：官方 VLN-CE 接入、双 benchmark smoke、真实 API 与隔离生成代码实验已开始，详见项目根目录 [RESEARCH_PROGRESS.md](../../RESEARCH_PROGRESS.md)。本文的“未检查/未实现”是设计原型发布时状态；尚未取得好的导航结果或完成正式消融评测。

> 日期：2026-10-31。性质：研究梳理 + 可实施工程设计 + mock 协作协议原型。  
> 目标：在**新拉取、已可评测的 R2R-CE / RxR-CE Habitat 项目**上，实现可替换模型、多 Agent 协作、真实 Python Policy、视觉历史和程序修复。  
> 新评测仓库路径/版本/动作/传感器**尚未在此环境检查**，不能继承 RollbackNav 的配置。  
> 定位：ASENA-inspired 的独立工程项目；不声称已有论文完全未涉及该组合，不声称已经复现 ASENA 数值。

## 0. Executive Summary

**核心方向**：Code Agent 将导航指令编译为长期运行、可修复的 Python Policy；Vision Agent 对 Policy 提出的结构化视觉问题进行有界调查、检索历史并提交可撤销的证据；Policy 在两个 Code Agent 高层调用之间独立做多步决策；唯一拥有 `env.step` 的是本地可信动作 Broker。Code Agent / Vision Agent 通过 Canonical Evidence Ledger（同一证据账本）而非互相聊天传递状态。

这个设计最值得探索的三个机制：

- **Executable Perception Contract (EPC)**：Python 程序发出的不是含糊的“这里是厨房吗”，而是带有任务目标、证据要求、预算和 UNKNOWN 处理策略的视觉调查合同。Vision Agent 是有约束、有工具、能检索历史的调查者。
- **Evidence-Conditioned Program Repair (ECPR)**：视觉证据反驳现有阶段假设时，系统定位受影响的程序状态与控制分支，暂停 Policy，让 Code Agent 仅重写未完成逻辑，保留实际已执行动作。
- **Two-Timescale Agentic Execution**：Code Agent 在慢时间尺度上合成/修复程序；Vision Agent 在中频率上做语义调查；本地 Controller 在高频率执行物理动作。**不是三个 LLM 都在规划下一步移动**。

**创新性边界**：多 Agent VLN、LLM+VLM 主动感知、检索历史、机器人程序生成/修复分别都已经有先例。可能形成独特贡献的是它们之间**可运行的、版本化、可审计的证据合同与程序续执行协议**。是否有学术创新必须检索更广、做 ablation 后才能判断。对简历工程项目而言，清晰实现与测量已经有价值。

## 1. 相关研究与已有覆盖

| 论文 | 已覆盖的技术点 | 我们必须避免重复宣称的东西 | 具体借鉴 |
|---|---|---|---|
| Code as Policies (2022), arXiv:2209.07753 | 模型生成包含视觉查询、条件分支、反馈循环的可执行机器人代码 | “用 Python 代表机器人策略”本身不新 | 生成程序的控制流确实需要运行 |
| ProgPrompt (ICRA 2023), arXiv:2209.11302 | 程序化动作 API、assertion、条件与恢复 | “用代码做任务检查与恢复”不新 | 提前暴露合法 API 与能力限制 |
| ASENA (2026), arXiv:2609.39207 | Coding Agent、程序执行/修复、经验工作区、可选导航网络 | “编写修复具身代码”不新 | 不复制训练好的 ASENA-VLN-4B；借鉴 Agent-Program 工具边界 |
| ProFocus (CVPR 2026) | LLM-VLM 协作、主动视觉查询、聚焦历史 | “规划 Agent + 视觉 Agent”不新 | 按明确问题检索区域/历史，避免大量无关图像 |
| CA-VLN (Sensors 2026) | Knowledge Agent 与 Hierarchical History Agent | “双 Agent + Episodic Memory”不新 | 为导航历史建立有结构的检索与证据来源 |
| MA-CoNav (arXiv:2603.03024) | 观察、规划、执行、记忆分角色的多 Agent 导航 | “按角色拆分多个 Agent”不新 | 层次控制避免 Agent 决策打架 |
| AgenticNav (arXiv:2606.10577) | Pixel Action、Depth Tool、Recall Tool，R2R-CE | “图像导航点 + 历史回顾”不新 | 提供短距离合法目标，不要求模型猜绝对步数 |
| SuperNav (arXiv:2610.12126) | MLLM Harness、Skills、上下文管理、visual-point executor | “Agent + Tools + Skills”不新 | Controller 独立于任务语义 |
| SkillNav (ACL 2026) | 专门技能 Agent + VLM Router | “Skill-level 多 Agent 路由”不新 | 避免多个 Agent 在每个 primitive 决策轮流发言 |
| EvoNav (CVPR 2026) | 历史经验与未来预判的循环 | “历史回顾减少重复失败”不新 | Evidence ledger 要保存被纠正的错误判断 |

**重要区分**：MAVLN / TRISS（arXiv:2609.35965）研究**多机器人**协同导航；本项目研究**一个机器人的多软件 Agent 协作**，不要混用二者的 benchmark 术语。

官方资料：
- ASENA: https://research.nvidia.com/labs/gear/asena/ , https://arxiv.org/abs/2609.39207
- ProFocus: https://openaccess.thecvf.com/content/CVPR2026/html/Xue_ProFocus_Proactive_Perception_and_Focused_Reasoning_in_Vision-and-Language_Navigation_CVPR_2026_paper.html
- CA-VLN: https://pmc.ncbi.nlm.nih.gov/articles/PMC12944077/
- MA-CoNav: https://arxiv.org/abs/2603.03024
- AgenticNav: https://arxiv.org/abs/2606.10577
- SuperNav: https://arxiv.org/abs/2610.12126
- SkillNav: https://aclanthology.org/2026.acl-long.595/
- Code as Policies: https://arxiv.org/abs/2209.07753
- ProgPrompt: https://arxiv.org/abs/2209.11302
- EvoNav: https://openaccess.thecvf.com/content/CVPR2026/html/Dai_History_to_Future_Evolving_Agent_with_Experience_and_Thought_for_CVPR_2026_paper.html

## 2. 系统边界：哪些是 Agent，哪些只是程序

本项目第一版**只有两个模型驱动的 Agent**，无需引入 Master LLM、Memory LLM、Execution LLM 或 Verifier LLM。

```
                  New R2R-CE / RxR-CE evaluation runner
                           (GT private)
                                |
                    safe instruction + RGB/Depth*
                                v
           +-------------------------------------------+
           |        Episode Supervisor (code)          |
           |  single action owner · budgets · routing  |
           +---------+---------------------+-----------+
                     |                     |
            task / error / stage     perception contract
                     v                     v
          +------------------+    +-------------------+
          |    Code Agent    |    |    Vision Agent   |
          | persistent thread|    | visual inquiry    |
          | code + repairs   |    | recall + claims   |
          +--------+---------+    +---------+---------+
                   |                        |
                   +--------+---------------+
                            v
             Canonical Event Store + Evidence Ledger
                  |                       |
                  v                       v
          Python Policy Runtime <-- PerceptionResult
                 |          ^
                 | nav.step | MotionReceipt
                 v          |
           ControllerBackend / action broker
                 | single env.step
                 v
        Habitat Adapter → native evaluator (private)
```

\* Depth 仅当选定合法 Track 提供时可使用；不同 Sensor Track 需要单独报告。

### 权限表

| 角色 | 可以读取 | 可以写入 | 不能做 |
|---|---|---|---|
| Code Agent | 任务原文、程序、状态、证据摘要及授权帧 | 提交新程序/修复建议 | 直接 `env.step`、读取 benchmark GT、任意 shell 扫描数据 |
| Vision Agent | 当前/授权历史 RGB、可用 Depth 摘要、与问题相关的指令片段 | 提交候选视觉证据/请求新视角 | 直接移动、重写 Policy、读 GT |
| Policy Worker | TaskSpec、JSON State、白名单 NavAPI 返回 | JSON State、合法工具请求 | 模型 API Key、网络、Simulator 内部对象、文件系统探索 |
| Supervisor/Broker | 合法传感器/动作结果、预算、事件账本 | action commit、事件与状态 | 独自猜测语义目标、把 GT 注入 Agent |
| Evaluator | ground truth、轨迹、metrics | 独立实验报告 | 在 episode 期间反哺 Agency Context |

**关键原则：单写者运动**。只有 Broker 可以提交动作，Code Agent 和 Vision Agent 都不能绕过运行中的 Python Policy 让机器人移动；若设计 Direct-Agent baseline，必须复用同一个受控 Broker。

## 3. 双 Agent 各自的长期上下文

### Code Agent（全局、低频）

持续一个 episode 的逻辑 Agent Thread，负责完整指令、策略解释、生成/修复代码及审查反事实。Agent Thread 是**推理工作缓存**；压缩或上下文溢出时，能从 Event Store/ContextBuilder 重建必要事实，不假设 Agent 有无限可靠上下文。

输入：完整原文及语言、公开动作/sensor capabilities、当前程序版本、JSON 状态、最近高层事件、相关证据 id；可主动 `recall_evidence(obs_ids)`/`inspect_trace`。默认少量关键帧，可按需读取更多合法历史。

输出：`PolicyArtifact`（源码 + 入参 schema + 触发事件 + state migration）或 `DECLINE_REPAIR`。不直接输出 primitive actions。

### Vision Agent（局部调查、中频）

拥有自己当前 episode 的短会话，以及受权限限制的 `FrameStore`/`EvidenceLedger` 检索工具。**不能只把单次图像问答叫作一个 Agent**；真实 VisionAgentBackend 必须至少能执行有限次主动历史检索/裁剪/比较/二次查询，然后形成证据结果。

输入：EPC + 当前观测和 relevant frames + 当前任务阶段 + 最近动作。可读取**本 episode** 所有合法历史帧，但每次推理默认展开 1~3 张图；超过默认预算时主动申请，受总预算上限约束。

输出：`EvidenceReport`，其中 SUPPORTED 表示模型证据支持、**不等于 GT verified**；可返回 `NEED_MORE_VIEW`（建议视角但不移动）。Vision Agent 不应自行改写 `stage_complete=True`，它只提交证据；Policy 决定语义进度，Code Agent 必要时负责重计划。

### 共同记忆不等于共享聊天 Transcript

Canonical Episode Memory 分成：

1. Append-only Event Store：每次 action、帧、Agent 调用、程序 revision、Tool receipt；审计真实发生了什么。
2. Frame Store：带 `obs_id` 的 RGB/Depth；来自合法 sensor，不含 GT overlay。
3. Evidence Ledger：候选 claim、证据帧、来源 Agent、revision、证据冲突/撤回记录。
4. Policy State：显式任务阶段、计数器、已处理 event ids、失败重试预算，必须 JSON 可序列化。
5. ContextBuilder：从以上记录构造**面向 Code Agent**和**面向 Vision Agent**的不同上下文；不复制历史真相到多个独立长文本文件。
6. Frozen Workspace：通用技能与 prompt 示例在正式 val_unseen 测试前冻结；禁止读取其他 evaluation episode 的轨迹。

“看了第二道门”必须表示为 `claim_id + evidence_obs_ids + source + uncertainty + revision`，不是一个不可修改的 `crossed_door=True`。

## 4. 核心独特接口：Executable Perception Contract (EPC)

### 为什么不用 `nav.inspect("Am I in the kitchen?")` 作为唯一协议？

自由文本无法约束验证条件、历史搜索范围和失败动作，Vision Agent 可能给出看似自信但缺少依据的答案，Code Agent 也难以判定何种证据触发程序修复。

### 规范数据结构（建议正式实现）

```python
@dataclass(frozen=True)
class PerceptionContract:
    request_id: str
    episode_epoch: str
    policy_revision: int
    operation_id: str
    task_span: str           # 原语言指令片段，不得删除歧义上下文
    stage_id: str
    predicate: str           # e.g. "distinct_door_crossed"
    target_ref: str | None   # 稳定的 landmark candidate ID
    current_obs_id: str
    evidence_before: tuple[str, ...]
    allowed_tools: tuple[str, ...]  # fetch_frame, crop, recall, depth_if_allowed
    max_visual_turns: int
    max_images: int
    deadline_ms: int
    on_unknown: str          # "REQUEST_VIEW" | "YIELD_TO_CODE_AGENT"

@dataclass(frozen=True)
class EvidenceReport:
    request_id: str
    verdict: Literal["SUPPORTED", "REFUTED", "UNKNOWN", "NEED_MORE_VIEW"]
    subject_id: str | None
    evidence_obs_ids: tuple[str, ...]
    evidence_regions: tuple[dict, ...]
    rationale_summary: str
    suggested_observation: str | None
    model_id: str
    usage: dict | None
```

输入到模型的历史**可以主动检索**，但必须记录哪些关键帧被选择、每张图片是为判断什么问题而选。每个 `EvidenceReport` 必须和 `request_id/policy_revision/current_obs_id` 对齐；过时结果不得更新当前程序状态。所有返回进行 schema validation。

视觉 Agent 可以建议 `LOOK_RIGHT` / `SCAN`，**不能自行发给 Habitat**；Supervisor 将其转成 `NEED_MORE_VIEW` 事件交由 Python Policy 决定是否采取。未知证据默认 `UNKNOWN`，不可为了成功率强制转成 SUPPORTED。

### Visual Target 与 Navigation Waypoint 必须严格分离

Vision Agent 可以输出：地标 bbox、描述、朝向候选，或者**可通行地面 waypoint**。但“门的 bbox 中心”和“能走到的地面点”不是同一个东西。若使用 waypoint，必须绑定 `obs_id`、坐标系（原始像素或归一化）、选点类型以及证据；Motion Controller 检查几何有效性和可达性。任何 `move_to_pixel` 都不得用 GT pose/shortest path/navmesh 绕过 Track 传感器权限。

## 5. Program ↔ Supervisor ↔ Agent 交互协议

### Code Agent 工具（不得移动环境）

`get_task_spec`, `read_policy`, `read_policy_state`, `recall_evidence`, `inspect_trace`, `submit_policy`, `run_or_resume_policy`, `request_program_patch`。这些全是经过权限过滤的结构化接口，**不等于给 Codex 自由 shell**。

### Policy NavAPI（Python 真正运行）

```python
class NavAPI(Protocol):
    def observe(self) -> ObservationHandle: ...
    def perceive(self, contract: PerceptionContract) -> EvidenceReport: ...
    def recall(self, query: str, limit: int = 5) -> list[MemoryHit]: ...
    def step(self, action: PrimitiveAction, *, repeat: int = 1) -> MotionReceipt: ...
    def move_to_pixel(self, waypoint: Waypoint, *, max_actions: int = 8) -> MotionReceipt: ...
    def checkpoint(self, stage_id: str, state: dict) -> None: ...
    def stop(self) -> StopReceipt: ...
```

`move_to_pixel` 只有在独立 controller 能证明它适配当前 sensor/action 设置后才可启用；RGB-only 且没有合法 learned controller 时，返回 `UNSUPPORTED`，不是隐含使用 NavMesh。

### Supervisor 有限事件词汇

```
EPISODE_START
POLICY_SUBMITTED
PERCEPTION_REQUESTED / PERCEPTION_RESOLVED
NEED_MORE_VIEW
LANDMARK_CLAIM_SUPPORTED / CLAIM_REFUTED / CLAIM_CONTRADICTED
STAGE_COMPLETED
NEEDS_REPLAN
POLICY_EXCEPTION
POLICY_PATCHED
STOPPED / FAILED / BUDGET_EXHAUSTED / INFRA_FAILURE
```

**启动**：Code Agent 生成阶段级策略后离开运动控制环；Worker 独立执行 Python `while/if`，可多次提交 primitive，遇语义需求向 Supervisor 提交 EPC。Supervisor 让 Vision Agent 在受限工具上下文里调查，返回报告后**恢复同一个 Worker**。只有异常、冲突、阶段缺失或预算事件才重新唤醒 Code Agent。

**重要防死锁要求**：如果 Code Agent 以工具方式启动 Policy，则不得让未结束的同一 Agent Turn 在内部同步重入自己。Policy 的视觉请求交给 Vision Agent Service；需要 Code Agent 时在阶段事件边界完成 `run_policy` 工具回合，再发起新的 Agent Turn。

### 程序 Repair 语义

- `PAUSED` ≠ Habitat `STOP`。前者只是 Runtime 不再提交动作。
- 每个动作有 `episode_epoch + action_seq + op_id + payload_hash`，Broker 去重；修复只准在最新实际状态继续。
- 程序迁移使用 JSON 逻辑 checkpoint（stage、landmark ids、processed event ids、剩余 budget），不能假装恢复任意 Python 栈。
- 代码补丁会产生新 `policy_revision`；必须校验新版本对原状态 schema 的要求；对已提交动作不得重复执行。
- Vision Agent 反驳先前进度时，Ledger 写新 revision，不修改历史记录。Program State 中受影响的字段只能在**显式撤销事件**下迁移。未经证据关联的“门数+1”必须避免重复计数。

## 6. 一条具体指令怎么执行

指令：“走过两道不同的门，左转，进入目标房间后停下”。

1. Code Agent 收到指令和初始 RGB，生成一段阶段性 Python Policy，不猜测完整未知环境中的运动距离。
2. Policy 调用 `nav.observe()`，向 Vision Agent 提交 `FIND_WAYPOINT` 或 `DOOR_CANDIDATE` 合同；Vision Agent 回看上一次经过的门、判断新目标是否可能为同一物理门。
3. 在合法 Controller 中执行短程运动，返回已提交动作数、新 obs_id 和是否 blocked；每个动作进入账本。
4. 经过门口时，Policy 提交 `distinct_door_crossed` 合同；Vision Agent 读取前后帧及近期运动记录，给出 SUPPORTED / UNKNOWN 并附证据。
5. Policy 把有证据的新门加入自己已经处理的事件集合；如果 Vision Agent 后来撤回结论，触发状态重新评估，而非偷偷自增/自减。
6. 第二道门满足条件后，程序通过合法角度控制器左转（具体动作步长从新 benchmark 读取），进入目标房间并进行必要的视觉验证。
7. 若证据冲突或重复失败，则触发 `NEEDS_REPLAN`；Code Agent 查看相关代码/状态/关键帧，提交兼容当前 checkpoint 的新程序版本。
8. `nav.stop()` 发送真实 STOP；原生 evaluator 私下计算成功、SPL、nDTW 等；任何判断都不依赖在线 GT。

这个例子强调的是**多 Agent 的协作协议**，不能以当前 mock route 的六个动作序列代表真实 R2R/RxR 成功率。

## 7. Model Backend：不绑定厂商和模型

```yaml
code_agent:
  backend: codex_harness  # codex_harness | direct_llm | mock
  model: null
  persistent_episode_thread: true
  max_turns_per_episode: 12
  trigger: [episode_start, needs_replan, policy_exception, contradiction]
vision_agent:
  backend: direct_multimodal  # direct_multimodal | multimodal_harness | mock
  model: null
  per_request_max_turns: 3
  default_max_images: 3
  max_recall_images: 8
  allow_crop_and_evidence_retrieval: true
memory:
  event_store: sqlite
  frames: filesystem
  claim_ledger: append_only
  freeze_workspace_during_eval: true
controller:
  backend: primitive  # primitive | sensor_legal_waypoint | learned
  sensor_track: inherit_and_verify
runtime:
  python_generated: true
  os_sandbox_required_for_untrusted_code: true
  only_one_motion_writer: true
benchmark:
  suites: [r2r_ce, rxr_ce]
  runner: inspect_new_repository
  oracle_exposure: forbidden
```

`Code Agent` 与 `Vision Agent` **可以使用同一个底层多模态模型**，但通过不同会话、提示词、工具权限和上下文窗口承担不同职责；“Multi-Agent”指角色/执行循环，不要求一定是不同的模型权重。实际部署时可以选不同模型以做成本实验。Code Agent 也可以在错误诊断时主动查看图像；Vision Agent 不占有视觉真相，而是专门调查证据。

如果真实 Code Backend 是 Codex，重点是**Tool Proxy 和工作区隔离**；不能让其 arbitrary shell 获得 val-unseen GT、真实目标坐标或其他 episode 文件。SDK/权限是否满足，需要在 M0 验证。

## 8. 对照实验与创新性验证

### 固定可比较的实验条件

相同 episode manifest、同一合法传感器 Track、同一个 ControllerBackend、同一动作预算和整体 wall-time 预算，尽量采用一致的底层模型以区分架构增益。R2R-CE / RxR-CE 不与原始 R2R/RxR 离散图导航混报。不同 Depth/Oracle Geometry 设定必须分别标注。

| 实验 | 架构 | 关键解释 |
|---|---|---|
| B0 Direct Agent | 同一高层模型直接使用合法感知/运动工具 | 持续决策的基础表现 |
| B1 One-shot Code | 开始生成一次程序，不改代码 | 静态程序的局限 |
| B2 Single-Agent Code | 同一多模态 Agent 编程并在需要时看图 | 排除拆分 Agent 本身的必要性 |
| B3 Dual-Agent Code | Code Agent + Vision Agent，程序为控制中心 | 双角色分工是否带来实际收益 |
| B4 Dual-Agent + EPC/Ledger | 增加主动视觉合同、证据撤销机制 | 可追溯协作的额外价值 |
| B5 Dual-Agent + Repair | 证据冲突触发版本化修复 | 程序续执行的价值 |

如果只做 B2 与 B3，能测试双 Agent 架构，但**不能**归因 EPC 和 Ledger 的贡献；设计文档应保留这些消融。

### 成功率之外必须测量

SR、SPL、nDTW（若原生提供）、平均环境动作数、停止/过冲错误、实际模型输入/输出 Token、调用与重试、模型费用（缺失 Usage 标 unknown）、wall time、高层 Code Agent 唤醒次数、每 episode 视觉调查次数、每次调查图片数、历史 Recall 命中率、无进展比例、证据冲突频次、冲突解决时长、Program Repair 成功/失败分类。

额外人工抽查一个小规模标注子集（例如 30 个高歧义片段），估计“目标被识别为第二道门”的判断准确率和证据是否足以支撑决策；不能仅以模型自报 confidence 代替标注质量。

**停止阈值**：如果 B3 较 B2 没有实质好处，或延迟/调用成本显著更高，应该让单 Agent 继续做默认配置，并将双 Agent 定位为可选模式，不强行包装胜利。

## 9. 新 benchmark 接入的工程路线

### M0：新评测仓库预检（必须）

- 分别检查 R2R-CE、RxR-CE 环境类型、动作 ID、前进步长、转角、RGB/Depth、语言、episode 时限、ST0P、Runner、评测计算、现有外部 Client 接口。
- 从源码及真实 smoke 记录对应的 `BenchmarkCapabilities`（路径/commit/config/hash），不能使用旧项目的 0.25m 或 30° 作为保证。
- 证实不经 GT sensor、metrics、GT top-down map、reference path 向 Agent 提供信息；无 Oracle Goal Stop。
- 确认原环境可供新 Agent 连接；不下载已存在资产、不重新安装已有 Habitat。

### M1：一条可信手写 Python Policy 同时接双 Benchmark

- 一个 Adapter 支持两个 Profile；`ObservationFilter` 只提供合法传感器。
- 可信程序能调用 primitive、observe、stop；Action Broker 唯一提交动作。
- 记录每个原子动作与新 obs_id；完整保存原生评测结果。

### M2：两个 Agent 的事件协作与历史

- 接入 `CodeAgentBackend` 和 `VisionAgentBackend`，使用结构化感知合同、ContextBuilder、Evidence Ledger。
- 先录制 responses / Mock，再连接真实模型（只有用户授权才产生费用）。
- 测试主动检索更早帧、同一 landmark 去重、错误证据撤回、跨 episode 禁止检索。

### M3：真实生成代码的隔离执行与部分恢复

- 使用 **OS 级沙箱 Worker + Capability RPC**，AST 只是辅助校验；未完成沙箱时禁止运行模型生成 Python。
- 支持 pause/resume、action_seq/op_id 去重、JSON checkpoint、程序 revision、跨版本迁移；异常不会重放动作。
- 加入预算、超时、取消和模型返回校验。

### M4：合规 Local Controller / Waypoint

- 优先复用新 benchmark 提供的工具；如果启用深度必须单列 RGB-D Track；若依赖 oracle navmesh/pose，只能做诊断上界。
- Grounding 返回 waypoint obs_id + coordinate frame + type；Controller 检查 stale pixel、深度/避障、局部运动、目标丢失。
- 如尚无合法 waypoint backend，保持 primitive 路线可运行，不假装 `move_to_pixel` 可用。

### M5：真实实验、ablation、演示

- 固定 development episodes 调参；冻结 workspace/prompts 后评估 unseen；报告正式指标和必要失败样例。
- Web Demo：生成代码/当前代码行/Code-Agent 事件/Vision-Agent 问题与历史帧/证据撤回/动作轨迹/成本。
- 补齐 README、许可证、第三方归属，明确与 ASENA/ProFocus/AgenticNav 的关系。

## 10. 已实现的 mock 协作协议原型（2026-10-31）

目录：`navcode-ma-prototype/`，完全标准 Python 库（测试依赖 pytest），**不需要真实 VLM / Habitat**。

已实现：

- `MockCodeAgent` 提供 Python 字符串策略（1 个初始策略 + 1 个有界修复策略），保留 Program Revision。
- `TrustedFixtureRuntime` 只执行 SHA256 白名单中的固定审阅策略，真实 Python `if/for/state` 会运行多步。
- `MockVisionAgent` 接收 PerceptionTask，进行按需历史检索，返回结构化证据；自身没有动作接口。
- `EpisodeMemory` 保存 episode 隔离事件、观测和可版本化/可撤销的 claim。
- `Supervisor/NavFacade` 是唯一动作提交路径；模拟需要经过两道不同的门再左转进入房间。
- 可以人为注入一次视觉判断不确定，触发 Code Agent 的第二版程序；从当前位置继续，而不是重新执行旧运动前缀。
- 8 项单元测试通过，正常及修复模式都产生 `trace.jsonl` 和 `result.json`。

**未实现 / 绝不宣称已实现**：真实 VLM、真正多轮工具调用式 Vision Agent、真实 Codex Thread、Habitat/R2R/RxR 接入、RGB-D waypoint、真实异步 Agent 调度、跨进程 OS 沙箱、跨进程 action idempotency、真实 SR/SPL/nDTW。当前 `visual_hint` 是**明确标注的合成数据**，Mock 成功只用于协议回归测试。

**安全**：fixture runtime 含 `exec` 但只运行固定已审阅源码，AST/有限 builtins 不构成安全沙箱；不得删除 hash 白名单来执行任何 LLM 生成程序。上线前应先建立 OS 隔离 worker 及最小权限的 IPC。

### 最小运行命令

```bash
cd navcode-ma-prototype
python -m navcode_ma.demo --output runs/demo
python -m navcode_ma.demo --inject-uncertain-goal --output runs/repair_demo
python -m pytest -q
```

### 进入真实 R2R/RxR 前 Codex 应做的事情

先完成 M0，并把此原型的协议（Agent Role / EPC / Evidence Ledger / Policy Outcome）作为**测试契约**迁移进新项目。不要直接把 `MockRouteEnvironment` 适配成 Habitat 并保留 `visual_hint`；真实 Vision Agent 只能接收合法 RGB/Depth 和自行检索的观察历史。

## 11. Codex 执行清单（不得自行决定范式）

1. 阅读本设计与原型 README；以 **Code Agent + Vision Agent + Python Policy + Non-LLM Supervisor** 作为固定核心。
2. M0 只读新仓库源码 + 双 Benchmark smoke，不建立旧 RollbackNav 依赖；记录真实动作/传感器/GT 边界。
3. 复用本原型的 contracts 和单测思路，但真实 `PerceptionContract` 必须取代 demo 简化的 `PerceptionTask`；加入 `episode_epoch`、`policy_revision`、`request_id` 和 schema 校验。
4. 在正确处理模型线程权限、Agent 工具、Python 沙箱之前不得进行收费模型的生成代码执行。
5. 若底层 motion/backend 难以合法迁移，优先完成 primitive 闭环和双 Agent 视觉推理，不擅自调用 oracle geometry。
6. 交付实际源码路径、测试脚本、真实 R2R/RxR episode log、失败案例、已验证与未验证项。
