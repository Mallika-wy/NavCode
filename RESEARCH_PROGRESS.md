# NavCode 研究进展与可复现实验

> 最新交接（2026-10-31，本轮结束后按用户要求暂停）：代码已分层，长提示词迁为资源文件，并接入参考 SuperNav 思路、针对 NavCode 重写的可读取技能包。完整测试 **76 项通过**。首轮 Skills v9 的两条 train 导航均失败，未证明性能提升；没有运行 held-out。所有实验进程已结束，不再启动新实验。用户将先与 GPT 讨论，之后再决定继续。最新交接、结果和未解决问题见文末“本轮收尾与暂停交接”。

2026-10-31。本轮实际推进了代码、运行环境、真实 API 和失败证据。目标仍是实现有良好导航结果的多 Agent Code-as-Policies 架构，**没有完成，当前不能宣称架构有效或达到好的 SR**。

## 当前判断

保留设计核心：Code Agent 生成/修复长期运行 Python Policy；独立 Vision Agent 调查视觉合同并检索历史；非 LLM Supervisor 管理动作、预算、状态和评测隔离。现阶段证据说明，程序格式、可执行性、证据 ID 正确只是必要条件。主要未解决问题是视觉的空间/运动判断、目标与可通行地面关联，以及局部运动闭环。

下一版应让 Vision Agent 从**合法传感器产生的局部候选地面目标**中选择，并为“看见 / 已经过 / 已抵达”提供不同证据合同；Controller 在每个 primitive 后检查新传感器。Code Agent 继续负责阶段、恢复、预算与条件分支。先以明确标注的 RGB-D track 验证深度局部控制，再考虑 RGB-only learned controller；二者单独报告。

这与已有分层导航工作一致，但只是工程选择依据，不构成我们已经成功的证据。[NaVILA 官方项目](https://navila-bot.github.io/)将高层 VLA 与实时运动技能分开；[ASENA 官方项目](https://research.nvidia.com/labs/gear/asena/)提供可选的训练过的单目导航策略作为编程 Agent 的工具。ASENA 的多轮经验积累结果针对重复任务，不能当作冻结策略在新 episode 上的零样本指标。[官方 waypoint 论文](https://openaccess.thecvf.com/content/ICCV2021/papers/Krantz_Waypoint_Models_for_Instruction-Guided_Navigation_in_Continuous_Environments_ICCV_2021_paper.pdf)也专门学习像素到局部导航目标的映射。当前项目没有复制这些训练策略或权重。

## 已运行、可核对的内容

- 新增源码在 `navcode/`；官方 `third_party/VLN-CE/` Git 跟踪源码保持原样。
- Habitat-Lab / Sim 0.1.7 复用机器上已有源码与 Sim 编译产物。独立 `.venv` 仅补齐兼容的 Python 依赖，继承已有 Qwen 环境的 PyTorch。没有重新下载数据、模型或重编译模拟器。
- R2R / RxR 英文 guide 使用同一 adapter、各自官方任务配置与原生 metrics。在线 task sensors 全部移除，原文指令从合法 instruction 字段读取，RxR 不需要预计算 BERT 特征。
- R2R 转角 15°、RxR 30°；两者实际解析的前进距离均为 0.25m。动作集合分别为四个和六个 primitive；当前生成策略仅使用 STOP / FORWARD / LEFT / RIGHT。
- `filter_observation` 白名单仅交付 RGB（独立 RGB-D 诊断允许 depth）。完整 config、GT、世界 pose、场景名、metrics 不进入模型或 Worker 上下文。Habitat reset 会把初始 pose 写入 config，故 Code Agent 的 capabilities 必须使用显式字段选择。
- `ActionBroker` 唯一调用 `env.step`，检查 episode epoch、op_id、payload、动作集合与预算。重试去重，不允许同一 ID 换动作。metrics 只在终止后读取。
- `model_api.py` 仅使用用户指定的独立 `RollbackNav/model_client` 包；不导入旧项目的环境、导航或评测实现。请求/响应、usage、延迟、截断、错误落盘，不记录密钥，不自动重试。
- `PolicyRuntime` 用 bubblewrap 分离 user/mount/PID/network 等 namespace；只挂载只读系统 Python/库、单个 Worker 和临时目录。Worker 没有宿主 home、数据集、网络、API Key 或 GPU 权限。另有资源、消息、RPC 次数与 wall-time 限制；没有 in-process exec 回退。
- 测试覆盖真实 Python 循环执行、宿主文件/环境/网络隔离、死循环终止、未授权 RPC、修复保留 checkpoint 且不重放已提交动作，以及感知 schema / 历史检索 / 工具纠错。测试报告：`experiments/tests_current.txt`。
- `VisionAgent` 可在单个合同内主动 recall / crop，再提交报告；短帧 ID 在可信边界映射回完整 episode obs_id。无效裁剪/引用在调查预算内反馈纠错，耗尽后返回 UNKNOWN。报告可显式撤回旧 claim，写入追加事件并触发程序检查；真实撤回质量尚未实测验证。

复现入口：

```bash
source scripts/navcode_env.sh
PYTHONPATH="$PWD/navcode-ma-prototype:$PYTHONPATH" .venv/bin/python -m pytest -q tests navcode-ma-prototype/tests
.venv/bin/python -m navcode.benchmark --suite r2r --output experiments/new_r2r_smoke
.venv/bin/python -m navcode.benchmark --suite rxr --output experiments/new_rxr_smoke
# 产生模型费用，输出目录必须不存在：
.venv/bin/python -m navcode.develop --suite r2r --episode-id 1 --output experiments/new_dev
.venv/bin/python -m navcode.develop --suite rxr --episode-id 48721 --output experiments/new_rxr_dev
.venv/bin/python scripts/summarize_runs.py
```

环境来源/版本：`experiments/environment.json`；额外 Python 依赖：`scripts/requirements-navcode.txt`。启动环境路径可以通过 `NAVCODE_SIM_BUILD`、`NAVCODE_HABITAT_LAB` 覆盖。官方 extensions 的 dataset、measures、config 以 namespace 方式直接加载，跳过会导入全部训练器的 package initializer，未替换 dataset 或 metric 的实现。

## 真实结果：都是开发诊断，不是正式 benchmark

每个目录含 `result.json`、逐事件 `trace.jsonl`、源码 revision、模型调用记录和 RGB。所有收费导航尝试使用 train；没有把 val_unseen 成绩反馈给模型或调参。

| 实验目录 | 内容 | 结果与解释 |
|---|---|---|
| `experiments/m0_r2r/` | 可信手写 4 动作 RGB smoke | native SR=0，SPL=0，nDTW=0.4042；验证链路 |
| `experiments/m0_rxr/` | 同上，RxR train episode 1 | native SR=1，SPL=1，nDTW=0.6913；仅前进 0.25m 即成功，不能证明导航能力 |
| `experiments/api_probe/` | Omni 视觉真实帧描述 | 成功识别厨房岛台等地标；不是闭环导航成绩 |
| `experiments/dev_r2r_001_v1/` | Omni 编程 | 60s 读超时，未执行导航动作；usage 未返回 |
| `experiments/dev_r2r_001_v2/` | DeepSeek 编程 | 2200 输出 tokens 耗在默认思考，最终正文为空；保留记录 |
| `experiments/dev_r2r_001_v3/` | 关闭思考，真实沙箱执行 | 长帧 ID 抄错导致感知引用校验失败；未前进 |
| `experiments/dev_r2r_001_v4/` | 帧短 ID + 程序循环检查 | 能调用 crop / recall；裁剪坐标单位和工具数量错误导致失败 |
| `experiments/dev_r2r_001_v5/` | 工具错误在 Vision 内处理 | 行走 1m，NE 从 6.608 降到 5.614m，native SR=0、nDTW=0.4214；随后重复请求工具，耗尽预算 |
| `experiments/dev_r2r_001_v6/` | 强制最终报告阶段，Vision 改用 Qwen Flash | 原地左右振荡，行走 0m，native SR=0；说明程序执行成功不代表运动策略有效 |
| `experiments/dev_rxr_48721_v1/` | 固定 manifest 中另一个场景的 RxR | 6 个转动动作、行走 0m，NE=11.038m，native SR=0、nDTW=0.2116；预算耗尽 |
| `experiments/m0_r2r_rgbd/` | 单独 RGB-D smoke 与深度几何诊断 | 成功采集真实 depth；只验证可见表面的几何估计，尚未驱动导航 |

开发 budget 当前为最多 120 个 Agent primitive、12 个感知合同、16 次 Vision 调用、2 次 Code 调用。调试失败记录全部保留。Supervisor 为结束环境补发的 STOP 独立标记 `forced_stop`，不把它算成 Agent 成功；新结果另存 `agent_success`。环境原始 metrics 始终保留。早期调试结果没有该新字段，需结合 `forced_stop` 解读。

## 实验改变了哪些判断

1. **需要显式关闭默认思考来打通低成本结构化链路。** DeepSeek 曾返回空 final content 与 finish_reason=length；关闭后约 7–11s 即可产生实际程序。参数依据 [DeepSeek 官方 thinking 文档](https://api-docs.deepseek.com/guides/thinking_mode/) 和 [DMXAPI Qwen 参数说明](https://doc.dmxapi.cn/thinking-qwen.html)。这只是本次配置下观察，不是模型质量排名。
2. **复制 opaque ID 不应成为模型能力测试。** 原 32 位 epoch 帧 ID 曾被抄少一位。现由模型选择 f0/f1，宿主严格映射，不做模糊匹配或猜测修正。
3. **工具错误属于 Vision 调查循环。** 不应为了修复 crop 单位而重新生成导航代码。已有有界工具纠错；最终回合使用无工具 final prompt，避免重复工具请求吞掉全部预算。
4. **视觉置信与进度存在实质错误。** R2R v6 中没有任何前进动作，却有 SUPPORTED “已经绕过岛台”。RxR 也可能把命令性短语误写为可判定 predicate。下一版须把 instruction compilation 的动作目标、可观察完成条件、必要运动前提分开验证。
5. **先解决合法局部控制。** 仅靠 VLM 猜 bearing / free-space，容易振荡或过早推进阶段。应该比较同一 Controller 下的 B2/B3，而不是把更好的 Controller 的收益归因于多 Agent。
6. **深度几何也要实测校准。** R2R 初始深度显示地面到相机约 1.394m，而 sensor 的相对 y 配置为 1.25m；Agent origin 不等于渲染地面。`local_geometry.py` 因此从合法 depth 估计水平地面，未用 simulator pose 补偿。诊断见 `depth_clearances.json`，仍未验证楼梯、空洞、各种相机角度及可达性，不能当作完整 Controller。

## 固定样本、费用与后续门槛

`experiments/manifests/` 已固定 R2R / RxR 各 12 个 train development trajectories、各 30 个 val_unseen held-out trajectories；seed=20261031，按 scene 轮流选择，每 trajectory 只选一条指令，不参考结果。两个开发集各覆盖 12 scenes，两个 held-out 集各覆盖 11 scenes。R2R episode 1 属于额外接口调试样例；RxR 48721 属于已固定开发集。当前没有读取 held-out 轨迹作在线上下文，也未运行 held-out 导航评测。

API 请求有硬调用数与输出长度限制；usage 汇总见 `experiments/api_usage_summary.json`。实际人民币扣费、剩余额度尚不知，不能把 token 数当费用。未返回 usage 的超时也不能算零费用。[DMXAPI 当前余额接口](https://doc.dmxapi.cn/yuer.html)要求系统访问令牌和用户 ID，现有模型调用 Key 不等同于这些管理凭据。没有输出/复制密钥到实验数据，也没有修改账号设置。

继续工作的门槛：

- 实现并验证绑定 obs_id 的地面目标与 primitive 局部执行；转动后重算几何，每步前进后读取新深度；RGB-D 单独标记。
- 将 route compilation 的阶段谓词改成可观察、可证伪的条件；识别纯旋转无法证明 crossing，避免预期中的动作被当作已发生。
- 补真实证据撤回、状态迁移与 resume 的压力测试；强化 Worker 的 IPC/超时与基础设施失败分类。
- 在固定 train 子集完成 B0/B2/B3 的同 Controller 对照，再测 EPC / Ledger / Repair 消融。要有多场景实际提升，不能依靠单条 train 样例成功。
- 冻结程序生成提示、视觉提示与技能后，才运行 val_unseen held-out。报告 SR/SPL/nDTW、调用/usage/费用、动作、wall time、停止/振荡/碰撞/语义进度错误及置信区间。
- 仍需做更完整评测规模、人工证据抽查、可视化演示和最终架构结论；这些均未被当前单测或 smoke 证明完成。

## 第二阶段：RGB-D 候选目标、阶段检查与真实恢复

新增 `navcode/controller.py` 与 `navcode/grounded.py`，并保留原 RGB primitive 开发入口。当前实验设计更新为 [v1.3 Experimental](navcode-ma-prototype/docs/NavCode_MA_Design_v1.3_Experimental.md)。

### 新增并验证的机制

- 深度生成可见地面候选；Vision 选择短标记 W1/W2，宿主映射为 `obs_id/W1` 完整句柄。标记在下一帧可重用，完整句柄不可重用，防止生成程序把某帧 W1 的失败永久套用到所有后续 W1。
- 每个 primitive 后刷新 RGB-D；转向后的前进检查使用新深度。相对 `nav.turn(degrees)` 折成各 track 的 15°/30°动作，避免每转 15°就消耗一个视觉合同。
- `VISIBLE / SPATIAL / TRANSITION` 分开；当前位置判断须引用当前帧，crossing 须有阶段内 forward 命令、图像变化和前后帧证据。原始报告与应用后 verdict 分开追加记录。新阶段不能越过未获支持或已撤回的前序阶段。
- 反复无动作、反复局部受阻会暂停 Worker；Code Agent 可以读取当前 RGB 与 checkpoint 修复。真实 Omni RxR v4 已触发第二次编程调用，继续同一 epoch、递增动作序号，无环境 reset；导航最终仍失败，不能称修复成功到达目标。
- Code Agent 从 v4 起接收初始 RGB，避免把“到楼梯顶后右转”盲编成启动即右转。初始照片仍可能有歧义，需先调查前提是否成立。
- 分清 nominal commanded advance 与物理进展。VISUALLY_STALLED 即使提交了 0.25m 命令也计为无进展；同一 RGB-D view 下曾停滞的方向不重复尝试。此缓存不是物理地图，也不证明其他视点目标可达。
- Qwen Max 曾在 final content 写长段分析，导致 JSON 解析或输出长度失败。当前通过 payload 的 `response_format=json_object` 强制 JSON，同时继续关闭所引用 Client 的自动 fallback/retry，确保每次请求被预算记录。真实 API probe 验证该模式可用。
- 每次新实验保存 `implementation/` 源码副本及 `provenance.json`；固定批次启动每个 episode 前检查源文件 hash，避免边改代码边把结果混在同一批。

当前 **49 项测试通过**，见 `experiments/tests_current.txt`。包括窄通道、2m/3m 地面范围、旧帧不能支持当前目标、候选跨帧身份、真实停止图像循环交接、程序 revision/attempt 区分，以及 JSON 模式不触发 Client 隐式重试。RxR 原生仍有六个动作，但本版水平相机控制器禁止 Policy 使用 LOOK_UP/DOWN，避免相机俯仰后仍套用水平地面投影。

实际 RxR simulator sensor spec 已只读核对：RGB/Depth 均为 position y=0.88、640×480、HFOV=79；记录在 `experiments/rxr_sensor_calibration_audit.json`。没有读取或使用 agent world pose 修正控制器。

### 新结果与重要边界

| 实验 | SR/停止 | SPL | nDTW | NE / 实际路程 | 解释 |
|---|---|---:|---:|---|---|
| `grounded_r2r_001_v1` | 真正自主成功 | 0.755 | 0.414 | 2.16m / 8.75m | 调试样例，路线遵循仍弱；1 Code + 21 Vision 次调用 |
| `grounded_batch_r2r_v1` 首三条固定 train | **0/3** | 均为0 | 均值0.316 | 见逐例 JSON | 3586/4173/8814，全部预算耗尽 |
| `grounded_batch_rxr_v1` 首三条固定 train | **0/3** | 均为0 | 均值0.287 | 见逐例 JSON | 48721/5116/36121，全部失败 |
| `grounded_r2r_3586_v2` | 真正自主成功 | 0.786 | 0.618 | 0.49m / 14.50m | 对失败开发例修订后；1 Code + 31 Vision |
| `grounded_batch_r2r_fresh_v3` 下一组三条 train | **1/3** | 均值0.333 | 均值约0.454 | 见逐例 JSON | 3202误入错误房间；7509预算耗尽；6333成功。此三条在 v3 修订前未用于调试 |
| 同上 6333 | 真正自主成功 | 1.000 | 0.829 | 2.90m / 5.08m | 不是单独调通后挑选进入批次 |
| `grounded_rxr_36121_v3` | 失败 | 0 | 0.398 | 5.93m / 0.28m | 原生实际路程与多次 forward 命令严重不符；19次 visual stall |
| `grounded_omni_rxr_36121_v4` | 修复后仍失败 | 0 | 0.475 | 5.37m / 0.88m | Code revision 2，恢复协议已执行，任务未成功 |
| `grounded_max_r2r_3202_v4_json` | 真正自主成功 | 1.000 | 0.866 | 1.31m / 7.88m | v3中同例 NE=16.17m、nDTW=0.078。使用初始RGB + Max + JSON，不是只换一个变量的消融 |
| `grounded_max_rxr_36121_v4_json` | 失败 | 0 | 0.374 | 6.12m / 0m | 更强视觉模型也未解决该例的局部运动问题 |

**不能据此宣称“多 Agent 带来提升”。** 原始 RGB 与 RGB-D 开发实验在动作/调用预算、控制器、提示与模型配置上不同；同一 episode 的不同程序也来自独立模型生成。当前都是探索性证据。正式归因必须补同程序或配对编译、同 Controller、同模型/预算的 B0/B2/B3 及 EPC/Repair 消融。

v3 的 1/3 是很小的 train development 结果，统计不确定性很大，不能替代 val_unseen。已有成功并不表示目标完成；尚未做冻结后的正式 held-out 实验。

### RxR 运动失败的免费物理探针

`scripts/probe_local_recovery.py` 只重放某条 train 运行到首次停滞的动作前缀，然后运行预先固定的 primitive 恢复动作；不调用模型、不读 pose/navmesh，不用 goal metrics 决策。原生 metrics 只在每个 probe STOP 后读取。这些是物理诊断，不是导航成功率。

`experiments/recovery_probe_rxr_36121/summary.json` 显示：

- 原地再试3次 forward：RGB 完全不变，实际总路程仍0.280m。
- 先转180°退一步再恢复朝向：回到原接触点，后续继续停滞。
- 退向另一侧（相对150°）再恢复朝向：后续3次 forward 都产生明显RGB变化，总路程1.411m。

这给出明确下一步：实现**由合法深度选择、Policy 显式调用、有次数/动作上限**的本地退让/脱困技能，再验证其是否真正改善 RxR 完整导航。不能把针对该例离线选出的150°方向直接当作通用策略；应检查后视深度候选来决定方向，并复测其他场景。

### 交付与下一步

复现新入口（有 API 费用，输出目录必须不存在）：

```bash
source scripts/navcode_env.sh
.venv/bin/python -m navcode.grounded --suite r2r --episode-id 3586 --output experiments/new_grounded
.venv/bin/python -m navcode.grounded --suite r2r --episode-id 3202 --model qwen3.8-max --output experiments/new_max
.venv/bin/python scripts/run_grounded_manifest.py --manifest experiments/manifests/r2r_train_12.json --start 3 --count 3 --output experiments/new_fixed_batch
.venv/bin/python scripts/build_replay.py experiments/new_grounded
```

本地互动回放：[R2R 3586](experiments/grounded_r2r_3586_v2/replay.html)、[R2R 6333](experiments/grounded_batch_r2r_fresh_v3/6333/replay.html)、[Max R2R 3202](experiments/grounded_max_r2r_3202_v4_json/replay.html)。可逐帧查看原始RGB/地面候选、阶段合同、实际动作、Python revision 和历史证据。它是离线研究回放，还没有 Python 当前行高亮或在线服务。

接下来优先：RxR 通用局部恢复 → 配对冻结程序的模型/角色对照 → 扩大固定开发集 → 冻结提示与技能 → val_unseen。已有 source/manifest/轨迹/失败均保留。费用仍只能报告已返回 usage 的 token 总量；实际人民币扣费和余额未取得，公开 pricing 接口及模型 Key 尝试均返回403，未尝试修改账号设置。

## 最新：有界退让与初始程序配对

`nav.recover()` 已接入，最多调用两次；根据后视深度选侧、逐步重新检查、必要时换侧，并返回原朝向。若地面不可见，该动作只是短距离探测，不保证地面可通行；退让前进不计入阶段路线进展。单个 train 场景的免费模拟器探针 `experiments/recovery_controller_probe_rxr_36121/result.json`：第一次选择的侧向深度复核受阻，第二次换侧后一步使视图变化，后续路线探针三次前进，整段原生路程 1.411m。第二次退让最终状态仍为 `REAR_DEPTH_BLOCKED`，因为后续一步被深度检查阻止；不能把该状态写成完全脱困或任务成功。该探针不使用目标位置、全局姿态或 navmesh 决策。

初始程序缓存仅接受提交前无动作、相同任务/语言、episode、split、模型、RGB-D 轨道与初始 RGB 的原始程序，不读取运行结果或后续轨迹。两条 train 3202 对照均使用同一原始程序、源码版本和预算：`paired_3202_max_v5` SR=0、NE=16.08m、nDTW=0.079；`paired_3202_omni_v5` SR=0、NE=16.15m、nDTW=0.078。两者均耗尽视觉合同并强制停止，这是一个探索性模型配对，不是架构消融或总体模型排名。缓存调用本身为零次编程 API；公平核算时两组均应计入原始编程调用的 3267 reported tokens，此外各自计入运行时视觉调用。

控制器图像快照现在复制数组，防止传感器缓冲原地更新使变化检测漏报。完整测试 54 项通过，见 `experiments/tests_current.txt`。目前初始程序的 episode/track 匹配不自动证明相机配置及完整控制参数相同，正式配对还需核查源码 hash 和配置。实际费用与余额仍未知；没有运行 held-out。

端到端 `grounded_rxr_36121_recovery_v6` 使用新生成的程序与 Omni：两次调用退让，第一次未移动；程序修复后第二次换侧退让产生视图变化，随后一次局部移动提交四次 forward。之后再次连续受阻，第二次修复请求超出两次 Code API 上限而强制停止：SR=0、SPL=0、nDTW=0.488、NE=5.160m、原生路程 1.911m。该结果证明了本次端到端调用链和局部运动延续，并不证明任务成功或可靠增益；它与旧实验的程序及过程不同，不能当作严格消融。轨迹可在 `experiments/grounded_rxr_36121_recovery_v6/replay.html` 查看。

人工检查第 37 帧及相应感知报告：视觉模块正确指出前方是 console 墙和左右开口，却选择画面中部地面 W1 作为通向开口的目标；后续选点/深度复核重复受阻。候选点只描述局部可见地面，不保证其朝向语义目标；应检验当开口与候选方向不一致时先转向再获取新候选的策略，而不是放宽深度保护或直接把候选视为目的地。

`paired_rxr_36121_no_recovery_v6` 重用上一运行的初始程序、相同模型、源码 hash 与动作/感知/修复次数上限，仅禁用退让能力；关闭退让结果 SR=0、SPL=0、nDTW=0.398、NE=5.930m、路程 0.280m，修复次数耗尽。开启退让一侧 SR=0、nDTW=0.488、NE=5.160m、路程 1.911m。两侧初始编程的成本应均计入，关闭侧实际新编程请求仅为一次修复。修复程序各自重新生成，退让也改变后续观察和视觉调用次数；这是单样本机制诊断，不证明一般性能提升或完整架构的效果。

## 本轮收尾与暂停交接

用户最新要求：本轮结束即停止，更新 progress，等用户与 GPT 讨论后再继续。本节为当前接手入口；前文保留历史，不把早期规划中的“下一版尚未实现”当作最新实现状态。

### 1. 本轮代码与研究交付

- **代码分层完成。** `agents/`（Code/Vision/协议）、`models/`（API）、`control/`（深度与局部动作）、`evidence/`（证据检查）、`runtime/`（Broker/沙箱/Worker）、`benchmark/`（官方环境）、`artifacts/`（程序缓存和快照）、`runners/`（组装实验）。统一 CLI 为 `python -m navcode navigate`；旧 grounded/develop/model_api 命令保留薄兼容入口。详见 [结构与依赖边界](docs/ARCHITECTURE.md)。
- 重构前源码在 `experiments/package_refactor_20261031/before/`。主要方法 AST 对比及独立 Worker 字节比对均一致；重构后真实 RxR 恢复诊断复现1.411m的原生路程。详见该目录 `semantic_checks.json` 与 `simulator_probe/result.json`。
- **Prompt 和 Skills 分开。** `navcode/prompts/roles/` 为短角色提示；`prompts/legacy/` 保留旧配置对照且逐项验证文本一致；实验方向提示单列。`navcode/skills/` 有 policy-writing、state-repair、route-following、blocked-motion、verification 五个 Markdown 技能及角色授权目录。
- Skills 从本次 `implementation/skills/` 冻结快照加载；入口/反馈触发与模型主动读取均有事件，记录名称、角色、hash和原因。模型可用 `read_skill` 工具，但不获得额外场景或文件访问权。源快照/批次冻结现在覆盖 **50项资源：34个Python、15个Markdown、1个JSON**，不归档 `.env`。
- `--skills` 为显式实验开关。Code调用上限由旧模式2次变为技能模式4次，用于可计费的技能读取；Policy最多2个revision不变。Vision读取技能与recall/crop共用原调查和调用上限。正式消融必须统一总预算并报告实际token，不能直接归因于技能。
- 完整测试 **76项通过**，见 `experiments/tests_skills_v9_final.txt`。覆盖技能角色/路径权限、非空checkpoint的修复指导、技能读取的调用计数、最后一次编程调用保留、视觉图像权限和指导资源冻结。详见 [导航技能机制](docs/NAVIGATION_SKILLS.md)。
- 阅读了 [SuperNav论文](https://arxiv.org/html/2610.12126v1)、官方技能包和LaViRA、CA-Nav等工作；研究副本 `/tmp/navcode-supernav-reference-20261031`，commit `89f8f5d2ea8f5e5409540e16ac2d74faab40bcc8`。导航技能内容针对本项目工具和R2R/RxR路线任务重新编写，没有采用其navmesh执行器权限或ObjectNav停止阈值。相关机制与比较条件见 [外部方法记录](navcode-ma-prototype/docs/NavCode_External_Ideas_2026-10-31.md)。

### 2. 新增的真实运行结果（全部是train开发）

| 目录（`experiments/`下） | 变体 | outcome | SR | nDTW | NE / 实际路程 |
|---|---|---|---:|---:|---|
| `grounded_rxr_36121_route_omni_v7b` | 同初始程序，Omni，图像路线anchor | REPAIR_EXHAUSTED | 0 | 0.474 | 6.014m / 2.911m |
| `grounded_rxr_36121_route_max_v7b` | 同初始程序，Max，图像路线anchor | BUDGET_EXHAUSTED | 0 | 0.480 | 5.488m / 1.721m |
| `grounded_rxr_36121_memory_v8` | 同初始程序，有界路线文本上下文 | REPAIR_EXHAUSTED | 0 | 0.488 | 5.160m / 1.911m |
| `grounded_rxr_23531_memory_v8` | 固定清单另一场景，新程序及路线文本上下文 | REPAIR_EXHAUSTED | 0 | 0.211 | 11.298m / 0m |
| `grounded_rxr_23531_skills_v9` | 重用上行初始程序，Skills及路线上下文 | REPAIR_EXHAUSTED | 0 | 0.211 | 11.298m / 0m |
| `grounded_r2r_3586_skills_v9` | 重用历史初始程序，Skills及路线上下文 | BUDGET_EXHAUSTED | 0 | 0.265 | 10.903m / 1.000m |

这些运行均被强制终止，SPL均为0。不能将模型/程序修复随机性、控制器变化、上下文和预算变化混成技能或多Agent收益。方向anchor和路线文本上下文均未提供可靠改善，未提升为默认配置。历史3586成功没有在本轮Skills运行中保持；这值得检查，但不是一次严格配对消融。

两条Skills v9运行实际新增 **38次API请求、162,920 reported tokens**（RxR：5次/20,232；R2R：33次/142,688）。它们重用已有初始程序，公平核算还应计入原始编程token（分别3,309和2,418），实际没有重复支付这两次初始生成。整个项目累计已记录793个结果文件、2,238,472 reported tokens，4次结果缺失usage；**实际人民币扣费和余额仍未知**。汇总在 `experiments/api_usage_summary.json`。

回放：[RxR23531 Skills](experiments/grounded_rxr_23531_skills_v9/replay.html)、[R2R3586 Skills](experiments/grounded_r2r_3586_skills_v9/replay.html)。各v7/v8运行也已生成 `replay.html`。

### 3. 机制已经发生，但不能当作导航提升

- RxR23531的Code Agent修复时确实加载policy-writing和state-repair。本次没有再出现v8的 `KeyError: failed_handles`，但仍未摆脱物理停滞。仅能说明该次修复避免了先前错误。
- R2R3586的Vision Agent确实主动请求读取技能；不是仅把长提示词改名。该运行的工具请求包括5次crop、2次read_skill和2次recall，另有JSON/裁剪schema纠错，最终耗尽32次视觉调用，只完成17个合同。
- 图像anchor第一版因模型返回0..1000而要求0..1失败；现在显式声明坐标系并验证，不默默猜测数值单位。方向绑定只检查几何一致性，不证明语义目标正确或路径可达。
- 局部移动现在记录每批 `forward_with_visual_change`，不会把先有观察变化、最后一步停滞的整批动作误判为完全无进展。图像变化仍不等于测量了物理位移。

### 4. 建议与GPT优先讨论的问题（尚未修改/验证）

1. **证据verdict与下一步动作分离。** R2R初始有多次 `REFUTED + target=null + suggested_observation=NONE`，旧程序因此不采取动作，反复检查同一帧。需要让未完成合同明确给出可执行目标、观察请求或让出复审，而不是只重复“尚未发生crossing”。不能靠把verdict改成SUPPORTED来绕过停滞。
2. **修复触发计数过早。** 当前一次前进失败会累加blocked_streak，紧接着一次失败退让又累加；下一次感知前便触发“两次局部目标失败”的Code修复。RxR23531中，这使Vision在当前revision内没有机会根据退让失败调查其他入口。应讨论按独立移动尝试计数，以及先允许一次带反馈的视觉调查。此逻辑目前未修改。
3. **局部控制与路线选点仍是主要瓶颈。** RxR23531转身后能看到左前方门口，但中央地面W1朝床边，前进没有位移，后方窗户也没有退让空间。需要查明合法侧向primitive能否脱离该点，以及地面候选为何不能支持合适入口方向。新脚本 `scripts/diagnostics/probe_heading_escape.py` 已写出，固定比较预先声明的相对方向；**仅语法检查，尚未运行模拟器探针**。不得把该例离线选出的最佳方向写死为通用策略。
4. **技能要做行为消融。** 当前首轮主要证明加载、权限与修复机制可运行，没有证明导航更好。应审查技能是否过度强调判定而忽略行动、是否增加不必要的读技能/裁剪，以及JSON返回可靠性。先解决具体失败，再扩大固定多场景实验。
5. **架构结论仍缺实验。** B0/B2/B3同模型、同控制器、同总预算的正式比较未实现/未完成；EPC、记忆、修复和技能的独立消融及人工证据抽查未完成。val_unseen仍保留，不应在开发中调参。

### 5. 暂停点

本轮所有实验均已结束，live jobs为空。没有安排自动批次或新API请求。接手时先读本节、`docs/ARCHITECTURE.md`、`docs/NAVIGATION_SKILLS.md`，再根据用户讨论结论决定下一步。目标尚未达成，当前是用户要求的暂停，不是完成。
