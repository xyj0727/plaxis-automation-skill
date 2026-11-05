# PLAXIS 3D 自动化技能

面向 Codex 的 PLAXIS 3D 建模、计算、结果提取与问题诊断技能。通过 `plxscripting` 操作 Input / Output，结合已有实测经验和《PLAXIS 3D基础教程》的逐页知识整理。

## 能做什么

- 组织地层、几何、土体与结构材料、荷载、边界、地下水、界面和施工阶段。
- 按完整脚本建模，逐项回读参数；先验证相关小模型，再展开已确认的正式工况。
- 检查求解状态、保存步和结果对象，脚本打开 Output，提取曲线、场数据和结构内力。
- 查阅本构模型、排水/固结/渗流、网格与数值控制、动力分析和典型工程案例。
- 追溯书页、图表与未决问题，区分教学示例、当前版本文档和已实测行为。

## 教程知识库

入口：[知识索引](references/book/index.md)。覆盖源文件 378 页，包括 18 章、安装附录、参考文献和末尾彩插。各主题按用途拆分，逐页记录见 [阅读账本](references/book/page-ledger.jsonl)。

教材以 2013 版为背景。本增补保留旧版条件、示例参数和书内矛盾；没有宣称所有案例已在当前版本重新求解。实际使用前阅读 [兼容性与勘误](references/book/compatibility-and-errata.md)，不要将教学数值当作工程默认值。

## Codex 安装

优先使用本仓库已有的 marketplace：

```powershell
codex plugin marketplace add xyj0727/plaxis-automation-skill --ref main
codex plugin add plaxis-automation@plaxis-automation-skill
```

在 `~/.codex/settings.json` 中，为 `extraKnownMarketplaces.plaxis-automation-skill` 设置 `"autoUpdate": true`。安装后重启 Codex 加载。手动刷新可执行：

```powershell
codex plugin marketplace upgrade plaxis-automation-skill
```

Codex CLI 不在 PATH 时，使用本机实际安装的 `codex.exe` 完整路径。插件能力因客户端版本而异；本仓库沿用可被 Codex 识别的兼容 marketplace 格式，见 [OpenAI 插件打包说明](https://developers.openai.com/plugins/build/plugins)。

若所用客户端无法安装该插件，可使用技能安装器：

```powershell
npx --yes skills add https://github.com/xyj0727/plaxis-automation-skill -g -a codex -y --copy
```

`npx` 安装不自动更新，手动执行 `npx skills update -g`。更新前先备份自己追加的经验。

## 文件与保留方式

|位置|用途|
|---|---|
|[SKILL.md](SKILL.md)|既有建模指南与实测经验；本次仅在原有内容末尾追加知识入口|
|[references/book/index.md](references/book/index.md)|按任务和章节检索教程知识|
|[scripts/book_lookup.py](scripts/book_lookup.py)|关键词/页码检索与逐页覆盖检查，无额外依赖|
|[plaxis_toolkit.py](plaxis_toolkit.py)|保留的 Python 示例工具包，使用前核对当前版本及任务参数|

运行 PLAXIS 脚本优先使用与当前安装匹配的 Python 与 `plxscripting`。系统 Python 的版本兼容性须单独验证；技能安装并不替代 PLAXIS 软件、许可证或项目参数确认。

本仓库提供独立整理的知识与操作指导，不分发书籍 PDF、扫描图或完整 OCR。新增内容的来源与页码可追溯。代码及既有材料的许可条款见 [LICENSE](LICENSE)。
