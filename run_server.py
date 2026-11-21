import os
import subprocess
import sys

# Set your Gemini API key here or via environment variable
os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
os.environ["GEMINI_MODEL"] = "gemini-3.1-flash-lite"
os.environ["PORT"] = "5050"
os.environ["HOST"] = "::"

cmd = [sys.executable, "app.py"]
p = subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
p.wait()
