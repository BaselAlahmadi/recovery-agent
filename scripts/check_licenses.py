"""List the licence of every third-party package we depend on and flag anything that mentions GPL/LGPL/AGPL.

  python scripts/check_licenses.py

It walks the dependency closure of requirements.txt using the metadata of the installed packages.
A flag is a prompt to read the licence text, not an automatic verdict (see the matplotlib note in README.md).
"""
import importlib.metadata as md
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOTS = [re.split(r"[=<>! #]", l.strip())[0] for l in (ROOT / "requirements.txt").read_text().splitlines()
         if l.strip() and not l.startswith("#")]


def norm(n):
    return re.sub(r"[-_.]+", "-", n).lower()


def licence_of(name):
    m = md.metadata(name)
    lic = m.get("License-Expression") or ((m.get("License") or "").splitlines() or [""])[0][:70]
    cls = [c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    return lic or ", ".join(cls) or "(none in metadata)"


def main():
    seen, todo = {}, list(ROOTS)
    while todo:
        n = todo.pop()
        if norm(n) in seen:
            continue
        try:
            seen[norm(n)] = (n, md.version(n))
            reqs = md.requires(n) or []
        except md.PackageNotFoundError:
            continue
        todo += [re.split(r"[ ;<>=!~\[(]", r)[0] for r in reqs if "extra ==" not in r]
    print(f"{'package':28} {'version':10} licence")
    flagged = []
    for key in sorted(seen):
        name, version = seen[key]
        lic = licence_of(name)
        blob = lic + " " + (md.metadata(name).get("License") or "")
        if re.search(r"\b(GPL|LGPL|AGPL|GNU)\b", blob, re.I):
            flagged.append(name)
        print(f"{name:28} {version:10} {lic}{'   <-- mentions GPL/GNU, read the text' if name in flagged else ''}")
    print(f"\n{len(seen)} packages checked. Flagged for a manual read: {flagged or 'none'}")


if __name__ == "__main__":
    main()
