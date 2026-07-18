"""Honest hardware label for report headlines.

The old headlines hard-coded ``on GPU`` — true on the blessing box (an RX 6900 XT),
but a lie on any CPU-fallback run. This maps the *actual* device a run used to a
truthful ``GPU``/``CPU`` label. Accepts a device string, a config dict, or a config
object (dataclass). Reported on the public feed, so it must never overclaim.
"""


def hw(src) -> str:
    """Return ``"GPU"`` iff the run used an accelerator device, else ``"CPU"``."""
    if isinstance(src, dict):
        dev = src.get("device", "cuda")
    elif hasattr(src, "device"):
        dev = src.device
    else:
        dev = src
    return "GPU" if str(dev).lower().startswith(("cuda", "hip", "rocm")) else "CPU"
