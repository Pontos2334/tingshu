import ctypes
import ctypes.util
import glob
import logging
import os

logger = logging.getLogger("tingshu.subtitle.runtime_check")

_MISSING_LIBS_MESSAGE = (
    "本地 Whisper 需要 CUDA 12 GPU 运行时，当前环境缺少必要的 CUDA 库。"
    "请在 WSL/Linux 中安装 CUDA 12 userspace 运行库（如 cuda-toolkit-12-x），"
    "并确保 libcublas.so.12 和 libcuda.so.12 可被加载。"
    "参考: https://opennmt.net/CTranslate2/installation.html"
)

_NVIDIA_PIP_LIB_DIRS = [
    "nvidia/cublas/lib",
    "nvidia/cuda_runtime/lib",
    "nvidia/cudnn/lib",
    "nvidia/cuda_nvrtc/lib",
]


def setup_nvidia_library_path():
    """Auto-inject nvidia pip package library paths into LD_LIBRARY_PATH.

    Should be called once at backend startup so that CTranslate2 / CUDA
    can discover libcublas.so.12 and friends even when they are not
    installed system-wide.
    """
    extra_dirs: list[str] = []
    try:
        import site
        roots = site.getsitepackages() + [site.getusersitepackages()]
    except Exception:
        roots = []

    for root in roots:
        for sub in _NVIDIA_PIP_LIB_DIRS:
            candidate = os.path.join(root, sub)
            if os.path.isdir(candidate):
                extra_dirs.append(candidate)

    if not extra_dirs:
        return

    current = os.environ.get("LD_LIBRARY_PATH", "")
    new_paths = [d for d in extra_dirs if d not in current]
    if new_paths:
        os.environ["LD_LIBRARY_PATH"] = ":".join(new_paths + [current]) if current else ":".join(new_paths)
        logger.info("Auto-injected NVIDIA pip lib paths: %s", new_paths)


def _find_nvidia_pip_lib_dir(lib_name: str) -> str | None:
    """Search for a shared library inside pip-installed nvidia-* packages."""
    try:
        import site
        roots = site.getsitepackages() + [site.getusersitepackages()]
    except Exception:
        roots = []

    # Also walk venv site-packages from this file's location
    this_dir = os.path.dirname(os.path.abspath(__file__))
    venv_sp = os.path.join(this_dir, "..", "..", "venv", "lib")
    if os.path.isdir(venv_sp):
        for entry in os.listdir(venv_sp):
            candidate = os.path.join(venv_sp, entry, "site-packages")
            if os.path.isdir(candidate):
                roots.append(candidate)

    for root in roots:
        for sub in _NVIDIA_PIP_LIB_DIRS:
            pattern = os.path.join(root, sub, f"{lib_name}*")
            matches = glob.glob(pattern)
            if matches:
                return os.path.dirname(matches[0])
    return None


def _can_load(lib_name: str) -> bool:
    """Try to load a shared library by name, respecting LD_LIBRARY_PATH."""
    # 1. Try ctypes.util.find_library (works when lib is in standard paths)
    if ctypes.util.find_library(lib_name) is not None:
        return True

    # 2. Try direct CDLL load (respects LD_LIBRARY_PATH)
    try:
        ctypes.CDLL(f"lib{lib_name}.so.12")
        return True
    except OSError:
        pass
    try:
        ctypes.CDLL(f"lib{lib_name}.so.1")
        return True
    except OSError:
        pass
    try:
        ctypes.CDLL(f"lib{lib_name}.so")
        return True
    except OSError:
        pass

    # 3. Search pip-installed nvidia-* packages
    for suffix in (".so.12", ".so.1", ".so"):
        lib_dir = _find_nvidia_pip_lib_dir(f"lib{lib_name}{suffix}")
        if lib_dir:
            full = os.path.join(lib_dir, f"lib{lib_name}{suffix}")
            try:
                ctypes.CDLL(full)
                return True
            except OSError:
                pass

    return False


def check_local_whisper_gpu_runtime() -> dict:
    """Check whether the local Faster-Whisper GPU runtime dependencies are satisfied.

    Returns:
        {
            "ok": bool,
            "missing": list[str],
            "message": str
        }
    """
    missing: list[str] = []

    if not _can_load("cuda"):
        missing.append("libcuda.so.1")

    if not _can_load("cublas"):
        missing.append("libcublas.so.12")

    if missing:
        return {
            "ok": False,
            "missing": missing,
            "message": f"缺少以下 CUDA 运行库: {', '.join(missing)}。{_MISSING_LIBS_MESSAGE}",
        }

    # Final validation: try to instantiate WhisperModel with CUDA
    try:
        from faster_whisper import WhisperModel

        WhisperModel("tiny", device="cuda", compute_type="float16")
    except Exception as exc:
        normalized = _normalize_cuda_error(str(exc))
        return {
            "ok": False,
            "missing": _extract_missing_libs(str(exc)),
            "message": normalized,
        }

    return {"ok": True, "missing": [], "message": ""}


def _normalize_cuda_error(raw: str) -> str:
    """Normalize raw CUDA/CTranslate2 exception into a user-friendly message."""
    lower = raw.lower()

    if "libcublas" in lower:
        return f"本地 Whisper 需要 CUDA 12 GPU 运行时，当前缺少 libcublas.so.12。{_MISSING_LIBS_MESSAGE}"
    if "libcuda" in lower:
        return f"本地 Whisper 需要 NVIDIA GPU 驱动，当前缺少 libcuda.so.1。{_MISSING_LIBS_MESSAGE}"
    if "cublas" in lower or "cuda" in lower:
        return f"本地 Whisper GPU 初始化失败: {raw[:200]}。{_MISSING_LIBS_MESSAGE}"
    if "out of memory" in lower or "oom" in lower:
        return "GPU 显存不足，请尝试使用更小的 Whisper 模型（如 base 或 small）。"

    return f"本地 Whisper 初始化失败: {raw[:300]}"


def _extract_missing_libs(raw: str) -> list[str]:
    """Best-effort extraction of missing .so names from an error string."""
    missing = []
    for lib in ("libcublas.so.12", "libcuda.so.1", "libcudnn.so", "libcublasLt.so.12"):
        if lib in raw:
            missing.append(lib)
    return missing if missing else ["unknown CUDA library"]
