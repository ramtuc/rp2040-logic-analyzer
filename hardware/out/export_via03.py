"""Export a separate updated manufacturing set and verify drilled tool sizes."""
import pathlib
import re
import subprocess
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
out = root / 'out' / 'via-0p3'
gerbers = out / 'gerbers'
gerbers.mkdir(exist_ok=True)
cli = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
board = root / 'rp2040-logic-analyzer.kicad_pcb'
for args in [
    ['pcb', 'export', 'gerbers', '-l', 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts', '-o', str(gerbers), str(board)],
    ['pcb', 'export', 'drill', '-o', str(gerbers), str(board)],
]:
    result = subprocess.run([cli, *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        print(result.stdout, result.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.strip())
tools = []
for drill in gerbers.glob('*.drl'):
    sizes = [float(v) for v in re.findall(r'^T\d+C([0-9.]+)', drill.read_text(), re.M)]
    tools.extend(sizes)
    print(drill.name, 'tool diameters (mm):', sizes)
assert tools and min(tools) >= .3, tools
archive = out / 'rp2040-logic-analyzer-via03-gerbers.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(gerbers.iterdir()):
        z.write(path, path.name)
print('Archive:', archive)
