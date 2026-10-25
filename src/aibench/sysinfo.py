"""Host description + background GPU sampling (VRAM, GTT spill, power, busy%).

AMD is read straight from amdgpu sysfs; NVIDIA via nvidia-smi.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GiB = 1024 ** 3


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    v = _read(path)
    return int(v) if v and v.lstrip("-").isdigit() else None


@dataclass
class Gpu:
    id: str                 # pci slot or nvidia index
    name: str
    vendor: str
    vram_total: int
    sysfs: Path | None = None

    def sample(self) -> dict[str, float]:
        if self.sysfs is None:
            return {}
        d = self.sysfs
        out: dict[str, float] = {}
        if (v := _read_int(d / "mem_info_vram_used")) is not None:
            out["vram"] = v
        if (v := _read_int(d / "mem_info_gtt_used")) is not None:
            out["gtt"] = v
        if (v := _read_int(d / "gpu_busy_percent")) is not None:
            out["busy"] = v
        for hw in d.glob("hwmon/hwmon*"):
            p = _read_int(hw / "power1_average") or _read_int(hw / "power1_input")
            if p is not None:
                out["power_w"] = p / 1e6
            if (t := _read_int(hw / "temp1_input")) is not None:
                out["temp_c"] = t / 1000
        return out


def _lspci_name(slot: str) -> str:
    if shutil.which("lspci"):
        try:
            line = subprocess.run(["lspci", "-s", slot], capture_output=True, text=True, timeout=5).stdout.strip()
            if ": " in line:
                return line.split(": ", 1)[1]
        except (OSError, subprocess.SubprocessError):
            pass
    return slot


def discover_gpus() -> list[Gpu]:
    gpus: list[Gpu] = []
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
        if "-" in card.name:
            continue
        dev = card / "device"
        total = _read_int(dev / "mem_info_vram_total")
        if total is None:
            continue
        slot = os.path.basename(os.path.realpath(dev))
        gpus.append(Gpu(id=slot, name=_lspci_name(slot), vendor="amd", vram_total=total, sysfs=dev))
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10).stdout
            for line in out.strip().splitlines():
                idx, name, mem = [x.strip() for x in line.split(",")]
                gpus.append(Gpu(id=f"nvidia{idx}", name=name, vendor="nvidia", vram_total=int(mem) * 1024 ** 2))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return gpus


def select_gpus(gpus: list[Gpu], spec: str | list[str]) -> list[Gpu]:
    """'auto' = every GPU with >= 4 GiB dedicated VRAM (skips iGPUs' small carve-outs)."""
    if spec == "auto":
        return [g for g in gpus if g.vram_total >= 4 * GiB]
    if spec in ("none", None):
        return []
    wanted = [spec] if isinstance(spec, str) else spec
    return [g for g in gpus if g.id in wanted or any(w in g.id for w in wanted)]


def _nvidia_samples() -> dict[str, dict[str, float]]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,power.draw,utilization.gpu,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    res = {}
    for line in out.strip().splitlines():
        try:
            idx, mem, pw, util, temp = [x.strip() for x in line.split(",")]
            res[f"nvidia{idx}"] = {"vram": float(mem) * 1024 ** 2, "power_w": float(pw), "busy": float(util),
                                   "temp_c": float(temp)}
        except ValueError:
            continue
    return res


def sample_all(gpus: list[Gpu]) -> dict[str, dict[str, float]]:
    out = {g.id: g.sample() for g in gpus if g.vendor == "amd"}
    if any(g.vendor == "nvidia" for g in gpus):
        out.update({k: v for k, v in _nvidia_samples().items() if any(g.id == k for g in gpus)})
    return out


@dataclass
class GpuSampler:
    """Samples in a thread while a suite runs; summary() gives peak/avg/energy."""
    gpus: list[Gpu]
    interval: float = 0.5
    samples: dict[str, list[tuple[float, dict[str, float]]]] = field(default_factory=dict)

    def __post_init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        if self.gpus:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.is_set():
            now = time.monotonic()
            for gid, s in sample_all(self.gpus).items():
                self.samples.setdefault(gid, []).append((now, s))
            self._stop.wait(self.interval)

    def summary(self) -> dict[str, dict[str, float]]:
        out = {}
        for gid, rows in self.samples.items():
            if not rows:
                continue
            s: dict[str, float] = {}
            vram = [r["vram"] for _, r in rows if "vram" in r]
            gtt = [r["gtt"] for _, r in rows if "gtt" in r]
            power = [(t, r["power_w"]) for t, r in rows if "power_w" in r]
            busy = [r["busy"] for _, r in rows if "busy" in r]
            temp = [r["temp_c"] for _, r in rows if "temp_c" in r]
            if vram:
                s["peak_vram_gib"] = max(vram) / GiB
            if gtt:
                s["peak_gtt_gib"] = max(gtt) / GiB
            if power:
                s["avg_power_w"] = sum(p for _, p in power) / len(power)
                s["peak_power_w"] = max(p for _, p in power)
                s["energy_kj"] = sum(p0 * (t1 - t0) for (t0, p0), (t1, _) in zip(power, power[1:])) / 1000
            if busy:
                s["avg_busy_pct"] = sum(busy) / len(busy)
            if temp:
                s["peak_temp_c"] = max(temp)
            out[gid] = s
        return out


def primary_gpu_summary(summary: dict[str, dict[str, float]]) -> dict[str, float]:
    """The GPU that did the work = the one with the highest average power/busy."""
    if not summary:
        return {}
    return max(summary.values(), key=lambda s: (s.get("avg_busy_pct", 0), s.get("avg_power_w", 0)))


def collect_sysinfo(gpus: list[Gpu] | None = None) -> dict[str, Any]:
    cpu = "unknown"
    for line in (_read(Path("/proc/cpuinfo")) or "").splitlines():
        if line.startswith("model name"):
            cpu = line.split(":", 1)[1].strip()
            break
    mem_kb = 0
    for line in (_read(Path("/proc/meminfo")) or "").splitlines():
        if line.startswith("MemTotal:"):
            mem_kb = int(line.split()[1])
    gpus = discover_gpus() if gpus is None else gpus
    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu,
        "cpu_threads": os.cpu_count(),
        "ram_gib": round(mem_kb / 1024 ** 2, 1),
        "gpus": [{"id": g.id, "name": g.name, "vendor": g.vendor, "vram_gib": round(g.vram_total / GiB, 1)}
                 for g in gpus],
    }
    if v := _read(Path("/sys/module/amdgpu/version")):
        info["amdgpu_version"] = v
    if shutil.which("vulkaninfo"):
        try:
            out = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=10).stdout
            info["vulkan_drivers"] = sorted({l.split("=", 1)[1].strip() for l in out.splitlines()
                                             if l.strip().startswith("driverInfo")})
        except (OSError, subprocess.SubprocessError):
            pass
    return info
