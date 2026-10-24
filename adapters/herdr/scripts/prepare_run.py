#!/usr/bin/env python3
"""Validate, render or verify local handoff artifacts; never dispatch or authorize."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

DEFAULTS = {
    'version': 1, 'operation': 'implement', 'delivery': 'implementation',
    'control': 'dispatch', 'base_branch': None, 'permission': 'inherit',
    'authority': {}, 'acceptance': [],
    'target': {'herdr_session': 'default'},
    'models': {'coordinator': 'gpt-6.1-sol', 'worker': 'claude-sonnet-5-5',
               'fallback_worker': 'gpt-6.1-sol', 'fallback_when': 'capacity',
               'reviewer': 'gpt-6-astra', 'effort': 'high', 'tier': 'default',
               'levels': 3, 'max_workers': 2},
    'limits': {'disk_reserve_gib': 8, 'pid_admission_fraction': 0.6,
               'max_heavy_jobs': 1, 'original_cutoff_utc': None,
               'checkpoint_seconds': 120},
    'escalation': {'route': 'manual-handoff'},
}
KEYS = set(DEFAULTS) | {'repository', 'scope'}
NESTED = {
    'authority': {'implementation', 'publish', 'merge', 'deploy', 'yolo',
                  'create_repository', 'stop', 'resume'},
    'target': {'ssh_host', 'container', 'herdr_session', 'pane',
               'native_session_uuid', 'account', 'cwd', 'goal_id'},
    'models': set(DEFAULTS['models']), 'limits': set(DEFAULTS['limits']),
    'escalation': {'owner', 'route', 'handoff_dir', 'capability_evidence'},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def string(value, name, nullable=False, limit=20000):
    if value is None and nullable:
        return
    require(isinstance(value, str) and bool(value.strip()), name + ' must be nonempty text')
    require(len(value) <= limit and '\x00' not in value, name + ' exceeds bounds or contains NUL')


def enum(value, name, choices):
    require(isinstance(value, str) and value in choices, name + ' must be one of ' + ', '.join(choices))


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def validate(raw):
    require(isinstance(raw, dict), 'configuration must be an object')
    require(not (set(raw) - KEYS), 'unknown fields: ' + ', '.join(sorted(set(raw) - KEYS)))
    config = copy.deepcopy(DEFAULTS)
    for key, value in raw.items():
        if key in NESTED:
            require(isinstance(value, dict), key + ' must be an object')
            require(not (set(value) - NESTED[key]), 'unknown ' + key + ' fields: ' + ', '.join(sorted(set(value) - NESTED[key])))
            config[key].update(value)
        else:
            config[key] = value
    require(type(config['version']) is int and config['version'] == 1, 'unsupported configuration version')
    for name in ('repository', 'scope'):
        string(config.get(name), name)
    repo = config['repository']
    if repo.startswith('https://github.com/'):
        repo = repo.removeprefix('https://github.com/').rstrip('/')
    if repo.endswith('.git'):
        repo = repo[:-4]
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repo)), 'repository must be owner/name or a GitHub HTTPS repository URL')
    config['repository'] = repo
    enum(config['operation'], 'operation', ('bootstrap', 'implement', 'sync-merge', 'recover', 'stop', 'deploy'))
    if 'delivery' not in raw:
        config['delivery'] = {'bootstrap': 'triage', 'stop': 'triage', 'sync-merge': 'merge', 'deploy': 'deploy'}.get(config['operation'], 'implementation')
    enum(config['delivery'], 'delivery', ('triage', 'implementation', 'pr', 'merge', 'deploy'))
    enum(config['control'], 'control', ('dispatch', 'supervise'))
    enum(config['permission'], 'permission', ('inherit', 'workspace', 'yolo'))
    string(config['base_branch'], 'base_branch', nullable=True, limit=1000)
    for key, value in config['authority'].items():
        string(value, 'authority.' + key, nullable=True)
        if value:
            require(not re.search(r'example only|replace with|\bTODO\b', value, re.I), 'replace example authorization with actual user evidence: ' + key)
    needed = set()
    op, delivery = config['operation'], config['delivery']
    if op == 'bootstrap':
        needed.add('create_repository')
    if op == 'recover':
        needed.add('resume')
    if op == 'stop':
        require(delivery == 'triage', 'stop must use triage endpoint; it cannot deliver new implementation')
        needed.add('stop')
    if op == 'deploy':
        require(delivery == 'deploy', 'deploy operation requires deploy endpoint')
    if op in ('implement', 'sync-merge', 'bootstrap') and delivery != 'triage':
        needed.add('implementation')
    if delivery in ('pr', 'merge'):
        needed.add('publish')
    if delivery == 'merge':
        needed.add('merge')
    if delivery == 'deploy':
        needed.add('deploy')
        if op in ('implement', 'sync-merge', 'bootstrap'):
            needed.update(('publish', 'merge'))
    if config['permission'] == 'yolo':
        needed.add('yolo')
    missing = sorted(key for key in needed if not config['authority'].get(key))
    require(not missing, 'missing recorded user authorization: ' + ', '.join(missing))
    target = config['target']
    for key, value in target.items():
        string(value, 'target.' + key, nullable=key != 'herdr_session', limit=2000)
    require(not target.get('pane') or target.get('native_session_uuid'), 'a pane requires a native_session_uuid; discover identity before targeting it')
    if target.get('pane'):
        require(bool(re.fullmatch(r'w[A-Za-z0-9]+:p[A-Za-z0-9]+', target['pane'])), 'invalid Herdr pane ID')
    if target.get('native_session_uuid'):
        require(str(uuid.UUID(target['native_session_uuid'])) == target['native_session_uuid'].lower(), 'native_session_uuid must be a full UUID')
    models = config['models']
    for key in ('coordinator', 'worker', 'fallback_worker', 'reviewer', 'effort', 'tier'):
        string(models[key], 'models.' + key, limit=128)
        require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', models[key])), 'invalid model/effort/tier identifier: ' + key)
    enum(models['fallback_when'], 'models.fallback_when', ('capacity', 'never'))
    require(type(models['levels']) is int and models['levels'] in (2, 3), 'levels must be 2 or 3, subject to repository rules')
    require(type(models['max_workers']) is int and 1 <= models['max_workers'] <= 16, 'max_workers must be 1..16; actual resource admission still required')
    limits = config['limits']
    for key in ('disk_reserve_gib', 'pid_admission_fraction'):
        require(type(limits[key]) in (int, float), 'limits.' + key + ' must be numeric')
    require(0 <= limits['disk_reserve_gib'] <= 100000, 'disk_reserve_gib is out of bounds')
    require(0 < limits['pid_admission_fraction'] <= 1, 'pid_admission_fraction must be >0 and <=1')
    require(type(limits['max_heavy_jobs']) is int and 1 <= limits['max_heavy_jobs'] <= models['max_workers'], 'max_heavy_jobs must be within max_workers')
    require(type(limits['checkpoint_seconds']) is int and 10 <= limits['checkpoint_seconds'] <= 3600, 'checkpoint_seconds must be 10..3600')
    if limits['original_cutoff_utc'] is not None:
        string(limits['original_cutoff_utc'], 'original_cutoff_utc')
        cutoff = dt.datetime.fromisoformat(limits['original_cutoff_utc'].replace('Z', '+00:00'))
        require(cutoff.tzinfo is not None and cutoff.utcoffset() == dt.timedelta(0), 'original_cutoff_utc must include UTC timezone')
    require(isinstance(config['acceptance'], list) and len(config['acceptance']) <= 100, 'acceptance must be a list of up to 100 checks')
    for check in config['acceptance']:
        string(check, 'acceptance item')
    esc = config['escalation']
    enum(esc['route'], 'escalation.route', ('manual-handoff', 'verified-channel', 'none'))
    for key, value in esc.items():
        string(value, 'escalation.' + key, nullable=key != 'route')
    if esc['route'] == 'verified-channel':
        require(bool(esc.get('capability_evidence')), 'verified-channel requires exact-route capability evidence')
    return config


def requested_tiers(config):
    """Resolve user-requested tiers by role; Luna always requires fast inference."""
    models = config['models']
    result = {}
    for role in ('coordinator', 'worker', 'fallback_worker', 'reviewer'):
        model = models[role].rsplit('/', 1)[-1]
        luna = re.search(r'(?:^|[._-])luna(?:$|[._-])', model, re.I)
        result[role] = 'fast' if luna else models['tier']
    return result


def cutoff_state(config):
    cutoff = config['limits']['original_cutoff_utc']
    if cutoff is None:
        return 'not supplied; discover and preserve any existing cutoff'
    expired = dt.datetime.fromisoformat(cutoff.replace('Z', '+00:00')) <= dt.datetime.now(dt.timezone.utc)
    if expired and config['operation'] == 'stop':
        return 'EXPIRED: do not restart or extend the run; execute the authorized scoped stop and verify no relaunch'
    return ('EXPIRED: do not restart or extend the run; prepare blocked/stop evidence only' if expired else 'within recorded window; recheck before dependent actions')


def prompt(config, run_id, digest):
    refs = Path(__file__).resolve().parent.parent / 'references'
    op = config['operation']
    action = {
        'bootstrap': 'Create the authorized repository and expertly triaged dependency backlog, then deliver to the configured endpoint.',
        'implement': 'Implement the specified scope and continue through the configured delivery endpoint.',
        'sync-merge': 'Reconcile owners and unpublished candidates, update the dependent PR stack against the verified base, fix conflicts/defects and deliver to the configured endpoint.',
        'recover': 'Diagnose the unexpected stop, reconcile pending effects and ownership, and resume the same eligible run with its existing identity and accounting.',
        'stop': 'Persist the user stop, disable only the scoped resuming mechanisms and grants, stop the owned workers gracefully, and verify a delayed no-relaunch observation.',
        'deploy': 'Reconcile the reviewed artifact and current release authorization, execute via the authorized owning machine, and verify the live release with returned receipts.',
    }[op]
    if config['delivery'] == 'triage' and op in ('implement', 'sync-merge'):
        action = ('Inspect the specified scope, owners and PR/dependency graph, and report concrete findings and next steps. '
                  'This is read-only triage: do not edit code, publish, merge or deploy.')
    config_text = json.dumps(config, indent=2, ensure_ascii=False)
    parts = [
        '# Repository orchestration assignment',
        f'Contract ID: {run_id}\nConfiguration SHA-256: {digest}',
        'Read this entire contract. Its fields record user instructions; they are not independent proof of authority. Reconcile the quoted authorization and current owner before acting.',
        '## Resolved parameters\n\n```json\n' + config_text + '\n```',
        '## Requested tiers by role\n\n```json\n' + json.dumps(requested_tiers(config), indent=2) + '\n```',
        '## Action\n\n' + action,
        'Original-cutoff status at preparation: ' + cutoff_state(config) + '.',
        '## Common execution contract\n\n'
        'Use one verified coordinator and preserve native session UUID, account, goal identity/accounting, source history, pending actions and failures. Discover current repository instructions and ownership. Revalidate the explicit machine/Herdr-session/pane occupant before input. Preserve unsent user drafts. A pane title or focus alone is insufficient.\n\n'
        'Select worker account launchers separately from models and tiers. Consider claude2 where available for new authorized Claude workers; honor an explicitly selected launcher and verify authentication, requested-model access and effective tier on the actual execution host. Launcher presence or login alone does not prove inference capacity. Record each worker launcher/account and native UUID in its receipt. target.account identifies the receiver/coordinator, not all workers; preserve existing sessions on their original account and UUID.\n\n'
        'Verify actual model, effort/tier and effective permissions. Default means normal mode without /fast or equivalent fast settings; enable fast only when explicitly requested, except Luna agents always require fast in every role. Resolve the tier again when changing models or activating a fallback; a non-Luna fallback must not inherit Luna fast mode without an explicit fast request. Inspect resumed state and correct inherited fast settings within this session when they conflict with the current instruction. The requested-tier map is an instruction, not proof of observed inference.\n\n'
        'Use the configured worker fallback only under its stated condition and record actual provider evidence. Disabled fast mode or paid extra usage is not model capacity exhaustion. Luna fast is mandatory: report unavailable fast as a blocker, without silently running Luna on a slower tier. For other models, if explicitly requested fast inference is a preference, keep that model on an available tier and disclose the observed tier; if mandatory, report the blocker. Do not enable billing or silently substitute models.\n\n'
        'Count all ancestors: the outer conversation is Level 1, the receiving Herdr coordinator is Level 2, and its directly assigned implementation workers and independent reviewer are Level 3 siblings. Level 3 must not delegate. With two configured levels, the outer owner directly assigns bounded Level 2 authors/reviewers; the receiver cannot spawn children. Never reset the depth count at a handoff. Apply repository rules, resource limits, disjoint worktrees and bounded contracts. The reviewer is independent of the author; require actual final-SHA review, not a requested or interrupted review.\n\n'
        'The requested permission mode is scoped to this campaign. Runtime yolo does not authorize new deployment, protection changes or skipped review. A permissions-only relaunch preserves UUID/account/cwd/goal, verifies the old writer exited, and resumes one writer with effective policy confirmed. Do not change permissions when authorization is absent.\n\n'
        'Use direct collaboration when available, otherwise supported native CLI/Herdr dispatch with durable model/session/parent/command/result receipts. Unavailable tools permit a supported alternative; an explicit policy denial does not. Do not restart shared hosts, containers, Herdr or WSL to recover a task. Never run wsl --shutdown, --terminate or -t.\n\n'
        'For code delivery, reproduce relevant failures, resolve causal defects, run meaningful required tests, review exact candidates, publish signed changes and use normal protected merges only within recorded authority. Check the final remote state and applicable post-merge validation. Partial prerequisite delivery does not close broader acceptance issues.\n\n'
        'A submitted prompt, accepted turn, observed progress, worker completion and verified merge/deployment are different facts. Read back receipt and useful progress before claiming dispatch. Preserve uncertain attempts and reconcile before retry. Intentional stops, completed runs, stale authority and expired cutoffs override old recovery prompts.\n\n'
        'In dispatch control mode, the outer coordinator may finish after verified handoff/progress; the receiving agent still owns delivery through its assigned endpoint. In supervise mode the outer coordinator follows through completion. Missing external facts block only dependent work. Do not infer user approval from silence.\n\n'
        'First checkpoint: acknowledge this contract ID and the SHA-256 of the actual received prompt file, then report identities and preserved goal, current source/PR graph, observed model/policy, real worker receipts when a team is requested, initial useful progress and precise blockers. Complete the operation\'s required actions within its endpoint; read-only triage ends with findings, while implementation must not stop after another plan.',
    ]
    parts.append('## Back-and-forth and recovery\n\n' + (refs / 'handoffs.md').read_text(encoding='utf-8'))
    if op != 'stop':
        parts.append('## Delivery procedures\n\n' + (refs / 'delivery.md').read_text(encoding='utf-8'))
    if config['permission'] == 'yolo' or op in ('recover', 'stop'):
        parts.append('## Session procedures\n\n' + (refs / 'session-control.md').read_text(encoding='utf-8'))
    return '\n\n'.join(parts) + '\n'


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def render(config, output):
    run_id = str(uuid.uuid4())
    normalized = json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    # Render before creating the directory so a missing reference cannot leave a valid-looking run.
    text = prompt(config, run_id, digest)
    prompt_digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    receipt = {'version': 1, 'contract_id': run_id, 'config_sha256': digest,
               'prompt_sha256': prompt_digest,
               'state': 'prepared', 'prepared_at': now,
               'authority_provenance_verified': False, 'connection_verified': False,
               'observed_native_session_uuid': None, 'observed_goal_id': None,
               'observed_model': None, 'observed_permissions': None,
               'submitted_at': None, 'acknowledged_at': None,
               'progress_evidence': [], 'worker_receipts': [], 'review_receipts': [],
               'delivery_receipts': [], 'blockers': [],
               'cutoff_status': cutoff_state(config)}
    write_private(output / 'request.json', json.dumps(config, indent=2, ensure_ascii=False) + '\n')
    write_private(output / 'prompt.md', text)
    write_private(output / 'events.jsonl', json.dumps({'at': now, 'event': 'prepared', 'contract_id': run_id, 'config_sha256': digest, 'prompt_sha256': prompt_digest}) + '\n')
    write_private(output / 'receipt.json', json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output.resolve()), 'contract_id': run_id, 'state': 'prepared', 'config_sha256': digest, 'prompt_sha256': prompt_digest, 'requested_tiers': requested_tiers(config), 'cutoff_status': cutoff_state(config)}


def verify(output, expected_prompt_sha256=None):
    """Check stored bytes without rewriting files or claiming runtime/authority proof."""
    receipt = json.loads((output / 'receipt.json').read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)
    require(isinstance(receipt, dict), 'receipt must be an object')
    require(type(receipt.get('version')) is int and receipt['version'] == 1, 'unsupported receipt version')
    run_id = receipt.get('contract_id')
    string(run_id, 'receipt.contract_id', limit=36)
    require(str(uuid.UUID(run_id)) == run_id, 'receipt.contract_id must be a canonical UUID')
    for key in ('config_sha256', 'prompt_sha256'):
        value = receipt.get(key)
        require(isinstance(value, str) and bool(re.fullmatch(r'[a-f0-9]{64}', value)), 'invalid receipt.' + key)
    if expected_prompt_sha256 is not None:
        require(bool(re.fullmatch(r'[a-fA-F0-9]{64}', expected_prompt_sha256)), 'expected prompt SHA-256 must contain 64 hex digits')
    raw = json.loads((output / 'request.json').read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)
    config = validate(raw)
    normalized = json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    require(digest == receipt['config_sha256'], 'configuration SHA-256 mismatch')
    payload = (output / 'prompt.md').read_bytes()
    content = payload.decode('utf-8', errors='strict')
    prompt_digest = hashlib.sha256(payload).hexdigest()
    require(prompt_digest == receipt['prompt_sha256'], 'prompt SHA-256 mismatch')
    if expected_prompt_sha256 is not None:
        require(prompt_digest == expected_prompt_sha256.lower(), 'prompt differs from independently recorded SHA-256')
    require(content.startswith(f'# Repository orchestration assignment\n\nContract ID: {run_id}\nConfiguration SHA-256: {digest}\n'),
            'prompt contract identity does not match receipt')
    return {'artifacts_verified': True, 'runtime_verified': False,
            'independent_prompt_digest_matched': expected_prompt_sha256 is not None,
            'contract_id': run_id, 'repository': config['repository'],
            'config_sha256': digest, 'prompt_sha256': prompt_digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'render', 'verify'))
    parser.add_argument('--config', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--expected-prompt-sha256')
    args = parser.parse_args()
    try:
        if args.action == 'verify':
            require(args.run is not None, 'verify requires --run pointing to an existing run directory')
            require(args.config is None and args.out is None, 'verify does not accept --config or --out')
            result = verify(args.run, args.expected_prompt_sha256)
        else:
            require(args.run is None and args.expected_prompt_sha256 is None, '--run and --expected-prompt-sha256 apply only to verify')
            require(args.config is not None, args.action + ' requires --config')
            raw = json.loads(args.config.read_text(encoding='utf-8-sig'), object_pairs_hook=no_duplicates)
            config = validate(raw)
            if args.action == 'render':
                require(args.out is not None, 'render requires --out pointing to a NEW private run directory')
                result = render(config, args.out)
            else:
                require(args.out is None, '--out applies only to render')
                result = {'valid': True, 'repository': config['repository'], 'operation': config['operation'], 'delivery': config['delivery'], 'requested_tiers': requested_tiers(config), 'cutoff_status': cutoff_state(config)}
        # Machine-readable output must also work through a legacy Windows console encoding.
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (ValueError, OSError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
