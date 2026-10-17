---
name: plaxis-automation
description: >
  通过 PLAXIS 3D Remote Scripting API（plxscripting）自动化创建、修改、修复和验证
  PLAXIS 3D 有限元模型。用于处理 .p3d/.p3dat 项目、材料、土层、几何体、钻孔、
  渗流边界、降雨、排水线/点/面、阶段、网格、计算、结果文件清理，以及保存失败、
  data.plxml/data.convd.rr1、中文路径或命令历史损坏等 PLAXIS 自动化问题。
---

# PLAXIS 3D 自动化建模

> 原作者：[Noahpeerless](https://github.com/Noahpeerless)（<https://github.com/Noahpeerless/plaxis-automation-skill>，MIT）。本文件为 xyj0727 的改进版。

使用 Python `plxscripting` 连接 PLAXIS 3D Input 的 Remote Scripting Server，完成建模、模型修改、核验和必要的项目文件修复。

## 基本连接

PLAXIS 3D 2024 默认安装路径：

```text
D:\Seequent\PLAXIS 3D 2024\Plaxis3DInput.exe
```

启动时优先不要传项目路径，先启动 Remote Scripting，再用 `s.open()` 打开项目：

```python
import subprocess
import time
from plxscripting.easy import new_server

exe = r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DInput.exe"
port = 10005
password = "12345678"

subprocess.Popen([
    exe,
    f"--AppServerPort={port}",
    f"--AppServerPassword={password}",
])

last = None
for _ in range(45):
    time.sleep(1)
    try:
        s_i, g_i = new_server("localhost", port, password=password, request_timeout=30)
        break
    except Exception as exc:
        last = exc
else:
    raise RuntimeError(f"PLAXIS 连接失败: {last!r}")

s_i.open(r"C:\short_ascii_path\model.p3d")
g_i.gotosoil()
```

注意：

- `g_i.gotosoil()` 后再访问 `Volumes`、`LineDrains`、`Points`、`Materials` 等对象。
- 如果 `10000` 端口异常监听或连接卡死，换新端口，例如 `10005`、`10006`。
- 中文路径容易在 PowerShell 管道、Python stdin 或 PLAXIS 命令历史中变成 `?`；优先创建 ASCII 硬链接/目录联接，例如 `C:\plaxis_drainage_link\model.p3d`。
- 结束前清理卡住的 PLAXIS/Python 进程，避免文件锁：

```powershell
Get-Process python,Plaxis3DInput -ErrorAction SilentlyContinue |
  Stop-Process -Force -ErrorAction SilentlyContinue
```

## 路径与项目文件

PLAXIS 项目不是只有外层 `.p3d`。实际模型几何通常从同名 `.p3dat\data.plxml` 读取：

```text
model.p3d
model.p3dat\
  data.plxml
  data.p3d
  data.success.p3dlog
  data.full
  data.opi
```

关键经验：

- 只改外层 `.p3d` 或 `data.p3d/data.full` 命令日志，不一定改变 GUI 打开的模型树。
- 没有有效 `.p3dat\data.plxml` 时，`s.open("model.p3d")` 可能只打开空模型；纯命令日志 `.p3d` 不会自动重放。
- 如果要从命令日志重建模型，应逐条执行命令并检查 `feedback.success`，而不是只 `s.open()`。

## 执行命令日志并核验

逐条执行命令时，必须检查 PLAXIS 返回的失败反馈；`s.call_commands()` 对部分失败不会抛异常。

```python
from pathlib import Path

def run_command_file(s_i, path):
    failures = []
    for index, raw in enumerate(Path(path).read_text(encoding="ascii").splitlines(), start=1):
        cmd = raw.strip()
        if not cmd or cmd.startswith("##"):
            continue
        result = s_i.call_commands(cmd)
        ok = True
        messages = []
        for item in result:
            feedback = item.get("feedback", {})
            ok = ok and bool(feedback.get("success", False))
            messages.append(str(feedback.get("extrainfo", "")))
        if not ok:
            failures.append((index, cmd, " | ".join(messages)))
    return failures
```

常用核验函数：

```python
def value(obj):
    try:
        return obj.value
    except Exception:
        return obj

def name_of(obj):
    try:
        return str(value(obj.Name))
    except Exception:
        return str(obj)

g_i.gotosoil()
weep_rows = [name_of(d) for d in g_i.LineDrains if name_of(d).startswith("LD_WEEP_ROW_")]
old_weep = [
    name_of(d) for d in g_i.LineDrains
    if name_of(d).startswith("LD_WEEP_") and not name_of(d).startswith("LD_WEEP_ROW_")
]
print("Volumes", len(g_i.Volumes))
print("LineDrains", len(g_i.LineDrains))
print("LD_WEEP_ROW", len(weep_rows), weep_rows)
print("old LD_WEEP", len(old_weep))
print("Points", len(g_i.Points))
print("Lines", len(g_i.Lines))
```

## 修改排水对象

创建线排水：

```python
parts = g_i.linedrain((23.95, 0.5, 0.8), (23.95, 19.5, 0.8))
```

命令日志里等价写法：

```text
linedrain (23.95 0.5 0.8) (23.95 19.5 0.8)
rename Point_1 "PT_WEEP_ROW_01_1"
rename Point_2 "PT_WEEP_ROW_01_2"
rename Line_1 "LN_WEEP_ROW_01"
rename LN_WEEP_ROW_01.LineDrain "LD_WEEP_ROW_01"
set LN_WEEP_ROW_01.LineDrain.h 0.0
```

将大量逐孔泄水孔等效为按高程排的线排水时：

- 删除对象树里的旧 `LD_WEEP_###`、相关 `Line/Point/PointDrain`。
- 同时删除命令历史中的原始 `pointdrain ...` 行；否则重建时会再次生成逐孔排水。
- 删除旧的 `mesh`、`_mesh`、`calculate`、`_calculate`、`save`、`_save`、`gotomesh`、`view`、`count Mesh` 等历史命令，避免旧结果文件和保存失败复现。
- 如果中文对象名已在 `.p3d` 中乱码并导致引号不闭合，重建命令中改用 ASCII 对象名和注释。

9 条高程排等效线排水示例：

```python
z_positions = [0.8, 1.4, 2.0, 2.6, 3.2, 3.8, 4.4, 5.0, 5.6]
for i, z in enumerate(z_positions, start=1):
    parts = g_i.linedrain((23.95, 0.50, z), (23.95, 19.50, z))
    line = parts[2]
    drain = parts[3]
    line.rename(f"LN_WEEP_ROW_{i:02d}")
    drain.rename(f"LD_WEEP_ROW_{i:02d}")
    drain.h = 0.0
```

## 材料与几何注意点

土体材料常用属性：

```python
mat = g_i.soilmat()
mat.setproperties(
    "Name", "MAT_FOUNDATION",
    "SoilModel", "Mohr-Coulomb",
    "gammaUnsat", 19.0,
    "gammaSat", 20.0,
    "Eref", 50000.0,
    "nu", 0.3,
    "PermHorizontalPrimary", 0.001,
    "PermHorizontalSecondary", 0.001,
    "PermVertical", 0.001,
    "cRef", 5.0,
    "phi", 32.0,
    "psi", 0.0,
)
```

Geogrid 材料在 PLAXIS 3D 2024 中不要直接设置 `EA`；先设材料类型，再设 `EA1`。等向时 `EA2` 可能只读。

```text
geogridmat
set GeogridMat_1.Name "MAT_STEEL_GRID"
set MAT_STEEL_GRID.MaterialType "Elastic"
set MAT_STEEL_GRID.EA1 2000.0
```

非水平土层标高不要直接写 `Zone.Top/Bottom`；用命令：

```python
g_i.commands("setsoillayerlevel Borehole_3 Soillayer_1 Top -1.5")
```

## 保存失败与 data.convd.rr1 处理

`g_i.save()`、`s_i.call_and_handle_commands("_save ...")` 可能因为旧计算结果文件 `data.convd.rr1` 卡死或弹出“保存失败”。表现为目标 `.p3dat` 里只出现 `data.convd.rr1`，没有 `data.plxml`。

处理流程：

1. 先备份原 `.p3d/.p3dat`。
2. 清理 PLAXIS/Python 进程。
3. 用短 ASCII 路径和新端口启动 PLAXIS。
4. 执行干净命令，核验对象数量。
5. 如果 `_save` 失败，检查临时目录：

```text
%LOCALAPPDATA%\Temp\Plaxis3DTemp
```

如果临时目录中已经生成了新的 `data.plxml`、`data.p3d`、`data.full`，可以手工组装项目包：

```powershell
$temp = "$env:LOCALAPPDATA\Temp\Plaxis3DTemp"
$project = "C:\short_ascii_path\model"
New-Item -ItemType Directory -Path "$project.p3dat" -Force | Out-Null
Copy-Item "$temp\data.p3d" "$project.p3d" -Force
foreach($name in @(
  "data.p3d",
  "data.success.p3dlog",
  "data.full",
  "data.plxml",
  "data.opi",
  "data.new.p3dlog",
  "__reference_project__"
)){
  $src = Join-Path $temp $name
  if(Test-Path $src){ Copy-Item $src "$project.p3dat\$name" -Force }
}
```

不要复制：

- `data.convd.rr1`
- `3DCalc*`
- 旧计算阶段结果目录

组装后必须重新打开 ASCII 路径核验，例如：

```python
s_i.open(r"C:\short_ascii_path\model.p3d")
g_i.gotosoil()
print(len(g_i.Volumes), len(g_i.LineDrains))
```

## 已知限制

- `ModelType`、`ElementType` 在项目创建后不可随意修改。
- `DrainageType` 部分情况下外部 API 不稳定，必要时在 GUI 中确认。
- 直接保存新建项目可能不可靠；保存失败时优先看 `Plaxis3DTemp` 是否已产生可组装的 `data.plxml`。
- 修改已有项目时，`data.plxml` 是最终核验对象；文本命令日志只作为重建和审计依据。
- 重建/替换 `.p3dat` 前，必须备份原目录，并确认操作目标路径在预期工作区内。
## 防排水对比阶段与 Output 判读经验

用于“无排水措施 vs 有排水措施”的积水点/排水路径识别时：

- 必须建立两条独立分支：无排水分支从 `InitialPhase` 分出并 `deactivate` 所有 `LineDrain/SurfaceDrain`；有排水分支从 `InitialPhase` 分出并 `activate` 所有排水对象。旧的单一有排水阶段应设 `ShouldCalculate False`，避免混淆。
- `PorePresCalcType = 2` 表示 `Steady state groundwater flow`，可让排水边界参与水力场。`PorePresCalcType = 1` 只适合沿用上阶段孔压，通常看不出有无排水差异。
- 不要把所有排水线 `h` 统一设为 `0`。线排水/面排水的 `h` 应按自由出流高程或排水线高程设置：基底 PVC 约 `0.10`，碎石盲沟约 `-0.05`，9 条泄水线按 `0.8, 1.4, ..., 5.6`，C30 边缘约 `6.02`，表面边沟/排水面约 `6.30`。否则高位排水对象会被强制拉到 0m 水头，造成非真实大梯度或 GWF 不收敛。
- 普通阶段里 `DeformCalcType=9 (Flow only)` 可能被 PLAXIS 2024.1 API 拒绝，只允许 `plastic/consolidation/safety`。不要假设脚本能强制普通阶段变成纯水力阶段；若力学坍塌干扰水力判读，优先在 GUI 中确认是否能使用纯水力/Flow only 工作流，或将水力分析与力学稳定分析分开。
- 如果计算提示“后续阶段无法计算，因为起始阶段未成功计算”，说明父阶段失败，子阶段即使在 Output 中有旧步数，也不能作为当前对比的有效结果。

Output 判读：

```python
from plxscripting.easy import new_server
s_o, g_o = new_server("localhost", 10000, password="12345678", request_timeout=60)

for p in g_o.Phases:
    print(p.Name.value, len(p.Steps))

phase = g_o.PH_WITHDRAIN_RAIN
pw = g_o.getsingleresult(phase, g_o.ResultTypes.Soil.PWater, 23.45, 10.0, 0.18)
head = g_o.getsingleresult(phase, g_o.ResultTypes.Soil.GWHead, 23.45, 10.0, 0.18)
vals = g_o.getresults(phase, g_o.ResultTypes.Soil.PWater, "node")
```

- `getsingleresult` 的三维坐标参数直接展开传入；不要额外加 `"node"`，否则可能报“参数无效”。
- `getresults(phase, result_type, "node")` 可用于统计全场范围。
- 同时查看 `.p3dat\log.f##` 和 `.p3dat\log.d##`：`log.f## ErrorCode=0` 代表 GWF 稳态渗流子计算完成；若 `log.d##` 报 `Soil body collapses`，说明后续塑性力学失败，不能把最终变形阶段结果当作可靠积水云图。
- 有排水阶段若观察点 `PWater≈0` 且 `GWHead≈排水高程/点高程`，说明排水边界起到了水头控制作用，这是预期趋势；无排水阶段若出现极大负孔压或异常水头，应视为失败阶段产物，不宜解释为真实积水点。

端口与路径：

- Input 计算卡住后，远程端口可能残留 `LISTEN/CLOSE_WAIT`，即使进程列表里看不到旧 PID。此时不要继续向同一端口发命令；改用新端口或重启 PLAXIS。
- Output 可以和 Input 共用端口号，但同一时刻端口只能属于一个进程。先用 `Get-NetTCPConnection -LocalPort <port>` 判断当前是 Input 还是 Output。
- 中文路径和全角冒号在脚本/命令历史里可能变成 `?`，导致打开空模型或异常模型。需要自动化验证时，优先复制到短 ASCII 路径，例如 `C:\plaxis_current_ascii\model.p3d`。

## 环境与连接补充（2026-09-30）

- 系统 Python 3.14 没有 `distutils`，`import plxscripting.easy` 会报 `No module named 'distutils'`。解决：建一个 shim 目录 `shim/distutils/__init__.py`（空）+ `shim/distutils/version.py`：

```python
from packaging.version import Version as _V
class StrictVersion(_V):
    def __init__(self, v): super().__init__(str(v))
LooseVersion = StrictVersion
```

  运行时 `PYTHONPATH=shim`，或在脚本开头 `sys.path.insert(0, shim路径)`。
- PLAXIS 中文界面返回中文 extrainfo，Windows 控制台需 `PYTHONIOENCODING=utf-8`，否则 `UnicodeEncodeError`。
- 工程文件夹是中文路径时，用目录联接让文件实际落在工程文件夹里：
  `New-Item -ItemType Junction -Path C:\plaxis_xxx -Target "<中文工程目录>\plaxis"`，PLAXIS 一律用 `C:\plaxis_xxx\...` 保存/打开。
- 推荐统一的命令包装（失败立即抛出，不会静默跳过）：

```python
def cmd(c):
    out = []
    for it in s.call_commands(c):
        fb = it.get("feedback", {})
        if not fb.get("success", False):
            raise RuntimeError(f"FAIL: {c}\n{fb}")
        out.append(fb.get("extrainfo", ""))
    return out
```

- `s.new()` 新建项目；`cmd('save "C:\plaxis_xxx\model.p3d"')` 直接另存（新项目、无旧计算结果时可靠）。

## 材料属性的只读陷阱（PLAXIS 3D 2024.1）

- 枚举用字符串，不要用数字：`("SoilModel","Mohr-Coulomb")`、`("DrainageType","Drained")`、`("K0Determination","Manual")`、`("InterfaceStrengthDetermination","Manual")`。
- 属性按依赖顺序逐个 `setproperties(k, v)`：先 SoilModel/DrainageType，再参数；先 `K0Determination="Manual"` 再 `K0Primary`，否则 "无法设置只读属性 K0Primary"。
- 各向同性 K0 时 `K0Secondary` 只读（自动等于 K0Primary），不要设。
- `DrainageType="Non-porous"` 时 `gammaSat` 只读，只设 `gammaUnsat`。线弹性结构体（如电杆）用 `SoilModel="Linear elastic"` + Non-porous。
- 界面强度：复制一份土体材料，设 `InterfaceStrengthDetermination="Manual"`、`Rinter`；界面对象上 `set <If>.MaterialMode "Custom"`、`set <If>.Material <mat>`。不同结构–土界面（钢 0.67、混凝土 0.7）各用一份。
- 板材料 `platemat`：先 `set PlateMat_1.MaterialType "Elastic"`，再设 `Gamma`（体积重度 kN/m³，PLAXIS 自动乘 d）、`E1`、`StructNu12`、`d`；Isotropic 默认 True，E2/G 自动计算。
- **改 `Identification` 会同时改对象名**（PlateMat_1 → STEEL_5MM），之后必须用新名字引用。建议最后再改名，或改名后立即换引用。

## 几何：半圆柱、分解面、按包围盒识别对象

- `cylinder r h (x0 y0 z0)` 默认轴向是 **+Y**，竖向桩必须写 `cylinder r h (x0 y0 z0) (0 0 1)`。
- 半模型切分：建竖向平面 `surface (-1 0 zmin) (1 0 zmin) (1 0 zmax) (-1 0 zmax)`，`intersect Vol_a Vol_b ... Polygon_n`，然后按 `BoundingBox` 删掉 y<0 的半体和平面残片。
- 所有几何对象都有 `BoundingBox`、`CenterOfGravity` 属性，`echo X.BoundingBox` 解析 xMin…zMax 可可靠识别切分/分解后的对象（`echo X` 的参考点 x/y/z 不能判断在哪一侧）。解析函数：

```python
import re
def bb(n):
    t = cmd('echo ' + n + '.BoundingBox')[0]
    return {k: round(float(v), 4) for k, v in re.findall(r'(\w+Min|\w+Max): ([-\dE.+]+)', t)}
```

- `decomposesrf Vol` 得到侧面、顶面、底面、切面，用 BoundingBox 区分（侧面 z 范围跨全高、顶/底面 zMin=zMax、对称面上的切面 yMax≈0）。套管 Plate 放在地下段电杆的侧面上即与电杆共节点。
- 界面向下延伸（消除端部奇异）：再建一个短圆柱（高 0.2）分解，只保留侧面加界面，删掉体和其他面。
- `info <obj>` 可列出对象支持的命令和属性，查 API 时先用它。
- `cmd('undo')` 可撤销上一步试验性操作。

## 界面正负侧

- Positive interface 在面法向（局部轴 3）一侧。平面 polygon 的法向按点顺序右手定则；需要指定土体侧时调整点顺序，统一用 posinterface。
- 由体 `decomposesrf` 得到的面，按惯例法向朝外（本条未经数值验证，API 读不出法向；AxisVector 在 Automatic 下全为 0）。关键模型应在首次计算后核对：结构与相邻体节点位移是否一致，或在 GUI 显示局部轴。
- 对称面上的板：只在朝土体一侧设界面，板等效厚度取一半。

## 网格与分阶段模式的重命名

- 进入 `gotomesh` / `gotostages` 后对象被重命名：体 → `BoreholeVolume_1_<名>_1` 或 `<名>_1`；面若被其他几何切开会变成 `<名>_1`、`<名>_2`（都继承板/界面）；Soil 变成 `Soil_1_Soil_8_1` 之类；荷载 → `WIND_Q_1`。每进一个模式先打印 `g.Volumes / g.Surfaces / g.Soils / g.Plates / g.Interfaces / g.LineLoads` 的名字再操作。
- 局部加密：mesh 模式下 `set <名>.CoarsenessFactor 0.25`。
- `mesh`（无参数）= Medium，全局单元尺寸 = 0.05 × 模型包围盒对角线（包括地上结构高度）；实际数值在 `.p3dat\data.input3d.log` 里 "Set global coarseness to …" 可查。没有 `Mesh` 对象可 echo。

## 分阶段设置

- `phase <上一阶段>` 返回新阶段名在 extrainfo 最后一个词；`set Phase_n.DeformCalcType "Plastic"`、`set Phase_n.Deform.ResetDisplacementsToZero True`、`set Phase_n.MaxStepsStored 1000`。
- `Deform.MaxSteps` 在 `UseDefaultIterationParams=True` 时只读（默认已是 1000）。推覆分辨率：`set Phase_n.Deform.UseDefaultIterationParams False` 后设 `MaxLoadFractionPerStep 0.01`。
- 分阶段材料：`setmaterial <Soil> <Phase> <Mat>`（wished-in-place：初始阶段桩区为土材料，下一阶段换成桩材料）；`activate/deactivate <obj> <Phase>`。
- 核查激活状态：`obj.Active[phase]` 返回 None 表示"沿用上一阶段"，不是错误；取值写成 `try: x.value except: x`。
- 荷载在结构模式里先设值（新建线荷载默认 qz=-1、点荷载 Fz=-1，要清零）。
- **Input 端没有 `addcurvepoint` 命令**，3D 曲线点只能在 Output 里选；替代做法：`MaxStepsStored` 设大，算完后在 Output 用 `getsingleresult` 逐步读取指定坐标点。
- 要让多个模型网格密度一致，用绝对尺寸反算局部系数：`factor = 目标尺寸 / (0.05 × 模型包围盒对角线)`，对角线随埋深/结构高度变化，每个模型单独算。线（如荷载线）也有 CoarsenessFactor（默认 0.5），会在杆轴上产生局部尺寸，必要时一并设置。重新划分网格后分阶段设置（激活、材料、荷载、迭代参数）保留不变，但仍应复核。
- EMR 会从加密面向外快速放大单元，只给结构面设小系数时，桩周土体（被动区）不一定够细；需要时另建一个同材料的土体子体作为加密区。
- 加密土体区做法：结构模式 `surface` 画矩形 → `extrude <Polygon> (0 0 dz)` 得到体 → 删掉原矩形 → `set Soil_n.Material CLAY`（同土材料）→ 网格模式设该体 CoarsenessFactor。与桩体重叠部分会自动切分，桩体那块的分阶段材料（初始 CLAY、P1 换桩材料）在重命名后（如 `Soil_1_Soil_2_Soil_8_1`）仍保留，但必须复核。实例：近场 0.08 m + 加密区 0.15 m，单元从 6.8k 增至 3.0 万，网格生成约 10 s。
- **初始阶段冻结的土体也必须有材料**（例如地上结构体在 InitialPhase deactivate），否则计算前报错"阶段包含无材料的类型 Soil 的特性"。做法：`setmaterial <Soil> InitialPhase <Mat>` 后再 deactivate；建完模型检查 `o.Material[g.InitialPhase]` 不为空。
- 计算前 GUI 的"未为曲线选择节点和应力点"只是警告；3D 曲线点只能在 Output 里选，可点"立即选择节点和应力点"在 Output 中按坐标选点后再计算。

## 3D 曲线点（Output 端选点）

- Input 中 `selectmeshpoints`（分阶段模式、已划分网格）会打开 Output，返回值 `returnedobjects[0]['json']` 是 Output 的脚本端口（实测 Input 10000 → Output 10001，密码同 Input）。
- Output 中：`addcurvepoint "node" (x y z)`；有多个候选（界面双节点、板/体共点）时会提示"找到了多个候选对象"并任选一个，必须指定实体：`addcurvepoint "node" <网格实体名> (x y z)`，实体名用网格名（如 `Soil_1_Soil_8_1`、`Soil_1_1`、`Soil_1_Soil_2_1`），`go.Soils` 给出的短名（Soil_8）不可用。坐标处无该实体节点时报"没有发现节点和应力点"。
- 曲线点不能用 `delete` 删除；可用 `set CN_n.Identification "名称"` 命名。`echo CN_n` 可看 DataFrom（实体）和节点号。
- `update` 把选点写回项目（`.p3dat\data.cps`）并关闭 Output；之后在 Input 再 `save` 一次。
- 结构–土界面处可同时选结构侧和土侧两个节点（同坐标、不同实体），算完对比位移即可判断界面滑移/界面侧别。

## 推覆结果提取（Output）

- 曲线点时程：`go.getcurveresultspath(go.CN_n, go.Phase_2, go.Phase_2, go.ResultTypes.Soil.Ux)` 一次返回整阶段所有步，1000 步约 0.06 s。逐步 `getcurveresults` 每次约 2–3 s，不要用。
- ΣMstage 没有对应的 ResultType，只能逐步读 `step.Reached.SumMstage.value`，1000 步约 400 s。阶段末状态：`echo Reached_<最后步ID>`，可看 SumMstage、RelativeStiffness（≈0 表示已达破坏平台）。
- 推覆到破坏时常以"荷载步长不足（错误代码 102）"、CalculationResult = Failed (soft) 结束：用满 MaxSteps 仍未达 ΣMstage = 1。若 RelativeStiffness 接近 0、杆顶位移很大，说明已到破坏平台，可当作极限状态，不是建模错误。
- GUI 计算后，结果文件先在 `%LOCALAPPDATA%\Temp\Plaxis3DTemp`（data.calc.*），Input 里 `save` 后才写进项目的 `.p3dat`。计算耗时可从 data.calc.* 文件时间戳估算。
- 实测（i5-12450H，6,810 单元半模型）：P2 推覆 1000 步约 11 min。MaxLoadFractionPerStep = 0.01 时，倾斜率 15‰ 之前只有约 19 步，插值 M₁₅ 分辨率偏粗；大部分步数耗在破坏平台上。
- 推覆步长实测（同一 6,810 单元模型）：MaxLoadFractionPerStep 0.01 → 0.002，M₁₅ 23.21 → 23.16（差 0.2%），15‰ 前步数 19 → 105，计算约 9 min；但 1000 步只推到倾斜率约 143‰，未到破坏平台（M 35.25 仍缓慢上升，0.01 时为 37.08）。需要极限荷载时加大 MaxSteps/步长，或分两段推覆。提取+分析脚本模式：先 extract（ΣMstage + 各曲线点 Ux/Uz 存 json），再离线 numpy 插值求 M₁₅、各档风荷载倾斜率、转动中心。
- 加密土体区实测：近场 0.08 m 基础上再加 0.15 m 加密区（6.8k → 3.0 万单元），M₁₅ 仅降 0.36%，大位移段（倾斜率 100‰）降 1.8%；计算约 29 min（无加密区约 9 min），提取 ΣMstage 也从 ~410 s 增至 ~690 s。结论：近场结构面已加密时，土体加密区对 M₁₅ 影响可忽略。
- 复制模型改网格：`s.open(原)` → `save "新路径"` → 改 CoarsenessFactor → `mesh`。重新划分网格后曲线点必须重选（节点号变化），已有计算结果作废。新项目的 mesh 日志在 `新.p3dat\data.input3d.log / data.mesher3d.log`，不一定在 Plaxis3DTemp。
- Windows 路径写进 PLAXIS 命令时，在 `python -c "..."` 或 heredoc 里手写反斜杠极易出现转义错误（`'\'`、`r'...\'` 结尾）。统一用正斜杠写路径，再 `os.path.normpath()` 转换后拼进 `save "..."`。
- 网格收敛实测（L10-B2 半模型）：近场 0.08 → 0.05 m（6.8k → 11.7k 单元），M₁₅ 23.16 → 23.07（−0.36%），计算约 10 min。近场 0.08 m 已收敛，可作为工作网格。

## 参数化建模脚本（四翼套管桩课题实例）

- 完整脚本在 项目的 `scripts` 目录：build.py（L、B、half/full、角度 → 建模+网格+分阶段+保存）、verify.py（打印各阶段激活/材料/荷载/迭代参数）、selpts.py（Output 选曲线点）、extract.py / analyze.py（提取曲线、求 M₁₅）。密码和端口从环境变量 PLX_PASSWORD / PLX_PORT / PLX_OUT_PORT 读，不写进文件。
- 通用做法：体分解后按 BoundingBox + 名字前缀识别侧面/底面；对称面上的板按右手法则调整点顺序使法向朝 +y；Soil 特征名用 `echo <Volume>` 取（如 Soil_8），分阶段名用 `re.findall(r'Soil_\d+')` 的 token 匹配（`Soil_1_Soil_8_1` 含 Soil_8）。
- 全模型中套管圆柱面会被 4 片翼板切成 4 块（Plate_1_1…1_4），界面同理；半模型被 1 片切成 2 块。
- 回归：脚本重建与手工模型单元数差约 1%（6,879 vs 6,810，网格参数相同，几何创建顺序不同所致），在已验证的网格收敛范围内。
- 半模型 vs 全模型实测（L10-B2，对称面翼板取半厚 + 单侧界面，荷载减半）：M₁₅ 23.16 vs 23.38（半模型低 0.96%，偏保守），全程差值 ≤1.9%；全模型 11.6k 单元计算约 16 min，半模型约 9 min。对称等效处理成立。
- build.py 中 B = 0 时跳过翼板（否则会生成零宽退化面）；正式模型输出到 `Pile\model\<编号>\<编号>.p3d`。无翼板时套管面不被切分（单块 Plate_1_1）。
- 分析脚本注意：目标荷载超过推覆达到的最大荷载时，`np.argmax(M >= Mw)` 返回 0，插值会给出无意义结果；必须先判断 `Mw > M.max()` 并标为"基础破坏"。弱工况（如 L05-B0）极限弯矩可能低于所有风荷载档。
- Output 中删除曲线点：单个 `delete CN_n` 无效，用 `clearcurvepoints CurvePoints` 清空后重新 addcurvepoint，再 `update`。已计算项目改选曲线点后计算结果不受影响（CalculationResult 和 .p3dat 结果文件保留，存储步足够时曲线由存储步生成）。
- 批量建模（实测 16 个半模型约 40 min）：`batch.py` 依次调用 build.py → verify.py，并从 data.input3d.log / data.mesher3d.log 解析实际网格尺寸和最差单元质量写入汇总；再用 `geocheck.py` 在结构模式下按包围盒逐个核对几何、板材料、点荷载高度。最差单元质量 0.27~0.46（Gmsh SICN），均在外围土体。geocheck 只打开、不保存，已计算模型的结果不受影响。
- 脚本计算（calc_one.py）：长计算必须用 `new_server(..., request_timeout=None)`，否则 `calculate` 会超时断开。`s.call_commands("calculate")` 阻塞到算完；之后 `save` 把结果写进项目；`view Phase_2` 打开 Output 并在 returnedobjects[0]['json'] 返回 Output 端口，再提取曲线，结束时 Output 端 `close`。实测 L05-B1（5.1k 单元）计算 3.7 min、提取 4.5 min。
- 后台批量计算受 Claude Code 后台任务约 2 小时上限限制：超时后外层循环被杀，但正在跑的 calc_one.py 子进程可能继续（计算、保存完成），其后续 extract 会因丢失控制台崩溃（退出码 3221225794 = 0xC0000142）。对策：每个后台任务只排 2~3 个模型；被杀后先查 `Get-CimInstance Win32_Process` 是否还有 calc_one 进程，等其结束，再用 `calc_one.py <编号> --extract-only` 补提取。
- **斜向（非 0°/90°）板与圆柱面相接会导致网格失败**：直接把翼板内边放在圆柱面上（如 45° 处），mesher 出现约 5 mm 的伪小特征（"Smallest EMR-based element size ... below the minimum"）和负雅可比单元（"Still negative jacobians"，质量 < 0），推测是圆柱面内部按多边形处理、45° 处不在顶点上。0°/90° 不受影响。解决：翼板内边伸进桩内 5 cm，用 `intersect SLEEVE SLEEVE_EXT FIN...` 让 PLAXIS 在套管面上精确切开，再按包围盒删除桩内的小片、重命名外侧片和套管碎片（build.py 的 OBLIQUE 分支）。修正后网格质量 0.38，正常。
- `rotate` 命令的参数格式试了多种都报"参数无效"，未找到正确写法。
- mesh 可能超过 120 s（斜向翼板），plx.py 的 request_timeout 已改为 None。

## 验证模型补充（2026-10-07/08，Vivek 2017 电杆试验、Bienen 2012 翼桩离心试验）

- **梁材料**：`beammat` 后先 `set BeamMat_n.MaterialType "Elastic"`，再 `set BeamMat_n.CrossSectionType "User-defined"`，之后才能设 `A`、`I2`、`I3`、`E`、`Gamma`（默认 Predefined/实心圆，A、I 不可直接设）。荷载只在一个平面内时可令 I2 = I3，避开竖向梁局部轴方向的判断。
- **梁接到实体上传递弯矩**：梁端只落在体单元的一个节点上时，体单元没有转动自由度，相当于铰接。做法：把梁线一直延伸进实体（如电杆穿过整个混凝土基础块到底），梁与体共节点，弯矩通过多个节点的力偶传递。
- **对称面上的梁**：A、I 取一半，荷载取一半。
- **Hardening Soil 属性名**（PLAXIS 3D 2024.1，大小写敏感）：`E50Ref`、`EOedRef`、`EURRef`、`PowerM`、`nuUR`、`pRef`、`cRef`、`phi`、`psi`、`RF`、`K0NC`。
  - `RF`、`K0NC` 在 "其他/Advanced" 下，`UseDefaults=True` 时只读（报"无法设置只读属性 RF"）→ 先 `("UseDefaults", False)` 再设。
  - **关掉 UseDefaults 后 K0NC 变成 1.0**，与 φ 不相容，材料被判为无效，`calculate` 报"无效材料 …，不管是否实际使用该材料，都需要在计算前解决该问题"。必须同时设 `K0NC = 1 − sin φ`。
- **`calculate` 不抛异常**：`s.call_commands("calculate")` 失败时只在 feedback 里 `success=False`，阶段仍显示 "Not calculated"。脚本必须检查 feedback，否则会继续去开 Output，报 `KeyError: 'returnedobjects'`。
- **Output 曲线点提取速度（关键）**：曲线点必须在**计算前**选好（Input 分阶段模式 `selectmeshpoints` → Output `addcurvepoint` → `update` → Input `save` → `calculate`），PLAXIS 在计算时就写入曲线数据，之后 `getcurveresultspath` 整阶段 1000 步 < 1 s。若计算后才在 Output 里加点，每次 `getcurveresultspath` 都要重读全部存储步文件，约 1–2 s/步（实测：202 步 190 s/点；535 步、2 万单元 860 s/点），且无论 Output 由 GUI 还是脚本 `view` 打开都一样慢，Output 窗口期间卡住不刷新。加点时有多个候选（体/界面/板共节点）会提示"找到了多个候选对象"，用 `addcurvepoint "node" <网格实体名> (x y z)` 指定；实体名用分阶段模式的 Soil 名（如 `Soil_1_Soil_8_1`、`Soil_6_1`），`go.Soils` 的短名不可用；梁节点无需实体名。脚本示例：`D:\Pile\scripts\calc_val.py`。
- **体-体之间的方形基础**：`surface` 画顶面矩形 → `extrude <Polygon> (0 0 -h)` 得体 → 删掉原矩形；`decomposesrf` 后按 BoundingBox 识别侧面/底面，顶面（与空气接触）和对称面上的面删掉。
- **板（翼板）接到带界面的实体表面上会"浮空"（2026-10-08 Bienen 验证模型实测）**：桩用实体 + 桩侧面设 posinterface 时，界面在桩面生成双节点（桩侧/土侧）。翼板内边落在这个面上，结果连到了**土侧节点**，与桩不相连：翼板随土一起移动，内力几乎为零（N11 ≤ 14 kN/m，荷载 20 MN），翼桩曲线与单桩完全相同（比值 1.00）。判别：Output 中翼板内边 Ux 小于同深度桩轴 Ux。解决：在桩侧面再放一块板（如钢套管；没有套管时放一块"连接用"薄板，E 和 d 取小值使其刚度可忽略），翼板与该板共节点即与桩相连，界面设在该板面上。四翼套管主模型因有套管板，不受此问题影响。

## Output 导出云图与 Input 截图（2026-10-10，组会 PPT 出图实测）

**Output 脚本导出图片（不用截屏）**
- `export <Plot> "<路径.png>" W H` 直接按指定分辨率出图（如 1800×1200）。路径用正斜杠。
- Plot 属性：`DrawFrame/DrawTitle/DrawLogo/DrawProjectDirectory/DrawLegend/DrawAxes`、`ResultType`、`Step`（设 Step 会同时改 Phase）、`ScaleFactor`、`LegendSettings.MinValue/MaxValue/Intervals`、`MeshSettings.*`。
- **默认 `DrawFrame=True` 会在图下方画信息栏（项目名、步号、Company 授权字符串等）**，放进 PPT 前一律 `DrawFrame=False`。
- `PlotType` 不能直接设字符串：`set Plot_1.PlotType "Shadings"` 报“值无效：允许值为 "none" 或者序数值”。做法：直接设 `ResultType = ResultTypes.Soil.Utot` 等，PlotType 会自动变成 Shadings。剖面图上 `PlotType='none'` 也不允许（只允许 nodearrows/contourlines/shadings/distributionplane）。
- 视角：`view <Plot> "front"|"top"|"default"` 或 `view <Plot> (x y z)`（视线方向向量）；缩放：`zoom <Plot> (x1 y1 z1) (x2 y2 z2)`。**改完 view/zoom 后第一次 export 可能取景不对（实测得到整幅单色图），同样参数连续 export 两次，第二张正确。**
- 指定计算步：`plot.Step = go.Phase_2.Steps[k]`，k 为曲线 json 中的序号（Phase_2 的 Steps[0] 对应全局 Step_3）。例如倾斜率 15‰ 时刻取 `argmax(u_top/12 >= 0.015)`。
- 隐藏对象：`hide Plot_1 Soil_6`（地上段电杆）、`hide Plot_1 WIND_Q`、`hide Plot_1 WIND_F`（荷载箭头会盖住近场）。实体名用 Output 中 `go.Soils/go.Plates/go.LineLoads` 的名字。

**对称面云图用剖面，不用 3D 正视**
- 半模型 3D 图用 `view "front"` 看 y=0 对称面时，会叠加三维的塑性点、对称面上的翼板等，图面很乱。改用剖面：`crosssectionplot Plot_1 (-8 0.02 0) (8 0.02 0) (0 0.02 -9)`（离开对称面 2 cm，避开板），再对新图 `view "front"` + `zoom`，得到干净的平面云图。水平剖面用三点 `(0 0 z) (1 0 z) (0 1 z)` + `view "top"`。
- **新图名从返回值解析**：返回 extrainfo 为“添加 Plot_9”，用正则取 `Plot_\d+`；不要用 `go.Plots[-1]`。
- **`crosssectionplot` 实际以“当前激活的图”为母图**（现象，机理未核实）：先建了 `structureplot`（板图）后再 `crosssectionplot Plot_1 ...`，新剖面成了板的剖面，设土体结果报“指定的结果类型具有 Soil 结构，但图需要的是 Plate”。对策：所有土体剖面先出，`structureplot` 放最后。
- 剖面图的单元网格线是 `MeshSettings.CSElementContours`（`ElementContours` 对剖面无效）；画网格图可设 `ResultType=Soil.MaterialIndex`、`CSElementContours=True`、`DrawLegend=False`。
- 板（套管+翼板）三维图：`structureplot Plate_1 Plate_2 ...`，`ResultType=ResultTypes.Plate.Utot`，并设 `MeshSettings.StructureAxes=False`，否则满屏局部坐标轴箭头。
- 塑性点：`ResultType=Soil.PlasticPoint` 在 3D 中显示为成片块体，剖面中也不易读；汇报用剪应变 `Soil.TotalDeviatoricStrain`（γs）剖面更清楚。
- 打开 Output：Input 中 `s.open(...)` → `gotostages` → `view Phase_2`，返回 json 即 Output 端口（10001，密码同 Input）；用完在 Output 端发 `close`，换下一个模型前先关。

**Input 截图（Input 没有 view/zoom 命令）**
- 本机 150% 缩放，Input 不支持高 DPI：`PrintWindow(hwnd, hdc, 2)` 抓到的内容只占位图左上角 1/1.5（逻辑分辨率约 1720×930），按 1/1.5 裁剪即可；屏幕坐标 = 窗口左上角 + 逻辑坐标×1.5。窗口最小化时 GetWindowRect 为 (-48000,…)，先 `ShowWindow(h, 3)` 最大化。
- 视图操作只能模拟鼠标：滚轮在光标处缩放；中键拖动=平移；Ctrl+中键拖动=旋转（不好精确控制，汇报图用默认视角+滚轮放大即可）。
- Input 的“网格”模式只显示土体外形，不显示单元；网格图要到 Output 里出。
- `s.open` 打开已算完的正式模型约 1 s（不复制结果文件）；只截图不保存，项目标题出现 `*` 也不要保存。

## 不排水黏土与分层土中的桩（2026-10-15，Cowden 现场试验验证模型 build_cowden.py）

- **Mohr-Coulomb + `DrainageType "Undrained (C)"` 的属性名与普通 MC 不同**（PLAXIS 3D 2024.1）：
  - 强度用 `sURef`（不是 `cRef`），刚度 `ERef`（即 Eu），泊松比 `nuU`；随深度增长用 `sUInc`、`EInc`、`VerticalRef`。
  - `gammaSat`、`phiU` 为只读：设置时报"无法设置只读属性 gammaSat / phiU"。只设 `gammaUnsat`；φu 固定为 0，不要设。
  - 查属性名的办法：`m = g.soilmat()` → 先设 SoilModel、DrainageType → `echo <材料名>` 列出全部属性。
- **多层钻孔**：`soillayer 0` 调用 n 次得 n 层，再 `setsoillayerlevel Borehole_1 i z_i`（i = 0…n）；层的土体特征依次为 Soil_1…Soil_n，`set Soil_i.Material <mat>` 赋材料。
- **桩体穿过多个土层会被层面切开**：分阶段模式中名字为 `Soil_<层号>_Soil_<桩体号>_1`。按 token 匹配找出所有桩段（含桩体 token 的都是桩），初始阶段每段按名字里的层 token 赋对应层的土材料，P1 再统一换成桩材料。
- **界面 `MaterialMode` 默认是 "From adjacent soil"**：取哪一侧土的材料从 API 无法确认（分阶段模式的界面分片没有 BoundingBox，`echo PositiveInterface_1_1.BoundingBox` 报"未知对象"）。要让界面强度随土层变化又不依赖默认规则：在结构模式用各层分界处的水平面（`surface` 画小矩形）与桩侧面 `intersect`，把侧面切成每层一片，再逐片 `posinterface` + `MaterialMode "Custom"` + 该层材料（各层材料都设 Rinter）。
- **`intersect` 会把被切的面改名为 `Surface_n`**（原名 PILE_SIDE 不保留）。切完后按 BoundingBox 重新识别：非水平面 = 侧面分片，水平面 = 切割平面残片（删除），已命名的底面（PILE_BASE）不受影响。
- 实测：D = 0.273 m 半模型，近场 0.06 m、0.25 m 分层，单元 2.65 万～3.1 万，建模（含网格）约 2～3 min。
- **不排水 (C) 推覆早期"土体似乎要倒塌…[错误代码: 111]"（2026-10-15 实测）**：Undrained (C) 黏土默认 `TensionCutOff True`、`TensileStrength 0`，地表附近总应力很小，桩后（主动侧）一卸载就进入受拉截断，荷载控制推覆在很小荷载下停住（D = 0.273 m 桩约 0.7 kN 即停，增量位移集中在地表桩背）。解决（同 PISA 有限元做法：土体可通过负孔压承受拉力，桩土界面不受拉、可脱开）：土体材料 `("TensionCutOff", False)`；另建一份界面专用材料（同参数）保持 `TensionCutOff True`，界面 `MaterialMode "Custom"` 用它。修改后同一模型完整推到 1000 步。
- 定位"坍塌"位置的办法：Output 中 `getresults(phase, ResultTypes.Soil.dUtot, "node")` 与 X/Y/Z 一起取出，按 dUtot 排序看最大值所在坐标。
- 土层分得很细（0.25 m）而计算域很大时，网格被层面强制加密：D = 0.762 m、30 m × 15 m 计算域时单元数 9.3 万；把上部层厚改为 0.5 m 后降到 2.2 万。层面离桩端只有 1 cm 时会出现 "small in-surface proximity / small edges" 警告，把离桩端 6 cm 内的层面移到桩端标高即可。
