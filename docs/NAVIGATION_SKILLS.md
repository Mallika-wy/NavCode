# 导航技能包

## 内容组织

角色提示词位于 `navcode/prompts/roles/`，只定义角色、工具协议、输出结构和预算。具体导航做法放入 `navcode/skills/`：

| 技能 | 使用角色 | 触发情形 |
|---|---|---|
| policy-writing | Code | 编写或修订 Python Policy |
| state-repair | Code | 已有 checkpoint 上的程序修复 |
| route-following | Code / Vision | 将指令阶段关联到当前可见路线 |
| blocked-motion | Code / Vision | 停滞、深度拒绝、退让失败、重复选点 |
| verification | Code / Vision | 经过、跨越、当前位置和终点判断 |

每个技能是独立的 `SKILL.md`。`catalog.json` 仅登记名称、用途、角色和入口；`registry.py` 只允许按登记名称读取。不接受模型提供的任意文件路径，也不允许读取角色之外的技能。技能内容只是流程指导，不是场景观测或完成证据。

## 加载与预算

`--skills` 启用实验技能模式；默认配置仍可用于旧提示词对照。旧角色提示保留在 `navcode/prompts/legacy/`，迁移后的文本逐项验证与原版一致。

- Code 编写前由运行时加载 policy-writing；修复时补充 state-repair。
- Vision 调查时加载 route-following；收到受阻反馈时由运行时加载 blocked-motion。
- 两个角色还可显式返回 `{"tool":"read_skill","name":"verification"}` 等请求。
- 模型请求读取技能会消耗一次模型调用。Vision 的读取和 recall/crop 共用原有每合同调查轮数与整条轨迹调用上限。
- Code 每次编译最多两次额外技能读取，保留最后一个可用调用用于生成源码。技能模式整条轨迹 Code 调用上限为4，旧模式为2；Policy revision 上限仍为2。正式比较必须统一总预算并记录实际 usage。

技能从本次运行的 `implementation/skills/` 快照读取。快照同时归档 Python、Markdown 和 JSON，批次冻结也检查提示词和技能变化。`SKILL_LOADED` 记录角色、名称、内容 hash 和加载原因，可区分运行时触发和模型主动读取。技能读取不会扩大场景感知、运动或文件访问权限。

## SuperNav 的研究借鉴与适配

参考了 [SuperNav 论文](https://arxiv.org/html/2610.12126v1) 和[官方技能目录](https://github.com/zju3dv/SuperNav/tree/main/skills)，本地研究副本 commit 为 `89f8f5d2ea8f5e5409540e16ac2d74faab40bcc8`。阅读重点为前视全局技能、探索返回、入口调查、恢复及局部执行状态说明。

本项目采用可定位的触发条件、执行反馈分类、对应处理步骤和验证条件来组织自己的技能。内容针对当前 NavCode 工具和 R2R/RxR 指令任务重新编写，没有把 SuperNav 的 ObjectNav 距离规则、目标接触流程或 navmesh 执行器权限接入本项目。

技能结构值得研究，但性能须由本项目实验验证。首轮 Skills v9 的 RxR23531 与 R2R3586 均未成功；前者没有再出现之前的缺失状态字段异常，后者真实触发了模型主动技能读取。这些是机制运行证据，不能称为成功率提升。详细结果及待解决问题见根目录 `RESEARCH_PROGRESS.md`。

## 验证与运行

测试覆盖角色权限与路径逃逸拒绝、模型技能请求的实际调用计数、非空 checkpoint 的修复指导、视觉调查预算与图像权限保持、最后一次 Code 调用保留和资源快照冻结。当前完整测试76项通过。

恢复研究后可用新目录运行（调用收费 API）：

```bash
source scripts/navcode_env.sh
.venv/bin/python -m navcode navigate --suite rxr --episode-id 23531 \
  --skills --route-memory --output experiments/new_skills_run
```
