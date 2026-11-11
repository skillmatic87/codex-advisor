"""Synthetic accounting fixtures only: no real prompts, credentials or chat history."""
import contextlib
from datetime import date
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('advisor_stats', Path(__file__).resolve().parents[1] / 'scripts/stats.py')
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


def usage(input_tokens, output_tokens, cached=0, reasoning=0):
    return dict(input_tokens=input_tokens, cached_input_tokens=cached, cache_write_input_tokens=0,
                output_tokens=output_tokens, reasoning_output_tokens=reasoning, total_tokens=input_tokens + output_tokens)


def event(kind, when, **payload):
    return dict(type='event_msg', timestamp=when, payload=dict(type=kind, **payload))


def token(when, total, last=None):
    return event('token_count', when, info=dict(total_token_usage=total, last_token_usage=last if last is not None else total))


def context(when, turn='turn1', model='advisor-A', effort='high'):
    return dict(type='turn_context', timestamp=when, payload=dict(turn_id=turn, model=model, effort=effort))


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='advisor stats ü ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()

    def log(self, thread='thread1', folder='sessions', role='codex_advisor', path='/root/codex_advisor_test',
            parent='chat1', created='2026-01-01T12:00:00Z', records=None, **extra):
        meta = dict(id=thread, timestamp=created, agent_role=role, agent_path=path,
                    source=dict(subagent=dict(thread_spawn=dict(parent_thread_id=parent,
                        agent_role=role, agent_path=path))), **extra)
        records = records if records is not None else [
            event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'),
            token('2026-01-01T12:00:03Z', usage(100, 10, 80, 3)),
            event('task_complete', '2026-01-01T12:00:04Z', turn_id='turn1')]
        dest = self.home / folder / (thread + '.jsonl')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('\n'.join(json.dumps(e) for e in [dict(type='session_meta', payload=meta), *records]) + '\n', encoding='utf-8')
        return dest

    def test_totals_subsets_and_classification(self):
        self.log()
        self.log('ambiguous', role=None, path='/root/advisor_old')
        self.log('unrelated', role='worker', path='/root/work')
        self.log('ancestor', role=None, path='/root/codex_advisor_parent/worker')
        result = s.report(self.home)
        self.assertEqual(result['summary']['advisor_threads'], 1)
        self.assertEqual(result['summary']['rounds_started'], 1)
        self.assertEqual(result['summary']['ambiguous_threads'], 1)
        self.assertEqual(result['summary']['usage'], usage(100, 10, 80, 3))
        self.assertEqual(result['summary']['coverage'], 'complete')

    def test_reserved_path_and_legacy_role(self):
        self.log(role=None)
        self.log('legacy', role='astra_advisor', path='/root/old')
        self.assertEqual(s.report(self.home)['summary']['advisor_threads'], 2)

    def test_duplicate_files_and_snapshots(self):
        file = self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(100, 10)),
            token('2026-01-01T12:00:04Z', usage(100, 10)),
            token('2026-01-01T12:00:05Z', usage(150, 15), usage(50, 5)),
            event('task_complete', '2026-01-01T12:00:06Z', turn_id='turn1')])
        other = self.home / 'archived_sessions/copy.jsonl'
        other.parent.mkdir()
        other.write_bytes(file.read_bytes())
        result = s.report(self.home)
        self.assertEqual(result['summary']['usage']['total_tokens'], 165)
        self.assertEqual(result['summary']['rounds_started'], 1)
        self.assertGreater(result['diagnostics']['duplicate_records'], 0)

    def test_followup_model_and_date_filter_after_baseline(self):
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(100, 10)),
            event('task_complete', '2026-01-01T12:00:04Z', turn_id='turn1'),
            event('task_started', '2026-01-02T12:00:01Z', turn_id='turn2'),
            context('2026-01-02T12:00:02Z', turn='turn2', model='advisor-B'),
            token('2026-01-02T12:00:03Z', usage(150, 15), usage(50, 5))])
        result = s.report(self.home, date(2026, 1, 2), date(2026, 1, 2), model_filter='advisor-B', group_by='day')
        self.assertEqual(result['summary']['usage']['total_tokens'], 55)
        self.assertEqual(result['summary']['rounds_started'], 1)
        self.assertEqual(result['summary']['running_rounds'], 1)
        self.assertEqual(result['groups'][0]['group'], '2026-01-02')
        all_result = s.report(self.home, group_by='model')
        self.assertEqual(all_result['summary']['rounds_started'], 2)
        self.assertEqual({r['group'] for r in all_result['groups']}, {'advisor-A', 'advisor-B'})

    def test_missing_followup_context_does_not_inherit_model(self):
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(100, 10)),
            event('task_complete', '2026-01-01T12:00:04Z', turn_id='turn1'),
            event('task_started', '2026-01-01T12:00:05Z', turn_id='turn2'),
            token('2026-01-01T12:00:06Z', usage(150, 15), usage(50, 5))])
        result = s.report(self.home, group_by='model')
        groups = {row['group']: row for row in result['groups']}
        self.assertEqual(groups['advisor-A']['usage']['total_tokens'], 110)
        self.assertEqual(groups['unknown']['usage']['total_tokens'], 55)
        self.assertEqual(result['summary']['coverage'], 'partial')

    def test_missing_fork_creation_excludes_unassignable_history(self):
        self.log(created=None, forked_from_id='parent', records=[
            event('task_started', '2026-01-01T12:00:01Z', turn_id='inherited'),
            context('2026-01-01T12:00:02Z', turn='inherited'),
            token('2026-01-01T12:00:03Z', usage(100, 10)),
            token('2026-01-01T12:00:04Z', usage(150, 15))])
        result = s.report(self.home)
        self.assertIsNone(result['summary']['usage']['total_tokens'])
        self.assertEqual(result['summary']['rounds_started'], 0)
        self.assertEqual(result['summary']['incomplete_threads'], 1)

    def test_malformed_nested_metadata_does_not_abort_report(self):
        self.log()
        self.log('bad', role={'unexpected': []}, path='', parent={'bad': 'shape'}, records=[])
        file = self.home / 'sessions/bad.jsonl'
        record = json.loads(file.read_text().splitlines()[0])
        record['payload']['source'] = {'subagent': {'thread_spawn': None}}
        file.write_text(json.dumps(record) + '\n')
        result = s.report(self.home)
        self.assertEqual(result['summary']['advisor_threads'], 1)
        self.assertEqual(result['diagnostics']['malformed_metadata_shapes'], 1)

    def test_other_subagent_source_is_valid_and_unrelated(self):
        self.log()
        other = self.log('guardian', role=None, path='', records=[])
        meta = json.loads(other.read_text().splitlines()[0])
        meta['payload']['source'] = {'subagent': {'other': 'guardian'}}
        other.write_text(json.dumps(meta) + '\n')
        result = s.report(self.home)
        self.assertEqual(result['summary']['advisor_threads'], 1)
        self.assertEqual(result['summary']['coverage'], 'complete')

    def test_unknown_timestamp_cannot_disappear_from_filtered_coverage(self):
        self.log(created=None, records=[])
        result = s.report(self.home, date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(result['diagnostics']['unplaced_threads'], 1)
        self.assertEqual(result['summary']['coverage'], 'partial')

    def test_unknown_initial_baseline_not_counted(self):
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(1000, 100), usage(100, 10)),
            token('2026-01-01T12:00:04Z', usage(1050, 105), usage(50, 5))])
        result = s.report(self.home)
        self.assertEqual(result['summary']['usage']['total_tokens'], 55)
        self.assertEqual(result['summary']['coverage'], 'partial')
        self.assertEqual(result['threads'][0]['issues']['unknown_baseline'], 1)

    def test_fork_excludes_inherited_prefix(self):
        self.log(created='2026-01-02T12:00:00Z', records=[
            event('task_started', '2026-01-01T12:00:01Z', turn_id='parent-turn'),
            token('2026-01-01T12:00:03Z', usage(100, 10)),
            event('task_started', '2026-01-02T12:00:01Z', turn_id='turn1'),
            context('2026-01-02T12:00:02Z'),
            token('2026-01-02T12:00:03Z', usage(150, 15), usage(50, 5))])
        result = s.report(self.home)
        self.assertEqual(result['summary']['rounds_started'], 1)
        self.assertEqual(result['summary']['usage']['total_tokens'], 55)

    def test_fork_without_boundary_is_partial(self):
        self.log(forked_from_id='other', records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(100, 10))])
        result = s.report(self.home)
        self.assertIsNone(result['summary']['usage']['total_tokens'])
        self.assertEqual(result['summary']['coverage'], 'partial')

    def test_counter_discontinuity_skips_whole_interval(self):
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(100, 10, 80)),
            token('2026-01-01T12:00:04Z', usage(200, 20, 0)),
            token('2026-01-01T12:00:05Z', usage(250, 25, 10))])
        result = s.report(self.home)
        self.assertEqual(result['summary']['usage']['total_tokens'], 165)
        self.assertEqual(result['threads'][0]['issues']['counter_discontinuities'], 1)

    def test_missing_tokens_corrupt_line_and_running_round(self):
        path = self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
                                context('2026-01-01T12:00:02Z')])
        with path.open('a') as stream:
            stream.write('{invalid\n')
        result = s.report(self.home, model_filter='advisor-A')
        self.assertEqual(result['summary']['running_rounds'], 1)
        self.assertIsNone(result['summary']['usage']['total_tokens'])
        self.assertEqual(result['diagnostics']['malformed_event_lines'], 1)

    def test_unknown_optional_token_fields_are_not_zero(self):
        raw = usage(100, 10)
        del raw['cached_input_tokens']
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', raw)])
        result = s.report(self.home)
        self.assertIsNone(result['summary']['usage']['cached_input_tokens'])
        self.assertEqual(result['summary']['usage']['total_tokens'], 110)
        self.assertEqual(result['summary']['coverage'], 'partial')

    def test_chat_root_filter_archived_and_no_writes(self):
        self.log('chat1', role=None, path='', parent=None, records=[])
        self.log('advisor1', folder='archived_sessions')
        self.log('other', parent='other-chat')
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.home.rglob('*') if p.is_file()}
        result = s.report(self.home, chat='chat1', group_by='chat')
        self.assertEqual(result['summary']['advisor_threads'], 1)
        self.assertEqual(result['groups'][0]['group'], 'chat1')
        self.assertEqual(before, {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.home.rglob('*') if p.is_file()})

    def test_json_cli_language_and_content_exclusion(self):
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(100, 10)),
            dict(type='response_item', payload=dict(text='PRIVATE-PROMPT-MUST-NOT-EXPORT'))])
        cli = subprocess.run([sys.executable, str(Path(s.__file__)),
                              '--codex-home', str(self.home), '--json'], capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        result = json.loads(cli.stdout)
        self.assertEqual(result['summary']['usage']['total_tokens'], 110)
        self.assertNotIn('PRIVATE-PROMPT', cli.stdout)
        self.assertIn('Berater-Threads: 1', s.render(result, 'de'))
        self.assertIn('Advisor threads: 1', s.render(result, 'en'))

    def test_zero_usage_is_distinct_from_unknown(self):
        self.log(records=[event('task_started', '2026-01-01T12:00:01Z', turn_id='turn1'),
            context('2026-01-01T12:00:02Z'), token('2026-01-01T12:00:03Z', usage(0, 0))])
        result = s.report(self.home)
        self.assertEqual(result['summary']['usage']['total_tokens'], 0)
        self.assertEqual(result['summary']['coverage'], 'complete')

    def test_invalid_dates_and_codex_home_environment(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            s.main(['--since', '2026-01-02', '--until', '2026-01-01'])
        self.log()
        out = io.StringIO()
        with patch.dict(os.environ, CODEX_HOME=str(self.home)), contextlib.redirect_stdout(out):
            self.assertEqual(s.main(['--json']), 0)
        self.assertEqual(json.loads(out.getvalue())['summary']['advisor_threads'], 1)

    def test_midnight_uses_local_date_not_utc(self):
        self.log()
        # Stub calendar conversion to exercise the filter boundary independent of runner timezone.
        with patch.object(s, 'local_date', return_value=date(2026, 1, 2)):
            result = s.report(self.home, date(2026, 1, 2), date(2026, 1, 2), group_by='day')
        self.assertEqual(result['summary']['usage']['total_tokens'], 110)
        self.assertEqual(result['groups'][0]['group'], '2026-01-02')


if __name__ == '__main__':
    unittest.main()
