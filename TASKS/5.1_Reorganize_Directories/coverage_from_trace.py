import re, sys, trace
from pathlib import Path
d = Path(sys.argv[1]); tot_e = tot_h = 0
for cov in sorted(d.glob("*.cover")):
    name = cov.stem
    if name.startswith("test_"): continue
    src = Path(name + ".py")
    if not src.exists(): continue
    exe = set(trace._find_executable_linenos(str(src)))
    hit = {i for i, l in enumerate(cov.read_text().splitlines(), 1) if re.match(r"\s*\d+:", l)}
    e = len(exe); h = len(exe & hit); tot_e += e; tot_h += h
    print(f"{e:6d} {100*h/e:5.1f}%  {name}")
print(f"{tot_e:6d} {100*tot_h/tot_e:5.1f}%  TOTAL")
