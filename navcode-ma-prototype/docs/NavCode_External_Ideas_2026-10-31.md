# 相关工作到可验证改动（2026-10-31）

## 阅读依据

只把论文与官方仓库作为技术依据。下表区分原工作机制、当前系统可借鉴的设计和实现条件；不复用其他任务的成功率作为 R2R/RxR 目标成绩。

| 工作 | 原工作提供的线索 | 对当前实现的启发 | 比较时必须核对 |
|---|---|---|---|
| [SuperNav](https://arxiv.org/html/2610.12126v1)、[官方实现](https://github.com/zju3dv/SuperNav) | 工具化导航、图像点目标、方向视图、技能与持续任务上下文 | 明确语义目的方向，再交局部执行；失败后改变视角/入口；保留失败记录和待查分支 | 主要任务是目标搜索等；Geo executor 使用 simulator pose/navmesh/follower，不能作为本项目传感器控制器直接替代。Learned executor 也有训练来源和监控条件 |
| [LaViRA](https://arxiv.org/html/2510.19655v2)、[官方实现](https://github.com/NJU-R-L-Group-Embodied-Lab/lavira-code) | Language / Vision / Robot 分层，将方向计划与区域定位分开；四方向观察和历史上下文 | 避免把“谓词是否成立”和“具体朝哪里走”压缩成一个候选标签 | 论文使用 posed RGB-D、地图及 FMM；R2R-CE 的100条 val_unseen 子集、重复运行协议需与我们清单区分。无需训练不等于无需几何输入 |
| [CA-Nav](https://chenkehan21.github.io/CA-Nav-project/)、[官方实现](https://github.com/Chenkehan21/CA-Nav-code) | 用对象、位置、方向约束管理子指令；约束感知 value map 的区域选点 | 阶段条件应可观察且保留来源，选点应考虑连通区域而非只有单帧局部地面 | 地图与感知依赖需要单独核查；已有的 typed evidence gate 不能冒充复现其 value mapper |
| [VLMnav](https://proceedings.mlr.press/v288/goetting25a.html) | 将空间决策组织为 VLM 问答，并系统研究接口设计 | B0 应使用同样的可执行运动工具，让直接决策与 Code 策略公平比较 | 任务、动作候选与历史接口必须一致；不能把换模型当作角色消融 |

## 本项目的推断与实验假设

以下是我们针对已记录失败提出的实现方案，不是上述论文已经验证的结论。

1. **路线意图与局部地面目标分离。** Vision 返回当前图像中的路线 anchor 与显式坐标系。宿主只计算 bearing、匹配当前观测的候选；没有方向一致的候选时要求重新观察。anchor 本身不提供三维可达性或目的地成功证据，逐 primitive 的深度检查继续生效。
2. **可检索的路线经历。** 保留已支持的阶段条件、原始报告与应用后的状态、失败方向和相关帧。模型预测必须标注为待核实，撤回与新观察必须能覆盖旧假设。先测试有界文本上下文是否减少重复选点；不先引入未经验证的世界坐标地图。
3. **主动多方向观察。** 通过合法旋转获取环境视图，记录每次实际动作和相对方向。四方向信息会增加动作与图像成本，必须与相同预算的单视图配置比较；不能通过瞬时 simulator 相机 pose 读取免费全景冒充普通传感器输入。
4. **入口搜索与退让是不同技能。** 物理接触后短退让只能解除局部卡点。仍能看到目标、但前方不连通时，应改变目标点或调查入口；不继续反复请求同一类前进。相关选择仍由策略与 Vision 证据驱动。

## 已落地的第一项与实验记录

实现文件为 `navcode/control/route_grounding.py`，由 `--route-grounding` 显式启用，保持对照配置可运行。原始 Vision 报告、方向绑定结果、应用后的证据分别追加落盘。

训练样本36121第37–39帧的第一版离线调查暴露了 0..1 与 0..1000 坐标接口不一致；非法输出被拒绝，没有执行动作。修订为显式 `coordinate_frame` 后，两种坐标系都只按声明转换，不从数值范围猜测。完整测试65项通过。探针目录：

- `experiments/route_grounding_probe_rxr_v7`：第一版接口失败，保留失败证据。
- `experiments/route_grounding_probe_rxr_v7b`：Omni，方向绑定有时要求先转头，但仍可能误判开口。
- `experiments/route_grounding_probe_rxr_max_v7b`：Max，与Omni对开口选择仍有分歧。

这些是同一训练轨迹中的连续帧，不是三条独立导航样本，也没有导航成功率。之后的端到端运行使用同一运动前初始程序，以避免初始代码随机变化掩盖接口差异；修复与视觉调用仍可能不同，需要如实记录。

后续端到端 `grounded_rxr_36121_route_omni_v7b` 和 `grounded_rxr_36121_route_max_v7b` 均失败，未把方向绑定提升为默认配置。官方 SuperNav 参考仓库另行只读检出到 `/tmp/navcode-supernav-reference-20261031`，commit `89f8f5d2ea8f5e5409540e16ac2d74faab40bcc8`；阅读了前视配置的恢复与入口搜索说明，尚未复现其系统或执行器。

## 实验顺序

先完成方向绑定的端到端诊断，再冻结配置测试固定 train 清单中其他场景。若未解决具体失败，不直接扩大调用量。随后实现 B0、B2、B3 的同模型/控制器/预算比较，并分别消融路线 anchor、经历上下文、主动视角和修复。最后冻结提示与技能，运行既定 val_unseen 清单，报告全部结果与资源开销。
