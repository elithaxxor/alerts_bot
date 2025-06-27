import ast
import subprocess
import sys
from pathlib import Path


def audit_strategy_file(path: Path) -> list[str]:
    """Return a list of warnings for a strategy file."""
    warnings: list[str] = []
    text = path.read_text()
    if 'eval(' in text or 'exec(' in text:
        warnings.append('uses eval/exec')
    if 'os.system' in text:
        warnings.append('uses os.system')
    try:
        ast.parse(text)
    except SyntaxError as exc:
        warnings.append(f'syntax error: {exc}')
    return warnings


def audit_strategies() -> dict[str, list[str]]:
    """Audit all strategies in the strategies folder."""
    strategy_dir = Path(__file__).resolve().parents[1] / 'strategies'
    report = {}
    for f in strategy_dir.glob('*.py'):
        warns = audit_strategy_file(f)
        if warns:
            report[f.name] = warns
    return report


def audit_dependencies() -> list[str]:
    """Return a list of packages with pre-release versions."""
    try:
        res = subprocess.run(
            [sys.executable, '-m', 'pip', 'list', '--format', 'json'],
            capture_output=True, text=True, check=True
        )
        packages = __import__('json').loads(res.stdout)
    except Exception:
        return []
    flagged = []
    for pkg in packages:
        ver = pkg.get('version', '')
        if 'a' in ver or 'b' in ver or 'rc' in ver:
            flagged.append(f"{pkg['name']} {ver}")
    return flagged


def main() -> int:
    strat_report = audit_strategies()
    dep_report = audit_dependencies()
    if strat_report:
        print('Strategy Issues:')
        for name, warns in strat_report.items():
            print(f' - {name}: {", ".join(warns)}')
    if dep_report:
        print('Dependency Warnings:')
        for pkg in dep_report:
            print(f' - {pkg}')
    if not strat_report and not dep_report:
        print('No issues found.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
