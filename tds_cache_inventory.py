import os
import hashlib
from pathlib import Path

def inventory(root):
    root = Path(root).resolve(strict=True)
    rows = []
    if not root.is_dir():
        raise ValueError("Cache root must be a directory")
    def fail(error):
        raise error
    generated = {"reports", "builds", "model_results", "training_candidates"}
    for base, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        dirs[:] = sorted(d for d in dirs
                         if not (Path(base) == root / "AuroraKnowledge" and d in generated)
                         and d != "__pycache__"
                         and not (Path(base) / d).is_symlink()
                         and not getattr(os.path, "isjunction", lambda p: False)(Path(base) / d))
        for name in sorted(files):
            p = Path(base) / name
            if p.suffix.lower() not in (".pdf", ".docx"):
                continue
            if p.is_symlink() or not p.resolve().is_relative_to(root):
                raise ValueError("Escaping source")
            before = p.stat()
            h = hashlib.sha256()
            with p.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1048576), b""):
                    h.update(chunk)
            after = p.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Changed source")
            rows.append(dict(sha256=h.hexdigest(), path=str(p.resolve()), filename=p.name, suffix=p.suffix.lower(), size=before.st_size))
    return sorted(rows, key=lambda r: r["path"].casefold())