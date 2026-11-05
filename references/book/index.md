# PLAXIS 3D 基础教程知识索引

本知识库把《PLAXIS 3D基础教程》的正文、操作截图、表格、公式、算例和末尾彩插整理为可检索的建模与分析指导。书籍信息：刘志祥、张海清编著，机械工业出版社，2014 年，ISBN 978-7-111-48654-1。扫描 PDF 共 378 页；本次还读取了同一文件经 Adobe 识别后的文字层。

**先读 [兼容性与勘误](compatibility-and-errata.md)**。教材采用 PLAXIS 3D 2013 背景；书中数值、默认值、界面和安装方式不自动适用于当前工程。应用示例导言（PDF 264）明确提示示例参数不能直接作为实际工程推荐值。未在当前版本执行的内容保持“书中定义/待验证”状态。

## 按任务查阅

|任务或问题|阅读模块|
|---|---|
|单位、符号、文件管理、界面、模式、浏览器、命令行|[units-input.md](units-input.md)|
|钻孔、层面、水头、几何创建/变换/导入|[geology-geometry.md](geology-geometry.md)|
|荷载、指定位移、动力乘子、板/梁/桩/锚/界面、水力对象|[loads-structures-water.md](loads-structures-water.md)|
|本构选型、排水类型、强度/刚度、界面、结构材料|[constitutive-materials.md](constitutive-materials.md)|
|持水/渗透模型及书版 Hypres、USDA、Staring 参数表|[hydraulic-presets.md](hydraulic-presets.md)|
|三轴、固结、DSS、一般应力路径与参数比较|[soil-test-calibration.md](soil-test-calibration.md)|
|网格、阶段树、K0/重力、求解类型、步长、误差与停止|[mesh-phases-solvers.md](mesh-phases-solvers.md)|
|地下水、固结、全耦合、降雨、干湿与流边界|[groundwater-consolidation.md](groundwater-consolidation.md)|
|Output 视图、剖面、图例、导出、报告和动画|[output-visualization-export.md](output-visualization-export.md)|
|位移/应变/应力/孔压/流量/板梁桩锚界面结果的含义与符号|[output-quantities-signs.md](output-quantities-signs.md)|
|曲线选点、存储步、应力路径、曲线编辑与导出|[curves-interpretation.md](curves-interpretation.md)|
|第7–10章的公式、表述疑点及版本限制|[errors-version-notes.md](errors-version-notes.md)|
|刚性基础、筏板/桩筏、支护基坑、吸力桩加载|[foundation-excavation-caisson.md](foundation-excavation-caisson.md)|
|软土路堤、排水、安全分析、盾构推进、库水骤降|[embankment-tunnel-drawdown.md](embankment-tunnel-drawdown.md)|
|机器振动、自由振动、地震、旧安装附录和彩插索引|[dynamics-installation.md](dynamics-installation.md)|
|把教程转为完整脚本、工况表、参数确认、回读及验证|[automation-review-workflow.md](automation-review-workflow.md)|

## 页码与覆盖定位

PDF 页从 1 起算。正文与参考文献印刷页 1–357 对应 PDF 14–370；封面、前言、目录、分部扉页、空白页和彩插按实际页面单独记录，不能一概用偏移关系推算其印刷页码。

|章节|内容|印刷页|PDF 页|
|---|---|---|---|
|1|PLAXIS 3D 简介|3|16|
|2|一般说明|4–6|17–19|
|3|输入程序概述|7–30|20–43|
|4|地层模拟|31–40|44–53|
|5|荷载和结构|41–78|54–91|
|6|材料属性和材料数据库|79–142|92–155|
|7|网格和计算|143–198|156–211|
|8|输出程序概述|199–223|212–236|
|9|输出结果|224–236|237–249|
|10|曲线|237–249|250–262|
|11|超固结黏土地基基础沉降|253–273|266–286|
|12|砂土中基坑开挖支护|274–285|287–298|
|13|吸力桩加载|286–290|299–303|
|14|软土地基路堤填筑稳定性|291–303|304–316|
|15|盾构分段开挖沉降|304–318|317–331|
|16|库水骤降坝体稳定性|319–326|332–339|
|17|弹性地基振动装置|327–333|340–346|
|18|建筑物自由振动及地震|334–344|347–357|
|附录|历史安装、许可和常见问题|345–355|358–368|
|参考文献|进一步阅读入口|356–357|369–370|
|彩插|原书彩色图对照|无统一印刷页码|371–378|

每页的实读主题、图表、提炼知识和未决项见 [page-ledger.jsonl](page-ledger.jsonl)；文件指纹、页数与处理方式见 [source-manifest.json](source-manifest.json)。账本是逐页原创提炼记录，不是逐字转写。图中的小字、缺失示例输入文件及书内矛盾，按条目保留不确定性，不用 OCR 猜测补齐。

[case-catalog.json](case-catalog.json) 将八章应用示例组织为十个条目（第11章区分 A/B/C 三种基础），记录几何、材料、阶段、输出和待确认事项。它是来源索引，未标为当前版本已执行的模型输入文件。

## 快速检索

在技能目录执行，不需要启动 PLAXIS：

```powershell
python scripts/book_lookup.py "不排水"
python scripts/book_lookup.py "吸力" --limit 20
python scripts/book_lookup.py --page 101 --json
python scripts/book_lookup.py --check
```

关键词同时检索逐页记录与主题模块正文；`--page` 按 PDF 页精确查询。先定位页或专题，再读周围完整说明及表头单位；需要复核原始图表时打开用户本地 PDF。仓库不附书籍 PDF、扫描图片和完整 OCR 文件。
