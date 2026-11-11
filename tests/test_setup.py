import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import tomllib

SPEC = importlib.util.spec_from_file_location('advisor_setup', Path(__file__).resolve().parents[1] / 'scripts/setup.py')
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='advisor space ü ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def run_setup(self, *args):
        return s.main(['--codex-home', str(self.home), *args])

    def test_clean_idempotent_and_update(self):
        self.assertEqual(self.run_setup('--defaults'), 0)
        before = {p: p.stat().st_mtime_ns for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(self.run_setup('--check'), 0)
        self.run_setup()
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.home.rglob('*') if p.is_file()})
        cfg = tomllib.loads((self.home / 'config.toml').read_text())
        self.assertEqual(cfg['model_reasoning_effort'], 'medium')

    def test_custom_selection_preserves_comments_profiles_and_settings(self):
        (self.home / 'config.toml').write_text('# keep me\nmodel = "old" # model comment\n[profiles.work]\nmodel = "other"\n')
        (self.home / 'AGENTS.md').write_text('Unrelated instructions.\n')
        self.run_setup('--base-model', 'custom', '--base-effort', 'low', '--advisor-model', 'other', '--advisor-effort', 'xhigh')
        text = (self.home / 'config.toml').read_text()
        self.assertIn('# keep me', text)
        self.assertIn('# model comment', text)
        self.assertEqual(tomllib.loads(text)['profiles']['work']['model'], 'other')
        self.assertTrue((self.home / 'AGENTS.md').read_text().startswith('Unrelated instructions.'))
        self.run_setup()
        settings = json.loads((self.home / 'codex-advisor/settings.json').read_text())
        self.assertEqual(settings['base_model'], 'custom')

    def test_legacy_migration(self):
        (self.home / 'AGENTS.md').write_bytes((s.ROOT / 'references/legacy-AGENTS.md').read_bytes())
        (self.home / 'agents').mkdir()
        (self.home / 'agents/astra-advisor.toml').write_bytes((s.ROOT / 'references/legacy-astra-advisor.toml').read_bytes())
        self.run_setup('--defaults')
        self.assertFalse((self.home / 'agents/astra-advisor.toml').exists())
        self.assertEqual((self.home / 'AGENTS.md').read_text().count(s.BEGIN), 1)
        self.assertEqual(self.run_setup('--check'), 0)

    def test_custom_legacy_conflict_no_writes(self):
        (self.home / 'AGENTS.md').write_text('# Automatic Astra advisor\nMy custom rule')
        with self.assertRaises(ValueError):
            self.run_setup('--defaults')
        self.assertFalse((self.home / 'config.toml').exists())

    def test_bad_toml_and_dry_run(self):
        self.run_setup('--defaults', '--dry-run')
        self.assertEqual(list(self.home.iterdir()), [])
        (self.home / 'config.toml').write_text('invalid = [')
        with self.assertRaises(Exception):
            self.run_setup('--defaults')
        self.assertFalse((self.home / 'codex-advisor/settings.json').exists())

    def test_model_effort_validation(self):
        with self.assertRaises(ValueError):
            s.validate(s.DEFAULTS, {'gpt-6.1-sol': ['low']})
        with self.assertRaises(ValueError):
            s.validate(dict(s.DEFAULTS, advisor_effort='bogus'), {})

    def test_wizard_german_and_cancel(self):
        answers = ['de', 'custom-base', 'low', 'custom-advisor', 'xhigh', 'j']
        with patch('builtins.input', side_effect=answers):
            settings = s.wizard(s.DEFAULTS.copy(), {})
        self.assertEqual(settings['language'], 'de')
        self.assertEqual(settings['advisor_model'], 'custom-advisor')
        self.assertEqual(settings['advisor_effort'], 'xhigh')
        with patch('builtins.input', side_effect=['en', '', '', '', '', 'n']):
            with self.assertRaises(ValueError):
                s.wizard(s.DEFAULTS.copy(), {})
        self.assertFalse((self.home / 'config.toml').exists())

    def test_copy_only_install_then_setup(self):
        installed = self.home / 'skills/codex-advisor'
        installed.mkdir(parents=True)
        (installed / 'SKILL.md').write_bytes((s.ROOT / 'SKILL.md').read_bytes())
        self.assertFalse((self.home / 'codex-advisor/settings.json').exists())
        self.run_setup('--base-model', 'gpt-6.1-sol', '--base-effort', 'medium',
                       '--advisor-model', 'gpt-6-astra', '--advisor-effort', 'high')
        result = subprocess.run([sys.executable, str(installed / 'scripts/setup.py'),
                                 '--codex-home', str(self.home), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_interrupted_install_rolls_back(self):
        (self.home / 'config.toml').write_text('# original\n')
        original = s.atomic
        def interrupt(path, data):
            if path == self.home / 'agents/codex-advisor.toml':
                raise KeyboardInterrupt()
            original(path, data)

        with patch.object(s, 'atomic', interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_setup('--defaults')
        self.assertTrue((self.home / 'codex-advisor/pending.json').exists())
        with self.assertRaises(ValueError):
            self.run_setup('--defaults')
        self.run_setup('--recover')
        self.assertEqual((self.home / 'config.toml').read_text(), '# original\n')
        self.assertFalse((self.home / 'agents/codex-advisor.toml').exists())

    def test_recovery_preserves_later_edits(self):
        pending = self.home / 'codex-advisor/pending.json'
        pending.parent.mkdir()
        target = self.home / 'config.toml'
        target.write_text('later edit')
        pending.write_text(json.dumps({'entries': [dict(path=str(target), backup=None, before=None, after='different')]}))
        with self.assertRaises(ValueError):
            self.run_setup('--recover')
        self.assertEqual(target.read_text(), 'later edit')

    def test_legacy_crlf_bom_with_other_instructions(self):
        legacy = (s.ROOT / 'references/legacy-AGENTS.md').read_text().strip()
        original = 'Before.\r\n' + legacy.replace('\n', '\r\n') + '\r\nAfter.\r\n'
        (self.home / 'AGENTS.md').write_bytes(b'\xef\xbb\xbf' + original.encode())
        self.run_setup('--defaults')
        actual = (self.home / 'AGENTS.md').read_bytes().decode()
        self.assertTrue(actual.startswith('Before.\r\n'))
        self.assertTrue(actual.endswith('\r\nAfter.\r\n'))
        self.assertNotIn('# Automatic Astra advisor', actual)

    def test_two_process_lock_prevents_install(self):
        with s.installation_lock(self.home):
            result = subprocess.run([sys.executable, str(s.ROOT / 'scripts/setup.py'),
                                     '--codex-home', str(self.home), '--defaults'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Another installer', result.stderr)
            self.assertFalse((self.home / 'config.toml').exists())
        self.run_setup('--defaults')
        self.assertEqual(self.run_setup('--check'), 0)

    def test_damaged_backup_leaves_every_target_untouched(self):
        target = self.home / 'config.toml'
        target.write_text('current')
        backup = self.home / 'damaged-backup'
        backup.write_text('')
        pending = self.home / 'codex-advisor/pending.json'
        pending.parent.mkdir()
        pending.write_text(json.dumps({'entries': [dict(path=str(target), backup=str(backup),
                           before=s.digest(b'original'), after=s.digest(b'current'))]}))
        with self.assertRaises(ValueError):
            self.run_setup('--recover')
        self.assertEqual(target.read_text(), 'current')
        self.assertTrue(pending.exists())
        backup.unlink()
        with self.assertRaises(OSError):
            self.run_setup('--recover')
        self.assertEqual(target.read_text(), 'current')
        self.assertTrue(pending.exists())

    def test_codex_home_environment(self):
        with patch.dict(os.environ, CODEX_HOME=str(self.home)):
            self.assertEqual(s.main(['--defaults']), 0)
        self.assertTrue((self.home / 'codex-advisor/settings.json').exists())

    def test_missing_settings_check_and_role_divergence(self):
        with self.assertRaises(ValueError):
            self.run_setup('--check')
        self.run_setup('--defaults')
        path = self.home / 'agents/codex-advisor.toml'
        path.write_text(path.read_text().replace('gpt-6-astra', 'gpt-6.1-sol'))
        self.assertEqual(self.run_setup('--check'), 1)
        self.run_setup()
        self.assertEqual(self.run_setup('--check'), 0)


if __name__ == '__main__':
    unittest.main()
