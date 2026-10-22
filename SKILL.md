---
name: plaxis-automation
description: >
  通过 PLAXIS Remote Scripting API (plxscripting) 自动化构建、求解与分析 PLAXIS 3D 有限元模型。
  支持端到端全流程闭环：模板克隆与会话管理、土层与钻孔地质建模、结构与防排水构件（板/接触面/盲沟）、
  网格剖分与局部细化、分期施工步与降雨瞬态渗流工况编排、求解器监听、以及 Output 自动提取安全系数(Msf)、
  孔压吸力场、位移与云图。
  触发词: PLAXIS, .p3d, 有限元, 地层, 钻孔, soilmat, borehole, soillayer, 渗流, 边坡, 基坑,
  隧道, 加宽, 防排水, plate, interface, staged construction, 降雨入渗, 瞬态渗流, 安全系数, Msf。
  也用于桩（单桩、翼桩、筒型基础）水平推覆与参数化批量建模，以及保存失败、
  data.plxml/data.convd.rr1、中文路径、命令历史损坏、端口残留等 PLAXIS 自动化问题。
---

# PLAXIS 3D 端到端自动化建模与求解系统

> 原作者：[Noahpeerless](https://github.com/Noahpeerless)（<https://github.com/Noahpeerless/plaxis-automation-skill>，MIT）。本文件为 xyj0727 的改进版：正文为原作者 2026-10-09 的新版，附录 A 保留原作者旧版的实操小节，附录 B 为实测补充的坑与经验。

通过 Python `plxscripting` 连接 PLAXIS 3D (PLAXIS 3D 2024) 的 Remote Scripting 服务器，
实现**“几何参数/工况输入 → 地层与结构建模 → 施工工况编排 → 求解计算 → 结果指标提取与出图”**的全流程自动化闭环。

---

## 目录
1. [端到端全流程管道](#端到端全流程管道)
2. [环境前置与生命周期管理](#环境前置与生命周期管理)
3. [模块 1：土体与钻孔地质建模 (Soil Mode)](#模块-1土体与钻孔地质建模-soil-mode)
4. [模块 2：结构与防排水构件建模 (Structures Mode)](#模块-2结构与防排水构件建模-structures-mode)
5. [模块 3：网格剖分与局部细化 (Mesh Mode)](#模块-3网格剖分与局部细化-mesh-mode)
6. [模块 4：施工步与工况流转编排 (Staged Construction Mode)](#模块-4施工步与工况流转编排-staged-construction-mode)
7. [模块 5：求解器驱动与收敛监控 (Calculate Engine)](#模块-5求解器驱动与收敛监控-calculate-engine)
8. [模块 6：后处理数据提取与云图导出 (Output API)](#模块-6后处理数据提取与云图导出-output-api)
9. [端到端全流程可执行脚手架范式](#端到端全流程可执行脚手架范式)
10. [核心避坑与已知限制总结](#核心避坑与已知限制总结)

---

## 端到端全流程管道

```
[基准模板工程 (.p3d + .p3dat)]
       │ (shutil.copytree 物理克隆，彻底解决二进制丢失痛点)
       ▼
[拉起 Plaxis3DInput 远程服务 (自动分配端口)]
       │
       ├─► 1. Soil Mode: 轮廓定义、土工参数建库、钻孔布置、非水平地层标高设置
       │
       ├─► 2. Structures Mode: 防冲刷面板/板构件、土工膜/滑移接触面、盲沟排水线面、几何求交
       │
       ├─► 3. Mesh Mode: 敏感区局部细化因子配置、网格生成与单元检查
       │
       ├─► 4. Staged Construction Mode: 
       │      ├─ 初始地应力相 (K0 / Gravity Loading)
       │      ├─ 分期开挖/拼宽填筑相 (激活/钝化土体与构件)
       │      ├─ 降雨瞬态渗流相 (Discharge 强度、TimeInterval 历时、水边界)
       │      └─ 边坡稳定性相 (Safety 强度折减、计算控制)
       │
       └─► 5. Calculate: 状态检查、启动求解、日志收敛监听与容错
              │
              ▼
[拉起 Plaxis3DOutput 远程服务]
       │
       ├─► 提取边坡稳定安全系数: Msf
       ├─► 提取渗流指标: 孔隙水压力(PWater)、基质吸力(Suction)、饱和度(DegreeOfSaturation)
       ├─► 提取变形指标: 位移极值(Ux, Uy, Uz, |u|)及坐标
       ├─► 提取结构内力: 板单元弯矩(M)、剪力(Q)、轴力(N)
       └─► 自动导出结果云图截图与结构化 JSON/CSV 报表
```

---

## 环境前置与生命周期管理

### 1. 依赖与路径
- Python 依赖：`pip install plxscripting`
- PLAXIS 3D 2024 默认安装路径：
  - Input: `D:\Seequent\PLAXIS 3D 2024\Plaxis3DInput.exe`
  - Output: `D:\Seequent\PLAXIS 3D 2024\Plaxis3DOutput.exe`

### 2. 核心架构模式：模板克隆模式（Template Cloning Pattern）
⚠️ **致命陷阱防范**：通过 `s_i.new()` 创建的空白工程不包含底层二进制模型文件，且脚本 `save()` 无法可靠写入二进制几何。
**标准做法**：
1. 维护一个基础干净的工程模板目录（包含 `.p3d` 文件及同名 `.p3dat` 文件夹）。
2. 在 Python 中先使用 `shutil.copytree` 完整拷贝为工作目录工程。
3. 通过 `s_i.open(cloned_p3d_path)` 打开并操作，计算保存后完全自洽。

### 3. 会话启动与清理封装
```python
import subprocess, time, socket, shutil
from pathlib import Path
from plxscripting.easy import new_server

def get_free_port(start=10000):
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    raise RuntimeError("未找到可用端口")

class PlaxisSession:
    def __init__(self, exe_path, port=None, password="plx_auto_password"):
        self.exe_path = exe_path
        self.port = port or get_free_port()
        self.password = password
        self.proc = None
        self.s = None
        self.g = None

    def start(self, timeout=60):
        self.proc = subprocess.Popen([
            self.exe_path,
            f"--AppServerPort={self.port}",
            f"--AppServerPassword={self.password}"
        ])
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(2)
            try:
                self.s, self.g = new_server("localhost", self.port, password=self.password, request_timeout=timeout)
                return self.s, self.g
            except Exception:
                pass
        self.close()
        raise TimeoutError(f"无法在 {timeout}s 内连接 PLAXIS 服务 (端口 {self.port})")

    def close(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
            self.proc = None
```

---

## 模块 1：土体与钻孔地质建模 (Soil Mode)

### 1. 初始化与激活
```python
s_i.open(project_p3d_path)
g_i.gotosoil()  # 必须最先调用！否则 Soillayers/Boreholes 等几何对象不可见
```

### 2. 土壤边界轮廓
```python
# 初始化矩形几何范围 (x_min, y_min, x_max, y_max)
g_i.SoilContour.initializerectangular(0, 0, length_x, length_y)
```

### 3. 土体材料批量定义
**关键属性映射 (PLAXIS 3D 2024 外部 API):**

| 参数项 | API 属性名 | 单位 | 示例值 |
|---|---|---|---|
| 本构模型 | `SoilModel` | - | `"Mohr-Coulomb"`, `"Linear elastic"`, `"Hardening soil"` |
| 天然重度 | `gammaUnsat` | kN/m³ | `18.5` |
| 饱和重度 | `gammaSat` | kN/m³ | `20.0` |
| 弹性模量 | `Eref` | kPa | `20000.0` |
| 泊松比 | `nu` | - | `0.3` |
| 各向异性渗透系数 | `PermHorizontalPrimary`, `PermHorizontalSecondary`, `PermVertical` | m/day | `0.01` |
| 粘聚力与内摩擦角 | `cRef`, `phi` | kPa, ° | `15.0`, `25.0` |
| 剪胀角 | `psi` | ° | `0.0` |

```python
def create_soil_material(g_i, name, soil_model, gamma_unsat, gamma_sat, Eref, nu, perm, c=0, phi=0, psi=0):
    mat = g_i.soilmat()
    props = [
        "Name", name,
        "SoilModel", soil_model,
        "gammaUnsat", gamma_unsat,
        "gammaSat", gamma_sat,
        "Eref", Eref,
        "nu", nu,
        "PermHorizontalPrimary", perm,
        "PermHorizontalSecondary", perm,
        "PermVertical", perm,
    ]
    if soil_model in ["Mohr-Coulomb", "Hardening soil"]:
        props += ["cRef", c, "phi", phi, "psi", psi]
    mat.setproperties(*props)
    return mat
```
> ⚠️ `DrainageType`（排水类型）外部脚本无法修改，若需修改需在初始模板中预设。

### 4. 钻孔与非水平地层构建
```python
# 1. 沿断面布设钻孔
bh_positions = [(0.0, y_mid), (5.0, y_mid), (12.0, y_mid), (25.0, y_mid)]
for x, y in bh_positions:
    g_i.borehole(x, y)

# 2. 从下至上创建标准层厚
layers_cfg = [
    (10.0, mat_bedrock),
    (5.0,  mat_soft_clay),
    (3.0,  mat_old_subgrade),
    (0.5,  mat_cushion)
]
for thk, mat in layers_cfg:
    g_i.soillayer(thk)
    g_i.Soillayers[-1].Soil.Material = mat

# 3. 针对拼宽台阶、放坡、老路界面的非水平调整 (setsoillayerlevel 命令)
# 语法: setsoillayerlevel <Borehole_N> <Soillayer_N> Top|Bottom <z_value>
# 注: Borehole 从 1 开始计数，Soillayer 从 0 开始计数
g_i.commands('setsoillayerlevel Borehole_1 Soillayer_2 Top 2.5')
g_i.commands('setsoillayerlevel Borehole_1 Soillayer_2 Bottom 0.0')
# 台阶削坡/厚度归零设置:
g_i.commands('setsoillayerlevel Borehole_3 Soillayer_2 Top 0.0')
g_i.commands('setsoillayerlevel Borehole_3 Soillayer_2 Bottom 0.0')  # 厚度为 0 视为开挖消除
```

---

## 模块 2：结构与防排水构件建模 (Structures Mode)

完成土层后切换到结构模式：
```python
g_i.gotostructures()
```

### 1. 几何基本元素构建
```python
# 创建空间线段
line_1 = g_i.line((x1, y1, z1), (x2, y2, z2))

# 创建空间多边形平面 (4点)
surf_1 = g_i.surface((x1, y1, z1), (x2, y2, z2), (x3, y3, z3), (x4, y4, z4))

# 几何拉伸 (将面沿 Y 方向拉伸形成体)
g_i.extrude(surf_1, 0, dy, 0)
```

### 2. 板单元（Plate - 护壁/混凝土面板/路面结构）
```python
# 1. 定义板材料
plate_mat = g_i.platemat()
plate_mat.setproperties(
    "Name", "C30_Retaining_Wall",
    "MaterialName", "C30_Retaining_Wall",
    "Isotropic", True,
    "E1", 3.0e7,     # 弹性模量 kPa
    "nu12", 0.2,     # 泊松比
    "d", 0.25,       # 板厚 m
    "gamma", 25.0    # 容重 kN/m³
)

# 2. 为目标表面赋予板构件
g_i.plate(surf_1)
surf_1.Plate.Material = plate_mat
```

### 3. 接触面与防渗隔离膜（Interface）
防渗土工膜、结构与土体接触弱面需布置正/负接触面：
```python
# 为表面添加正向/负向接触面
g_i.posinterface(surf_1)
g_i.neginterface(surf_1)

# 若为防渗土工膜，设置水力不透水接触面
# g_i.commands(f'set {surf_1.Name}.PositiveInterface.GroundwaterFlow.Condition "Impermeable"')
```

### 4. 排水体构件（Line Drain / Surface Drain）
防排水系统的盲沟、渗水管与透水垫层：
```python
# 1. 线排水体 (盲沟/纵向集水管)
g_i.linedrain(line_1)

# 2. 面排水体 (横向透水垫层/排水分离面)
g_i.surfdrain(surf_1)
```

### 5. 几何求交与拓扑重建 (关键步骤)
```python
# 必须调用几何相交计算，确保板/面/排水体与土体单元形成共节点拓扑
g_i.intersect()
```

---

## 模块 3：网格剖分与局部细化 (Mesh Mode)

### 1. 局部细化与敏感区设置
为避免盲沟、防渗薄层产生网格畸变或渗流数值震荡，在关键构件上施加局部细化：
```python
g_i.gotomesh()

# 对高水力梯度区、排水线局部细化 (0.25 ~ 0.5)
g_i.commands(f'set {line_1.Name}.CoarsenessFactor 0.25')
g_i.commands(f'set {surf_1.Name}.CoarsenessFactor 0.5')
```

### 2. 全局网格划分与验证
```python
# 网格粗细度系数 (例如: Medium=0.06, Fine=0.04)
coarseness = 0.05
g_i.mesh(coarseness)

# 检查网格是否生成
time.sleep(3)
print(f"网格单元已生成")
```

---

## 模块 4：施工步与工况流转编排 (Staged Construction Mode)

切换至施工步模式：
```python
g_i.gotostages()
```

### 1. 初始地应力阶段 (InitialPhase)
```python
init_p = g_i.InitialPhase
# 边坡或非水平地层建议采用重力加载 (Gravity loading)，水平地层可用 K0
init_p.CalculationType = "Gravity loading"   # 或 "K0 procedure"
```

### 2. 施工开挖与填筑阶段 (Plastic Phase)
```python
# 阶段 1：老路削坡开挖
p_exc = g_i.phase(init_p)
p_exc.Identification = "Phase_1_Excavation"
p_exc.CalculationType = "Plastic"
p_exc.LoadingInput = "Staged construction"

# 钝化开挖土体 (开挖)
for vol in excavation_volumes:
    g_i.deactivate(vol, p_exc)

# 阶段 2：轻质土拼宽填筑与盲沟激活
p_fill = g_i.phase(p_exc)
p_fill.Identification = "Phase_2_Widening_Fill"
p_fill.CalculationType = "Plastic"

# 激活新填土体与防排水板、排水盲沟
for vol in fill_volumes:
    g_i.activate(vol, p_fill)
g_i.activate(surf_1.Plate, p_fill)
g_i.activate(line_1.LineDrain, p_fill)
```

### 3. 降雨入渗瞬态渗流工况 (Transient Flow Phase)
```python
p_rain = g_i.phase(p_fill)
p_rain.Identification = "Phase_3_Rainfall_Transient"
p_rain.CalculationType = "Flow only"        # 纯渗流；若分析边坡变形耦合可设为 "Fully coupled"
p_rain.TimeInterval = 3.0                   # 降雨历时 3 天 (day)
p_rain.MaxSteps = 150                       # 最大时间步数

# 施加降雨强度 (Precipitation)
g_i.Precipitation.TimeDependency = "Constant"
g_i.Precipitation.Discharge = 0.05          # 降雨强度 50 mm/day -> 0.05 m/day
g_i.commands(f'activate Precipitation {p_rain.Name}')
```

### 4. 稳定性安全系数工况 (Safety Phase - 强度折减法)
```python
# 评估降雨完成后的边坡稳定安全系数
p_safe = g_i.phase(p_rain)
p_safe.Identification = "Phase_4_Slope_Safety"
p_safe.CalculationType = "Safety"
p_safe.LoadingInput = "Incremental multipliers"
p_safe.MaxSteps = 100
p_safe.ToleratedError = 0.01
```

### 5. 保存工程
```python
g_i.save()
```

---

## 模块 5：求解器驱动与收敛监控 (Calculate Engine)

### 1. 触发计算
```python
# 计算所有标记阶段
print("开始执行有限元计算求解...")
s_i.calculate()
```

### 2. 状态检查与发散诊断
```python
for p in g_i.Phases:
    # 检查是否成功完成
    reach = getattr(p, 'Reached', None)
    log_info = getattr(p, 'LogInfo', '')
    print(f"阶段 [{p.Identification}]: 计算完成={bool(reach)}, Log={log_info[:100]}")
    
    # 对 Safety 阶段，打印折减乘数 Msf
    if p.CalculationType == "Safety" and reach:
        print(f"==> 极限安全系数 Msf = {reach.Msf}")
```

---

## 模块 6：后处理数据提取与云图导出 (Output API)

使用 `Plaxis3DOutput.exe` 批量提取指标并导出云图截图。

### 1. 连接 Output 服务
```python
session_out = PlaxisSession(r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DOutput.exe")
s_o, g_o = session_out.start()
s_o.open(project_p3d_path)
```

### 2. 提取安全系数与极值
```python
results = {}
for p in g_o.Phases:
    p_name = p.Identification.value if hasattr(p.Identification, 'value') else str(p.Identification)
    if "Safety" in p_name:
        last_step = p.Steps[-1]
        msf = last_step.Reached.Msf.value
        results['SafetyFactor_Fs'] = msf
        print(f"稳定分析最终安全系数 Fs = {msf:.3f}")
```

### 3. 提取特征场变量 (孔压、基质吸力、位移)
```python
def extract_phase_field_summary(g_o, phase, target_step=-1):
    step = phase.Steps[target_step]
    soil_rt = g_o.ResultTypes.Soil
    summary = {}
    
    # 1. 孔隙水压力与吸力极值
    for field in ['PWater', 'PActive', 'Suction', 'DegreeOfSaturation', 'GroundwaterHead']:
        if hasattr(soil_rt, field):
            typ = getattr(soil_rt, field)
            vals = g_o.getresults(step, typ, 'Soil')
            vals = [float(v) for v in vals if v is not None]
            if vals:
                summary[field] = {'min': min(vals), 'max': max(vals)}
                
    # 2. 变形极值
    for field in ['Ux', 'Uy', 'Uz']:
        if hasattr(soil_rt, field):
            typ = getattr(soil_rt, field)
            vals = g_o.getresults(step, typ, 'Soil')
            vals = [float(v) for v in vals if v is not None]
            if vals:
                summary[field] = {'min': min(vals), 'max': max(vals)}
                
    return summary
```

### 4. 提取关键监测点数值
```python
# 在关键截面 (如护壁根部、滑动带控制点) 提取单点时程
key_point = (18.65, 10.0, 3.5)
step = g_o.Phases[-1].Steps[-1]

p_water = g_o.getsingleresult(step, g_o.ResultTypes.Soil.PWater, key_point)
u_total = g_o.getsingleresult(step, g_o.ResultTypes.Soil.Utot, key_point)
print(f"监测点 {key_point}: 孔压={p_water} kPa, 总位移={u_total} m")
```

### 5. 自动导出结果云图截图
```python
output_img_dir = Path("./analysis_plots")
output_img_dir.mkdir(exist_ok=True)

# 语法: g_o.export(<target_path>, <width>, <height>)
target_img = output_img_dir / "pore_pressure_distribution.png"
g_o.export(str(target_img), 1920, 1080)
print(f"云图已导出: {target_img}")
```

---

## 端到端全流程可执行脚手架范式

以下代码为 AI 执行完整建模求解的标准调用模板：

```python
import os, sys, time, shutil, json
from pathlib import Path
from plxscripting.easy import new_server

# 1. 准备工作区工程 (克隆基准模板)
TEMPLATE_P3D = Path(r"D:\防排水\templates\base_model.p3d")
WORK_DIR = Path(r"D:\防排水\runs\run_case_01")
WORK_DIR.mkdir(parents=True, exist_ok=True)

# 物理克隆 .p3d 及 .p3dat
work_p3d = WORK_DIR / "model.p3d"
work_p3dat = WORK_DIR / "model.p3dat"
if not work_p3d.exists():
    shutil.copy2(TEMPLATE_P3D, work_p3d)
    shutil.copytree(TEMPLATE_P3D.with_suffix(".p3dat"), work_p3dat)

# 2. 启动 Input 并建模
session_in = PlaxisSession(r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DInput.exe", port=10001)
s_i, g_i = session_in.start()

try:
    s_i.open(str(work_p3d))
    g_i.gotosoil()

    # (A) 调整材料参数与地层标高
    # ... create_soil_material(...) / setsoillayerlevel ...

    # (B) 建立防排水构件与网格
    g_i.gotostructures()
    # ... plate / linedrain / intersect ...
    g_i.gotomesh()
    g_i.mesh(0.05)

    # (C) 编排工况并保存
    g_i.gotostages()
    # ... 配置 Excavation -> Fill -> Rain -> Safety ...
    g_i.save()

    # (D) 求解计算
    s_i.calculate()
    g_i.save()
finally:
    session_in.close()

# 3. 启动 Output 提取成果指标
session_out = PlaxisSession(r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DOutput.exe", port=10002)
s_o, g_o = session_out.start()

try:
    s_o.open(str(work_p3d))
    # 提取安全系数与极值 JSON
    report = {
        "phases": [p.Identification.value for p in g_o.Phases],
        "safety_factor": getattr(g_o.Phases[-1].Steps[-1].Reached.Msf, 'value', None)
    }
    (WORK_DIR / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    # 导出云图
    g_o.export(str(WORK_DIR / "final_plot.png"), 1920, 1080)
finally:
    session_out.close()

print("PLAXIS 端到端自动化运行完成！")
```

---

## 核心避坑与已知限制总结

1. **模板克隆原则**：绝对禁止直接用 `s_i.new()` 创建无根工程；一律采用 `shutil.copytree` 复制已存在的干净基准工程（`.p3d` 与 `.p3dat`），再通过 `s_i.open()` 加载。
2. **模式进入顺序不可颠倒**：打开工程后必须先进入 `g_i.gotosoil()` 唤醒几何核心；后续严格按 `gotosoil() -> gotostructures() -> gotomesh() -> gotostages()` 流程推进。
3. **几何求交必做**：在结构模式下定义任何板（Plate）、接触面（Interface）、排水线（LineDrain）后，必须调用 `g_i.intersect()`，否则结构与土体不会生成拓扑共面网格。
4. **非水平土层只读限制**：`Zone.Top` 和 `Zone.Bottom` 属性为只读，修改土层顶底标高必须使用 `g_i.commands('setsoillayerlevel <Borehole> <Soillayer> Top|Bottom <val>')`。
5. **DrainageType 限制**：土体材料的 `DrainageType`（Drained / Undrained / Non-porous）不能通过外部 Python API 更改，需在模板工程的材料库中预先设好。
6. **进程守护与端口清理**：务必使用 `try...finally` 包裹 PLAXIS 会话，确保异常时即使报错也能彻底杀死后台 `Plaxis3DInput.exe` / `Plaxis3DOutput.exe` 进程，防止端口与文件锁死。

---

# 附录 A：上游 v2.0 旧版内容（原样保留）

> 上游 2026-10-09 的新版（上文）改写为通用的端到端教程，删去了下面这些实操细节（连接、路径、命令日志核验、排水对象、保存失败与 data.convd.rr1 处理等）。这些内容经实测仍然有效，附录 B 的经验也以它们为基础，所以原文保留。

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

---

# 附录 B：实测补充的坑与经验（2026-09-30 起）

> **与上游新版说法不一致之处，以本附录的实测为准**（PLAXIS 3D 2024.1）：
> - 新版说“绝对禁止 `s_i.new()`”：实测 `s.new()` 新建项目后用 `save "路径"` 直接另存是可靠的（新项目、无旧计算结果时），见“环境与连接补充（2026-09-30）”。模板克隆仍是改已有工程时的稳妥做法。
> - 新版说“`DrainageType` 不能通过外部 API 更改”：实测用字符串 `setproperties` 可以设置，包括 `"Drained"`、`"Undrained (C)"`、`"Non-porous"`，但要先设 SoilModel/DrainageType 再设参数，见“材料属性的只读陷阱”和“不排水黏土与分层土中的桩”。
> - 长时间计算：新版示例用 `s_i.calculate()`；实测须 `new_server(..., request_timeout=None)`，否则计算中途超时断开。

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

## 脚本可移植性与存储步（2026-10-17，筒型基础脚本包）

- **PLAXIS 自带 Python**：`C:\ProgramData\Seequent\PLAXIS Python Distribution V2\python\python.exe`（3.8.18，自带 plxscripting、numpy 1.24，**没有 pandas、python-docx**）。给其他电脑用的脚本优先只依赖 numpy，用它运行可免装环境。
- **distutils shim 只在 Python ≥ 3.12 时加载**：3.8 自带 distutils；无条件 `sys.path.insert(0, shim)` 会遮住真的 distutils，且旧 shim 依赖 `packaging`（3.8 环境可能没有）。做法：`if sys.version_info >= (3, 12): sys.path.insert(...)`，shim 内用正则解析版本号自写比较，不依赖第三方包。
- **MaxStepsStored < 实际步数时 ΣMstage 可能取不全（未验证）**：曲线点逐步记录，但 Output 的 `Phase.Steps` 只含存储步，逐步读 `Reached.SumMstage` 会比曲线短、按序号对不上（错位）。对策：先试 `getcurveresultspath(cn, P2, P2, ResultTypes.<组>.SumMstage)`，再试存储步，长度都对不上就改为存全部步重算。是否存在 SumMstage 的曲线结果类型尚待实测。
- **存储步占用**：实测约 0.7 KB/单元/存储步（1.6 万单元每步约 11 MB）；设 MaxStepsStored = 50 实际落盘 71 个 data.### 文件（多约 40%）。
- `mesh` 返回提示中文为“已生成 N 个单元”，英文界面不同，解析用 `r'(\d+)\s*(?:个单元|elements)'`。
- python-docx 表格：`cell.text = ...` 生成的 run 没有 rFonts 节点，直接 `run._element.rPr.rFonts.set(...)` 报 `'NoneType' object has no attribute 'set'`；先设 `run.font.name` 再设东亚字体。

## 推覆以 102 结束但未到破坏平台（2026-10-20，筒型基础 112 个模型实测）

- **现象**：荷载控制推覆（MaxLoadFractionPerStep 0.002、MaxSteps 1000、弧长控制）全部 112 个模型的 Phase 2 都以“荷载步长不足（错误代码 102 Not enough load steps）”、Failed (soft) 结束，ΣMstage 只到 0.37～0.58，筒盖转角 0.74°～2.09°，末端切线刚度（最后 50 步割线）仍为初始刚度的 2.5%～5.5%，曲线还在上升，**没有到破坏平台**。上文“102 常表示已到破坏平台”只在末端相对刚度接近 0 时成立；102 本身只表示用满 MaxSteps 时 ΣMstage < 1。
- **原因**：前 14～34 步按上限 0.002 推进，土体屈服后 PLAXIS 自动缩小步长，最后 100 步平均每步 ΔΣMstage 约 0.00009（0.000055～0.000117），1000 步几乎都耗在屈服段。验证变体把步长上限减半（0.001）、MaxSteps 加倍（2000），终点 ΣMstage 几乎不变（0.3937 对 0.3935）：终点由“步长上限 × 步数”的预算决定。H_ref 取估算承载力约 2 倍时尤其明显。
- **判断与处理**：每个工况检查末端切线刚度与初始刚度之比、最后若干步的 ΔM；小转角指标（如 θ = 0.25°、0.5° 处的弯矩）只要交点落在已算曲线内就有效，但终点 M_max 不能当极限承载力。需要极限承载力时：保持步长上限、把 MaxSteps 加到 3000～5000；或改为在加载点施加水平位移的位移控制推覆（不要加在筒盖上，否则 M/H 改变）；或经验证后加大步长上限。三者都要重算推覆阶段。
- **转角取法**：加载柱用单节点与筒盖相连时，用柱顶与筒盖中心水平位移差 /22 m 算的“柱转角”在筒盖转角 0.25° 时为 0.254°～0.358°（1.015～1.434 倍），差别来自连接处局部变形；筒基础转角应取筒盖前后缘竖向位移差 / D。
- **逐步 ΣMstage 的来源**：工作站上 Codex 是从结果目录的原始 `data.c02` 逐步读出荷载乘子并与曲线点逐值对齐的（按 2.00 格式、记录长度、连续步序校验）。具体解析代码在工作站脚本中，本机未验证；上文“ΣMstage 可能取不全”的问题可用此法绕过。
- **教训（2026-10-21）：要“推到破坏”就用位移控制，批量前先试算确认到平台。** 四翼板筒型基础 108 个工况沿用电杆课题的荷载控制设置（步长上限 0.002、1000 步），全部没推到平台，极限承载力要整批重算。电杆课题已有“0.002、1000 步只推到倾斜率约 143‰”的预警（见上文），当时应据此改设置。做法：在柱顶加载点加指定位移（只规定荷载方向，其余方向和转动放开），新推覆阶段从安装阶段开始；力从加载点反力读（半模型 ×2）；先在代表工况上试算，确认到平台、小转角指标与荷载控制一致，再批量计算。
