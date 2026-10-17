# plaxis-automation（PLAXIS 3D 自动化建模 Claude Code Skill · 改进版）

通过 PLAXIS 3D Remote Scripting API（`plxscripting`）自动化创建、修改、修复和验证 PLAXIS 3D 有限元模型的 Claude Code skill。

## 原作者与来源

- **原作者：[Noahpeerless](https://github.com/Noahpeerless)**
- **原仓库：<https://github.com/Noahpeerless/plaxis-automation-skill>**（MIT License）

本仓库基于原作者 2026-09 的版本修改，`plaxis_toolkit.py` 与原版一致，主要改进在 `SKILL.md`。版权和功劳归原作者，修改部分由 [xyj0727](https://github.com/xyj0727) 完成。

## 相对原版的改进

`SKILL.md` 从约 12 KB 扩充到约 39 KB，补充了在 PLAXIS 3D 2024 实际建模中踩过的坑和解决办法，每条都写明现象（含报错原文）、原因和解决办法，涉及：

- 连接与启动、保存失败、中文路径、命令历史损坏的处理
- 几何体分解、桩体穿越多土层后的命名与材料赋值
- 板/界面法向、对称面处理、分阶段激活
- 网格、计算参数、Output 取点与结果提取
- 先写脚本、再用脚本建模、建完逐项核验的流程

## 安装

```bash
git clone https://github.com/xyj0727/plaxis-automation-skill ~/.claude/skills/plaxis-automation
pip install plxscripting
```

## 文件

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Skill 定义与完整建模指南（改进版） |
| `plaxis_toolkit.py` | 原作者的 Python 工具包 |

## 许可

MIT License，见 [LICENSE](LICENSE)。
