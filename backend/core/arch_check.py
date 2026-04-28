import ast
import os


def check_no_services_import_api(*, repo_root: str | None = None) -> None:
    root = repo_root
    if not root:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        root = os.path.dirname(backend_dir)

    services_dir = os.path.join(root, "backend", "services")
    if not os.path.isdir(services_dir):
        return

    violations: list[tuple[str, str, int]] = []

    for dirpath, _dirnames, filenames in os.walk(services_dir):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    src = f.read()
            except Exception:
                continue
            try:
                tree = ast.parse(src, filename=path)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name or ""
                        if name == "backend.api" or name.startswith("backend.api."):
                            violations.append((path, name, int(getattr(node, "lineno", 0) or 0)))
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod == "backend.api" or mod.startswith("backend.api."):
                        violations.append((path, mod, int(getattr(node, "lineno", 0) or 0)))

    if violations:
        violations_sorted = sorted(violations, key=lambda x: (x[0], x[2], x[1]))
        lines = ["Architecture rule violated: backend/services/** must NOT import backend/api/**", ""]
        for p, mod, lineno in violations_sorted:
            rel = os.path.relpath(p, root)
            lines.append(f"- {rel}:{lineno} imports {mod}")
        raise RuntimeError("\n".join(lines))

