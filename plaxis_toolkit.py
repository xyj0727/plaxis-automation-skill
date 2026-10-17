#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PLAXIS 3D 自动化建模工具包
==========================
通过 plxscripting Remote Scripting API 连接并操控 PLAXIS 3D Input。

用法:
    from plaxis_toolkit import PlaxisSession

    session = PlaxisSession(password="123456")
    session.connect()           # 连接运行中的 PLAXIS，或启动新的
    session.open_project(path)  # 打开项目

    # 建模
    mat = session.create_material("地基土", "Mohr-Coulomb", 18.5, 20.0, 2e4, 0.33, 0.001)
    session.add_boreholes([0.0, 2.0, 5.0, 10.5, 12.0])
    session.add_soil_layer(5.0, mat)
    session.set_zone_level("Borehole_1", "Soillayer_0", "Top", -3.0)
    session.save()
"""

import subprocess
import time
import os

PLAXIS_INPUT_PATH = r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DInput.exe"


class PlaxisSession:
    """PLAXIS 3D Input 远程脚本会话。"""

    def __init__(self, password="123456", port=10000,
                 plaxis_path=None, auto_launch=True):
        self.password = password
        self.port = port
        self.plaxis_path = plaxis_path or PLAXIS_INPUT_PATH
        self.auto_launch = auto_launch
        self.s_i = None
        self.g_i = None
        self._process = None

    # ---- 连接 ----

    def connect(self, timeout=60):
        """连接 PLAXIS Input。如果未运行则启动。"""
        from plxscripting.easy import new_server

        # 尝试连接已运行的实例
        for i in range(5):
            try:
                self.s_i, self.g_i = new_server(
                    "localhost", self.port, password=self.password)
                self.s_i.major_version  # 验证连接
                print(f"[OK] 已连接 PLAXIS {self.s_i.major_version}.{self.s_i.minor_version}")
                return self
            except Exception:
                time.sleep(2)

        # 启动新实例
        if self.auto_launch:
            print("启动 PLAXIS 3D Input...")
            self._process = subprocess.Popen([
                self.plaxis_path,
                f"--AppServerPort={self.port}",
                f"--AppServerPassword={self.password}"
            ])
            for i in range(timeout // 3):
                time.sleep(3)
                try:
                    self.s_i, self.g_i = new_server(
                        "localhost", self.port, password=self.password)
                    self.s_i.major_version
                    print(f"[OK] PLAXIS 已启动并连接 ({i*3}s)")
                    return self
                except Exception:
                    if i % 5 == 4:
                        print(f"  等待中... ({i*3}s)")
            raise TimeoutError("PLAXIS 启动超时")

        raise ConnectionError("无法连接 PLAXIS")

    def open_project(self, path):
        """打开项目并切换到土壤模式。"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"项目文件不存在: {path}")
        self.s_i.open(path)
        self.g_i.gotosoil()
        print(f"[OK] 项目已打开, {len(self.g_i.Soillayers)}层, "
              f"{len(self.g_i.Boreholes)}钻孔, {len(self.g_i.Materials)}材料")
        return self

    def new_project(self, title="新项目", length_x=12, length_y=8):
        """创建新项目。"""
        self.s_i.new()
        self.g_i.Project.Title = title
        self.g_i.SoilContour.initializerectangular(0, 0, length_x, length_y)
        self.g_i.gotosoil()
        print(f"[OK] 新项目已创建: {title}")
        return self

    # ---- 材料 ----

    def create_material(self, name, soil_model, gamma_unsat, gamma_sat,
                        Eref, nu, perm_h, perm_v=None,
                        cRef=None, phi=None, psi=None):
        """创建土壤材料。返回材料对象。"""
        mat = self.g_i.soilmat()
        if perm_v is None:
            perm_v = perm_h
        props = [
            "Name", name, "SoilModel", soil_model,
            "gammaUnsat", gamma_unsat, "gammaSat", gamma_sat,
            "Eref", Eref, "nu", nu,
            "PermHorizontalPrimary", perm_h,
            "PermHorizontalSecondary", perm_h,
            "PermVertical", perm_v,
        ]
        if cRef is not None:
            props += ["cRef", cRef]
        if phi is not None:
            props += ["phi", phi]
        if psi is not None:
            props += ["psi", psi]
        mat.setproperties(*props)
        return mat

    # ---- 钻孔 ----

    def add_boreholes(self, x_positions, y=4.0):
        """沿X方向批量创建钻孔。返回钻孔列表。"""
        bhs = []
        for x in x_positions:
            bh = self.g_i.borehole(x, y)
            bhs.append(bh)
        return bhs

    # ---- 土层 ----

    def add_soil_layer(self, thickness, material=None):
        """添加一个土层。可选择分配材料。"""
        self.g_i.soillayer(thickness)
        if material is not None:
            self.g_i.Soillayers[-1].Soil.Material = material
        return self.g_i.Soillayers[-1]

    def add_soil_layers(self, layers):
        """批量添加土层。layers = [(厚度, 材料), ...]"""
        for thk, mat in layers:
            self.add_soil_layer(thk, mat)

    # ---- 非水平地层 ----

    def set_zone_level(self, borehole_name, soillayer_name, top_or_bottom, value):
        """设置特定钻孔处特定土层的顶/底标高。

        borehole_name: "Borehole_1", "Borehole_2", ...
        soillayer_name: "Soillayer_0", "Soillayer_1", ...
        top_or_bottom: "Top" 或 "Bottom"
        value: 标高数值 (m)
        """
        cmd = f"setsoillayerlevel {borehole_name} {soillayer_name} {top_or_bottom} {value}"
        self.g_i.commands(cmd)

    def set_zone_levels_batch(self, commands):
        """批量设置Zone标高。commands = [(bh, sl, tb, val), ...]"""
        for bh, sl, tb, val in commands:
            self.set_zone_level(bh, sl, tb, val)

    # ---- 边界条件 ----

    def set_deformation_bc(self, xmin="Normally fixed", xmax="Normally fixed",
                           ymin="Normally fixed", ymax="Normally fixed",
                           zmin="Fully fixed", zmax="Free"):
        """设置变形边界条件。"""
        d = self.g_i.Deformations
        d.BoundaryXMin = xmin
        d.BoundaryXMax = xmax
        d.BoundaryYMin = ymin
        d.BoundaryYMax = ymax
        d.BoundaryZMin = zmin
        d.BoundaryZMax = zmax

    def set_flow_bc(self, xmin="Closed", xmax="Open",
                    ymin="Open", ymax="Open", zmin="Closed"):
        """设置渗流边界条件。"""
        gwf = self.g_i.GroundwaterFlow
        gwf.BoundaryXMin = xmin
        gwf.BoundaryXMax = xmax
        gwf.BoundaryYMin = ymin
        gwf.BoundaryYMax = ymax
        gwf.BoundaryZMin = zmin

    def set_rainfall(self, intensity=0.01):
        """设置降雨入渗强度 (m/day)。"""
        self.g_i.Precipitation.TimeDependency = "Constant"
        self.g_i.Precipitation.Discharge = intensity

    # ---- 保存 ----

    def save(self):
        """保存项目。"""
        self.g_i.save()
        print("[OK] 已保存")

    # ---- 诊断 ----

    def info(self):
        """打印模型摘要。"""
        print(f"PLAXIS {self.s_i.major_version}.{self.s_i.minor_version}")
        print(f"项目: {self.g_i.Project.Title}")
        print(f"SoilContour: {self.g_i.SoilContour}")
        print(f"Soillayers: {len(self.g_i.Soillayers)}")
        print(f"Boreholes: {len(self.g_i.Boreholes)}")
        print(f"Materials: {len(self.g_i.Materials)}")

    def list_layers(self):
        """列出所有土层及其Zone标高。"""
        for i, sl in enumerate(self.g_i.Soillayers):
            mat_name = sl.Soil.Material.Name if hasattr(sl.Soil, 'Material') else "?"
            print(f"Layer {i}: {mat_name}")
            for j, z in enumerate(sl.Zones):
                print(f"  Zone {j}: Top={z.Top}, Bottom={z.Bottom}, Thk={z.Thickness}")

    def raw_command(self, cmd):
        """执行原始 PLAXIS 命令。"""
        return self.g_i.commands(cmd)

    # ---- 清理 ----

    def close(self):
        """关闭连接。"""
        if self._process:
            self._process.terminate()
            self._process = None
        print("[OK] 会话已关闭")


# ============================================================
# 快捷函数：从文档参数直接构建防排水模型
# ============================================================

def build_drainage_model(password="123456", project_path=None):
    """根据《防排水模拟》文档快速构建泡沫轻质土防排水模型。

    参数:
        password: PLAXIS Remote Scripting 密码
        project_path: 项目文件路径（None则创建新项目）
    """
    session = PlaxisSession(password=password)
    session.connect()

    if project_path and os.path.exists(project_path):
        session.open_project(project_path)
    else:
        session.new_project("泡沫轻质土防排水模拟", 12, 8)

    # 参数
    MLX, MLY = 12.0, 8.0
    FOAM_H = 4.0
    OLD_FILL_H = 3.0
    CROSS_SLOPE = 0.02

    # 材料
    M = {}
    M['fdn']  = session.create_material('地基土', 'Mohr-Coulomb', 18.5, 20.0, 2e4, 0.33, 0.001, cRef=10, phi=25)
    M['old']  = session.create_material('老路基填土', 'Mohr-Coulomb', 19.0, 20.5, 5e4, 0.30, 0.05, cRef=15, phi=30)
    M['sand'] = session.create_material('砂垫层', 'Mohr-Coulomb', 18.0, 20.0, 3e4, 0.30, 10.0, cRef=1, phi=32, psi=2)
    M['foam'] = session.create_material('泡沫轻质土', 'Mohr-Coulomb', 6.0, 8.0, 5e5, 0.28, 1e-8, cRef=200, phi=25)
    M['c30']  = session.create_material('C30水泥板压顶', 'Linear elastic', 25.0, 25.0, 3e7, 0.20, 1e-12)
    M['sub']  = session.create_material('级配碎石底基层', 'Mohr-Coulomb', 22.0, 23.0, 3e5, 0.30, 1.0, cRef=5, phi=40, psi=10)
    M['base'] = session.create_material('水泥稳定碎石基层', 'Mohr-Coulomb', 23.0, 23.5, 1.5e6, 0.25, 0.01, cRef=300, phi=38, psi=8)
    M['asp']  = session.create_material('沥青面层', 'Linear elastic', 24.0, 24.0, 1.2e6, 0.35, 1e-9)

    # 钻孔
    bh_x = [0.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.5, 11.5, 12.0]
    session.add_boreholes(bh_x)

    # 土层
    session.add_soil_layers([
        (5.0, M['fdn']), (OLD_FILL_H, M['old']), (0.15, M['sand']),
        (FOAM_H, M['foam']), (0.10, M['c30']), (0.20, M['sub']),
        (0.20, M['base']), (0.18, M['asp']),
    ])

    # 非水平地层：各区标高
    z_old_top, z_old_bottom = 0.0, -OLD_FILL_H
    z_step_bottom = -1.5
    z_sand_top = z_step_bottom + 0.15
    z_foam_top = z_sand_top + FOAM_H
    z_asp_top_0 = z_foam_top + 0.68
    FDN_BOTTOM = -5.0

    def road_z(x):
        if x <= 11.0:
            return z_asp_top_0 - x * CROSS_SLOPE
        else:
            return z_asp_top_0 - 11.0 * CROSS_SLOPE - (x - 11.0) * 0.04

    bh_names = [f"Borehole_{i+1}" for i in range(len(bh_x))]

    for zi, (bh_name, x) in enumerate(zip(bh_names, bh_x)):
        rz = road_z(x)

        if x <= 2.0:
            cmds = [
                (bh_name, "Soillayer_0", "Top", z_old_bottom),
                (bh_name, "Soillayer_0", "Bottom", FDN_BOTTOM),
                (bh_name, "Soillayer_1", "Top", z_old_top),
                (bh_name, "Soillayer_1", "Bottom", z_old_bottom),
                (bh_name, "Soillayer_2", "Top", z_old_top), (bh_name, "Soillayer_2", "Bottom", z_old_top),
                (bh_name, "Soillayer_3", "Top", z_old_top), (bh_name, "Soillayer_3", "Bottom", z_old_top),
            ]
        elif x <= 5.0:
            step_idx = int(x - 2.0)
            st = z_old_top - (step_idx - 1) * 0.5
            sb = st - 0.5
            cmds = [
                (bh_name, "Soillayer_0", "Top", sb), (bh_name, "Soillayer_0", "Bottom", FDN_BOTTOM),
                (bh_name, "Soillayer_1", "Top", st), (bh_name, "Soillayer_1", "Bottom", sb),
                (bh_name, "Soillayer_2", "Top", st), (bh_name, "Soillayer_2", "Bottom", st),
                (bh_name, "Soillayer_3", "Top", st), (bh_name, "Soillayer_3", "Bottom", st),
            ]
        else:
            cmds = [
                (bh_name, "Soillayer_0", "Top", z_step_bottom), (bh_name, "Soillayer_0", "Bottom", FDN_BOTTOM),
                (bh_name, "Soillayer_1", "Top", z_step_bottom), (bh_name, "Soillayer_1", "Bottom", z_step_bottom),
                (bh_name, "Soillayer_2", "Top", z_sand_top), (bh_name, "Soillayer_2", "Bottom", z_step_bottom),
                (bh_name, "Soillayer_3", "Top", z_foam_top), (bh_name, "Soillayer_3", "Bottom", z_sand_top),
            ]

        c30_bot = rz - 0.68
        sub_bot = c30_bot + 0.10
        base_bot = sub_bot + 0.20
        asp_bot = base_bot + 0.20
        cmds += [
            (bh_name, "Soillayer_4", "Top", sub_bot), (bh_name, "Soillayer_4", "Bottom", c30_bot),
            (bh_name, "Soillayer_5", "Top", base_bot), (bh_name, "Soillayer_5", "Bottom", sub_bot),
            (bh_name, "Soillayer_6", "Top", asp_bot), (bh_name, "Soillayer_6", "Bottom", base_bot),
            (bh_name, "Soillayer_7", "Top", rz), (bh_name, "Soillayer_7", "Bottom", asp_bot),
        ]
        session.set_zone_levels_batch(cmds)

    # 边界条件
    session.set_deformation_bc()
    session.set_flow_bc()
    session.set_rainfall()

    # 保存
    session.save()

    print("防排水模型构建完成!")
    return session


if __name__ == "__main__":
    build_drainage_model()
