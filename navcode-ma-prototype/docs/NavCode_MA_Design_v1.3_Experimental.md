# NavCode-MA v1.3 — 从真实执行反推的实验架构

2026-10-31。实验实现，尚未证明优于单 Agent，也未完成正式 val_unseen 评测。保留 v1.2 的 Code Agent + Vision Agent + Python Policy + 非 LLM Supervisor 核心。

## 1. 当前实际运行的职责

Code Agent 使用 DeepSeek Flash 把原文编译成阶段与 Python 循环；初始代码不读取 GT 或 simulator。Vision Agent 使用 Omni Flash 调查当前阶段，可以检索历史或裁剪。Policy 自己决定何时转向、选择地面目标、推进阶段或停止。Supervisor 管理证据适用性、预算、程序暂停/修复和唯一 ActionBroker。DepthController 是纯代码局部运动器，检查新深度，不理解任务语义。

```
原文 + 公开能力 → Code Agent → Python Policy（bubblewrap Worker）
                                    │
                  perceive(contract)│ move_to_candidate / turn / STOP
                                    ▼
                          非 LLM Supervisor
                         ↙                 ↘
                Vision 调查服务          DepthController
                current / recall / crop   新 depth / 每步检查
                         ↘                 ↙
                           唯一 ActionBroker
                                    │ primitive
                                    ▼
                         官方 Habitat / VLN-CE
                                    │ episode 终止后
                                    ▼
                          私有原生 SR/SPL/nDTW
```

源码：项目根目录 `navcode/grounded.py`、`controller.py`、`agents.py`、`sandbox.py`、`policy_worker.py`、`benchmark.py`。旧 mock fixture runtime 没有放开模型源码执行权限，真实 Worker 是另一套 OS 隔离实现。

## 2. 视觉 ID、动作句柄、物理状态三者分开

视觉模型只选择短别名：帧 f0/f1，当前图上的 W1/W2 地面标记。宿主把帧别名映射为完整 `episode_epoch:action_seq`，把地面标记映射为 `obs_id/W1` 这样的完整动作句柄。Code Policy 读取、传递完整句柄，不要求模型手工复制 opaque ID。

这是实测必须的边界：早期模型曾抄错长帧 ID；另一条生成程序把 W1 永久加入 blocked 列表，误把以后每张图上的 W1 都当作同一目标。完整句柄在观测之间不同，因此局部失败记录不会错误污染新帧。控制器同时校验句柄确实在当前 catalog 中、obs_id 仍为当前帧。

地面标记来自 RGB-D 合法传感器：根据相机内参把深度投影到局部坐标，估计可见水平地面，按当前合法转角提供方向候选。没有目标坐标、navmesh 查询、世界 pose 或 shortest path。标记表示可见地面候选，不保证整段路径可达。

## 3. 可执行的感知合同与证据应用

Policy 请求至少包含 `stage_id / task_span / predicate / predicate_type`。Supervisor 增加 epoch、request、revision、current_obs、stage_start_obs、运动收据摘要、当前 catalog、工具/时限预算。

`predicate_type` 的用途：

- `VISIBLE`：只判断地标/开口可见，不能作为到达目的地的充分条件。
- `SPATIAL`：当前在房间内、在目标旁；SUPPORTED 必须引用当前帧。
- `TRANSITION`：经过、穿过、绕过；SUPPORTED 至少需要当前阶段发生过 forward command、有对应图像变化，并引用不同的阶段开始/当前帧。转头不能证明 crossing。

这些检查是**必要条件，不是语义真值验证**。有 forward 命令及图像变化，仍不能证明移动了准确距离、跨过正确的门或沿指令走了正确的一侧。

原始 Vision 报告写 `PERCEPTION_RESOLVED`；宿主检查后另写 `EVIDENCE_APPLIED`，拒绝时保留 `source_verdict` 与拒绝原因，不抹除原报告。只有应用后的 SUPPORTED 可以支持新阶段；扫描耗尽不能跳阶段。显式撤回 claim 会清除依赖的已接受阶段并暂停 Policy，交 Code Agent 审查。

现有证据检查仍有限：没有可靠的 landmark 物理身份追踪，没有人工标注的判断精度，没有证明撤回链在复杂真实失败上正确。不能把 schema 通过或 SUPPORTED 当作 GT。

## 4. 连续执行与恢复

Worker 通过 JSON RPC 调用：

```python
nav.observe()
nav.perceive(contract)
nav.move_to_candidate(handle, obs_id, max_steps=4)
nav.turn(degrees)       # [-90, 90]，按当前 track 转角量化
nav.recover()           # 显式请求有上限的传感器退让探针
nav.checkpoint(state)
nav.step("STOP", op_id)
```

局部移动绑定原始观测。转向后用新深度检查，前进每个 primitive 后重新获取 RGB-D。返回 `PARTIAL / DEPTH_BLOCKED_OR_UNKNOWN / VISUALLY_STALLED` 和 nominal commanded advance，不声称测到了真实世界位移。

相对转向 helper 防止模型把“再看右边”实现为 15° 一次、每次都重新调用 VLM。所有角度仍折成合法 primitive，全部计入动作预算。

两次局部移动没有可观察进展（包括提交 forward 但图像停滞），或同一阶段/同一观察连续请求四次，会在下一个感知 RPC 前暂停 Worker。Code Agent 收到 checkpoint、已应用证据、失败原因与当前合法 RGB，修复未完成逻辑。已提交动作由 Broker 保留，不重新 reset 或重放运动前缀。检查触发后会重置监控计数，给修复程序行动机会。

模型传输/正文异常与程序异常使用不同异常类型。传输失败不应被当成需要重新编写代码的问题；当前没有隐藏自动重试，每次 API 尝试独立计数并落盘。复杂异步服务、断点持久化及跨 Supervisor 进程重启的动作幂等性仍需继续实现。

## 5. 从真实失败得到的控制参数约束

RxR 的 640×480、79° HFOV 下，某帧最近可见地面约在 2.3m。旧候选生成允许该点，运动检查却只统计 2m 内地面，导致有目标也不能前进。现在两者使用相容的可见范围，地面统计到 3m，候选最远 2.5m。

旧走廊检测额外横向膨胀 8cm，在 RxR radius=18cm 时把相邻门框也计入通道障碍。实际深度显示一簇约 x=23cm 的近距离侧面点，超出机器人半径，却封死中心方向。当前横向余量为 3cm；单测同时要求真正位于身体通道内的近障碍仍被检测。该选择需要更多狭窄通道和碰撞样例验证。

水平地面假设、地面估计范围和深度截断仍是限制；尚无合格的上下楼梯控制器，也未证明传感器噪声/网格漏洞下可靠。当前只报告 RGB-D track，不把这些结果写成 RGB-only 成绩。

## 6. 已有结果与验证要求

R2R 调试 episode 1 真实自主停止，native SPL=0.755、nDTW=0.414；固定开发清单中的 R2R 3586 经 v2 修改后自主停止，NE=0.492m、SPL=0.786、nDTW=0.618。它们是训练集调试结果，不能报告为“2/2 泛化成功”。

修改前固定清单首三条 R2R 和首三条 RxR 均失败（0/6），记录完整保留。当前正在用修订控制器复测 RxR，并在未用于这些修订的其他 train 场景上检验。提示词、动作/调用预算、源码 snapshot 与结果均需分版本解释。

下一阶段必须补：相同 Controller/模型/总费用预算的 B0/B2/B3 对照；EPC、阶段检查与修复各自的消融；人工证据抽查；冻结后运行独立 val_unseen 清单。现有模型混用及 budget 变化不支持把成功改善单独归因于多 Agent 或 Controller。

后续 v4 还让 Code Agent 接收初始 RGB 并检查锚定条件；Max 的服务端 JSON 输出已实测接通。原失败例 3202 达到 NE=1.312m、SPL=1.0、nDTW=0.866。v3 在另外三个此前未调试的 train 样例中为1/3，仍不足以宣称稳定泛化。

当前已接入显式调用的传感器退让探针：最多两次，根据后视深度选择方向，再次尝试时换侧，单次前进前重新检查深度并恢复原朝向。地面不可见时标记未知，不能声称可通行；退让动作不能作为沿路线前进的阶段证据。单个 RxR 停滞点的模拟器诊断中，第一次受阻，第二次换侧后发生位移并可继续三个前进动作；这不是端到端导航成功率或跨场景验证。

加入仅重用初始、运动前生成程序的配对机制：检查任务、场景身份、传感器轨道和初始 RGB，不读取后续轨迹与指标。3202 的 Max/Omni 同程序配对均失败，结果不能支持模型或多 Agent 的总体排序；此配对也不是单 Agent 与双 Agent 架构消融。

详细日志、测试、费用已知/未知项及当前进展见根目录 `RESEARCH_PROGRESS.md`；互动回放由 `scripts/build_replay.py RUN_DIRECTORY` 从真实事件生成。
