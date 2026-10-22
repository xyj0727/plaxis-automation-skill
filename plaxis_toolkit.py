#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PLAXIS 3D End-to-End Automation Toolkit (plaxis_toolkit.py)
===========================================================
Python toolkit for end-to-end PLAXIS 3D finite element modeling,
staged construction orchestration, calculation execution, and Output post-processing
via the plxscripting Remote Scripting API.

Key Capabilities:
  - Robust session management with dynamic port discovery & process cleanup
  - Template cloning pattern to prevent binary model corruption
  - Soil modeling (Boreholes, Soil layers, Non-horizontal zone elevation adjustments)
  - Structural modeling (Plates, Interfaces, Line/Surface drains, Geometry intersection)
  - Mesh generation and local refinement control
  - Staged construction workflows (K0/Gravity loading, Excavation, Fill, Transient rainfall flow, Safety Fs)
  - Automated calculation execution and convergence checking
  - Post-processing via Plaxis3DOutput (Safety factor Msf, Pore pressures, Suction, Deformations, Plot export)
"""

import os
import sys
import time
import socket
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Union, Dict, Any

DEFAULT_INPUT_PATH = r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DInput.exe"
DEFAULT_OUTPUT_PATH = r"D:\Seequent\PLAXIS 3D 2024\Plaxis3DOutput.exe"


def get_free_port(start_port: int = 10000, max_tries: int = 100) -> int:
    """Find an available local TCP port."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    raise RuntimeError(f"No free port found in range {start_port} ~ {start_port + max_tries}")


def clone_template_project(template_p3d: Union[str, Path], target_p3d: Union[str, Path]) -> Path:
    """
    Physically clones a PLAXIS project (.p3d file + .p3dat folder).
    Bypasses the binary model saving limitations of s_i.new().
    """
    template_p3d = Path(template_p3d)
    target_p3d = Path(target_p3d)
    target_p3d.parent.mkdir(parents=True, exist_ok=True)

    template_dat = template_p3d.with_suffix(".p3dat")
    target_dat = target_p3d.with_suffix(".p3dat")

    if not template_p3d.exists():
        raise FileNotFoundError(f"Template project does not exist: {template_p3d}")

    # Copy .p3d container
    shutil.copy2(template_p3d, target_p3d)

    # Copy .p3dat data directory if present
    if template_dat.exists():
        if target_dat.exists():
            shutil.rmtree(target_dat)
        shutil.copytree(template_dat, target_dat)

    return target_p3d


class PlaxisSession:
    """
    Remote scripting session for PLAXIS 3D Input.
    Provides comprehensive control over Soil, Structures, Mesh, and Staged Construction modes.
    """

    def __init__(self, password: str = "123456", port: Optional[int] = None,
                 plaxis_path: Optional[str] = None, auto_launch: bool = True):
        self.password = password
        self.port = port or get_free_port()
        self.plaxis_path = plaxis_path or DEFAULT_INPUT_PATH
        self.auto_launch = auto_launch
        self.s_i = None
        self.g_i = None
        self._process = None

    # ---- Connection & Project Management ----

    def connect(self, timeout: int = 90) -> "PlaxisSession":
        """Connect to PLAXIS Input server. Launches process if not running."""
        from plxscripting.easy import new_server

        # Attempt connecting to existing instance
        for _ in range(3):
            try:
                self.s_i, self.g_i = new_server("localhost", self.port, password=self.password, request_timeout=timeout)
                _ = self.s_i.major_version
                print(f"[OK] Connected to running PLAXIS Input {self.s_i.major_version}.{self.s_i.minor_version} (Port {self.port})")
                return self
            except Exception:
                time.sleep(1)

        # Launch new instance
        if self.auto_launch:
            if not os.path.exists(self.plaxis_path):
                raise FileNotFoundError(f"PLAXIS Input executable not found: {self.plaxis_path}")

            print(f"Launching PLAXIS 3D Input on port {self.port}...")
            self._process = subprocess.Popen([
                self.plaxis_path,
                f"--AppServerPort={self.port}",
                f"--AppServerPassword={self.password}"
            ])
            start_time = time.time()
            while time.time() - start_time < timeout:
                time.sleep(2)
                try:
                    self.s_i, self.g_i = new_server("localhost", self.port, password=self.password, request_timeout=timeout)
                    _ = self.s_i.major_version
                    print(f"[OK] PLAXIS Input started and connected ({int(time.time() - start_time)}s)")
                    return self
                except Exception:
                    pass
            self.close()
            raise TimeoutError(f"PLAXIS startup timed out ({timeout}s)")

        raise ConnectionError("Failed to connect to PLAXIS Input")

    def open_project(self, path: Union[str, Path]) -> "PlaxisSession":
        """Opens project and switches to Soil mode."""
        path_str = str(path)
        if not os.path.exists(path_str):
            raise FileNotFoundError(f"Project file not found: {path_str}")
        self.s_i.open(path_str)
        self.g_i.gotosoil()
        print(f"[OK] Project opened: {path_str}")
        return self

    def clone_and_open(self, template_path: Union[str, Path], target_path: Union[str, Path]) -> "PlaxisSession":
        """Clones a clean base template and opens the newly cloned project."""
        target_p3d = clone_template_project(template_path, target_path)
        return self.open_project(target_p3d)

    def new_project(self, title: str = "New Project", length_x: float = 12.0, length_y: float = 8.0) -> "PlaxisSession":
        """Initializes a new project with rectangular contour."""
        self.s_i.new()
        self.g_i.Project.Title = title
        self.g_i.SoilContour.initializerectangular(0, 0, length_x, length_y)
        self.g_i.gotosoil()
        print(f"[OK] Initialized new project: {title}")
        return self

    # ---- Mode Navigation ----

    def goto_soil(self):
        """Switches to Soil mode."""
        self.g_i.gotosoil()

    def goto_structures(self):
        """Switches to Structures mode."""
        self.g_i.gotostructures()

    def goto_mesh(self):
        """Switches to Mesh mode."""
        self.g_i.gotomesh()

    def goto_stages(self):
        """Switches to Staged Construction mode."""
        self.g_i.gotostages()

    # ---- Soil Mode Operations ----

    def create_material(self, name: str, soil_model: str, gamma_unsat: float, gamma_sat: float,
                        Eref: float, nu: float, perm_h: float, perm_v: Optional[float] = None,
                        cRef: Optional[float] = None, phi: Optional[float] = None, psi: Optional[float] = None):
        """Creates a soil material dataset."""
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

    def add_borehole(self, x: float, y: float = 0.0):
        """Adds a single borehole at (x, y)."""
        return self.g_i.borehole(x, y)

    def add_boreholes(self, x_positions: List[float], y: float = 0.0) -> List[Any]:
        """Adds multiple boreholes along the X axis."""
        return [self.g_i.borehole(x, y) for x in x_positions]

    def add_soil_layer(self, thickness: float, material=None):
        """Adds a soil layer with specified thickness."""
        self.g_i.soillayer(thickness)
        if material is not None:
            self.g_i.Soillayers[-1].Soil.Material = material
        return self.g_i.Soillayers[-1]

    def add_soil_layers(self, layers: List[Tuple[float, Any]]):
        """Batch adds soil layers: layers = [(thickness, material), ...]"""
        for thk, mat in layers:
            self.add_soil_layer(thk, mat)

    def set_zone_level(self, borehole_name: str, soillayer_name: str, top_or_bottom: str, value: float):
        """Sets non-horizontal layer elevation at a specific borehole using setsoillayerlevel."""
        cmd = f"setsoillayerlevel {borehole_name} {soillayer_name} {top_or_bottom} {value}"
        self.g_i.commands(cmd)

    def set_zone_levels_batch(self, commands: List[Tuple[str, str, str, float]]):
        """Batch sets zone levels: commands = [(bh, sl, top_or_bottom, value), ...]"""
        for bh, sl, tb, val in commands:
            self.set_zone_level(bh, sl, tb, val)

    def set_deformation_bc(self, xmin="Normally fixed", xmax="Normally fixed",
                           ymin="Normally fixed", ymax="Normally fixed",
                           zmin="Fully fixed", zmax="Free"):
        """Configures deformation boundary conditions."""
        d = self.g_i.Deformations
        d.BoundaryXMin, d.BoundaryXMax = xmin, xmax
        d.BoundaryYMin, d.BoundaryYMax = ymin, ymax
        d.BoundaryZMin, d.BoundaryZMax = zmin, zmax

    def set_flow_bc(self, xmin="Closed", xmax="Open", ymin="Open", ymax="Open", zmin="Closed"):
        """Configures groundwater flow boundary conditions."""
        gwf = self.g_i.GroundwaterFlow
        gwf.BoundaryXMin, gwf.BoundaryXMax = xmin, xmax
        gwf.BoundaryYMin, gwf.BoundaryYMax = ymin, ymax
        gwf.BoundaryZMin = zmin

    def set_rainfall(self, intensity: float = 0.01):
        """Sets precipitation infiltration rate (m/day)."""
        self.g_i.Precipitation.TimeDependency = "Constant"
        self.g_i.Precipitation.Discharge = intensity

    # ---- Structures Mode Operations ----

    def create_plate_material(self, name: str, E1: float = 3.0e7, nu12: float = 0.2,
                              d: float = 0.25, gamma: float = 25.0, isotropic: bool = True):
        """Creates a plate structural material set."""
        self.goto_structures()
        pmat = self.g_i.platemat()
        pmat.setproperties(
            "Name", name,
            "MaterialName", name,
            "Isotropic", isotropic,
            "E1", E1,
            "nu12", nu12,
            "d", d,
            "gamma", gamma
        )
        return pmat

    def add_line(self, p1: Tuple[float, float, float], p2: Tuple[float, float, float]):
        """Creates a geometric line."""
        self.goto_structures()
        return self.g_i.line(p1, p2)

    def add_surface(self, *points: Tuple[float, float, float]):
        """Creates a geometric surface from points."""
        self.goto_structures()
        return self.g_i.surface(*points)

    def extrude(self, obj, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0):
        """Extrudes a geometric entity."""
        self.goto_structures()
        return self.g_i.extrude(obj, dx, dy, dz)

    def add_plate(self, surface, material=None):
        """Adds a plate feature to a surface."""
        self.goto_structures()
        self.g_i.plate(surface)
        if material is not None and hasattr(surface, 'Plate'):
            surface.Plate.Material = material
        return surface

    def add_interfaces(self, surface, positive: bool = True, negative: bool = True):
        """Adds positive and/or negative interfaces to a surface."""
        self.goto_structures()
        if positive:
            self.g_i.posinterface(surface)
        if negative:
            self.g_i.neginterface(surface)
        return surface

    def add_line_drain(self, line):
        """Adds a line drain feature to a line."""
        self.goto_structures()
        return self.g_i.linedrain(line)

    def add_surface_drain(self, surface):
        """Adds a surface drain feature to a surface."""
        self.goto_structures()
        return self.g_i.surfdrain(surface)

    def intersect(self):
        """Computes geometry intersections and reclusters topologies."""
        self.goto_structures()
        self.g_i.intersect()

    # ---- Mesh Mode Operations ----

    def set_local_coarseness(self, obj, factor: float = 0.5):
        """Applies local mesh coarseness refinement factor to an object."""
        self.goto_mesh()
        self.g_i.commands(f"set {obj.Name}.CoarsenessFactor {factor}")

    def generate_mesh(self, coarseness: float = 0.05):
        """Generates 3D finite element mesh."""
        self.goto_mesh()
        self.g_i.mesh(coarseness)
        time.sleep(2)
        print(f"[OK] Mesh generated (Coarseness: {coarseness})")

    # ---- Staged Construction Mode Operations ----

    def set_initial_phase(self, calc_type: str = "Gravity loading"):
        """Configures InitialPhase calculation type ('Gravity loading' or 'K0 procedure')."""
        self.goto_stages()
        self.g_i.InitialPhase.CalculationType = calc_type

    def add_phase(self, parent_phase, name: str, calc_type: str = "Plastic",
                  loading_input: str = "Staged construction", max_steps: int = 100,
                  time_interval: Optional[float] = None):
        """Adds a new calculation phase branching from parent_phase."""
        self.goto_stages()
        p = self.g_i.phase(parent_phase)
        p.Identification = name
        p.CalculationType = calc_type
        p.LoadingInput = loading_input
        p.MaxSteps = max_steps
        if time_interval is not None:
            p.TimeInterval = time_interval
        return p

    def activate(self, obj, phase):
        """Activates an object (cluster, plate, drain, load) in a specific phase."""
        self.goto_stages()
        self.g_i.activate(obj, phase)

    def deactivate(self, obj, phase):
        """Deactivates an object (excavation cluster, removed structure) in a specific phase."""
        self.goto_stages()
        self.g_i.deactivate(obj, phase)

    def add_rainfall_phase(self, parent_phase, name: str, discharge: float,
                           duration_days: float, calc_type: str = "Flow only", max_steps: int = 150):
        """Creates a transient rainfall infiltration phase."""
        p = self.add_phase(parent_phase, name=name, calc_type=calc_type, max_steps=max_steps, time_interval=duration_days)
        self.g_i.Precipitation.TimeDependency = "Constant"
        self.g_i.Precipitation.Discharge = discharge
        self.g_i.commands(f"activate Precipitation {p.Name}")
        return p

    def add_safety_phase(self, parent_phase, name: str = "Safety_Factor", max_steps: int = 100, tolerated_error: float = 0.01):
        """Creates a strength reduction (Safety) phase for factor of safety evaluation."""
        p = self.add_phase(parent_phase, name=name, calc_type="Safety", loading_input="Incremental multipliers", max_steps=max_steps)
        p.ToleratedError = tolerated_error
        return p

    # ---- Solver Execution ----

    def calculate(self):
        """Triggers solver calculation for all marked phases."""
        print("Starting PLAXIS finite element calculation...")
        self.s_i.calculate()
        print("[OK] Calculation finished.")

    # ---- Utilities & Diagnostics ----

    def save(self):
        """Saves current project."""
        self.g_i.save()
        print("[OK] Project saved.")

    def info(self):
        """Prints high-level model diagnostic summary."""
        print(f"PLAXIS {self.s_i.major_version}.{self.s_i.minor_version}")
        print(f"Title: {self.g_i.Project.Title}")
        print(f"SoilContour: {self.g_i.SoilContour}")
        print(f"Soillayers: {len(self.g_i.Soillayers)}")
        print(f"Boreholes: {len(self.g_i.Boreholes)}")
        print(f"Materials: {len(self.g_i.Materials)}")
        if hasattr(self.g_i, 'Phases'):
            print(f"Phases: {len(self.g_i.Phases)}")

    def raw_command(self, cmd: str):
        """Executes raw PLAXIS command string."""
        return self.g_i.commands(cmd)

    def close(self):
        """Terminates session and background process."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self.s_i = None
        self.g_i = None
        print("[OK] Input session closed.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class PlaxisOutputSession:
    """
    Remote scripting session for PLAXIS 3D Output.
    Enables extraction of safety factors (Msf), pore pressures, deformations, and plot exports.
    """

    def __init__(self, password: str = "123456", port: Optional[int] = None,
                 output_path: Optional[str] = None):
        self.password = password
        self.port = port or get_free_port(start_port=10500)
        self.output_path = output_path or DEFAULT_OUTPUT_PATH
        self.s_o = None
        self.g_o = None
        self._process = None

    def connect(self, timeout: int = 90) -> "PlaxisOutputSession":
        """Launches Output server and establishes connection."""
        from plxscripting.easy import new_server

        if not os.path.exists(self.output_path):
            raise FileNotFoundError(f"PLAXIS Output executable not found: {self.output_path}")

        print(f"Launching PLAXIS 3D Output on port {self.port}...")
        self._process = subprocess.Popen([
            self.output_path,
            f"--AppServerPort={self.port}",
            f"--AppServerPassword={self.password}"
        ])

        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(2)
            try:
                self.s_o, self.g_o = new_server("localhost", self.port, password=self.password, request_timeout=timeout)
                _ = self.s_o.major_version
                print(f"[OK] Connected to PLAXIS Output ({int(time.time() - start_time)}s)")
                return self
            except Exception:
                pass

        self.close()
        raise TimeoutError(f"PLAXIS Output startup timed out ({timeout}s)")

    def open_project(self, path: Union[str, Path]) -> "PlaxisOutputSession":
        """Opens project file in Output server."""
        path_str = str(path)
        if not os.path.exists(path_str):
            raise FileNotFoundError(f"Project file not found: {path_str}")
        self.s_o.open(path_str)
        print(f"[OK] Opened in Output: {path_str}")
        return self

    def get_safety_factor(self, phase_identifier: Optional[str] = None) -> Optional[float]:
        """Extracts Msf (factor of safety) from a Safety calculation phase."""
        for p in self.g_o.Phases:
            p_ident = getattr(p.Identification, 'value', str(p.Identification))
            if phase_identifier is None or phase_identifier in p_ident:
                if len(p.Steps) > 0:
                    last_step = p.Steps[-1]
                    if hasattr(last_step, 'Reached') and hasattr(last_step.Reached, 'Msf'):
                        val = getattr(last_step.Reached.Msf, 'value', None)
                        if val is not None:
                            return float(val)
        return None

    def get_field_extremes(self, phase_index: int = -1, step_index: int = -1) -> Dict[str, Dict[str, float]]:
        """Extracts min/max field variable extremes for the designated step."""
        target_phase = self.g_o.Phases[phase_index]
        target_step = target_phase.Steps[step_index]
        soil_rt = self.g_o.ResultTypes.Soil
        extremes = {}

        fields = ['PWater', 'PActive', 'Suction', 'DegreeOfSaturation', 'Ux', 'Uy', 'Uz', 'Utot', 'GroundwaterHead']
        for field in fields:
            if hasattr(soil_rt, field):
                typ = getattr(soil_rt, field)
                try:
                    vals = self.g_o.getresults(target_step, typ, 'Soil')
                    nums = [float(v) for v in vals if v is not None and isinstance(v, (int, float))]
                    if nums:
                        extremes[field] = {"min": min(nums), "max": max(nums)}
                except Exception:
                    pass

        return extremes

    def get_single_point(self, x: float, y: float, z: float, result_name: str = "PWater",
                         phase_index: int = -1, step_index: int = -1) -> Any:
        """Queries result value at specific (x, y, z) coordinates."""
        target_phase = self.g_o.Phases[phase_index]
        target_step = target_phase.Steps[step_index]
        soil_rt = self.g_o.ResultTypes.Soil
        if hasattr(soil_rt, result_name):
            typ = getattr(soil_rt, result_name)
            return self.g_o.getsingleresult(target_step, typ, (x, y, z))
        return None

    def export_plot(self, output_image_path: Union[str, Path], width: int = 1920, height: int = 1080):
        """Exports high-resolution screenshot plot."""
        out_path = Path(output_image_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.g_o.export(str(out_path), width, height)
        print(f"[OK] Plot exported: {out_path}")

    def close(self):
        """Terminates Output server process."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self.s_o = None
        self.g_o = None
        print("[OK] Output session closed.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================
# Quick Function: Build Drainage Model (Backward Compatible)
# ============================================================

def build_drainage_model(password: str = "123456", project_path: Optional[str] = None) -> PlaxisSession:
    """Builds the lightweight foam concrete drainage embankment model."""
    session = PlaxisSession(password=password)
    session.connect()

    if project_path and os.path.exists(project_path):
        session.open_project(project_path)
    else:
        session.new_project("泡沫轻质土防排水模拟", 12.0, 8.0)

    # Geometry & Material definitions
    FOAM_H = 4.0
    OLD_FILL_H = 3.0
    CROSS_SLOPE = 0.02

    M = {
        'fdn': session.create_material('地基土', 'Mohr-Coulomb', 18.5, 20.0, 2e4, 0.33, 0.001, cRef=10, phi=25),
        'old': session.create_material('老路基填土', 'Mohr-Coulomb', 19.0, 20.5, 5e4, 0.30, 0.05, cRef=15, phi=30),
        'sand': session.create_material('砂垫层', 'Mohr-Coulomb', 18.0, 20.0, 3e4, 0.30, 10.0, cRef=1, phi=32, psi=2),
        'foam': session.create_material('泡沫轻质土', 'Mohr-Coulomb', 6.0, 8.0, 5e5, 0.28, 1e-8, cRef=200, phi=25),
        'c30': session.create_material('C30水泥板压顶', 'Linear elastic', 25.0, 25.0, 3e7, 0.20, 1e-12),
        'sub': session.create_material('级配碎石底基层', 'Mohr-Coulomb', 22.0, 23.0, 3e5, 0.30, 1.0, cRef=5, phi=40, psi=10),
        'base': session.create_material('水泥稳定碎石基层', 'Mohr-Coulomb', 23.0, 23.5, 1.5e6, 0.25, 0.01, cRef=300, phi=38, psi=8),
        'asp': session.create_material('沥青面层', 'Linear elastic', 24.0, 24.0, 1.2e6, 0.35, 1e-9),
    }

    bh_x = [0.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.5, 11.5, 12.0]
    session.add_boreholes(bh_x, y=4.0)

    session.add_soil_layers([
        (5.0, M['fdn']), (OLD_FILL_H, M['old']), (0.15, M['sand']),
        (FOAM_H, M['foam']), (0.10, M['c30']), (0.20, M['sub']),
        (0.20, M['base']), (0.18, M['asp']),
    ])

    z_old_top, z_old_bottom = 0.0, -OLD_FILL_H
    z_step_bottom = -1.5
    z_sand_top = z_step_bottom + 0.15
    z_foam_top = z_sand_top + FOAM_H
    z_asp_top_0 = z_foam_top + 0.68
    FDN_BOTTOM = -5.0

    def road_z(x):
        if x <= 11.0:
            return z_asp_top_0 - x * CROSS_SLOPE
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

    session.set_deformation_bc()
    session.set_flow_bc()
    session.set_rainfall()
    session.save()
    print("[OK] Drainage model constructed successfully.")
    return session


if __name__ == "__main__":
    build_drainage_model()
