import os
import subprocess
import sys

os.environ["GEMINI_API_KEY"] = "AQ.Ab8RN6IkNEV4z43r9RKBPUIQ0IBJA_fyAuxxe1Rg3_nv2QhiIA"
os.environ["PORT"] = "5050"
os.environ["HOST"] = "::"

cmd = [sys.executable, "app.py"]
p = subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
p.wait()
