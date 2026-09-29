"""Run compiled C++ edge -> Python consumer without a broker, for local development."""
import argparse
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from digital_twin.state_manager import StateManager
from streaming.consumer import process

parser = argparse.ArgumentParser()
parser.add_argument("--edge", default="build/fabtwin-edge.exe" if sys.platform == "win32" else "build/fabtwin-edge")
parser.add_argument("--ticks", type=int, default=0)
parser.add_argument("--interval-ms", type=int, default=1000)
args = parser.parse_args()
store = StateManager()
child = subprocess.Popen([args.edge, "--machines", "24", "--ticks", str(args.ticks), "--interval-ms", str(args.interval_ms)], stdout=subprocess.PIPE, text=True)
try:
    for line in child.stdout:
        process(store, line)
    if child.wait() != 0:
        raise RuntimeError("Edge process failed")
except KeyboardInterrupt:
    child.terminate()
finally:
    if child.poll() is None:
        child.terminate()
    child.wait()
