#!/usr/bin/env python3
"""Required rembg invocation helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import ctypes
import json
from pathlib import Path


DEFAULT_MODEL = "birefnet-general-lite"
GPU_DISABLED_REASON: str | None = None
NVIDIA_PRELOAD_LIBRARIES = (
    "libcudart.so.13",
    "libnvrtc.so.13",
    "libcublas.so.13",
    "libcublasLt.so.13",
    "libcurand.so.10",
    "libcufft.so.12",
    "libcudnn.so.9",
)


def nvidia_library_dirs() -> list[Path]:
    dirs: set[Path] = set()
    for raw in sys.path:
        if not raw:
            continue
        root = Path(raw) / "nvidia"
        if not root.is_dir():
            continue
        for lib_dir in root.glob("**/lib"):
            if lib_dir.is_dir():
                dirs.add(lib_dir.resolve())
    return sorted(dirs)


def configure_nvidia_library_path(env: dict[str, str]) -> None:
    dirs = [str(path) for path in nvidia_library_dirs()]
    if not dirs:
        return
    existing = [part for part in env.get("LD_LIBRARY_PATH", "").split(os.pathsep) if part]
    merged = dirs + [part for part in existing if part not in dirs]
    env["LD_LIBRARY_PATH"] = os.pathsep.join(merged)


def preload_nvidia_libraries() -> None:
    dirs = nvidia_library_dirs()
    for library in NVIDIA_PRELOAD_LIBRARIES:
        for directory in dirs:
            candidate = directory / library
            if not candidate.is_file():
                continue
            ctypes.CDLL(str(candidate), mode=ctypes.RTLD_GLOBAL)
            break


configure_nvidia_library_path(os.environ)
preload_nvidia_libraries()

import onnxruntime as ort


def cache_root() -> Path:
    raw = os.environ.get("XDG_CACHE_HOME")
    root = Path(raw).expanduser() if raw else Path.home() / ".cache"
    return root / "codex-skills" / "animation-creator"


def rembg_model_cache() -> Path:
    return Path(os.environ.get("U2NET_HOME", cache_root() / "rembg-models")).expanduser().resolve()


def rembg_runtime_info() -> dict[str, object]:
    available = list(ort.get_available_providers())
    device = ort.get_device()
    if device == "GPU" and "CUDAExecutionProvider" in available:
        return {
            "backend": "cuda",
            "device": device,
            "available_providers": available,
            "selected_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
        }
    if device.startswith("GPU") and "ROCMExecutionProvider" in available:
        return {
            "backend": "rocm",
            "device": device,
            "available_providers": available,
            "selected_providers": ["ROCMExecutionProvider", "CPUExecutionProvider"],
        }
    return {
        "backend": "cpu",
        "device": device,
        "available_providers": available,
        "selected_providers": ["CPUExecutionProvider"],
    }


def background_removal_defaults(*, model: str = DEFAULT_MODEL, alpha_matting: bool = True) -> dict[str, object]:
    return {
        "required": True,
        "engine": "rembg",
        **rembg_runtime_info(),
        "model": model,
        "alpha_matting": alpha_matting,
        "model_cache": str(rembg_model_cache()),
    }


class CommandFailure(Exception):
    def __init__(self, command: list[str], returncode: int, stderr: str) -> None:
        super().__init__(stderr)
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(command, check=True, text=True, env=env, capture_output=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"required command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise CommandFailure(command, exc.returncode, exc.stderr or exc.stdout or "") from exc


def ensure_rembg_command() -> list[str]:
    override = os.environ.get("ANIMATION_CREATOR_REMBG_BIN")
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.is_file():
            raise SystemExit(f"ANIMATION_CREATOR_REMBG_BIN does not exist: {candidate}")
        return [str(candidate)]

    rembg = shutil.which("rembg")
    if rembg:
        return [rembg]
    raise SystemExit(
        "rembg CLI is required in the active animation-creator environment. Run the skill scripts with "
        "`uv run --project skills/animation-creator ...`, or set ANIMATION_CREATOR_REMBG_BIN to an existing rembg executable."
    )


def rembg_command(source: Path, output: Path, *, model: str, alpha_matting: bool, providers: list[str]) -> list[str]:
    command = [*ensure_rembg_command(), "i", "-m", model, "-x", json.dumps({"providers": providers})]
    if alpha_matting:
        command.append("-a")
    command.extend([str(source), str(output)])
    return command


def run_rembg(source: Path, output: Path, *, model: str, alpha_matting: bool, providers: list[str], env: dict[str, str]) -> None:
    run_checked(
        rembg_command(source, output, model=model, alpha_matting=alpha_matting, providers=providers),
        env=env,
    )


def remove_background(
    source: Path,
    output: Path,
    *,
    alpha_matting: bool = True,
    model: str = DEFAULT_MODEL,
) -> dict[str, object]:
    global GPU_DISABLED_REASON
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"background removal source image not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    model_cache = rembg_model_cache()
    model_cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    configure_nvidia_library_path(env)
    env["U2NET_HOME"] = str(model_cache)
    metadata = background_removal_defaults(model=model, alpha_matting=alpha_matting)
    if GPU_DISABLED_REASON and metadata.get("backend") != "cpu":
        metadata.update(
            {
                "backend": "cpu",
                "selected_providers": ["CPUExecutionProvider"],
                "gpu_fallback": {
                    "attempted_backend": metadata.get("backend"),
                    "attempted_providers": metadata.get("selected_providers", []),
                    "reason": GPU_DISABLED_REASON,
                    "skipped_after_prior_failure": True,
                },
            }
        )
    selected_providers = [str(provider) for provider in metadata.get("selected_providers", ["CPUExecutionProvider"])]
    try:
        run_rembg(source, output, model=model, alpha_matting=alpha_matting, providers=selected_providers, env=env)
    except CommandFailure as exc:
        if metadata.get("backend") == "cpu":
            raise SystemExit(f"command failed with exit code {exc.returncode}: {' '.join(exc.command)}\n{exc.stderr}") from exc
        cpu_providers = ["CPUExecutionProvider"]
        fallback_reason = exc.stderr.strip().splitlines()[-1] if exc.stderr.strip() else "rembg GPU execution failed"
        try:
            run_rembg(source, output, model=model, alpha_matting=alpha_matting, providers=cpu_providers, env=env)
        except CommandFailure as fallback_exc:
            raise SystemExit(
                f"command failed with exit code {fallback_exc.returncode}: {' '.join(fallback_exc.command)}\n{fallback_exc.stderr}"
            ) from fallback_exc
        metadata.update(
            {
                "backend": "cpu",
                "selected_providers": cpu_providers,
                "gpu_fallback": {
                    "attempted_backend": metadata.get("backend"),
                    "attempted_providers": selected_providers,
                    "returncode": exc.returncode,
                    "reason": fallback_reason,
                },
            }
        )
        GPU_DISABLED_REASON = fallback_reason
    if not output.is_file():
        raise SystemExit(f"rembg did not write output image: {output}")
    return metadata


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: rembg_runtime.py INPUT OUTPUT")
    print(remove_background(Path(sys.argv[1]), Path(sys.argv[2])))
