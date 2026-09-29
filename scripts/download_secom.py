"""Download official UCI data without executing or blindly extracting archive paths."""
import io
import urllib.request
import zipfile
from pathlib import Path

url = "https://archive.ics.uci.edu/static/public/179/secom.zip"
destination = Path("data/secom")
destination.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(url, timeout=60) as response:
    archive = zipfile.ZipFile(io.BytesIO(response.read()))
for name in ("secom.data", "secom_labels.data", "secom.names"):
    matches = [entry for entry in archive.namelist() if entry.split("/")[-1] == name]
    if matches:
        (destination / name).write_bytes(archive.read(matches[0]))
print(f"Downloaded official UCI SECOM files to {destination}")
