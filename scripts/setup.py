"""Portable Codex Advisor setup. Python 3.11+; pip install tomlkit."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import tempfile
import tomllib

try:
    import tomlkit
except ImportError:
    raise SystemExit('Install dependency first: python -m pip install "tomlkit>=0.13,<1"')

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = dict(schema_version=1, base_model='gpt-6.1-sol', base_effort='medium',
                advisor_model='gpt-6-astra', advisor_effort='high', language='en')
BEGIN = '<!-- codex-advisor:begin -->'
END = '<!-- codex-advisor:end -->'
BLOCK = f'''{BEGIN}
# Automatic Codex Advisor
For every coding task, load and apply the codex-advisor skill from the active
Codex home skills/codex-advisor/SKILL.md. Read its personal settings from
codex-advisor/settings.json in the same Codex home. Consult the configured
advisor automatically when the skill criteria apply, using its configured
model and reasoning effort. Preserve the active main model and effort.
This explicitly authorizes focused native advisor delegation. The main agent
owns implementation, validation, and start/end commentary notifications.
An advisor must not recursively invoke another advisor. Report unavailable
delegation honestly; never silently substitute a model.
{END}
'''
ADVICE = ('Act as a focused advisor. Inspect relevant files if necessary. Return diagnosis, '
          'recommendation, uncertainties and verification steps. Do not edit files, take '
          'external actions or spawn agents. The main agent implements and validates. '
          'Automatic advisor rules do not apply recursively to you.')


def read(path):
    return path.read_bytes() if path.exists() else None


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.advisor-tmp', dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextmanager
def installation_lock(home):
    """OS-released advisory lock; lock file persists harmlessly after interruption."""
    lock_path = home / 'codex-advisor' / 'install.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Another installer/recovery is running for this Codex home')
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def catalog(home):
    result = {}
    for p in sorted(home.glob('models_cache*.json')):
        try:
            for m in json.loads(p.read_text(encoding='utf-8')).get('models', []):
                result[m['slug']] = [e['effort'] for e in m.get('supported_reasoning_levels', [])]
        except (ValueError, KeyError, TypeError):
            continue
    return result


def validate(settings, models):
    if settings.get('schema_version') != 1:
        raise ValueError('Unsupported settings schema')
    if settings.get('language') not in ('en', 'de'):
        raise ValueError('Language must be en or de')
    for role in ('base', 'advisor'):
        model, effort = settings.get(role + '_model'), settings.get(role + '_effort')
        if not isinstance(model, str) or not model.strip() or any(c.isspace() for c in model):
            raise ValueError('Invalid model ID')
        if effort not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'):
            raise ValueError('Invalid reasoning effort')
        if model in models and models[model] and effort not in models[model]:
            raise ValueError(f'{model} does not advertise effort {effort}')
        if model not in models:
            print(f'WARNING: availability unverified: {model} / {effort}', file=sys.stderr)


def guidance(text):
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(END) < text.index(BEGIN):
            raise ValueError('Conflicting AGENTS.md markers')
        start, end = text.index(BEGIN), text.index(END) + len(END)
        return text[:start] + BLOCK.rstrip() + text[end:]
    legacy = (ROOT / 'references' / 'legacy-AGENTS.md').read_text(encoding='utf-8').strip()
    if '# Automatic Astra advisor' in text:
        # Build a normalized-to-original offset map so unrelated CRLF bytes survive.
        normalized, offsets = [], []
        for i, char in enumerate(text):
            if char == '\r' and i + 1 < len(text) and text[i + 1] == '\n':
                continue
            normalized.append(char)
            offsets.append(i)
        normalized = ''.join(normalized)
        if legacy not in normalized:
            raise ValueError('Customized legacy advisor instructions: resolve conflict before setup')
        start = normalized.index(legacy)
        end = start + len(legacy)
        return text[:offsets[start]] + BLOCK.rstrip() + text[offsets[end - 1] + 1:]
    return text + ('\n\n' if text.strip() else '') + BLOCK


def outputs(home, settings):
    cfg = home / 'config.toml'
    doc = tomlkit.parse((read(cfg) or b'').decode('utf-8-sig'))
    doc['model'] = settings['base_model']
    doc['model_reasoning_effort'] = settings['base_effort']
    # Agent files are discovered from the user's agents directory by current Codex.
    role = tomlkit.document()
    role.update(name='codex_advisor', description='Configured Codex Advisor; analysis only.',
                model=settings['advisor_model'], model_reasoning_effort=settings['advisor_effort'],
                developer_instructions=ADVICE)
    role_path = home / 'agents' / 'codex-advisor.toml'
    prior = read(role_path)
    if prior:
        old = tomllib.loads(prior.decode('utf-8-sig'))
        if old.get('developer_instructions') != ADVICE:
            raise ValueError('Customized codex-advisor role: refusing to overwrite')
    result = {cfg: tomlkit.dumps(doc).encode(), role_path: tomlkit.dumps(role).encode(),
              home / 'AGENTS.md': guidance((read(home / 'AGENTS.md') or b'').decode('utf-8-sig')).encode(),
              home / 'codex-advisor' / 'settings.json': (json.dumps(settings, indent=2) + '\n').encode()}
    old_role = home / 'agents' / 'astra-advisor.toml'
    if old_role.exists():
        known = (ROOT / 'references' / 'legacy-astra-advisor.toml').read_bytes()
        normalize = lambda b: b.decode('utf-8-sig').replace('\r\n', '\n').strip()
        if normalize(old_role.read_bytes()) != normalize(known):
            raise ValueError('Customized legacy Astra role: resolve conflict before setup')
        # Do not remove a registered role and leave a dangling config reference.
        if 'astra-advisor.toml' in tomlkit.dumps(doc) or 'astra_advisor' in tomlkit.dumps(doc):
            raise ValueError('Legacy role registered in config.toml: migrate registration first')
        result[old_role] = None
    for folder in ('scripts', 'references'):
        for src in sorted((ROOT / folder).rglob('*')):
            if src.is_file() and '__pycache__' not in src.parts and src.suffix != '.pyc':
                result[home / 'skills' / 'codex-advisor' / src.relative_to(ROOT)] = src.read_bytes()
    result[home / 'skills' / 'codex-advisor' / 'SKILL.md'] = (ROOT / 'SKILL.md').read_bytes()
    result[home / 'skills' / 'codex-advisor' / 'requirements.txt'] = (ROOT / 'requirements.txt').read_bytes()
    for path, data in result.items():
        if data and path.suffix == '.toml':
            tomllib.loads(data.decode())
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def recover(home):
    manifest = home / 'codex-advisor' / 'pending.json'
    if not manifest.exists():
        return False
    entries = json.loads(manifest.read_text())['entries']
    backups = {}
    for e in entries:
        if e['backup']:
            data = Path(e['backup']).read_bytes()
            if digest(data) != e['before']:
                raise ValueError('Damaged recovery backup: ' + e['backup'])
            backups[e['path']] = data
    # Avoid overwriting edits made after the interrupted installation.
    for e in entries:
        current = digest(read(Path(e['path'])))
        if current not in (e['before'], e['after']):
            raise ValueError('Recovery conflict: ' + e['path'])
    for e in entries:
        path = Path(e['path'])
        if e['backup']:
            atomic(path, backups[e['path']])
        else:
            path.unlink(missing_ok=True)
    manifest.unlink()
    print('Recovered previous installation; backups retained.')
    return True


def apply(home, changes):
    pending = home / 'codex-advisor' / 'pending.json'
    if pending.exists():
        raise ValueError('Interrupted installation: run --recover first')
    changed = {p: d for p, d in changes.items() if read(p) != d}
    if not changed:
        print('Already up to date.')
        return
    backup = home / 'codex-advisor' / 'backups' / str(time.time_ns())
    backup.mkdir(parents=True)
    entries = []
    for i, (path, data) in enumerate(changed.items()):
        before = read(path)
        saved = backup / str(i) if before is not None else None
        if saved:
            atomic(saved, before)
        entries.append(dict(path=str(path), backup=str(saved) if saved else None,
                            before=digest(before), after=digest(data)))
    atomic(pending, json.dumps(dict(entries=entries), indent=2).encode())
    try:
        for path, data in changed.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, data)
    except Exception:
        recover(home)
        raise
    pending.unlink()
    print(f'Installed {len(changed)} changes. Backups: {backup}')


def wizard(settings, models, language=None):
    language = language or input('Language / Sprache [en/de] (en): ').strip() or 'en'
    if language not in ('en', 'de'):
        raise ValueError('Language must be en or de')
    settings['language'] = language
    de = language == 'de'
    print(('Verfügbare Modelle: ' if de else 'Available models: ') + ', '.join(sorted(models)))
    for role, en, german in (('base', 'Base model', 'Basismodell'), ('advisor', 'Advisor model', 'Beratermodell')):
        key = role + '_model'
        settings[key] = input(f'{german if de else en} [{settings[key]}]: ').strip() or settings[key]
        levels = models.get(settings[key], [])
        print(('Denkstufen: ' if de else 'Reasoning efforts: ') + ', '.join(levels or ['availability unverified']))
        key = role + '_effort'
        settings[key] = input(f'{"Denkstufe" if de else "Effort"} [{settings[key]}]: ').strip() or settings[key]
    print(json.dumps(settings, indent=2))
    answer = input('Global installieren? [j/N]: ' if de else 'Install global defaults? [y/N]: ')
    if answer.lower() not in ('y', 'yes', 'j', 'ja'):
        raise ValueError('Cancelled; no changes made')
    return settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path)
    for key in ('base-model', 'base-effort', 'advisor-model', 'advisor-effort'):
        parser.add_argument('--' + key)
    parser.add_argument('--language', choices=['en', 'de'])
    for flag in ('defaults', 'reconfigure', 'dry-run', 'check', 'recover', 'list-models'):
        parser.add_argument('--' + flag, action='store_true')
    args = parser.parse_args(argv)
    home = (args.codex_home or Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))).expanduser().resolve()
    if args.check or args.dry_run or args.list_models:
        return execute(args, home)
    with installation_lock(home):
        return execute(args, home)


def execute(args, home):
    if args.recover:
        recover(home)
        return 0
    models = catalog(home)
    if args.list_models:
        print(json.dumps(models, indent=2))
        return 0
    path = home / 'codex-advisor' / 'settings.json'
    if args.check and not path.exists():
        raise ValueError('Not configured; run setup first')
    settings = json.loads(path.read_text()) if path.exists() and not args.defaults else DEFAULTS.copy()
    explicit = any(getattr(args, k) for k in ('base_model', 'base_effort', 'advisor_model', 'advisor_effort'))
    if not (args.defaults or args.check or args.dry_run) and (args.reconfigure or (not path.exists() and not explicit)):
        if not sys.stdin.isatty():
            raise ValueError('Interactive terminal required; use --defaults or explicit model/effort arguments')
        settings = wizard(settings, models, args.language)
    for key in DEFAULTS:
        if hasattr(args, key) and getattr(args, key) is not None:
            settings[key] = getattr(args, key)
    validate(settings, models)
    changes = outputs(home, settings)
    pending = home / 'codex-advisor' / 'pending.json'
    if pending.exists():
        raise ValueError('Interrupted installation: run --recover first')
    differences = [str(p) for p, d in changes.items() if read(p) != d]
    if args.check or args.dry_run:
        print(json.dumps(dict(settings=settings, changes=differences), indent=2))
        return int(args.check and bool(differences))
    apply(home, changes)
    print('Restart/open a new Codex session. Explicit session/project settings may override defaults.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(2)
