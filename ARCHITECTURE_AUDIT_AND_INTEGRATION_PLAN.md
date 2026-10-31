# NavCode Architecture Audit and Integration Plan

审计日期：2026-10-31。范围：只读检查 RollbackNav 源码、配置、已有日志、数据文件及 ASENA 官方材料；未运行模型请求、未安装环境、未下载数据、未执行 Habitat 评测、未修改 RollbackNav。

## 1. 决策与证据边界

保留现有 Habitat Env、dataset registry 和 evaluator measures，在现有评测循环中新增 `NavCodeAgent`。Astra 生成和修复 Python Policy；Python 保存长期控制流及显式任务状态；Visual VLM 按需解释图像；RGB-D Local Controller 产生原有离散动作；只有 Runner 调用 `env.step`；指标和真值仅留在 evaluator 域。Codex 只参与开发。无需训练或微调。

本文将事实标为“已检查”，将尚无运行证据的内容标为“待验证”，后文接口、目录和运行协议均是“NavCode 设计”，不是 ASENA 官方源码。

ASENA 官方证据：

- [论文 v2，§3.1、§3.2](https://arxiv.org/html/2609.39207v2)：Coding Agent 编写程序、调用固定工具；MCAP 将观测、动作、反馈与代码对齐；回看记录支持修复；workspace 保存笔记与可执行技能，模型权重固定。
- [论文 §3.3](https://arxiv.org/html/2609.39207v2)：ASENA-VLN 是可选导航工具；pixel goal 需另加规划器，论文评测使用轨迹输出。NavCode 的 RGB-D pixel controller 是自行实现。
- [论文 §4.4](https://arxiv.org/html/2609.39207v2)：workspace evolution 使用重复任务与 ground-truth feedback；这与无真值、冻结工作区的正式评测不同，不能把其增益当成未见任务泛化证据。
- [官方项目页](https://research.nvidia.com/labs/gear/asena/)展示 harness、技能伪代码和工作区演化；截至本次查阅，官方论文/项目页未找到完整官方源码仓库入口。不能断言所有代码均未发布，也不能把网页伪代码认作可执行源码。

关系：`workspace → Coding Agent → program → navigation tools → execution → trace → repair → revised program`；可泛化经验经单独流程形成 workspace 新版本。

NavCode 自行实现：七个 Navigation API、RPC 协议、Python 进程隔离、暂停与恢复、RGB-D 控制器、Program Debugger、JSONL trace、cost profiler。MCAP 可作为后续导出格式，不作为 M1 阻塞依赖。

## 2. 已检查的现有源码与复用策略

以下相对路径均以 `/home1/gmh/wangyang/vln/RollbackNav` 为根；本次读取到 Git HEAD 为 `77aa22a2317637f3157d6c3bdc2c443104fab019`。已确认工作树存在大量既有修改、删除与未跟踪文件，本审计依据当前磁盘内容，未更改或还原它们。HEAD 不是工作树内容的完整证明，M1 需记录 dirty 状态与关键文件 hash。

| 模块 | 具体路径 / 接口 | 结论 |
|---|---|---|
| 共用评测入口 | `run.py:134 run_eval`，`:203 evaluate_agent` | 复用抽样、固定 subset、分片、Env 生命周期和统计输出；增加 navcode 分支 |
| Agent 工厂 | `run.py:496 _build_agent` | 新增 method；当前 CLI choices 没有 navcode |
| Agent 契约 | `rbnav/agents/base.py`：`reset()`、`act(observations, info, episode_id)` | 可适配；新 Agent 内不保留完整 info |
| 动作规格 | `rbnav/agents/rollback_agent.py:38 ActionSpaceSpec.from_task_config` | 复用计算逻辑；独立抽出轻量规格，避免为常量导入 NaVid / 旧 Agent 全链路 |
| R2R 实验配置 | `VLN_CE/vlnce_baselines/config/r2r_baselines/baseline_r2r.yaml` | 复用并叠加 NavCode overrides |
| RxR 实验配置 | `VLN_CE/vlnce_baselines/config/rxr_baselines/baseline_rxr.yaml` | 同一套 runtime，不建第二个 evaluator |
| 任务配置 | `VLN_CE/habitat_extensions/config/vlnce_task_basic_r2r.yaml`、`vlnce_task_basic_rxr.yaml` | 保留动作和指标；修正路径、增加 depth，禁用 agent 不需要的 oracle sensors |
| 配置装配 | `VLN_CE/vlnce_baselines/config/default.py:get_config`；`habitat_extensions/config/default.py:get_extended_config` | 复用；支持 opts，现有 run.py CLI 未暴露通用 task opts |
| Dataset | `VLN_CE/habitat_extensions/task.py:VLNCEDatasetV1`、`RxRVLNCEDatasetV1` | 原样复用 registry / role / language 过滤 |
| 指标 | `VLN_CE/habitat_extensions/measures.py`，Habitat 内置 distance/success/SPL | 原样计算；补齐结果导出，不重写公式 |
| 模型客户端 | `model_client/base.py:ChatModelClient.generate(ChatRequest)->ChatResponse`；`types.py`、`openai_compat.py` | 可复用消息/usage 抽象；生成器和 VLM 分配置；Astra transport 能力需独立验证 |
| 轨迹记录 | `rbnav/trajectory/recorder.py:TrajectoryRecorder`；`checkpoint.py:StepCheckpoint` | 可借鉴字段；不直接作为不可变 trace，因为旧 recorder 会 truncate 动作 |
| 错误恢复 | `rbnav/rollback/executor.py:RollbackExecutor`；`verifier.py:RollbackVerifier` | 逆动作候选和 ORB 验证可借鉴；不保证回到原位，不等于 Python checkpoint |
| 监控 | `rbnav/rollback/execution_monitor.py`、`failure_memory.py` | 可复用循环检测/视觉检查思想；不沿用旧分解器主控 |
| Cost | `model_client/types.py:Usage,response_meta`；`rbnav/usage_stats.py` | 复用 token/latency 字段；新增事件级统计，现有汇总依赖固定组件名 |
| 调试与回放 | `scripts/debug_single_episode_r2r_navigation.py`、`replay_episode_video_from_logs.py`、`rbnav/visualization.py` | 复用图像保存和回放能力；适配新 trace，GT 视频仅 evaluator 可读 |

现有低层策略接口 `rbnav/policies/base.py:LowLevelPolicy.act(observations, instruction=..., info=...)->int` 可以包裹新 controller，但 NaVid/Qwen 动作策略不作为固定方案中的 RGB-D controller 使用。`DiscretePathPlanner` 明确假设无障碍空间，只适合借鉴动作量化。`GoTowardPoint` 使用模拟器几何和位置变更，`ShortestPathFollower` 使用特权几何；均不作为 NavCode 的移动后端。

### 2.1 现有有效配置与行为

| 项目 | R2R-CE | RxR-CE |
|---|---|---|
| shell 入口 | `run_r2r.sh` | `run_rxr.sh` |
| Dataset TYPE | `VLN-CE-v1` | `RxR-VLN-CE-v1` |
| split | val_unseen | val_unseen |
| 指令范围 | 原始英文指令 | 当前 YAML 为 guide，en-US/en-IN；不是全部语言 |
| 仿真 RGB | 640×480，HFOV 90°，位置 `[0,1.25,0]` | 相同 |
| 启用的仿真传感器 | 仅 RGB_SENSOR | 仅 RGB_SENSOR |
| 动作顺序 / ID | STOP=0，MOVE_FORWARD=1，TURN_LEFT=2，TURN_RIGHT=3 | 相同 |
| 几何参数 | 前进 0.25m，转角 30°，ALLOW_SLIDING=True | 相同 |
| Habitat 步数上限 | 500 | 500 |
| 成功距离 | 3m | 3m |
| task sensors | instruction、shortest_path_sensor、progress | instruction、shortest_path_sensor |
| measures | top_down_map_vlnce、distance_to_goal、success、spl、ndtw、path_length、oracle_success、steps_taken | 相同 |

当前不支持后退、相机俯仰或一次移动到任意坐标。API 不得悄悄扩大动作空间；保持现有 30°，不能因为论文使用 15°就更改 benchmark 配置。

### 2.2 需在 M1 解决的集成问题

1. **真值边界**：`run.py:279–294` 把 `env.get_metrics()` 整体传入 `agent.act`。`ShortestPathSensor` 使用 episode goal 求 oracle action，`VLNOracleProgressSensor` 使用目标 geodesic distance。必须从 agent 输入剔除，即便当前旧 Agent 未必实际利用它们。
2. **GT 地图**：`habitat_extensions/config/default.py:109` 起默认绘制目标、最短路、参考路、固定 waypoint。仅关闭绘制不够，整项 `top_down_map_vlnce` 均不进入 Agent/VLM/repair 视图。旧 Agent `_record_vis` 使用它拼接视频；新生成器不得读取该视频。
3. **隐式 oracle 终止**：`run.py:231–232` 硬编码 rotation=15、steps=150；`:281–286` 用 distance_to_goal 是否变化累计计数，再覆盖为 STOP。它不是纯旋转检测，也可能在原地碰撞时触发。保留 legacy 模式行为用于对照；NavCode 模式明确使用无 GT 的动作预算、视觉停滞检测和 Habitat 原有硬上限，并记录终止原因。旧 YAML 的 25/500 未控制这段逻辑。
4. **指标导出**：`target_key` 缺 ndtw；debug summary 有 ndtw，常规 stats 没有。新增导出 ndtw，不改计算。`scripts/analyze_results.py` 将 log 目录所有文件计入分母，会混入 usage/subset/error 文件；正式汇总只遍历 manifest 中 episodes，对失败/无效值显式报告，不静默删除失败。
5. **路径搬迁**：两套 task YAML 的 DATA_PATH / SCENES_DIR / NDTW.GT_PATH 仍指向不存在的 `/home1/gmh/wangyang/RollbackNav/...`，RxR 还多一层 `Habitat/`。通过配置 override 映射到现有 `.../vln/RollbackNav/VLN_CE/data`，不复制数据、不覆盖旧 YAML。
6. **异常语义**：现有 runner 异常后写 skipped_error 并继续；不能让 NavCode 失败 episode 从成功率分母消失。保留错误原始日志，汇总显式统计完成/失败/基础设施错误和全部尝试数量；基础设施错误不得混成可比较的 SR。

### 2.3 数据与 Habitat 版本核查

已直接读取本地 gzip JSON：R2R val_unseen 1839 episodes；RxR val_unseen guide 11006 episodes，其中当前配置英文 3669 episodes。两者涉及的 11 个场景 `.glb` 均存在于 `VLN_CE/data/scene_datasets/mp3d/`。R2R GT、RxR guide/follower GT 文件存在。尚未逐个打开场景/navmesh 验证可渲染性。

**实际运行环境版本待验证，不能写成已确认 0.1.7。** 两个 shell 脚本指定 `vlnce_navid`，当前 `/home1/gmh/anaconda3/envs` 及已登记 conda 环境没有该环境，当前 Python 找不到 habitat/habitat_sim。机器另有 `/home1/gmh/linyuze/NaVILA/habitat-lab` metadata 标注 Habitat 0.1.7，以及 habitat-sim-0.1.7 源码/构建；没有证据证明 RollbackNav 使用它们。包缓存中的版本也不是实际运行版本证据。

M1 在已有可用解释器中记录 `sys.executable`、Python/NumPy/Gym、habitat/habitat_sim/habitat_baselines 的版本及 `__file__`，editable checkout commit、构建信息和配置 hash；随后每个 benchmark 跑无模型调用的 reset→turn→forward→STOP。无需安装或升级 Habitat。若找不到原解释器，M1 运行验收保持未通过，继续做离线开发，不自行部署新 benchmark。

## 3. 依赖与代码组织（拟新增）

```text
现有 Runner / Evaluator（可信父进程 P0）
  ├─ Dataset + Habitat Env + measures + evaluator-only logs
  ├─ ObservationFilter → NavCodeAgent.act(safe_obs, safe_info, opaque_run_id)
  │    ├─ broker / NavigationService
  │    │    ├─ RGB-D geometry + local controller
  │    │    ├─ episode memory + frozen skill library
  │    │    ├─ perception gateway → Visual VLM（仅按需）
  │    │    └─ generator gateway → Astra（生成 / 修复）
  │    └─ RPC ⇄ Python Policy Worker P1（隔离子进程）
  └─ AgentTrace / Cost events；GT EvalTrace 另存，单向离线关联

Worker 不能取得 Env、sim、dataset、evaluator、模型凭证或任意宿主路径。
controller → 单个动作 → Runner.env.step → 最新观测 → controller / worker
```

NavCode 项目根：`/home1/gmh/wangyang/vln/NavCode`，建议新增目录如下；本轮尚未创建这些实现文件：

```text
src/navcode/
  contracts.py                    # API dataclasses / enums / RPC schemas
  integration/rollbacknav_agent.py # reset / act 桥接，不继承旧任务控制流
  integration/observation_filter.py
  integration/config_overlay.py   # 数据路径、depth、预算、profile
  api/service.py                 # 白名单 RPC、权限、预算、obs 版本检查
  runtime/{supervisor,worker,protocol,checkpoint}.py
  generation/{generator,program_validator}.py
  perception/{service,grounding,inspection}.py
  control/{camera_geometry,rgbd_controller,progress}.py
  memory/{episode_memory,workspace}.py
  debugger/{diagnose,repair,validation}.py
  trace/{events,writer,agent_view}.py
  profiling/{spans,usage,report}.py
configs/{navcode_r2r,navcode_rxr}.yaml
scripts/preflight.py
tests/{contracts,integration,runtime,controller,debugger,profiling}/
```

源码依赖以配置中的 `ROLLBACKNAV_ROOT` 定位；启动时工作目录仍设为 RollbackNav，解决旧相对路径。NavCode 包放入该解释器可访问路径。只在一个明确位置装配这两个源码根，不遍布 `sys.path` 修改。

RollbackNav 预计小改动集中在 `run.py`：注册 navcode 工厂/CLI、应用 task overrides、输入过滤、动作反馈/终止通知 hook、导出 ndtw 和 agent trace 引用。新 Agent 有轻量 `on_action_result` / `on_episode_end` 可选 hook，legacy agent 不要求实现。指标计算类与 Habitat 环境不变。

基础依赖优先标准库 multiprocessing/socket/json/hashlib/time/resource + 现有 numpy/opencv/yaml。隔离设施是系统依赖；MCAP 非必需。Astra 的具体模型 ID、transport、reasoning 参数由之后可验证的服务配置提供，不能从产品显示名推断。既有 Chat Completions transport 是否满足该服务需求仍待验证；本阶段只用 fake client，不请求付费 API。

## 4. 统一 Navigation API（NavCode v0 设计）

同步 Python facade；动作 RPC 在内部跨多个 `act` 调用，直到最终结果才返回。一个 episode 同时只允许一个会改动环境的调用。

公共类型：

```python
ObsId = str
MemoryId = str
Action = Literal['MOVE_FORWARD', 'TURN_LEFT', 'TURN_RIGHT']

@dataclass(frozen=True)
class Pixel:
    u: int  # 原始 RGB 像素，左上为原点，向右为正
    v: int  # 向下为正；必须绑定 obs_id

@dataclass
class Result(Generic[T]):
    status: Literal['ok', 'partial', 'error']
    value: Optional[T]
    error: Optional[NavError]  # code, message, retryable, evidence_ids
    obs_id: Optional[ObsId]
    trace_id: str
    env_steps: int
```

所有参数有限长/有限值并经 broker 校验；错误对象只包含脱敏 Agent 可见证据。没有把失败移动默认为成功的 fallback。

| API 签名 | value 返回类型 | 主要错误 / 状态 | 传感器 | Visual VLM | 真值边界 |
|---|---|---|---|---|---|
| `observe(*, channels: tuple[str,...]=('rgb','depth')) -> Result[Observation]` | obs_id、env_step、RGB uint8[H,W,3]、depth_m float32[H,W]、valid_mask、K/外参、sensor_spec；缺失通道显式返回 | SENSOR_UNAVAILABLE、INVALID_CHANNEL、EPISODE_ENDED | RGB；请求 depth 时必须有 depth | 否 | 只允许指定通道；无 oracle、地图、绝对姿态 |
| `recall(query: str, *, scope: Literal['episode','skills']='episode', limit: int=5) -> Result[list[MemoryHit]]` | memory_id、已记录观测/事件引用、文本、来源、workspace_revision、相关性分数 | INVALID_ARGUMENT、SCOPE_DENIED；无匹配返回空列表 | 无新传感器 | 否；v0 用本地索引 | 禁止访问别的 eval episode；skills 只读、版本冻结 |
| `ground(query: str, *, obs_id: ObsId, max_candidates: int=3) -> Result[list[Grounding]]` | candidate_id、bbox_px、pixel、置信度、证据帧；有有效深度时可附 camera-frame point_m | NOT_FOUND、AMBIGUOUS、STALE_OBSERVATION、MODEL_TIMEOUT、INVALID_MODEL_OUTPUT、INVALID_DEPTH | RGB；3D 可选 depth | 是；精确缓存命中除外 | 禁用 semantic simulator labels/object IDs；像素必须校验在帧内 |
| `inspect(question: str, *, obs_ids: tuple[ObsId,...], roi: Optional[Box]=None) -> Result[Inspection]` | answer、confidence、evidence_ids；允许 unknown，不返回 benchmark success | OBS_NOT_FOUND、INVALID_ROI、MODEL_TIMEOUT、INVALID_MODEL_OUTPUT | 指定历史 RGB；可选深度摘要 | 是；缓存命中除外 | 只读 safe frames；不能读 GT 拼图、指标或 judge 标签 |
| `step(action: Action, *, repeat: int=1) -> Result[MotionResult]` | executed_action_ids、executed_steps、final_obs_id、视觉运动估计、blocked/stalled 证据、terminal_reason | INVALID_ACTION、BUDGET_EXHAUSTED、STALLED、EPISODE_ENDED | RGB；前进保护需要 depth | 否 | 每个 primitive 经 Runner；不返回真实坐标/目标距离；无 depth 时拒绝受保护前进 |
| `move_to_pixel(pixel: Pixel, *, obs_id: ObsId, standoff_m: float=0.5, tolerance_m: float=0.3, max_steps: int=20) -> Result[MotionResult]` | 同上，加 local_goal_status 与估计剩余局部距离 | STALE_OBSERVATION、INVALID_PIXEL、INVALID_DEPTH、UNSAFE_TARGET、BLOCKED、NO_PROGRESS、LOCALIZATION_LOST、LOCAL_BUDGET_EXHAUSTED | 对齐 RGB-D、K、外参、跨帧相对运动估计 | 否 | 深度反投影 + 观测内局部几何；禁止 pathfinder / SPF / navmesh / teleport |
| `stop(reason: str='policy_done') -> Result[StopReceipt]` | requested/committed、terminal_obs_id、termination_reason；无 SR/goal_reached | EPISODE_ENDED；重复调用返回原 receipt，不重复发动作 | 无新增要求 | 否 | 发送原 STOP；只有 evaluator 判定成功 |

公共错误还包括 INVALID_ARGUMENT、CANCELLED、WORKER_TIMEOUT、MODEL_UNAVAILABLE、GLOBAL_BUDGET_EXHAUSTED、TRACE_IO_ERROR。全局终止通过控制消息生效，不能由 policy 的 `except Exception` 吞掉后继续运动。`partial` 必须包含已执行动作和中断原因，修复不得重放它们。

observe 不改变姿态、不推进仿真，也不自动调用 VLM；重复 observe 可取得同一帧。环视通过显式 step 转身完成并计步。ground/inspect 永不隐式运动。地面像素、墙面像素和物体表面像素不能混作可行走目标；controller 需检查地面支撑、立体障碍、身体净空和停靠距离，超出局部能力则返回错误。

建议初始 broker 限额：repeat≤8、单次 move≤20 primitive、VLM 输入≤8帧，实际均可配置且取剩余全局预算最小值。旋转也计 env step，修复不会重置预算。所有延迟和调用次数均单独计量。

### 4.1 RGB-D 与局部控制

新增 depth 与 RGB 同分辨率、同 HFOV、同位置/朝向；显式指定深度范围、是否归一化和单位，避免沿用未知 Habitat 默认值。建议 v0 配置 MIN_DEPTH=0、MAX_DEPTH=10、NORMALIZE_DEPTH=False；只有核实实际版本及空值语义后才能认定该配置有效。校验 pinhole K、光轴约定、depth 是 z-depth 还是 range、有效像素掩码。饱和/缺失深度不能当作可通行无限远。

局部目标在源相机系定义，转为局部 agent 坐标。通过 RGB-D 相对运动估计维护短时局部目标与 occupancy，障碍膨胀尺度来自已核实的 agent 碰撞体规格；每个 0.25m/30° 动作后重估，不用 `sim.get_agent_state()` 作里程计。跟踪丢失立即停止当前宏动作，要求重新 observe/ground。累计动作积分只能作为预测，不是已完成位移；滑移、碰撞会导致两者不同。v0 不承诺完整楼梯/跨层规划，遇到不能建模的地面或遮挡返回受限状态。

## 5. Python Policy Runtime

### 5.1 进程边界

P0 持有 Env 和 evaluator；broker、controller、memory 只使用白名单观测。模型 transport 在受控 gateway 内执行，policy worker 无直接网络和凭证。P1 仅取得 nav proxy、JSON task state、脱敏 TaskSpec、只读技能及必要图像缓冲区。禁止 fork 继承 Env；用 spawn 启动 worker。

P1 必须有 OS 级文件/网络隔离与 CPU/内存/墙钟限制，且以无特权身份运行；只挂载批准的 Python 运行时、技能和 episode 工作目录，不挂载 benchmark 数据/GT/父进程文件描述符。可选容器或 Linux namespace/seccomp 实现，M1 核查可用设施，M2 验证边界。仅 AST 白名单、受限 builtins、另开一个普通子进程都不足以构成安全边界；隔离未通过时只运行手写/录制程序 fixture，不执行模型生成代码。

TaskSpec 只含原文 instruction、language、剩余预算、action/sensor specs、workspace revision。用 opaque episode token 关联 worker；scene_id、trajectory_id、dataset path、goals、reference_path、start world pose 不传。Astra / VLM / repair prompt 采用同一 AgentView，无旁路读取结果文件。

### 5.2 持续执行与 Runner 协作

1. reset 取消旧 RPC、清空 episode memory、worker 和 controller；加载固定 workspace 快照。
2. Astra 产出受限 Python 模块；validator 检查 entrypoint、import/API schema、大小与版本。M1–M4 默认使用录制/fake Astra 响应，真实 transport 不发请求。
3. worker 执行 `run(nav, state, task)`；多个观察/计算调用可以发生在同一 Habitat 步之间。
4. worker 发动作 RPC 后阻塞；broker/controller 返回一个离散动作给现有 `act`。Runner 仅执行一次 `env.step`。
5. `on_action_result` 回传新 safe_obs、实际提交动作和 episode_over；controller 可继续请求下一个 primitive。完成后 RPC 返回 MotionResult，原 Python 栈继续运行，而不是每步重新生成 policy。
6. 最后一个动作导致 episode 结束时，即使下一次 act 不会发生，`on_episode_end` 也必须回传 receipt、写最终 trace 并关闭 worker。Runner 的预算覆盖动作必须记录 requested 与 committed 两个值。

API-only 循环、长计算、无限 while 都受墙钟和调用预算约束，不能靠 Habitat 步数限制处理。暂停时 P0 不调用 env.step，不把 STOP 当作暂停；STOP 会结束 episode。

### 5.3 状态、暂停、恢复和修复

状态机：`CREATED → VALIDATING → RUNNING ↔ WAITING_TOOL → PAUSED / REPAIRING → RUNNING → STOPPED / FAILED / CANCELLED`。终止态不再接收运动请求。

- **同进程协作暂停**：API 边界或 primitive 完成后暂停；保持 worker 的 Python 栈、循环局部变量和 P0 Env；resume 继续该栈。纯计算不合作时超时终止 worker，不能声称可无损暂停任意 Python 指令。
- **持久化逻辑 checkpoint**：`state` 只含 JSON 字段，例如 phase、instruction_cursor、landmark_memory_ids、attempts、last_completed_operation。技能在显式阶段边界提交 `checkpoint(label, state)`。保存 program hash/revision、workspace hash、最后已提交 action_seq / op_id、预算、观测引用与 RNG 状态；不 pickle 任意 Python 栈。
- **worker 崩溃 / 程序修复**：P0 Env 保持当前位置；新 worker 从最近逻辑阶段入口及实际最新动作账本启动，入口必须处理“上次宏动作部分执行”。检查状态 schema 兼容，显式 migration 后才接新程序。既不回到 checkpoint 物理位置，也不盲目重跑 run() 前缀。
- **Env/P0 崩溃**：不承诺精确热恢复 simulator、measures 和随机状态。将本次 attempt 标为中断，可由原 dataset reset 重开新 attempt；不能伪装成原 episode 无缝延续。
- **真实回退**：在当前世界执行新的旋转/前进行为，全部计入原轨迹、预算和 SPL。逆动作只是候选；ORB/RGB-D 证据验证后方可报告视觉位置接近。不能 reset/teleport 或删 trace 来实现恢复。

每次 RPC 有 episode_epoch、program_revision、op_id、参数 hash；每个 primitive 有递增 action_seq。P0 维护 queued/committed/result 日志和去重账本，重复请求返回缓存 receipt。提交后 worker 断线也不能重发 primitive；若父进程在提交窗口崩溃而结果不确定，终止该 attempt，不能宣称跨崩溃 exactly-once。队列取消丢弃尚未提交动作并保留已执行前缀。

### 5.4 异常与 Program Debugger

| 事件 | 处理 |
|---|---|
| SyntaxError / 非法 import / schema 不匹配 | 执行前拒绝，返回编译诊断与代码位置；不得发动作 |
| API 参数错误 / 旧像素 / 缺深度 | 结构化错误，policy 可重新观察或调整参数 |
| VLM 超时 / 无效输出 | 有限重试且单独记录 attempt；禁用自动前进兜底 |
| BLOCKED / NO_PROGRESS / 视觉证据不足 | 返回动作前缀及 safe evidence，先局部有界恢复，仍失败交 Debugger |
| Python 未处理异常 / assertion / 死循环 | 保存脱敏 traceback、源码行、state 和 trace 切片，暂停动作队列；有限修复 |
| Worker 越权 / CPU/内存超限 | 强制终止 worker、撤销 token；仅显式可信修复流程可继续 |
| 全局步数/时间/模型调用预算耗尽 | 不再修复；取消待执行动作，写强制终止原因，由 Runner 完成终止协议 |
| Habitat 或 trace 持久化错误 | 基础设施失败，取消 worker，保留诊断；不假装 policy 正常停止 |

Debugger 输入：program revision、异常行/栈、API 参数/错误、最新 RGB-D evidence、显式 state、已执行动作和剩余预算。输出：diagnosis、patch/new program、state migration、resume_label、修复假设。Astra 负责生成修复，确定性 validator 负责语法/契约校验，fake tools 先验证，再从当前位置恢复。没有完整隔离 simulator clone 时，不能声称修复已通过真实环境 dry-run。

v0 每 episode 建议最多 2 次 program repair，计入同一全局预算。终止理由为 policy_done 不等于 success。修复调用和生成调用分别标记，不能藏在普通 VLM 成本中。

## 6. Trace、工作区与 Cost Profiling

### 6.1 不可变记录

独立保存：`agent/trace.jsonl`、`agent/frames/`、`agent/depth/`、`agent/programs/`、`agent/checkpoints/`；`eval/metrics.jsonl`、`eval/manifests/`、GT 可视化仅 evaluator 访问。真实安全边界由隔离和访问权限提供，目录分开本身不构成隔离。

Agent 事件至少含：schema_version、episode_token、attempt_id、event_seq、单调时间、env_step、program_revision/hash、workspace_revision、op_id、action_seq、parent_span_id、source_line/阶段、request/result/error、obs_id/evidence hashes。RGB PNG、depth 无损 float 数组+mask+calibration 单独存储，通过 obs_id 对齐；不把浮点 depth 保存成 JPEG。代码版本、异常、修复 diff、状态迁移、暂停恢复、requested/committed 动作均 append-only。不能使用旧 recorder 的 truncate 作为原始 trace 存储。

回放有两种：离线证据回看，以及同一程序对 recorded tool results 的逻辑重放。后者禁发真实 env.step，不能称为物理轨迹精确重现。evaluator 可离线用 token 对齐指标，join 后的记录不得重新送 Agent/repair。

### 6.2 工作区协议

`skills/` 与 `notes/` 作为跨任务只读快照，带 revision/hash/provenance；episode 的程序、记忆和 trace 可写但不得进入其他 evaluation episode。正式评测固定 workspace revision，禁止场景/episode-keyed 历史成功动作检索。recall 仅本 episode 或冻结通用技能。

失败修复可在当前 episode 内使用自身执行证据；将修复推广成通用技能需单独离线审阅/验证并创建新 workspace revision。若未来开展 ASENA 风格重复任务/GT-feedback evolution，另设 development split 和独立结果名称，不与冻结 val_unseen 指标混合。本项目 M1–M4 不开展此实验。

### 6.3 成本与延迟

统一 span 分类：generator、visual_vlm、repair、python_compute、geometry/controller、habitat_step、trace_io、queue_wait。记录调用数、失败/重试、缓存命中、墙钟耗时、模型版本/endpoint 标识（不含 key）、tokens（区分 input/output/cache/reasoning，如服务提供）、图像数、primitive 数、修复数。

usage 缺失标为 unknown，不能填 0。金额仅在提供明确版本/币种/日期的价格表后离线计算，估计与账单实付分列；本轮不查询或调用付费推理服务。报告端到端 wall time 与各 span duration；嵌套或并行 span 不能直接相加当作总耗时。保留现有 model_usage_summary 兼容导出，并新增分组件/p50/p95/每 episode 成本、env step 耗时和失败率。

现有脚本/agent YAML 含凭证配置，导出配置、trace、异常和程序 prompt 时必须脱敏，worker 不继承宿主全部环境变量；本审计不复制凭证值。

## 7. M1–M4 开发与验收

所有阶段兼容同一 `NavCodeAgent` + 两个 profile。默认禁止真实模型网络调用，使用 deterministic fake generator / fake VLM / recorded responses。真实 Astra 实验不属于当前授权范围。已有 Habitat 可用时才运行本地无付费 smoke，不安装新 benchmark。

| 阶段 | 实现任务 | 验收测试 / 通过条件 |
|---|---|---|
| M1：接入与信息边界 | 固化运行时版本和数据路径；新增轻量 Agent、config overlay、safe observation schema；加入 depth；hook 和 trace 最小链路；修正 navcode 终止与 ndtw 导出 | R2R/RxR 各选固定 episode，用手写 turn→forward→STOP，原 Env 和 measures 输出完整；逐字段注入 oracle/GT，确认不能进入 Agent/VLM/repair；请求与提交动作逐步一致；零模型请求；未找到原运行时则运行验收标为未通过 |
| M2：持续 Python Runtime | worker/broker、API 契约、OS 隔离、超时和预算；实现 observe/recall/step/stop，ground/inspect fixture；动作去重及终止 hook | fake policy 包含循环、分支、变量累计，跨≥20 primitive 不重新生成；暂停期间 env step 不变，恢复局部变量保留；重复 op 不重复移动；STOP/500步/异常最后一步均返回最终 receipt；无限计算可终止；读取 GT/联网/继承 env 越权测试失败 |
| M3：视觉与 RGB-D 导航 | ground/inspect 服务抽象和结构校验；深度标定、RGB-D tracking、局部 occupancy/controller；实现 move_to_pixel | 几何 fixture 验证反投影/坐标/单位；过期像素、NaN/饱和深度、障碍、墙面目标、tracking lost 必须返回对应状态；本地固定短程可达目标能执行并在容差内停住或有界明确失败；两套 profile 各≥5个预先固定局部场景案例；每个 primitive 记录且无 sim pose/SPF/navmesh 调用；VLM 用录制响应 |
| M4：Debugger 与可审计评测 | diagnosis/repair 协议、显式 checkpoint/migration、append-only trace、cost span/report；episode 汇总兼容 | 注入语法错误、运行异常、stale pixel、blocked、VLM timeout、worker crash，各有诊断、预算和失败分类；录制修复从当前位置继续，不重放已提交动作；两 benchmark 各固定5个 episode 零付费运行；eval 指标与同动作序列对照一致（浮点容差预设）；所有尝试有终态，无静默删样本；usage unknown/重试/嵌套 span 统计正确 |

M3 局部控制测试的目标由观测/人工可见像素定义；目标位置误差可由测试/evaluator 私下度量，但绝不回传给控制器。能力验收不要求解决所有障碍或楼梯，必须覆盖可达、受阻、深度无效和定位丢失这四类行为。

依赖顺序：`M1 → M2 → M3 → M4`；contracts、过滤和不可变事件在 M1 定稿，避免最后补日志无法追溯。M4 的成功标准是执行正确、恢复可解释、成本可核对，不设未经实验支持的 SR/SPL 提升目标。

## 8. 本轮交付与下一步

已完成架构审计与接口/验收设计。尚未实施 API、controller 或 runtime，尚未确认可运行 Habitat 解释器。本轮只新增本文档。

下一实施单元应为 M1：定位已有评测解释器，提供两个配置 overlay、白名单过滤及最小 Agent 接入口，先以手写程序通过两套无模型 smoke；不启动付费模型实验，不重建评测系统。
