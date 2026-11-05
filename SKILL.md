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

- 完整脚本在 `C:\Users\xiong\Desktop\Pile\scripts\`：build.py（L、B、half/full、角度 → 建模+网格+分阶段+保存）、verify.py（打印各阶段激活/材料/荷载/迭代参数）、selpts.py（Output 选曲线点）、extract.py / analyze.py（提取曲线、求 M₁₅）。密码和端口从环境变量 PLX_PASSWORD / PLX_PORT / PLX_OUT_PORT 读，不写进文件。
- 通用做法：体分解后按 BoundingBox + 名字前缀识别侧面/底面；对称面上的板按右手法则调整点顺序使法向朝 +y；Soil 特征名用 `echo <Volume>` 取（如 Soil_8），分阶段名用 `re.findall(r'Soil_\d+')` 的 token 匹配（`Soil_1_Soil_8_1` 含 Soil_8）。
- 全模型中套管圆柱面会被 4 片翼板切成 4 块（Plate_1_1…1_4），界面同理；半模型被 1 片切成 2 块。
- 回归：脚本重建与手工模型单元数差约 1%（6,879 vs 6,810，网格参数相同，几何创建顺序不同所致），在已验证的网格收敛范围内。
- 半模型 vs 全模型实测（L10-B2，对称面翼板取半厚 + 单侧界面，荷载减半）：M₁₅ 23.16 vs 23.38（半模型低 0.96%，偏保守），全程差值 ≤1.9%；全模型 11.6k 单元计算约 16 min，半模型约 9 min。对称等效处理成立。
- build.py 中 B = 0 时跳过翼板（否则会生成零宽退化面）；正式模型输出到 `Pile\model\<编号>\<编号>.p3d`。无翼板时套管面不被切分（单块 Plate_1_1）。
- 分析脚本注意：目标荷载超过推覆达到的最大荷载时，`np.argmax(M >= Mw)` 返回 0，插值会给出无意义结果；必须先判断 `Mw > M.max()` 并标为"基础破坏"。弱工况（如 L05-B0）极限弯矩可能低于所有风荷载档。
- Output 中删除曲线点：单个 `delete CN_n` 无效，用 `clearcurvepoints CurvePoints` 清空后重新 addcurvepoint，再 `update`。已计算项目改选曲线点后计算结果不受影响（CalculationResult 和 .p3dat 结果文件保留，存储步足够时曲线由存储步生成）。
- 批量建模（实测 16 个半模型约 40 min）：`batch.py` 依次调用 build.py → verify.py，并从 data.input3d.log / data.mesher3d.log 解析实际网格尺寸和最差单元质量写入汇总；再用 `geocheck.py` 在结构模式下按包围盒逐个核对几何、板材料、点荷载高度。最差单元质量 0.27~0.46（Gmsh SICN），均在外围土体。geocheck 只打开、不保存，已计算模型的结果不受影响。
- 脚本计算（calc_one.py）：长计算必须用 `new_server(..., request_timeout=None)`，否则 `calculate` 会超时断开。`s.call_commands("calculate")` 阻塞到算完；之后 `save` 把结果写进项目；`view Phase_2` 打开 Output 并在 returnedobjects[0]['json'] 返回 Output 端口，再提取曲线，结束时 Output 端 `close`。实测 L05-B1（5.1k 单元）计算 3.7 min、提取 4.5 min。
- 后台批量计算受 Codex 后台任务约 2 小时上限限制：超时后外层循环被杀，但正在跑的 calc_one.py 子进程可能继续（计算、保存完成），其后续 extract 会因丢失控制台崩溃（退出码 3221225794 = 0xC0000142）。对策：每个后台任务只排 2~3 个模型；被杀后先查 `Get-CimInstance Win32_Process` 是否还有 calc_one 进程，等其结束，再用 `calc_one.py <编号> --extract-only` 补提取。
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

## 论文云图批量导出（2026-10-22，电杆四翼板基础论文图，scripts\paper_plaxis_figs.py / paper_compose_contours.py）

- **Output 端发 `close` 会停掉其脚本服务器**：之后 Input 再 `view Phase_2` 返回 `"json": 0`（没有端口），连 10001 被拒。换模型的可靠做法：`taskkill /IM Plaxis3DOutput.exe /F` → Input `s.open(...)` → `gotostages` → `view Phase_2`，返回 10001 后等约 10 s 再操作（窗口布局未完成时 zoom 取景会错）。
- **`zoom` 取景不稳定（已验证）**：同一剖面图、同样的 zoom 框，不同次导出得到的比例和中心都可能不同（有的放大约 2 倍，有的只剩地表一条）。对策：(1) 每次导出前重新 `zoom`，导出两次，检查非白像素比例，过低则重试；(2) **不要依赖相机，导出后按图中电杆宽度（D = 0.35 m）自动标定**：竖向剖面取地表行（非白占比 > 60% 的第一行），在地表上方几像素找电杆色块或在地表下方找电杆白色空洞，宽度/D 即像素每米；水平剖面在对称边（最下一行土体）找电杆半圆空洞（τrel 图中电杆无值、呈白色；γs 图中电杆有颜色，无法标定，水平剖面只用 τrel）。标定后按统一物理窗口裁剪，B0 与 B4 才能同比例对比，并可精确叠画电杆、套筒、翼板轮廓。
- 推覆末端的增量位移 dUtot 在土中很小、被电杆主导，云图几乎全蓝；表示破坏机构改用推覆末端的总剪应变 γs 或增量剪应变（IncrementalDeviatoricStrain，色标上限取 99.5% 分位）。
- 相对剪应力 `ResultTypes.Soil.RelativeShearStress`（τrel，固定 0–1，τrel = 1 即塑性点）比 PlasticPoint 更适合表示塑性区，剖面上清晰。
- 板件内力取值：`getresults(plate, step, ResultTypes.Plate.N11/N22/Q12/M11/M22/M12, "node")`，板面 von Mises 按 σ = N/t ± 6M/t² 换算；对称面上的半厚度翼板 t 取一半。界面法向应力：`ResultTypes.Interface.InterfaceEffectiveNormalStress`，配合 `Interface.X/Y/Z` 按深度分箱、沿圆周对 σn·cosθ 积分即单位深度净土抗力（半圆积分 ×2；用"合力 = 该时刻水平荷载"自校验，L10-B0 得 2.04 kN 对 2.05 kN）。
- 偶发 `EncryptionError: Reply code is different from what was sent! Server might be spoofed!`（连续开关多个模型后出现，原因未查明），重开 Output 后重跑该模型即可。

## 敏感性补算的参数化与提速（2026-10-23，scripts\build.py 环境变量覆盖 + scripts\sens_run.py）

- **弹塑性板材料**：`set PlateMat_n.MaterialType "Elastoplastic"` 后出现 `YieldStress11/22`、`W11/W22`（截面模量，按 t²/6）。**各向同性（Isotropic True，默认）时 `YieldStress22`、`W22` 为只读**，设置报"无法设置只读属性 YieldStress22"——只设 `YieldStress11` 和 `W11`。
- **Updated mesh**：`set Phase_n.Deform.UseUpdatedMesh True` 可用。实测 L10-B4 半模型 1000 步用时 55 min（小应变约 6 min）。Updated mesh 直接算得的 M15 比"小应变 + 解析 P-Δ 修正"高约 1.1%（L10-B3、L10-B4 两例），解析修正可信且略保守。
- **逐步读 ΣMstage 很慢**（`Phase.Steps[k].Reached.SumMstage`，约 0.5 s/步，1000 步约 8 min）。曲线点位移用 `getcurveresultspath` 秒级完成，所以先读位移、求出倾斜率达到所需值的步号，再只读到该步的 ΣMstage（L10-B4_UM 读 321 步约 3.5 min）。
- 给建模脚本加环境变量覆盖（默认值与主研究一致）是做敏感性补算的简便方式：土的 E、c，近场网格尺寸，翼板厚度，板弹塑性，延伸段 Rinter，Updated mesh，集中力大小；输出到单独的 `model_sens\` 目录，不污染主模型。
- **改荷载模式后，荷载乘子换算地面弯矩的系数必须跟着改（2026-10-23 踩坑）**：主研究用 `M_GL = 244·ΣMstage`（244 是两导线参考荷载 q = 1.63 kN/m、F = 10.83 kN 在地面的弯矩）。三导线敏感性算例只把集中力改为 15.92 kN，后处理仍乘 244，L10-B4 的 M15 算成 21.59 kN·m（−19%），像是承载力大幅下降。正确系数为 244·(q·12²/2 + F·11.7)/(两导线同式) = 303.5，换算后 M15 = 26.86 kN·m，与两导线只差 0.2%。做法：系数由每个算例的参考荷载算出（sens_run.py 的 `m_ref()`），后处理与计算分开，保存曲线文件后可 `--resummarize` 重算，不必重跑 PLAXIS。
- **转动中心比 zc/L 的公式**：zc = L·u_D/(u_D − u_E)，所以 zc/L = u_D/(u_D − u_E)，不要再除以 L（曾误除，L = 1.5 m 时得 0.41，正确为 0.62；L = 1.0 m 时看不出错）。
- **弹塑性板是否真的屈服，要和弹性算例对比判断（已验证）**：Output 中板的节点弯矩 `ResultTypes.Plate.M11` 是由积分点外推到节点的，弹塑性板（σy = 235 MPa，W11 = t²/6，屈服弯矩 0.979 kN·m/m）在 15‰ 时节点最大值仍有 1.49 kN·m/m，超过屈服弯矩，不能据此判断"塑性没生效"。核查方法：①在 Input 中读材料 `MaterialType`（1 = Elastic，2 = Elastoplastic）和 `YieldStress11`、`W11`，遍历 `g.Materials[:]` 并用 `TypeName.value == "PlateMat"` 筛选；②与同一模型的弹性算例比较：20‰ 时翼板节点弯矩最大值由 1.94 降至 1.53 kN·m/m（−21%），说明已屈服，而 99% 分位值仍低于屈服弯矩，说明只是局部屈服。脚本 `scripts\ep_check.py`。


## 2026-10-23 paper revision: verified corrections

The following supersedes the earlier blanket process-kill recommendation, the equivalence of relative shear stress to plastic-point history, and rounded reference-load coefficients. Historical observations above are retained, but should not be reused as universal rules.

# PLAXIS runtime findings, 2026-10-23 revision

These notes record the current run for a later, backed-up append to the shared skill. No password is stored here. Original models remain untouched; all active calculation copies are under this revision's `models` directory.

## 1. Input and Output phase identification strings differ (verified)

- Symptom / original error: matching an Output phase by exact equality to the Input identification raised `StopIteration` after successful calculation.
- Cause, verified by listing both APIs: Input identification is `REV_WIND_32_6_3C`, while Output returns `REV_WIND_32_6_3C [Phase_3]`. Output appends the internal phase name in brackets.
- Fix, verified: use the stable `Name` (`Phase_3`, `Phase_4`) to retrieve the Output object, e.g. `getattr(go, input_phase.Name.value)`. Do not compare the display identification strings directly.
- Scope: the first L15-B0 load/unload calculation had already finished correctly before this extraction error. Its saved results were reused; it was not recalculated merely to fix a label lookup.

## 2. Do not overlap independent Output extraction with an Input view request (observed failure; mechanism not conclusively established)

- Symptom / original error during parallel Output work: `plxscripting.plx_scripting_exceptions.EncryptionError: Reply code is different from what was sent! Server might be spoofed!`.
- A separate extraction process then waited without producing a summary while no Output process was present. Input remained responsive (`echo Project.Title` returned the expected copied project), and the completed calculation result had already been saved.
- Possible cause: multiple Output processes plus an Input `view` launch may interfere with application/session reuse. This causal mechanism is **not proven**; the exception text alone is not evidence of an external spoofing attack.
- Fix, verified for recovery: terminate only the identified Python process belonging to the stuck extraction, preserve Input and saved model files, then read the saved project in a dedicated Output process with its own free port. Run all Output extraction serially. L15-B2 was recovered from disk with no repeated calculation.
- The active script now uses `open_saved_output()` for ordinary result extraction. Mesh-node selection still uses the documented Input `selectmeshpoints` path and is performed while no other Output session is active.

## 3. Process ownership must be explicit (verified implementation)

- Several historical project scripts call `taskkill /IM Plaxis3DOutput.exe /F`. This would close every user Output window and should not be copied into a new workflow.
- Current scripts keep the precise process handle/PID they launch and close only that process in `finally`. No Input process is terminated. Do not confuse a matching executable name with process ownership.
- For Input-launched Output used in mesh selection, record the process inventory immediately before the launch and identify the newly created instance. This inventory method also requires serial launches; overlapping launchers would make ownership ambiguous.

## 4. Exact load conversion follows the applied pattern (verified from builder and staged loads)

- Old reporting scripts used `244*SumMstage`. Actual two-conductor full-model reference loads are `q=1.63 kN/m`, `F=10.83 kN`, `h=12 m`, `hF=11.7 m`, giving `Mref=244.071 kN m`.
- Saved three-conductor reference loads with `F=15.92 kN` give `Mref=303.624 kN m`.
- The new alpha=0.70 pattern normalizes q to the same value but changes F, yielding its own `Mref=293.3576965102041 kN m`. A shared conversion factor would create a false capacity difference.
- Compute the conversion from each case's actual staged line/point loads and full/half-model factor. The original rounded coefficient changes numbers by only 0.0291%, but all revised tables use one consistent convention.

## 5. A 102 result at the deliberately bounded tail does not erase earlier converged deformation thresholds (verified)

- New pushovers bounded to 300 steps terminate with `CalculationResult=4`, `LogInfo=102`, and an incomplete target load multiplier. This is the same step-budget behavior as the historical long pushovers.
- The saved phase calculation logs (`<project>.p3dat/log.d03` for the new wind phases, `log.d02` for mesh checks) explicitly report `ErrorCode=102`, `ErrorMsg=Not enough load steps.`, and `StepsCount=300` (wind) / `350` (mesh). This confirms the actual reason; do not infer a failure mechanism solely from the numeric code.
- The scripts check that the first crossing of 15 per mille exists in saved converged history and extract past 20 per mille. They do not rename the terminal moment an ultimate resistance or claim the full multiplier target was achieved.
- By contrast, the two new finite load/unload cases both reached `SumMstage=1` for both stages, with `CalculationResult=1`. Their residual displacement results can be reported as completed paths.

## 6. Interface relative displacement fields are available directly (field discovery verified; final physical comparison must use the serially checked exports)

- `dir(go.ResultTypes.Interface)` exposes `IRelUx`, `IRelUy`, `IRelUz`, and `IRelUtot`, as well as X/Y/Z. These provide direct interface-relative displacement, unlike the soil total-displacement contours.
- The vector norm of the three global components matches `IRelUtot` to numerical precision in the initial 45-degree export. A planar fin normal can therefore separate normal relative motion from tangential relative motion in offline processing.
- Exclude the artificial interface extensions below the structural toe. Their boundary node line at z=-L must not be mislabeled as the physical pole base merely because the filtered z range is zero.
- Cache `itf.Name.value` once per interface before iterating thousands of returned nodes; avoid issuing repeated remote property requests inside the local row-building loop.

## 7. Relative shear-stress contours are not a plastic-state history test

- `Soil.RelativeShearStress` describes the current strength-mobilization ratio. Values near one identify strong mobilization; a displayed value of one should not be equated automatically to a stored plastic-point history or a complete plastic mechanism.
- Keep this distinction in manuscript captions and in the shared skill; do not infer rigid soil blocks or zero slip from a total-displacement contour.

### 8. Empty Input project (verified)
Accessing g.Phases on an empty Input project raised AttributeError. First read server metadata and Project.Title; an authenticated connection is not evidence that the intended project is open. Open only the task's saved copy, then inspect phases.



## 2026-10-24 final export verification

Both 0-degree and 45-degree interface exports were re-read serially. The selected field-step top displacement and load multiplier agree with the source curve to absolute tolerance 1e-10; component norms agree with IRelUtot within 1.1e-14 mm. Report -L<z<=0 fin-face node subsets and exclude the toe intersection. Absolute normal relative motion does not determine contact opening sign.

## 8. A displacement-based export cutoff may omit another response criterion (verified recovery)

- Symptom: L30-B0_M06 initially reported M05deg=null even though its saved full phase crossed the ground-rotation threshold.
- Cause: the exporter retained load multipliers only until top inclination passed 20 per mille. For this deeper pole, bending contributes strongly to top displacement, so 0.5-degree ground rotation occurs later. The Ux/Uz arrays were complete, but the common multiplier prefix was too short.
- Fix: select the export length from the larger of the two threshold-crossing indices (with guard steps), then read the saved project only. No recalculation was needed. The recovered M05deg is 122.4395070145343 kN m; M15 and M5 are unchanged. Do not interpret a truncated-prefix null as proof of physical non-attainment.


## 2026-10-24: endpoint and plateau audit corrections

- Symptom: historical reporting equated ErrorCode=102 with having passed failure; a later review overcorrected this to "1000 steps means failure was not reached". Both inferences are unsupported. Cause: the termination code describes the solver stop condition, not the entire curve shape. Verified remedy: inspect the saved moment–rotation history. The original 21 pole models all have 1000 strictly increasing moment points, with maxima at the final point, yet shallow cases have very flat tails while deep cases retain appreciable slopes. A monotonic plateau need not contain a negative load increment or trigger unloading-based stop detection.
- Symptom: build.py sets MaxStepsStored=1000 and it was read as an explicit iteration cap. Cause: storage budget and Deform.MaxSteps are different properties. Remedy: distinguish stored steps from solver maximum steps; inspect actual phase settings/logs before claiming the script explicitly set MaxSteps.
- Verified analysis approach: use multiple tail spans (last 0.1 degree fitted slope, last 0.5 degree moment growth, last 20 percent of terminal rotation), not just a fixed number of very small final load steps. The 1-percent slope/growth screen used in this audit is exploratory only, not a code criterion or a validated Mu definition; fitted curve stiffness is not the solver's CSP/RelativeStiffness property. The original nominal rotation formula at large values also requires physical interpretation.
- Evidence and reproducible read-only script: D:/Pile/docs/paper_draft/full_zh/revision_20261023/analysis/audit_failure_moments.py and analysis/failure_moment_audit_20261024/. All 21 source hashes matched the revision provenance, and initial slope windows of 3/5/10 points did not change the less-than-1-percent tail-slope classifications. No PLAXIS recalculation was performed for this audit.

## PLAXIS 3D 2024.1 slope-pile API findings (2026-10-25)

- Symptom: `setsoillayerlevel Borehole_1 0 Top ...` returns `参数无效。请确保指定参数与需要的参数相匹配。` Cause: the installed 2024.1 command takes separator level/elevation pairs, not a Top/Bottom string. Verified fix: `g.setsoillayerlevel(bh, 0, top_z)` and `g.setsoillayerlevel(bh, 1, bottom_z)` for one layer. The bundled command reference agrees; this supersedes the earlier Top/Bottom examples for this installation.
- Symptom: Undrained C material batch setters fail with `无法设置只读属性 psi` or `无法设置只读属性 gammaSat`. Cause: phiU and psi are fixed at zero and gammaSat follows gammaUnsat in this drainage type. Verified fix: set `ERef`, `nuU`, `sURef`, `gammaUnsat`, and `TensionCutOff`; read back phiU=psi=0 and gammaUnsat=gammaSat=10. Do not assume a failed multi-property command partially applied its values; readback showed all numerical defaults remained zero.
- Symptom: `InterfaceStiffnessDetermination="Manual"` reports `值无效 ... 允许值为 "derived", "direct" 或者序数值。` Verified fix: use `Direct`, then `knInter` and `ksInter`. `InterfaceStrengthDetermination="Manual"` is a separate setting; its values must not be reused for stiffness determination.
- Symptom: `Deformations.XMin` is absent and setting `UseDefaultFixities` reports `无法设置只读属性 UseDefaultFixities`. Verified fix: use phase-dependent `BoundaryXMin`, `BoundaryXMax`, `BoundaryYMin`, `BoundaryYMax`, `BoundaryZMin`, and `BoundaryZMax` directly. Readback confirmed four Normally fixed sides, Fully fixed bottom, Free top.
- Symptom: tabulate with a feature-list plus two phase arguments fails with invalid parameters. Verified fix: tabulate each feature collection for one phase at a time. This also exposes inherited settings explicitly enough for staged material audits.
- Symptom: an Undrained C MC toe material with sURef=0 is rejected as `无效材料` before any phase solves, even when its interface is inactive. Verified workaround: sURef=1e-6 kPa, Rinter=1, direct normal/shear stiffness, zero tensile strength. Initial gravity and zero-motion installation phases then converged. This is a near-zero-shear approximation, not exact zero toe shear; export toe horizontal force separately and verify its influence before making a capacity claim. Exact-zero alternatives have not yet been verified.
- Verified: native rigidbody attached to a cylinder supports `TranslationConditionx/y/z="Displacement"`, `RotationConditionx/y/z="Rotation"`, reference point Xref/Yref/Zref, and phase-dependent ux. Apply a weightless interior material only in the installation phase; keep clay in the initial phase. Rigid-body reaction moments are not pile section bending moments.
- Evidence: C:/Users/xiong/Documents/Codex/2026-10-25/lia/outputs/models/F06_pilot_m05/, its material/staged snapshots, native calculation history, and phase_status.csv. Only initial gravity and zero-motion installation convergence were verified at the time of this entry; horizontal limit response was still being calculated.

### Additional solver/driver findings, 2026-10-25
- Symptom: setting Phase.Solver to `Pardiso` failed with `允许值为 "picosmulticoreiterative", "pardisomulticoredirect", "classicsinglecoreiterative" 或者序数值。` Fix: use the full enum display string `Pardiso (multicore direct)` (or the accepted normalized token), and read back actual phase settings. A bare label from the command-reference summary is insufficient.
- During a blocking Input calculate request, another API client with a five-second timeout could not even initialize. This is server busy behavior in this run, not evidence that the scripting server or license is unavailable. Keep calculations and Output exports serial.
- Stopping only the task-owned Python wrapper did not stop the GUI-owned PLAXIS solver: F06 Phase_5 (cumulative 0.01d) completed afterward. Reconnect, verify the intended project, save completed GUI state, and then continue only unfinished phases. Preserve the native log timestamps when an interrupted wrapper did not record duration; do not invent a duration.

### Contact and Output diagnostics, 2026-10-25
- Verified displacement semantics: in the native rigid-body test, cumulative ux targets -0.006, -0.012, -0.030, -0.060 m produced exactly these total Output Ux values. Do not convert them to stage increments in this API. The same 0.01d stage recomputed from its 0.005d parent with Pardiso gave -98231.1275996242 kN versus Picos -98231.9930924855 kN (0.000881 percent difference). This verifies that solver substitution reproduced this stage; it does not prove later convergence.
- Error 111 in the subsequent 0.02d stage reached only SumMstage=0.0065710702612175386. A separate ArcLengthControl Off control stalled at SumMstage=0.00602446420047375 for approximately 480 steps and was deliberately stopped (LogInfo=254). Turning off arc length alone was not a verified remedy. Do not report the failed/stopped force as a limit resistance.
- Exact-zero toe alternatives tested on a preserved diagnostic copy: Rinter=0 is rejected with `Rinter 必须介于 0.01 和 1 之间`. Direct ksInter=0 is accepted by the setter but `checkcalculationconditions` reports `无效材料` even with positive sURef=75. Thus setter acceptance alone is not material validation. A small positive toe ks, unchanged near-zero strength, and a direct normal stiffness remain a numerical experiment until calculated and checked; they are not automatically exact frictionless contact.
- In the Chinese 2024.1 installation `checkcalculationconditions(phase,"errors")` fails with `Invalid feedback severity, expected values are: 提示, 提示, 警告, 错误, all`. Verified workaround: use the language-independent `all`, then inspect its returned errors/warnings.
- Rigid-body Mxreaction/Myreaction/Mzreaction and Mx/My/Mz return `命令不传送任何结果` in 2024.1, while displacement/rotation and force fields work. Bentley's PLAXIS 3D 2024.2 release notes explicitly list fix 1043370 for rigid-body bending moment retrieval via command line: https://bentleysystems.service-now.com/community/en?id=kb_article_view&sysparm_article=KB0041968 . Preserve missing raw values as null with reason, never zeros. This API defect alone is not a cause of FE solver failure.
- Undrained-C interface stress-point exports in this run contain InterfaceEffectiveNormalStress, InterfaceShearStress, InterfaceShearStress2, X/Y/Z, ElementID and LocalNumber. InterfaceTotalNormalStress and VirtualInterfaceThickness return no results; IsCurved is absent. Any effective-to-total traction interpretation needs the model's water/total-stress convention and a signed force-balance check. Never silently substitute a field based on its label.
- Post-calculation rigid-body curve selection triggers slow middle-step loading. The pre-calculation check explicitly warns that not preselecting curve nodes/stress points makes later curves slower. Export essential Ux/Fxreaction histories and keep endpoint components separately; add appropriate pre-calculation selections in a future build. Do not interpret slow Output export as a failed Input solve.
- Evidence: C:/Users/xiong/Documents/Codex/2026-10-25/lia/outputs/models/F06_pilot_m05/control_diagnostics/ and F06_contact_repair/material_probes.json, zero_ks_validation.json. Contact conditioning as the cause of the 0.02d stall is still an unverified hypothesis at this entry.

### Contact repair verified at the formerly stalled stage (2026-10-25)
- Further evidence superseding the hypothesis-only status above: the original `data.convd.rr6` ends with global error0.001378, integrated soil error1.354e-6, integrated interface error0.006712 (all below0.01), but1950 inaccurate interface plastic points, including1739 inaccurate tension points. Maximum out-of-balance location(2.939,-0.6041,-3.956)m lies on the rear shaft. Thus the particular111 stop was an opening-interface point-accuracy failure; it was not evidence of a physical limit.
- A toe-only control lowering ksInter625000 to1kN/m3, keeping sURef1e-6 and normal stiffness unchanged, still stalled near SumMstage0.00606752 and was stopped. It did not remedy the shaft problem.
- A single-factor shaft control changed knInter6250000 to625000 and ksInter625000 to62500kN/m3 in a new phase from the same converged0.01d parent. Soil and interface strength, alpha0.5, zero tension, motion constraints, solver and ArcOff controls remained fixed. It fully converged to0.02d in126.476s, SumMstage1, actual Output Ux=-0.12m, all other translation/rotation components0, Fxreaction=-123871.781735198kN. This confirms over-stiff shaft contact contributed to this stall. It does not establish a universal stiffness recommendation or sensitivity-independent ultimate resistance. A full from-initial rebuild with the repaired contact is required.
- Verified raw integration: `__getmeshlocalaxes <cut_surface> (x y z)` returns local axes1,2,3 and the nearest point. For this cylinder, axes1/2 are shear directions and axis3 the outward normal; normal compression is negative. Batch the documented commands with `s.call_commands(*commands)` and preserve each native response. At actual SP coordinates, quadratically interpolated geometry, six-point Gauss weights and conservative depth-band clipping give shaft123871.931051574kN, toe2.72070e-5kN; signed equilibrium is Fxreaction+Fshaft+Ftoe=0. Relative residual0.000120563percent. Do not subtract the shaft from the already negative actuator reaction. Nearly zero baseline reactions need an absolute residual, not a misleading relative percent.
- Python serialization pitfall: SP coordinates from numpy may contain `numpy.int64` (e.g. constant Z=-36), raising `TypeError: Object of type int64 is not JSON serializable`. Convert coordinate columns to Python float and IDs to int. Preserve completed axis-query rows in JSONL and resume only missing interface/element/local-point keys, rather than repeating thousands of remote calls.
- Evidence: F06_contact_repair/SIDE_SCALE010_002d_result.json, raw/rigid_reference_endpoints.csv, raw/mesh_axes_responses.jsonl, raw/interface_basis.csv, force_balance.csv. A new independent F06_pilot_m05_v2 build was started; its final ultimate-platform status was not yet verified at this entry.

### Verified workaround for native rigid-body moments in2024.1 (2026-10-25)
- This supersedes the earlier missing-moment limitation for the tested case. Ordinary `getresults(phase,ResultTypes.RigidBody.Myreaction,"node")` fails, but the documented `getcurveresultspath(cp,last_step,last_step,ResultTypes.RigidBody.Myreaction)` works. `last_step=list(output_phase.Steps)[-1]`; select cp with `addcurvepoint("Rigid body",(0,0,0))`. This is a real native result retrieval, not a moment reconstructed and relabeled as raw.
- Verified Phase16 native reaction moments: My2618471.36414742, Mx10553.1770356508, Mz-157.075097153945kNm. Independently integrated shaft+toe moments were My-2618477.28386044, Mx-10552.5406817965, Mz157.636113502574kNm. The signs and dominant moment magnitude satisfy equilibrium; the tiny secondary component needs an absolute/scale-aware residual. Raw Fx and Ux from the same step matched the ordinary endpoint API exactly.
- All18 rigid-body displacement/rotation, reaction and applied-force/moment fields were recovered for34 stored steps in Phase2. The final row matches the independently verified native endpoint (Ux=-0.006m, Fx=-12954.2888912281kN, Myreaction263132.450110018kNm). Step-to-step queries avoid repeatedly loading an entire phase just to recover one missing endpoint field.
- `s.call_and_handle_commands(*curve_commands)` plus the official `connection.request_list(*queries)` can batch field requests. The34-step18-field benchmark decreased from176.29s to117.90s with identical endpoint values; native Output processing still costs time. Do not claim near-instant full histories. For the requested load-displacement plot, retain full Ux/Fx histories and all endpoint components, with full native results preserved.
- Evidence: C:/Users/xiong/Documents/Codex/2026-10-25/lia/outputs/models/F06_contact_repair/raw/moment_curve_probe.json, rigid_phase2_step_curves.csv, rigid_phase2_step_curves_batch.csv; scripts work/probe_moment_curve.py, work/probe_step_curves.py, work/probe_step_curves_batch.py. Output processes were task-owned and separate from the calculating Input; no Input view call was overlapped.

### Completed from-initial loading and resumable quality reports (2026-10-25)
- The repaired independent F06_pilot_m05_v2 completed all13 stages, including actual final Ux=-0.6m (0.1d), with normal convergence. Predefined last two total-force changes1.1181329% and0.9410388%; primary0.1d-to4d band mean changes1.0170644% and0.8266612%. All constrained reference motions0; maximum loaded-stage signed force-balance residual0.000110263%. This meets this study's candidate-platform gates only. Mesh/domain/stiffness and slope cases remain necessary before an overall validation claim.
- Symptom during final JSON writing: `TypeError: Object of type bool is not JSON serializable`, for `plateau_windows[].passed`. Cause: a NumPy scalar boolean from comparisons involving np.mean; its displayed type name can be bool. Verified fix: cast the logical expression with Python bool and the reported mean changes with float. Do not stringify booleans because it corrupts machine-readable quality gates.
- Retain completed depth_bands.csv and force_balance.csv before writing quality JSON. After a serialization-only failure, validate that every endpoint has all d/4 and d/8 bands, then rebuild the quality/metrics files from saved integrations. The run did not need another FE solve or repeated raw export. Code: outputs/postprocess.py finalize_saved_quality().
- The raw exporter now resumes only phases with all endpoint fields, every interface SP/node file, and the expected number of curve steps. It replaces incomplete phase rows and sorts the final rows chronologically. The pipeline reuses an already verified native run and does not recalculate it merely because its reporting controller restarted.
- Output object-method pitfall: `go.export(...)` raises `AttributeError: Requested attribute 'export' is not present` in this installation. `info Plot_1` lists export on the Plot object. Use plot.export(path,width,height), or the documented command `export Plot_1 "path" W H`. Other plot-scoped methods should likewise follow their object metadata rather than assuming a global Python method.

### Verified conservative postprocessing acceleration and fractional-length bands (2026-10-26)
- Symptom: the original postprocessor repeated quadratic-face geometry reconstruction, Gauss-point matching and conservative clipping for every phase, causing avoidable CPU time. Verified solution: cache the geometry-only band integration matrix, including the full quadratic traction reconstruction, then multiply by each phase's signed native traction. Require exact X/Y/Z/ElementID/LocalNumber and node-geometry array identity before reusing it; never reuse on a changed or updated mesh. Export the matrix and its depth edges/areas as NPZ for independent reproduction.
- Verification: all864 F06 depth-band rows and all12 phase force-balance rows were compared against the preserved old algorithm. Maximum band Pu difference5.46e-12 kN/m; maximum absolute change among force-balance numerical columns9.28e-11. Four independently checked phases included installation and0.001d,0.02d,0.1d, with bothd/4 andd/8. Complete recomputation took about5.6s; no FE solve was repeated. Evidence: lia/work/band_operator_verification.json, band_operator_full_comparison.json, outputs/interface_band_operator.py.
- Fractional-length pitfall found before any of the six short-pile runs: arange(0,L+dz/2,dz), followed by replacing the last edge with L, can omit a genuine final partial band or merge it into a band larger than dz. Use all edges strictly below L, then append the true L; validate ceil(L/dz) intervals, total heightL and every width<=dz. This preserves the intended last partial band. Existing fullL=6d results are unchanged. Actual fractional-length FE runs were still pending at this entry.
- Curve-export performance: preselect the native rigid-body point through Input selectmeshpoints -> Output addcurvepoint("Rigid body",(0,0,0)) -> update -> Input save before the first calculate. Preserve its native point name and reuse that point on export. The generic node workflow was already verified in prior work; this task's rigid-body preselection implementation was awaiting its first fresh-model execution at this entry. Never claim it has been verified merely from writing the function.
- Separate Input resource-probe attempt: a newly launched task-owned Input stayed without a listening port or a targetable window; its cause was not established. Do not call this a licensing failure. A Python new_server proxy existing is not proof of a responsive server; verify an actual native property and bound the readiness timeout. Only the exact probe-owned processes were closed. The main calculating Input remained untouched, and a build-only resource probe was moved to its idle boundary after V10 saved result extraction.
- V10 full3D d/5 completed all13 stages to actualUx=-0.6m. Candidate-platform final total-force changes1.1213016%/0.9481099%, primary local mean changes0.9150362%/0.7512071%, maximum loaded X-equilibrium residual0.0001482103%, all constrained motions0. Mesh/domain/stiffness verification remained pending; this is not an overall ultimate-validation claim.

###2024.1 rigid-body pre-calculation curve selection is unsupported (verified2026-10-26; supersedes the pending preselection suggestion)
- Symptom: in an uncomputed mesh, addcurvepoint("Rigid body",(0,0,0)) succeeds but actually returns CN_1 with PointType Node(0), DataFrom Soil_1_Soil_2_Soil_3_1 and coordinates near the origin, rather than a rigid-body point. Treating success alone as proof would misidentify the point. Inspect native point echo and type.
- Explicit addcurvepoint on the short Output RigidBody_1 proxy fails with the native entity-not-available error. Using the actual Input staged mesh name RigidBody_1_1 reaches the right entity but reports: 刚体在当前阶段处于非活动状态。 Precalc Output Phases is empty; changing Input current phase does not create an Output calculation phase. A temporary initial-activation probe did not resolve this and was restored from the last saved model; initial rigid inactivity was checked before any calculation.
- Primary confirmation: Bentley PLAXIS3D2024.2 release note1470154 says clarity was improved when a rigid body curve point cannot be selected as a pre-calculation point. KB0108388 explains that pre-calc point caches involve soil/rock, not structural/interface force data. https://bentleysystems.service-now.com/community/en?id=kb_article_view&sysparm_article=KB0041968 and https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0108388 . Do not promise cached rigid reaction histories from an ordinary preselected node.
- Verified recovery: retain optional preselected soil-motion point as such, but select the actual rigid-body point only after calculation. Endpoint18 components still use the verified native moment fallback. Curves are explicitly all actually stored steps. New runs in this task use MaxStepsStored20 per phase, retain every prescribed phase endpoint, and record storage_policy.json; this changes retention, not the solver tolerance. F06/V10 historical runs retain their original1000 setting. Do not label retained curves as every internal solver step.
- Independent native property audit pitfall: g.Boreholes is available in Soil mode but absent in staged construction (AttributeError: Requested attribute 'Boreholes' is not present). Read and check the heads while still in Soil mode, before gotostructures. Material readbacks remain available later. The corrected full d/15 resource-only model was saved with148427 elements,225966 nodes; it was not solved and is not a validation result. InputRSS0.623GiB and availableRAM4.861GiB after building do not prove the solver factorization will fit.

### MaxStepsStored saves intervals across a phase, not only the lastN steps (verified2026-10-26)
- The installed2024.1 Reference Manual page361 states that the final step is always retained; for MaxStepsStored>1, intermediate steps are saved as the calculation control parameter passes successive intervals. For Plastic calculation the interval is targetSumMstage/MaxStepsStored, usually1/N. Do not describe N=20 as keeping only the last20 steps.
- Page482 confirms structural force curves use post-calculation structural selections. Thus20 stored intervals can cover the whole phase, while still not retaining every internal calculation step. User-facing wording in this task was corrected after this manual check. Record both MaxStepsStored and actual stored-step identifiers in the data manifest.

### Native curve Step metadata includes unsaved results; verified bulk retrieval (2026-10-26)
- V11 Phase6 has68 native Step entries with MaxStepsStored20; only20 Ux/Fxreaction pairs are finite. Both step-to-step and whole-phase getcurveresultspath returnNaN at the same48 unsaved entries. The Step collection count is not the full-field saved count. Preserve raw unavailable entries and mark availability; plot only finite native pairs, with the unavailable count disclosed. Never replaceNaN by zero or invent interpolated FE values.
- Verified whole-phase benchmark: Ux20.888s plusFxreaction18.313s, versus about90s for the former per-step extraction. All20 finite pairs match exactly (max differences0), and all unavailable positions match. The source now uses two native phase-path calls and retains the per-step route only for unexpected count mismatch. Check the final values against independently read native endpoints.
- A post-calculation rigid-body point also reports PointType Node(0). Identify it from DataFrom=RigidBody_1_1, Identification and coordinates, not PointType alone. The supported point has Origin Postcalc(1), whereas the earlier mistaken pre-calc selection had DataFrom a Soil entity.
- Require all18 endpoint translations/rotations/forces/moments to be finite. Missing native moments still use the verified last-step fallback; missing endpoint data is an extraction failure, not a reason to insert0. Raw phase curves query onlyUx/Fxreaction; all18 fields are retained at each prescribed endpoint and native result directories remain available.
- Task-owned Output66076, parentInput18596 and creation matching the resource-probe selection, retained about1.56GB RSS while the main Input calculatedV12. It was closed by exactPID at the idle-Output boundary, freeing about1.3GB availableRAM. V12 subsequently completed its0.06d,0.07d and0.08d stages normally. Do not kill all Output processes by executable name. The single fine-run continuation has an additional ownership check based on parentPID and creation time matching its recorded V12 view launch; that automated cleanup was not yet reached at this entry.
- Source hashing on Windows: read_text/write_text can normalize/translate newlines, so hashing UTF8 text may differ from the saved file bytes. New snapshots capture/write raw bytes. Older manifests retain their original hash, explicitly label its text-normalized meaning when applicable, and add the exact saved-file SHA256; saved sources themselves are not changed.

### First-four pilot audit and regenerated-table safeguards (2026-10-26)
- Verified subsequent evidence: repaired F06, V10, V11 and V12 all completed thirteen stages from the initial state to actual0.10d. Every native endpoint has all eighteen finite rigid-reference components, actual interior pile-node translations exactly match the rigid reference, and candidate-platform gates pass. The largest loaded X-equilibrium residual among the four was0.0005037%. This establishes the pilot-grid repair, not completion of mesh/domain/stiffness validation. Evidence: lia/outputs/pilot_audit.json and the four per-run saved quality/motion files.
- Potential stale-table pitfall found by code inspection before actual cross-run comparisons were available: a CSV writer returning immediately for an empty regenerated result leaves the prior CSV in place. Clear the target to an empty file when the current table is empty, and preserve current pending-state metadata. Do not interpret stale prior rows as newly calculated checks. The fix is in prepare_cases.write_csv; no actual incorrect sensitivity table was used in this task.
- Mesh-gate interpretation: a d/5-versusd/10 discrepancy motivates refinement. It must not forever reject a separately stable d/10-versusd/15 pair. Preserve coarse-grid discrepancies in the evidence table, and judge the production grid on the finer pair and other controls. This is a gate-logic correction found by inspection; actual fine-pair FE data was still pending at this entry.
- Actual full d/15 F06 solve resource observation:148427 elements and225966 nodes, solver RSS above10GiB and minimum availableRAM below0.6GiB on the16GiB machine. This is more informative than the earlier uncomputed-file size. The run was still in progress; final storage and the fine-grid resistance had not been established. A later resource policy must preserve full/half identity and consistent full-force/area conversion, if a half model is used.

### Live native convergence monitoring without a second Input client (2026-10-26)
- Symptom: during a long fine-grid solve the native project p3dat directory and phase_status.csv can remain unchanged for several minutes; a momentary process snapshot can also fall between two kernel processes. Neither observation alone proves a stalled calculation.
- Verified cause in this run: the active kernel wrote its current data.convd.rrN under the PLAXIS temporary calculation directory, and the completed phase log/results were copied into the project directory at the phase boundary. The task-owned kernel's open_files list identified the actual temporary log. Its step/attempt/iteration and converged SumMstage advanced while the saved project log was still old.
- Reusable method: identify only plasw3df.exe descendants of the already verified task Input process, read their open convergence-log paths, require the rrN suffix to match the controller's current phase, and parse a bounded tail. Record last converged SumMstage separately from the current attempt's interface error and step size. This is passive filesystem/process inspection, not an overlapping Input API request. Implementation: lia/outputs/live_solver_status.py.
- Isolated high interface errors at the start of a new attempt are not final nonconvergence if the subsequent iterations converge and stage progress advances. Likewise the native phrase Prescribed ultimate state reached means that the prescribed phase target was reached; it does not by itself establish the study's physical or candidate-platform limit.
- Full F06 d/15 had normally completed initial gravity, installation and cumulative0.001d,0.002d,0.005d,0.010d by this entry. Its0.020d phase was still in progress. No fine-grid candidate resistance or completed mesh-convergence claim is made here.


## 2026-10-26: unintended refinement fill and result-field domains

- Symptom (verified, supersedes earlier four-pilot eligibility): old `V10_pilot_m05` converged, but its native mesh contained 68 finite-displacement node records /29 unique coordinates above the required slope, up to1.7320508076m. Native Output at(-11.5,0,-0.2)m, whose requested ground is-1.443375673m, returned nonzero SigzzT=-21.86148843kPa. Native material was CLAY_TRESCA. This is actual unintended fill, not merely the geometric outline or display interpolation.
- Cause (verified from construction and active clusters): a full radius2d near-field refinement cylinder topped atZ=0 crosses the slope when crestXc=-1.5d (b/d=1). The builder assigned clay and activated every intersected soil cluster, including the portion above the requested ground. Equal material does not make this added geometry harmless.
- Remedy: retain this invalid native run and mark its plots as historical; exclude it independently of convergence from physical comparisons. Construct a refinement prism whose top polygon follows the exact piecewise terrain where the refinement region reaches the slope, using the installed documented `surface Points` then `extrude Surface (direction)` commands. Add a saved-native-node terrain/domain gate to all result selection. **At this entry the corrected prism source is written but its native build/recalculation has not yet run; do not call the geometry correction verified until actual native mesh checks pass.** Flat F06 and farther-crest V11/V12 native node checks returned no points above terrain.
- Evidence: task `C:/Users/xiong/Documents/Codex/2026-10-25/lia/outputs/terrain_node_audit.json`, per-run geometry_validity.json, `work/V10_old_terrain_stress_evidence.json`, terrain_validation.py and plaxis_build.py. Original V10 is preserved, replacement planned asV10_pilot_m05_geo_v2.

- Symptom (verified): Soil.X/Y/Z/ElementID stress-point arrays include rigid-interior points, but RelativeShearStress omits them. Old V10 geometry length69604, RelativeShearStress58248, difference11356. PlasticPoint and TotalDeviatoricStrain retain69604 values. The same domain mismatch exists in the other three pilots. A single NPZ can therefore hold incompatible arrays without NumPy raising an error.
- Cause (verified by native MaterialIndex and identifications): the difference equals the exact number of WEIGHTLESS_RIGID_INTERIOR material points; RelativeShearStress is not defined for that material. Do not silently zip shorter stress arrays to the leading geometry points, and do not fill undefined stress with zero.
- Remedy (saved-file repair verified on all four old pilots): retain untouched native field arrays in last_phase_soil_stresspoints_native.npz, obtain full native MaterialIndex, check exact field-domain lengths, and insert NaN at rigid-interior material positions to form common-coordinate arrays. Keep other native values unchanged. Raise on any unrecognized domain length. The current exporter calls soil_result_alignment.py. `soil_domain_alignment_audit.json` checks every saved field length and exact equality to preserved native values. This repair concerns raw soil fields; it does not validate the old V10 physical geometry or alter the separately integrated shaft/toe interfaces.


### Initial-stage terrain gate and startup evidence,2026-10-26
- Verified remedy timing: read native Soil.X/Y/Z/Ux/Uy/Uz from saved InitialPhase through a dedicated owned Output immediately after gravity, before installation/loading. Run the same piecewise-terrain/domain test as the final Output gate. A real saved good F06 passed; real old invalid V10 failed with the same68/29 above-terrain records/coordinates. Source/evidence: terrain_validation.check_initial and initial_terrain_gate_audit.json in the task above. This early gate catches the construction error without calculating the entire horizontal path; final checks still remain required.
- Startup symptom: an isolated second Input launched with documented AppServerPort/AppServerPassword arguments did not expose the requested port during this active-fine-run session. No native geometry was created in it; only that owned Input was terminated. The cause is unconfirmed; do not diagnose license failure or a global lock merely from this observation. Reuse the already authenticated primary Input serially after its calculation completes.
- Connection probe pitfall: constructing new_server can return a lazy proxy before a later named-object request fails with HTTPConnectionPool.../namedobjects...WinError10061. Include a real metadata/property request in a connection readiness probe, and use a bounded socket-readiness deadline before initializing a newly launched server. A proxy constructor alone is not proof of a usable session. The complete initial Output gate was actually exercised successfully; the isolated Input launch remains a recorded unsuccessful alternative.


### Independent soil-domain point verification,2026-10-26
- The material-masked RelativeShearStress alignment was independently checked at six actual native stress points in V11_pilot_m05, Phase_12. Use documented `addcurvepoint("Stress point", xyz)`; read exact selected X/Y/Z with getsingleresult(..., curvepoint, False), then read the saved final stress-point value using getcurveresultspath(cp,last,last,ResultTypes.Soil.RelativeShearStress). All six coordinates and values matched exactly (zero difference), including values near0.1,0.3,0.6,0.9, the first defined point and the last point. Evidence: soil_alignment_native_point_audit.json. This verifies native index order beyond a mere array-length equality check.
- Verified domain layouts: F06/V11/V12 rigid points precede clay points; oldV10 has56clay points, then11356rigid points, then clay. Therefore simply zipping the short soil stress array to the first N geometry records would be wrong. Preserve NativeMaterialIndex and NaN-fill at the exact omitted material positions.
- A second isolated Input startup with an explicit saved task seed project and a free port10010 also failed to open scripting within90s. Only its owned PID was closed; seed hash was unchanged. Cause remains unconfirmed. Primary Input continues normally; no claim that choosing a higher port or seed fixes this installation is supported.
- Offline control-script review found that exporting only two algorithm-test branches would make postprocess call the first nonzero-displacement branch its installation baseline. Include the actual zero-motion installation phase in those exports. The optional subspace benchmark source has this correction, but no accelerator benchmark has yet been run and no acceleration policy has been adopted.


### Fine-grid Output cost and endpoint sampling,2026-10-26
- Measured performance: fullF06d/15 had completed all13FEphases, but2024.1 rigid-body internal-step curves took104.171s for the7-step installation phase and247.981s for33metadata steps/17available pairs in the0.001d phase. This is actual Output cost, not solver nonconvergence. Native Intermediate result files remain present.
- Task policy changed explicitly: report F-u plots now use actual native prescribed-phase endpoints (all18rigid components retained), with marker points and simple connections. Continue exporting shaft/toe fields for every endpoint, actual final soil fields and local-axis/weight data. Retain native saved intermediate steps and earlier extracted curve rows. Do not describe an endpoint curve as a full internal-step history or infer unobserved interval extrema from it. Source: extraction_policy.json, plaxis_extract.py, prepare_origin_data.py and report text.
- Recovery verified: after confirming13saved CalculationResult=1 rows and no active FEkernel, close only the exact export controller and its owned Input-launched Output; the native input SHA256 before/after was identical. The old wrapper exit15 is an intentional exporter stop, not an FEfailure. Resume on the same saved model, reuse successful phases and complete raw endpoint extraction; no FE recalculation is needed for this reporting-policy change.
- Preserve provenance during resume: existing execution_sources files/manifest must remain intact. A changed controller capture goes into a dated resume subfolder with a separate manifest. Do not overwrite the code that performed the original calculation with later postprocessing source.
- Timing annotation correction: exercising an InitialPhase coordinate gate on an already completed saved model is a retrospective initial-state audit. It proves geometric discrimination, but does not mean that original loading was preceded by the new gate. Record performed_before_loading separately. The new builder hook can perform the gate before first installation/loading; that timing requires an actually new run. The old F06/V10 checks and the resumed full-fineF06 audit are marked retrospective.


### Terrain-prism remedy now natively verified,2026-10-26
- The previously unexecuted `surface(*polygon_points)` plus `extrude(surface,(0,24,0))` construction was actually run successfully for corrected V10. Native mesh18872tetrahedra/29632nodes. InitialPhase converged in8.211s; the gate ran BEFORE installation/loading, with188720finite node records, zero above terrain, zero outside domain, maximum terrain elevation excess6.4e-14m.
- Actual full-domain extents matched X[-142.454593550183,60],Y[-60,60],baseZ=-66m. All expected outer terrain corner/crest/toe vertices matched native nodes within1e-6m. This distinguishes a correct full domain from an accidentally truncated smaller model that merely has no above-ground nodes.
- Main preloading point(-10.5,0,-0.4330127)m above requested groundZ=-0.8660254 returned native SigzzT=nan. An additional saved-InitialPhase control query below ground atZ=-1.3660254 returned SigzzT=-6.876760572kPa. Thus the air result is not a globally unavailable stress field. Additional point verification was retrospective while loading continued; its timing is not mislabeled as preloading.
- At this entry corrected V10 was continuing its full horizontal path; do not call the whole validation matrix complete from the initial geometry proof. Evidence: per-run initial_mesh_geometry_validity.json and initial_domain_coverage.json, plus corrected_v10_air_soil_point_audit.json. Original invalid V10 remains preserved/excluded.
- Full original-algorithm F06d/15 finished13phases to0.10d and passed final actual-node motion/terrain and candidate-platform gates. Final Fx=-146407.915857498kN; last two total changes1.02279/0.848584%, primary mean profile changes1.00554/0.815335%; loaded X-equilibrium residual maximum0.00001862154%. All83737unique interior-node coordinates match the reference translation exactly. Native61740interface stresspoint bases were individually queried. Measured native solve peakRSS10.166GiB, completed model/export folder6.609GiB. The original export wrapper exit15 records intentional export restart, not FEfailure; resumed_export_success=true.

### New-phase numerical defaults and coupled accelerator settings,2026-10-26
- Symptom (native probe): setting `UseSubspaceAccelerator=True` immediately after `g.phase(parent)` raised `无法设置只读属性 UseSubspaceAccelerator`. A new phase had UseDefaultIterationParams=True, MaxLoadFractionPerStep=0.5 and ArcLengthControl=On, while the completed parent/control baseline had manual parameters,0.1 andOff. New phases do not inherit all numerical controls. Unlock with UseDefaultIterationParams=False and explicitly set/read back the intended settings. Both Pardiso and Picos then accepted the accelerator flag in a no-calculation probe.
- Second native coupling: enabling the accelerator automatically changed OverRelaxation from1.2 to1.0. Trying to restore1.2 raised `无法设置只读属性 OverRelaxation`. This option is forced/locked while the accelerator is enabled. An accelerator comparison must disclose this coupled algorithm change; it cannot claim that literally only one scalar input changed. Keep all other numerical and all physical settings equal and verify readbacks before calculation.
- Evidence: lia/outputs/models/F06_solver_subspace_probe/numerical_setting_lock_probe.json; v2 benchmark_failure.json and timestamped attempt_history preserve the two preflight errors. No FE calculation ran in those failed preflights; no performance gain or new calculation policy was established at this entry. The original completed F06 native input was reopened and its file hash checked unchanged after each attempt.
- Verified update to the terrain repair: corrected V10_pilot_m05_geo_v2 completed all13native phases to actual0.10d. Initial and final terrain gates, full-domain coverage and actual rigid motion all passed. Final Fx=-135900.618121192kN; last two total changes1.13984/0.954782%, primary mean profile changes0.905943/0.736100%; maximum loaded X-equilibrium residual0.00021095794%. This repairs representative geometry; the rest of the validation matrix is still required.

### Surface coverage supplements no-extra-soil tests,2026-10-26
- Inspection limitation: no above-terrain nodes plus correct outer vertices does not by itself exclude a surface inadvertently cut too low inside the domain. This was a verification gap, not evidence that a second geometry defect actually existed.
- Verified supplementary check: at interior X locations spanning every terrain segment and both sides of crest/toe, and at three transverse Y positions, query native InitialPhase Soil.SigzzT at requested ground plus/minus0.01d. Require undefined stress above and defined finite stress below. Retain both raw native responses and coordinates. The corrected V10 passed all21locations; full fine F06 passed all3locations. These checks were retrospective and labeled as such. Source/evidence: terrain_validation.surface_point_coverage and lia/outputs/surface_point_coverage_audit.json.
- The new initial-stage hook runs this complementary availability test along with every-node terrain/domain checks before future loading. Keep geometry-bound checks, full-domain vertex coverage and the point samples together; sampled availability alone is not proof of complete geometry.

### Branch phase ordering and native rigid-step text records,2026-10-26
- Native Output branch ordering pitfall: a completed optional two-branch test returned Output.Phases in dependency-tree order, placing Phase14 before Phase13 although the requested list was Phase1,Phase13,Phase14. Filtering by a name set preserved that unexpected order and made the final soil-node export/motion check refer to Phase13(0.005d), not Phase14(0.10d). The individually named endpoint forces/profiles remained correctly keyed. Correct extraction by mapping Output proxies by name and then walking the explicitly supplied ordered Input phase list. The ordinary single-chain models were unaffected. Never silently label a branch motion check as the other branch's check.
- Verified supplementary data source: this actual2024.1 installation writes self-labelled ASCII `data.rigid.rrN` with nRigidNodes, sequential iStep, RefNode, uTot(6), ForceA(6) andReac(6). It includes parent state iStep0 and rigid-step records whose full soil/interface fields may not be saved. The printed format is six significant figures, so preserve the exact original files and disclose that precision; do not replace precise API endpoints without saying so.
- `native_rigid_history.py` rejects unknown layouts, multiple bodies, incomplete/repeated components, noncontiguous steps, mismatches with native FirstStep/LastStep counts, and any component disagreement beyond print precision. Actual five-model verification passed all1080API endpoint components and2070finite priorAPI internal-step components. The parser keeps parent-state flags and source hashes. Current plots use all actual loading records and precise API phase endpoints at matching final rows; installation transients and repeated parent records are excluded explicitly. No interpolated FE values or model/solver changes are introduced.
- This actual native-file check supersedes the earlier endpoint-only plotting workaround for this task. All earlier API curve CSV rows and the endpoint-only policy snapshot remain preserved. Native text-layout compatibility with other versions or multi-body projects is unverified and must not be assumed. Evidence is the five raw/native_rigid_ascii_audit.json files and extraction_policy.json in lia.

### Actual third-grid repair and F06 fine-pair comparison,2026-10-26
- Full original-algorithm F06_mesh_m10 completed all13stages to actual0.10d, with55838tetrahedra/87133nodes. The formerly stalled0.02d stage converged in329.225s. Last two total-force changes1.016554/0.854803%, primary mean profile changes0.995411/0.820692%; loaded X-equilibrium residual maximum0.00002081303%. Actual interior-node motion and terrain gates passed. This is the third actual mesh level supporting the contact repair, not merely a successful small branch.
- Same-stage0.10d actual F06d/10 versusd/15: total force147667.055236136 to146407.915857498kN, change-0.85268808%; primary(0.1-4d) mean absolute profile change0.61661894%, maximum2.26520511%. The fine pair passes the declared5% total/mean target. F06d/5 versusd/10 total-3.83046584%, primarymean2.11048149%, maximum5.70449751%; retaining the maximum prevents misreading an average criterion as a pointwise guarantee. V10 fine-pair results were still pending at this entry; no common grid or half-model policy had been adopted.
- Evidence: per-run quality/motion/terrain files, native_rigid_ascii_audit.json and lia/outputs/comparisons/numerical_checks.csv. Newd/10 native rigid history independently passed all216API endpoint component checks. Future-half code is written but not natively exercised yet; full-model calculations continue serially.

### Recompute dependent geometry metadata after H overrides,2026-10-26
- Verified planning-table symptom: V10_height2(H=12m) andV10_height4(H=24m) retained the H=18m toe coordinate Xt=-40.17691453623979m. The generator copied the baseline case then overwrote H without updating Xt.
- Impact: completed H=3d models were unaffected. The native builder already independently recomputes actual_Xt=Xc-H/tan(theta), so this was a stale planned-coordinate field, not evidence of an incorrectly built height model. Both affected height runs were still unbuilt when discovered.
- Repair: back up the actual run matrix, update only those unbuilt rows, and recompute Xt andH_d after overrides in the case generator. Correct values are-29.784609690826528m(H=12) and-50.569219381653056m(H=24), with Xc=-9m andtheta30degrees. No completed native input was changed. Keep planned and actual coordinate fields consistent rather than relying solely on the builder's independent safeguard. Evidence: lia/outputs/height_geometry_metadata_repair.json and timestamped run_matrix_before_height_metadata_fix backups. Native H=2d/H=4d calculations were still pending at this entry.

### Distinguish uncomputed preflight from actual solver controls,2026-10-26
- Verified traceability issue: the builder's uncomputed phase_settings.txt contained its staging defaults(Initial/installation200stored steps, loading300), while the runtime solver correctly set20 andPardiso8 before actual calls. The completed native Phase12_state.txt confirms actual20storage. Preflight values must not be presented as post-override controls. The intended stricter length tolerance is also set at runtime, so the distinction matters for its later evidence.
- Remedy: retain the uncomputed snapshot with an explicit scope label, then read back solver enum, cores, compression, stored-step budget, tolerance, arc/subspace/default-iteration flags, update-mesh and reset flags immediately before each calculate call. Save timestamped immutable JSON plus native phase/Deform echoes in calculation_settings, and link the record from phase_status.csv. Append the Deform echo to calculated-state records. Assert the declared actual8cores/storage/compression/tolerance before starting calculation; this adds observations, not new numerical settings.
- First native use verified in V10_mesh_m15 InitialPhase: solver enum1(afterPardiso setter),8cores,20stored steps, compressionTrue, tolerance0.01, defaultsTrue, maxfraction0.5, arcOn, subspaceOff, updatedmesh/reset flagsFalse. Initial gravity naturally retains its own default arc settings; lateral phases have their separately recorded manual0.1/arcOff controls. Native length0.0001 readback had not yet been exercised at this entry. Earlier completed non-length runs used unchanged0.01 and retain their native project, preflight, storage-policy and calculated-state evidence.

### Apply actual readiness checks to native figure export,2026-10-26
- Source inspection confirmed the installed plxscripting HTTPConnection._wait_for_server polls for its timeout but does not raise solely when the deadline expires; new_server can therefore return a proxy while the new process is still unavailable. The already observed isolated-Input startup symptom above remains the native evidence. Do not regard proxy construction as completed connection.
- Reuse the verified terrain-check startup method in final figure export: own the exact Output PID, wait for that process and its actual TCP port, then query server_full_name through the API before opening the saved model. Record actual PID/port/version with each figure and close only that owned process. Use request_timeout=None for long model/result operations.
- Applied to lia/outputs/export_native_figures.py with a timestamped source backup. The amended source compiles; its final native figure execution is pending completion of the selected calculation matrix. No active solver or material/mesh setting changed.

### 单算例脚本与独立后台进程的区别（2026-10-27，代码静态分析）
- 现象：建模和计算分成 `--build`、`--calculate` 两个入口的脚本，建模结束会正常退出；计算入口即使自动循环各阶段，若它运行在受会话生命周期约束的进程中，后续阶段仍可能因控制进程终止而无法继续。
- 原因：PLAXIS 执行计算，Python 进程负责逐阶段发命令、保存和继续；脚本流程是否串联、进程如何启动，是两个不同问题。`request_timeout=None` 仅表示请求不设超时，不保证进程独立存活。
- 可复用做法：先在保存的工程上检查 `--calculate` 的活动工程、密码环境变量、异常停止和保存逻辑，再考虑使用独立进程及文件日志执行；需要无人值守从建模到计算时，应明确编排两步并保留必要的建模检查。进程中断时不得假定后续阶段已经完成，应检查原生工程与日志。此处根据脚本和运行说明静态归纳，独立启动方式及会话退出后的实际行为尚未在本次验证。


## 2026-10-31 电杆 M15 原生牵引力矩闭合（已验证 L10-B4）

- 现象：仅按界面节点显示的 Area 乘固定高斯权重积分，套筒/杆底面积约低估 3%，M15 力矩残差为 1.208%。原因：6 节点曲边三角形的中边节点不全在角点线性插值位置，显示 Area 对应角点三角面积。解决：以原生 6 个应力点坐标匹配 6 点三角高斯规则，使用全部 6 节点的二次形函数及各高斯点变 Jacobian，积分 traction 与 r×traction。L10-B4 精确 15‰ 双步插值：外力矩 26.8217624623，积分抵抗矩 26.8328344254 kN·m，残差 −0.04128%；没有把差额分摊到分项。脚本 D:/Pile/docs/paper_draft/full_zh/revision_20261031/plaxis/integrate_tractions.py。
- 现象：按 Automatic 表面坐标规则假定 e1=n×z、e2=n×e1 时，当前分解圆柱和自建翼板的局部位移不吻合，部分误差约为位移本身的 2 倍，牵引矩会发生严重符号错误。原因：实际分解曲面/自建面保留不同原生轴向，不可拿自动规则代替当前面的真实坐标。解决：每个 6 节点单元同时读取 Interface 的 Ux/Uy/Uz 与 U1/U2/U3，以右手正交变换 Q 满足 Uglobal Q=Ulocal，独立用相邻第二保存步验证；这只是坐标恒等映射，不是用整体平衡校准分项或材料参数。本例误差约 1e−14，必须同时核查面法向、行列式及坐标误差，不能仅用小拟合误差断言任意退化位移集合可唯一确定坐标。
- 现象/依据：PLAXIS 3D 界面节点 τ1 与应力点 τ1 符号相反（官方说明 https://bentleysystems.service-now.com/community?id=kb_article&sysparm_article=KB0108294），τ2 不翻转。解决：优先使用 stresspoint 的两向剪应力进行牵引积分，不混用节点 τ1 的符号。InterfaceEffectiveNormalStress 可取 stresspoint；InterfaceTotalNormalStress、PActive、PWater 的 stresspoint 在本版本报“命令不传送任何结果”。本干燥模型逐节点 total/effective 法向应力相等，才可用原生有效应力点值代替总应力；饱和情景不得沿用此替代。
- 现象：过滤 z≤−L 的界面时，会误删恰在 z=−L 的真实杆底。解决：只排除 min(z)<−L−tol 且 max(z)≤−L+tol 的人工延伸面；真实水平杆底需单独保留。半模型只把 Fx/Fz/My 乘 2，Fy/Mx/Mz 的镜像部分相消，不能把它们也宣称为全模型净量。原始未变形参考坐标下的对称自重弯矩为零，不能擅自混入变形坐标 P–Δ 项。
- 现象：Server.call_commands(*commands) 批读中含一个不支持的字段时，返回结果少于请求条数，并在首个失败命令处停止；直接断言条数相等会报 AssertionError。解决：保存成功前缀、记录该项原始反馈，再从已返回条数处继续读后缀；不把缺失字段默认为零。Output 开新进程只记录其 PID，随机进程内密码不写报告、不打印、不保存工程。



### 2026-10-31 同轮后处理补充：材料子域、塑性状态及连接探针

- 现象：对 Soil_1 读取 XYZ/U 得到73710个节点值，但 RelativeShearStress 只有67360个；拼列报 ValueError（all the input array dimensions ... must match exactly）。原因已由原生 MaterialIndex 核实：Soil_1 父实体组仍含6350个线弹性埋入杆体节点，强度动员比只对67360个Mohr–Coulomb土节点有效。解决：分别读取 node/stresspoint 的 MaterialIndex，按当前材料子域筛选坐标和通用位移/应变字段，再与只在该本构上定义的字段对齐；本例土MaterialIndex=0、杆体=3。不可凭数组长度截断、填零、把杆体位移与宿土混合后插值。去除跨材料混合后，原始逐单元重复节点仅为离线插值作坐标合并，完整原始列表仍归档。
- 现象：PlasticPoint 在 node 上报“命令不传送任何结果”，stresspoint可读；除0/1/2外还出现12，不能按材料模型IPL的0–6枚举猜为组合塑性。官方 PLAXIS 3D Reference Manual 表9–1（本次下载手册印刷页453，PDF第453页）明确：1或−1=MC accurate，2=Tension cut-off accurate，11或−11=MC inaccurate，12=Tension cut-off inaccurate。解决：码12单独显示为局部误差超容限的拉截断点，不静默丢弃、不改成“剪切+拉截断”。0°/45°两宿土各18点，所选剖面各11点；原始状态点、准确/不准确类别与塑性历史要区分。依据与截图：D:/Pile/docs/paper_draft/full_zh/revision_20261031/plaxis/official_plastic_status_source.json、official_plastic_status_table_page.png，源 https://files.seequent.com/PLAXIS/Manuals/PLAXIS_3D/English/PLAXIS_3D_2_Reference%20Manual.pdf 。
- 现象：独立Output尚未打开工程时，用 go.echo(go.GeneralInfo) 作为循环启动探针，最终误报 RuntimeError: Output unavailable。改为真实服务器请求 so.connection.request_server_name() 后再 so.open(project)，补提成功。原因推断：GeneralInfo对象受当前工程是否已建立影响；本次原循环捕获了全部异常，未逐次保存具体内部异常，故对象可见性原因不能视为逐条实测证明。可复用做法：连接存活探针只检查实际TCP/API服务，不依赖未打开工程的模型对象；启动超时时记录非敏感异常类型，而不是统一抹成服务未启动。只关闭本脚本明确拥有的Output PID。
- 同轮可复用审计：旧0.05m分箱法向抗力轮廓的旧节点文件与新提同一步节点文件，复现的旧积分完全相同（B0 10.7021639478；B4套筒7.8179891940、翼板7.4445839146 kN·m），但原生应力点曲面积分分别为9.4708652082、7.2254043582、6.7290970671。不要把节点外推/深度分箱近似积分与六高斯点曲面积分混作同一口径，更不能将二者差额命名为新的承载机制。脚本 audit_old_profiles.py，审计 old_profile_integration_comparison.json。



### 2026-10-31 翼板在加载平面内的真实几何投影（离线验证）

- 现象：新增0°/45°云图只画出杆体/套筒，缺少原稿所用的翼板黑轮廓；直接将0°轮廓复制给45°会把后者画宽。原因：场图是固定加载方向的y′=0.02 m剖面，而原稿翼板轮廓实际为其向加载方向竖直平面的投影，不等于该剖面与所有翼板的交线。
- 已验证做法：直接使用先前提取并绑定原生模型、阶段和保存步的Interface.X/Y/Z节点。按实际几何识别翼板，排除杆底及结构趾部以下人工界面延伸面，对同一物理翼板两侧接触面的重复几何去重，再向加载方向的x′–z平面作正投影。两个保存工程均沿原生+x加载，45°工程转动的是翼板几何，因此本轮x′=原生x；把工程旋至固定翼板参考坐标后，这一加载平面关系不变。不能未经核对就用原生全局斜45°面替代加载面。
- 本例D=0.35 m、L=1.0 m、B=0.4 m的真实节点验证结果：0°投影外缘x′=±0.575 m，总投影宽1.150 m；45°为x′=±0.406586 m，总宽0.813172 m。45°数值保留原生建模坐标舍入，不用理论值覆盖节点值。关于y=0的半模型镜像不改变x′–z投影。上述尺寸仅属于这两例，不能用作其他模型的默认值。
- 绘图边界：只叠加不填色的黑色投影线，隐藏被不透明杆体遮挡的线段；不把翼板投影区域内的土体场值抹白、重涂或伪装成翼板内部结果。图注明确“黑线含翼板在加载方向竖直平面内的投影轮廓”，必要时补充“非y′=0.02 m剖面与全部翼板的实际交线”。
- 验证及复现：离线重绘的新旧字段/选步/色标/杆体掩膜/全部塑性状态点审计相同，旧PNG/PDF四个文件的SHA-256未变；本轮没有连接PLAXIS、修改模型或重新求解。脚本与原生节点几何证据为D:/Pile/docs/paper_draft/full_zh/layout_revision_20261031/figures/projected_fin_figures.py及projected_fin_geometry_evidence.json，说明见projected_fin_outline_note.md；新图独立输出Fig11_direction_fields和Fig12_relative_to_foundation，原图保留。


## 2026-11-05 教程逐页知识增补与检索入口

在保留以上全部已有内容的基础上，新增《PLAXIS 3D基础教程》的逐页知识库。处理范围为378页扫描文件的正文、图片、表格、公式、18章、安装附录、参考文献及末尾彩插；完整文字层和扫描原图留在用户本地，仓库收录独立提炼的操作知识与页码记录。

- **知识入口**：[references/book/index.md](references/book/index.md)。按当前任务选读对应模块，不必一次加载全部知识库。
- **版本与勘误**：[references/book/compatibility-and-errata.md](references/book/compatibility-and-errata.md)。书版为PLAXIS 3D 2013背景；旧正文与后来实测有冲突时，检查版本、适用模型及证据范围，不将历史限制当作当前普遍结论。
- **完整工况表与脚本化检查**：[references/book/automation-review-workflow.md](references/book/automation-review-workflow.md)。参数标记confirmed/source-defined-but-not-confirmed/unset-or-not-read-back；参数确认后先验证相关小模型正常收敛，再展开正式工况脚本。Output默认由脚本打开和提取。
- **逐页追溯**：[references/book/page-ledger.jsonl](references/book/page-ledger.jsonl) 记录每页主题、图表、知识及未决项；[source-manifest.json](references/book/source-manifest.json) 记录来源指纹与覆盖。快速检索：`python scripts/book_lookup.py "吸力"` 或 `python scripts/book_lookup.py --page 101 --json`。
- 教学案例给出的几何/材料/荷载/水位/阶段数值仅属于各例题，不是其他工程默认输入。书中半径/直径、材料各向异性、个别公式与数值前后矛盾均保留定位，复现前确认，不能通过试算替用户选择参数。

本轮复核与避坑补充：

1. **剪切模量表式疑误**：原书PDF101–102表6-2/6-3扫描分母印为`1(1+ν)`；2024.1材料手册第18页Eq31给出`G=E/[2(1+ν)]`。按后者计算，保留原书疑误说明，不照录错误公式。
2. **连接对象不等于连接成功**：本轮出现端口10000同时由PLAXIS通配地址与另一程序IPv4回环监听，实际请求报`RemoteDisconnected`，IPv6探针报`WinError 10013`。具体失败原因未完全验证；先检查监听地址/PID，再用真实服务器请求确认身份。未取得API回读，不得标为已连接或已验证模型，也不关闭不属于本任务的进程。
3. **解释器兼容性再次确认**：系统Python3.14导入旧wrapper报`ModuleNotFoundError: No module named 'distutils'`；本机配套Python3.8.18导入成功。复用原附录解释器经验，不将导入成功或脚本语法通过当作模型运行证明。

新增知识未自动执行书中案例求解；“书中定义”“官方文档核对”“实际API回读”“正常收敛验证”四种证据分别标明。
