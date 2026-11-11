"""Read-only advisor usage statistics from local Codex JSONL session logs (Python 3.11+)."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

FIELDS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
          'output_tokens', 'reasoning_output_tokens', 'total_tokens')
ROLES = {'codex_advisor', 'astra_advisor'}
ZERO = {field: 0 for field in FIELDS}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def local_date(value):
    # datetime.astimezone() uses the system's historical DST rules for each date.
    return value.astimezone().date()


def identity(meta):
    source = meta.get('source')
    spawn = source.get('subagent', {}).get('thread_spawn', {}) if isinstance(source, dict) and isinstance(source.get('subagent'), dict) else {}
    if not isinstance(spawn, dict):
        spawn = {}
    role = meta.get('agent_role') or spawn.get('agent_role')
    path = meta.get('agent_path') or spawn.get('agent_path') or ''
    own_name = path.rstrip('/').rsplit('/', 1)[-1] if isinstance(path, str) else ''
    parent = meta.get('parent_thread_id') or spawn.get('parent_thread_id')
    parent = parent if isinstance(parent, str) else None
    if isinstance(role, str) and role in ROLES:
        return 'confirmed', f'role:{role}', parent
    if own_name.startswith('codex_advisor_'):
        return 'confirmed', 'reserved_task_prefix', parent
    if own_name.startswith('advisor_') or (isinstance(role, str) and 'advisor' in role.lower()):
        return 'ambiguous', 'historical_name_only', parent
    return 'unrelated', None, parent


def metadata(path, diagnostics):
    try:
        with path.open(encoding='utf-8-sig', errors='replace') as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except (ValueError, TypeError):
                    diagnostics['malformed_metadata_lines'] += 1
                    continue
                if isinstance(item, dict) and item.get('type') == 'session_meta' and isinstance(item.get('payload'), dict):
                    payload = item['payload']
                    if isinstance(payload.get('id'), str):
                        source = payload.get('source')
                        spawn = source.get('subagent', {}).get('thread_spawn', {}) if isinstance(source, dict) and isinstance(source.get('subagent'), dict) else {}
                        if not isinstance(spawn, dict) or any(payload.get(key) is not None and not isinstance(payload[key], str) for key in ('agent_role', 'agent_path', 'parent_thread_id')):
                            diagnostics['malformed_metadata_shapes'] += 1
                        return payload
                if number >= 50:
                    break
    except OSError:
        diagnostics['unreadable_files'] += 1
        return None
    diagnostics['files_without_metadata'] += 1
    return None


def slim_event(item):
    """Discard prompts, tool arguments, responses and all other chat content."""
    if not isinstance(item, dict):
        return None
    payload = item.get('payload')
    if not isinstance(payload, dict):
        return None
    if item.get('type') == 'turn_context':
        return dict(timestamp=item.get('timestamp'), kind='context', turn_id=payload.get('turn_id'),
                    model=payload.get('model'), effort=payload.get('effort'))
    if item.get('type') != 'event_msg':
        return None
    kind = payload.get('type')
    if kind in ('task_started', 'task_complete', 'task_completed', 'turn_aborted'):
        return dict(timestamp=item.get('timestamp'), kind=kind, turn_id=payload.get('turn_id'))
    if kind == 'token_count':
        info = payload.get('info')
        # Rate-limit notifications with info=null carry no token observation.
        if not isinstance(info, dict):
            return None
        return dict(timestamp=item.get('timestamp'), kind=kind,
                    total=info.get('total_token_usage'), last=info.get('last_token_usage'))
    return None


def events(paths, diagnostics):
    """Read linewise; keep only minimal accounting records, dedup copied histories."""
    seen, result = set(), []
    for path in sorted(paths):
        try:
            with path.open(encoding='utf-8-sig', errors='replace') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        record = slim_event(json.loads(line))
                    except (ValueError, TypeError):
                        diagnostics['malformed_event_lines'] += 1
                        continue
                    if record is None:
                        continue
                    when = timestamp(record['timestamp'])
                    if when is None:
                        diagnostics['invalid_timestamps'] += 1
                        continue
                    key = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).digest()
                    if key in seen:
                        diagnostics['duplicate_records'] += 1
                        continue
                    seen.add(key)
                    record['when'] = when
                    result.append(record)
        except OSError:
            diagnostics['unreadable_files'] += 1
    return sorted(result, key=lambda event: event['when'])


def counters(raw):
    if not isinstance(raw, dict):
        return None
    result = {field: raw.get(field) for field in FIELDS}
    for value in result.values():
        if value is not None and (type(value) is not int or value < 0):
            return None
    if result['total_tokens'] is None:
        return None
    return result


def parse_thread(meta, paths, diagnostics):
    identification, evidence, parent = identity(meta)
    created = timestamp(meta.get('timestamp'))
    issues = Counter()
    if created is None:
        issues['unknown_creation_time'] += 1
        # Without a boundary, copied/forked history cannot be assigned to this thread.
        return dict(id=meta['id'], parent_id=parent, identification=identification, evidence=evidence,
                    created=None, turns={}, observations=[], issues=dict(issues))
    forked = any(meta.get(key) for key in ('forked_from_id', 'forked_from', 'forked_from_thread_id'))
    previous, active, model, effort = None, None, None, None
    turns, observations = {}, []
    inherited = False
    history = events(paths, diagnostics)
    for event in history:
        kind, when = event['kind'], event['when']
        if created and when < created:
            inherited = True
            if kind == 'token_count':
                previous = counters(event['total'])
            continue
        turn_id = event.get('turn_id')
        if kind == 'task_started':
            if not isinstance(turn_id, str):
                issues['missing_turn_id'] += 1
                active = None
                continue
            active = turn_id
            if turn_id not in turns:
                model, effort = None, None
                turns[turn_id] = dict(id=turn_id, started_at=when, status='running', models=set())
            elif turns[turn_id]['started_at'] is None:
                turns[turn_id]['started_at'] = when
                turns[turn_id]['status'] = 'running'
        elif kind == 'context':
            model = event['model'] if isinstance(event['model'], str) else None
            effort = event['effort'] if isinstance(event['effort'], str) else None
            if isinstance(turn_id, str):
                active = turn_id
                # Context identifies a round, but does not prove its start was recorded.
                turn = turns.setdefault(turn_id, dict(id=turn_id, started_at=None, status='unknown', models=set()))
                if model:
                    turn['models'].add(model)
        elif kind in ('task_complete', 'task_completed', 'turn_aborted'):
            target = turn_id if isinstance(turn_id, str) else active
            if target in turns:
                turns[target]['status'] = 'aborted' if kind == 'turn_aborted' else 'completed'
            if target == active:
                active = None
        elif kind == 'token_count':
            current = counters(event['total'])
            if current is None:
                issues['invalid_counters'] += 1
                previous = None
                inherited = True
                continue
            missing = [field for field in FIELDS if current[field] is None]
            if missing:
                issues['missing_token_fields'] += 1
            if previous is None:
                last = counters(event['last'])
                fresh = (not forked and not inherited and created is not None and active in turns
                         and turns[active]['started_at'] is not None and current == last)
                baseline = ZERO if fresh else None
                if baseline is None:
                    issues['unknown_baseline'] += 1
            else:
                baseline = previous
                if any(current[f] is not None and baseline[f] is not None and current[f] < baseline[f] for f in FIELDS):
                    issues['counter_discontinuities'] += 1
                    baseline = None
            if baseline is not None:
                delta = {field: current[field] - baseline[field]
                         if current[field] is not None and baseline[field] is not None else None for field in FIELDS}
                if any(value for value in delta.values() if value is not None) or not any(o['turn_id'] == active for o in observations):
                    if model is None:
                        issues['unknown_model_attribution'] += 1
                    if active is None:
                        issues['unknown_turn_attribution'] += 1
                    observations.append(dict(when=when, turn_id=active, model=model, effort=effort, usage=delta))
            previous = current
            # Only the first observed snapshot is eligible for the fresh-start rule.
            inherited = True
    for turn in turns.values():
        if not any(o['turn_id'] == turn['id'] for o in observations):
            issues['rounds_without_usage'] += 1
    return dict(id=meta['id'], parent_id=parent, identification=identification, evidence=evidence,
                created=created, turns=turns, observations=observations, issues=dict(issues))


def sum_usage(observations):
    if not observations:
        return {field: None for field in FIELDS}
    return {field: sum(o['usage'][field] for o in observations if o['usage'][field] is not None)
            if any(o['usage'][field] is not None for o in observations) else None for field in FIELDS}


def in_period(when, since, until):
    if when is None:
        return since is None and until is None
    day = local_date(when)
    return (since is None or day >= since) and (until is None or day <= until)


def report(home, since=None, until=None, chat=None, model_filter=None, group_by=None):
    diagnostics = Counter()
    sessions = {}
    for folder in ('sessions', 'archived_sessions'):
        root = home / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob('*.jsonl')):
            meta = metadata(path, diagnostics)
            if meta:
                entry = sessions.setdefault(meta['id'], dict(meta=meta, paths=[]))
                entry['paths'].append(path)
    diagnostics['files_scanned'] = sum(len(s['paths']) for s in sessions.values())

    def root_chat(thread_id):
        seen = set()
        while thread_id in sessions and thread_id not in seen:
            seen.add(thread_id)
            parent = identity(sessions[thread_id]['meta'])[2]
            if not parent:
                break
            thread_id = parent
        return thread_id

    selected, ambiguous, groups = [], [], defaultdict(lambda: dict(threads=set(), rounds=set(), observations=[]))
    for thread_id, item in sorted(sessions.items()):
        kind, evidence, parent = identity(item['meta'])
        if kind == 'unrelated':
            continue
        root_id = root_chat(thread_id)
        if chat and chat not in (root_id, parent, thread_id):
            continue
        thread = parse_thread(item['meta'], item['paths'], diagnostics)
        filtered = [o for o in thread['observations'] if in_period(o['when'], since, until)
                    and (model_filter is None or o['model'] == model_filter)]
        rounds = [t for t in thread['turns'].values() if in_period(t['started_at'], since, until)]
        if model_filter:
            model_turns = {t['id'] for t in thread['turns'].values() if model_filter in t['models']}
            rounds = [t for t in rounds if t['id'] in model_turns]
        if not filtered and not rounds and (since or until or model_filter):
            if 'unknown_creation_time' in thread['issues']:
                diagnostics['unplaced_threads'] += 1
            continue
        row = dict(thread_id=thread_id, chat_id=root_id, identification=kind,
                   evidence=evidence, rounds_started=sum(t['started_at'] is not None for t in rounds),
                   rounds_without_start=sum(t['started_at'] is None for t in rounds),
                   running_rounds=sum(t['status'] == 'running' for t in rounds),
                   coverage='partial' if thread['issues'] else 'complete', issues=thread['issues'],
                   usage=sum_usage(filtered))
        if kind == 'ambiguous':
            ambiguous.append(row)
            continue
        selected.append(row)
        for observation in filtered:
            key = (str(local_date(observation['when'])) if group_by == 'day' else
                   root_id if group_by == 'chat' else observation['model'] or 'unknown' if group_by == 'model' else 'all')
            group = groups[key]
            group['threads'].add(thread_id)
            group['observations'].append(observation)
        for turn in rounds:
            if turn['started_at'] is None:
                continue
            if group_by == 'model':
                keys = {m for m in turn['models'] if model_filter is None or m == model_filter} or {'unknown'}
            else:
                keys = {str(local_date(turn['started_at'])) if group_by == 'day' else root_id if group_by == 'chat' else 'all'}
            for key in keys:
                groups[key]['threads'].add(thread_id)
                groups[key]['rounds'].add((thread_id, turn['id']))
    rows = [dict(group=key, advisor_threads=len(value['threads']), rounds_started=len(value['rounds']),
                 usage=sum_usage(value['observations'])) for key, value in sorted(groups.items())]
    usages = [dict(usage=row['usage']) for row in selected if any(v is not None for v in row['usage'].values())]
    incomplete = sum(row['coverage'] != 'complete' for row in selected)
    return dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                source='local_codex_jsonl', timezone=dict(name=str(datetime.now().astimezone().tzinfo),
                policy='system_local_calendar_dates_with_historical_DST'),
                attribution=dict(tokens='usage_event_time', rounds='recorded_start_time', until='inclusive_calendar_day'),
                filters=dict(since=str(since) if since else None, until=str(until) if until else None,
                             chat=chat, model=model_filter, group_by=group_by),
                summary=dict(advisor_threads=len(selected), rounds_started=sum(r['rounds_started'] for r in selected),
                running_rounds=sum(r['running_rounds'] for r in selected),
                incomplete_threads=incomplete, ambiguous_threads=len(ambiguous),
                coverage='partial' if incomplete or any(diagnostics[k] for k in ('malformed_metadata_lines', 'malformed_metadata_shapes', 'malformed_event_lines', 'unreadable_files', 'files_without_metadata', 'invalid_timestamps', 'unplaced_threads')) else 'complete',
                usage=sum_usage(usages)), groups=rows, threads=selected, ambiguous=ambiguous,
                diagnostics=dict(diagnostics))


TEXT = {
    'en': dict(title='Codex Advisor usage', threads='Advisor threads', rounds='Rounds started', running='Running rounds',
               incomplete='Incomplete threads', ambiguous='Ambiguous historical threads (excluded)',
               period='Period', all='all available history', observed='Observed tokens', timezone='Timezone',
               group='Group', input='Input', cached='Cached input', output='Output', total='Total',
               none='No confirmed advisor records found.', note='Cached input and reasoning are subsets, not additional tokens. No billing/plan estimate.',
               partial='Coverage is partial; unknown usage is not zero.', issues='Diagnostics'),
    'de': dict(title='Codex-Advisor-Nutzung', threads='Berater-Threads', rounds='Gestartete Beratungsrunden', running='Laufende Runden',
               incomplete='Unvollständig erfasste Threads', ambiguous='Unklare historische Threads (ausgeschlossen)',
               period='Zeitraum', all='gesamter verfügbarer Verlauf', observed='Beobachtete Tokens', timezone='Zeitzone',
               group='Gruppe', input='Eingabe', cached='Davon gecacht', output='Ausgabe', total='Gesamt',
               none='Keine bestätigten Advisor-Datensätze gefunden.', note='Cache- und Reasoning-Tokens sind Teilmengen. Keine Kosten- oder Abo-Schätzung.',
               partial='Erfassung unvollständig; unbekannte Nutzung ist nicht null.', issues='Diagnose')}


def render(result, language):
    labels, summary = TEXT[language], result['summary']
    number = lambda n: '?' if n is None else format(n, ',').replace(',', '.' if language == 'de' else ',')
    lines = [labels['title'], f"{labels['timezone']}: {result['timezone']['name']}",
             f"{labels['period']}: " + (labels['all'] if not result['filters']['since'] and not result['filters']['until']
                else f"{result['filters']['since'] or '...'} / {result['filters']['until'] or '...'}")]
    for key, label in (('advisor_threads', 'threads'), ('rounds_started', 'rounds'), ('running_rounds', 'running'),
                       ('incomplete_threads', 'incomplete'), ('ambiguous_threads', 'ambiguous')):
        lines.append(f'{labels[label]}: {summary[key]}')
    lines.append(labels['observed'])
    headings = [labels[k] for k in ('group', 'threads', 'rounds', 'input', 'cached', 'output', 'total')]
    lines.append(' | '.join(headings))
    values = [('ALL', summary['advisor_threads'], summary['rounds_started'], summary['usage'])]
    if result['filters']['group_by']:
        values += [(r['group'], r['advisor_threads'], r['rounds_started'], r['usage']) for r in result['groups']]
    for key, threads, rounds, usage in values:
        lines.append(' | '.join([key, str(threads), str(rounds)] + [number(usage[f]) for f in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens')]))
    lines.append(f"Reasoning: {number(summary['usage']['reasoning_output_tokens'])}")
    if summary['coverage'] != 'complete':
        lines.append(labels['partial'])
    if not summary['advisor_threads']:
        lines.append(labels['none'])
    if result['ambiguous']:
        lines.extend(f"? {row['thread_id']} ({row['evidence']})" for row in result['ambiguous'])
    diagnostic = {k: v for k, v in result['diagnostics'].items() if v and k != 'files_scanned'}
    if diagnostic:
        lines.append(f"{labels['issues']}: {json.dumps(diagnostic)}")
    lines.append(labels['note'])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path)
    parser.add_argument('--since', type=date.fromisoformat)
    parser.add_argument('--until', type=date.fromisoformat)
    parser.add_argument('--chat')
    parser.add_argument('--model')
    parser.add_argument('--group-by', choices=['day', 'chat', 'model'])
    parser.add_argument('--language', choices=['de', 'en'])
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.since and args.until and args.since > args.until:
        parser.error('--since must not be after --until')
    home = (args.codex_home or Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))).expanduser().resolve()
    language = args.language
    if not language:
        try:
            language = json.loads((home / 'codex-advisor/settings.json').read_text(encoding='utf-8-sig')).get('language')
        except (ValueError, OSError, AttributeError):
            pass
    result = report(home, args.since, args.until, args.chat, args.model, args.group_by)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result, language if language in TEXT else 'en'))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(2)
