# NavCode

Code-as-Policies VLN 项目。当前采用从 GitHub 直接克隆的官方 VLN-CE 代码，同时支持 R2R-CE 和 RxR-CE。

## 上游评测代码

- 仓库：https://github.com/jacobkrantz/VLN-CE
- 本地目录：`third_party/VLN-CE/`
- 分支：`master`
- 本次获取并核对的远端 HEAD：`729d141b2ee10628061ada74dd3a5b9f70faeba5`
- 上游提交时间：2025-01-07；提交消息：`Fix RxR data link`
- 本次获取日期：2026-10-31

“最新”指获取时官方仓库默认分支的最新提交，不是将依赖升级到最新 Habitat。官方 README 指定 Habitat-Sim / Habitat-Lab 0.1.7。上游源码保持原样，含原始 Git 来源、LICENSE、requirements 和评测配置。

| 内容 | 路径（相对上游目录） |
|---|---|
| 统一 train / eval / inference 入口 | `run.py` |
| R2R 配置 | `vlnce_baselines/config/r2r_baselines/` |
| RxR 配置 | `vlnce_baselines/config/rxr_baselines/` |
| R2R task | `habitat_extensions/config/vlnce_task.yaml` |
| RxR English task | `habitat_extensions/config/rxr_vlnce_english_task.yaml` |
| Dataset 与 metrics | `habitat_extensions/task.py`、`habitat_extensions/measures.py` |
| 无学习 Agent 与评测循环 | `vlnce_baselines/nonlearning_agents.py` |
| 模型评测逻辑 | `vlnce_baselines/common/base_il_trainer.py` |

在依赖与数据齐备后，从上游目录执行评测入口，例如官方 R2R random-agent 配置：

```bash
cd third_party/VLN-CE
python run.py --exp-config vlnce_baselines/config/r2r_baselines/nonlearning.yaml --run-type eval
```

上面是官方 baseline 入口。新增 NavCode 真实环境接入与开发实验见文末；官方 RxR CMA baseline 仍需要其指令特征/模型权重。

## 本次纠正

不使用 RollbackNav 的代码作为项目基线。此前误复制的旧代码已移出当前项目；当前评测源码仍为干净的官方 GitHub 版本。

## 本地评测数据

已按用户要求将现有数据从 `/home1/gmh/wangyang/vln/RollbackNav/VLN_CE/data/` 完整复制到当前官方框架的 `third_party/VLN-CE/data/`，保留原始数据。数据为独立文件副本，不使用软链接或硬链接，不迁入旧项目评测代码，也不下载新 benchmark。

| 内容 | 当前路径 |
|---|---|
| R2R 原始指令 | `third_party/VLN-CE/data/datasets/R2R_VLNCE_v1-3/` |
| R2R 预处理指令与 GT | `third_party/VLN-CE/data/datasets/R2R_VLNCE_v1-3_preprocessed/` |
| RxR 指令与 guide/follower GT | `third_party/VLN-CE/data/datasets/RxR_VLNCE_v0/` |
| 90 个 MP3D 场景 | `third_party/VLN-CE/data/scene_datasets/mp3d/` |
| Connectivity graph | `third_party/VLN-CE/data/connectivity_graphs.pkl` |

复制范围为源目录的全部 393 个文件，合计 39,138,550,714 字节（约 36.45 GiB）。文件一致性与 val_unseen 场景/GT 覆盖校验见 `DATA_TRANSFER_REPORT.json`。上游仓库原有 `data/res/` 文件同时保留；它们不属于这 393 个源数据文件。

从 `third_party/VLN-CE/` 运行时，上游配置中的相对数据路径可直接定位这些数据，无需修改官方配置。未沿用旧项目改过的传感器、动作或 Runner。

源数据不含 RxR baseline 的预计算 BERT `text_features/`；此目录也未下载。现有指令、GT 与场景的数据迁移完成，不代表官方 CMA baseline 所需特征、权重和 Habitat 运行环境齐备。

`ARCHITECTURE_AUDIT_AND_INTEGRATION_PLAN.md` 保留作历史审计记录，其中针对 RollbackNav 的集成路径不再代表当前代码基线，后续需要基于官方上游重新审计。

## NavCode 真实环境开发（2026-10-31）

代码已按职责分为 `agents/`、`models/`、`control/`、`evidence/`、`runtime/`、`benchmark/`、`artifacts/` 和 `runners/`；目录说明、依赖关系与权限边界见 [代码结构](docs/ARCHITECTURE.md)。相关论文与拟验证机制见 [外部方法研究记录](navcode-ma-prototype/docs/NavCode_External_Ideas_2026-10-31.md)。

角色提示词已迁到 `navcode/prompts/`，导航过程指导位于 `navcode/skills/`，支持冻结快照、角色授权与按需读取，见 [导航技能包](docs/NAVIGATION_SKILLS.md)。`--skills` 为实验开关，首轮两条开发运行均失败，尚未证明性能收益。

已新增 `navcode/`：官方 R2R/RxR dataset + 原生 measures、单写者 ActionBroker、传感器白名单、DMXAPI 双角色调用、bubblewrap 隔离 Python Policy、视觉历史检索/裁剪与有界工具纠错。原型 `navcode-ma-prototype/` 继续保留作 mock 协议测试。

**已通过双 benchmark 仿真 smoke，并取得若干真实 R2R train 成功；RxR 稳定导航及正式 val_unseen 对照尚未验证。** 当前结果与下一步研究依据见 [RESEARCH_PROGRESS.md](RESEARCH_PROGRESS.md)。

```bash
source scripts/navcode_env.sh
# 本机 .venv 已复用现有 Python 3.10 / PyTorch / Habitat 0.1.7 构建。
.venv/bin/python -m navcode smoke --suite r2r --output experiments/new_r2r_smoke
.venv/bin/python -m navcode smoke --suite rxr --output experiments/new_rxr_smoke
PYTHONPATH="$PWD/navcode-ma-prototype:$PYTHONPATH" .venv/bin/python -m pytest -q tests navcode-ma-prototype/tests
# 以下命令会调用收费 API，读取根目录 .env 的 DMXAPI_TOKEN。
.venv/bin/python -m navcode develop --suite r2r --episode-id 1 --output experiments/new_dev_run
# 新的 RGB-D 地面候选/阶段证据/隔离代码实验：
.venv/bin/python -m navcode navigate --suite r2r --episode-id 3586 --output experiments/new_grounded_run
.venv/bin/python scripts/build_replay.py experiments/new_grounded_run
.venv/bin/python scripts/summarize_runs.py
```

模型 Client 仅引用用户指定的 `/home1/gmh/wangyang/vln/RollbackNav/model_client` 独立包；环境、评测、导航代码均不依赖旧项目。硬件/软件来源与版本在 `experiments/environment.json`。策略 Worker 只能看到系统 Python 和 RPC，无法读取 Client、数据集、宿主目录或 API Key。
