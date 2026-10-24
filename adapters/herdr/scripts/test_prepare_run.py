"""Offline contract and artifact invariants; no Herdr, GitHub or network calls."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import prepare_run as helper


class ContractTests(unittest.TestCase):
    def request(self, **kwargs):
        return {'repository': 'example/project', 'scope': 'Implement issue 7 with regression coverage.',
                'authority': {'implementation': 'Current user: implement issue 7.'}, **kwargs}

    def test_merge_needs_publication_and_merge_authority(self):
        with self.assertRaises(ValueError):
            helper.validate(self.request(delivery='merge'))
        cfg = helper.validate(self.request(delivery='merge', authority={
            'implementation': 'User: fix it.', 'publish': 'User: open the PR.',
            'merge': 'User: carry it through merge.'}))
        self.assertEqual(cfg['delivery'], 'merge')

    def test_yolo_is_independent_of_merge_authority(self):
        authority = {'implementation': 'User: fix.', 'publish': 'User: push.', 'merge': 'User: merge.'}
        with self.assertRaises(ValueError):
            helper.validate(self.request(permission='yolo', authority=authority))
        authority['yolo'] = 'User: use --yolo for this campaign.'
        self.assertEqual(helper.validate(self.request(permission='yolo', authority=authority))['permission'], 'yolo')

    def test_half_bound_identity_and_misspelled_control_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate(self.request(target={'pane': 'wK:p1'}))
        with self.assertRaises(ValueError):
            helper.validate(self.request(models={'reviewr': 'gpt-6-astra'}))

    def test_existing_artifact_deployment_does_not_need_code_authority(self):
        cfg = helper.validate(self.request(operation='deploy', authority={'deploy': 'User: deploy reviewed revision abc123 to staging.'}))
        self.assertEqual(cfg['delivery'], 'deploy')

    def test_code_through_deployment_records_all_delivery_stages(self):
        for operation in ('implement', 'sync-merge', 'bootstrap'):
            with self.subTest(operation=operation):
                authority = {'implementation': 'User: implement and deliver.',
                             'deploy': 'User: deploy the resulting release.',
                             'create_repository': 'User: create the project.'}
                with self.assertRaisesRegex(ValueError, 'merge, publish'):
                    helper.validate(self.request(operation=operation, delivery='deploy', authority=authority))
                authority.update(publish='User: deliver through PR.', merge='User: through merge and deployment.')
                self.assertEqual(helper.validate(self.request(operation=operation, delivery='deploy', authority=authority))['delivery'], 'deploy')

    def test_known_uuid_can_be_recovered_without_stale_pane(self):
        sid = '01a1224e-828f-77f3-9f00-ee41f526bce4'
        cfg = helper.validate(self.request(operation='recover', authority={'resume': 'User: find and recover the existing run.'},
            target={'native_session_uuid': sid, 'account': 'codex1', 'goal_id': 'preserved-goal'}))
        self.assertEqual(cfg['target']['native_session_uuid'], sid)
        self.assertNotIn('pane', cfg['target'])
        with self.assertRaises(ValueError):
            helper.validate(self.request(target={'native_session_uuid': 'not-a-uuid'}))

    def test_stop_cannot_expand_to_code_delivery(self):
        cfg = helper.validate(self.request(operation='stop', authority={'stop': 'User: stop the resuming mechanism.'}))
        self.assertEqual(cfg['delivery'], 'triage')
        with self.assertRaises(ValueError):
            helper.validate(self.request(operation='stop', delivery='merge', authority={'stop': 'User: stop.'}))

    def test_expired_resume_stays_preparation_only(self):
        cfg = helper.validate(self.request(operation='recover', authority={'resume': 'User: recover the run within its original window.'},
            limits={'original_cutoff_utc': '2000-01-01T00:00:00Z'}))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            result = helper.render(cfg, out)
            receipt = json.loads((out / 'receipt.json').read_text())
            self.assertIn('EXPIRED', result['cutoff_status'])
            self.assertEqual(receipt['state'], 'prepared')
            self.assertIsNone(receipt['submitted_at'])
            self.assertFalse(receipt['authority_provenance_verified'])

    def test_expired_window_still_allows_authorized_stop(self):
        cfg = helper.validate(self.request(operation='stop', authority={'stop': 'User: stop this run and its owned resumer.'},
            limits={'original_cutoff_utc': '2000-01-01T00:00:00Z'}))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'stop'
            result = helper.render(cfg, out)
            self.assertIn('execute the authorized scoped stop', result['cutoff_status'])
            self.assertIn('do not restart or extend', result['cutoff_status'])
            self.assertEqual(result['state'], 'prepared')
            self.assertFalse(helper.verify(out)['runtime_verified'])
        with self.assertRaisesRegex(ValueError, 'stop'):
            helper.validate(self.request(operation='stop', authority={},
                limits={'original_cutoff_utc': '2000-01-01T00:00:00Z'}))

    def test_durable_contract_identity_and_no_overwrite(self):
        cfg = helper.validate(self.request(repository='https://github.com/example/project.git'))
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            result = helper.render(cfg, out)
            files_before = {p.name: p.read_bytes() for p in out.iterdir()}
            normalized = json.dumps(cfg, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            self.assertEqual(result['config_sha256'], hashlib.sha256(normalized.encode()).hexdigest())
            self.assertEqual(result['prompt_sha256'], hashlib.sha256((out / 'prompt.md').read_bytes()).hexdigest())
            self.assertIn(result['contract_id'], (out / 'prompt.md').read_text())
            with self.assertRaises(FileExistsError):
                helper.render(cfg, out)
            self.assertEqual(files_before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_unproven_automatic_escalation_is_rejected(self):
        with self.assertRaises(ValueError):
            helper.validate(self.request(escalation={'route': 'verified-channel'}))

    def test_future_models_are_configurable_without_enabling_fallback(self):
        cfg = helper.validate(self.request(models={'worker': 'provider-next-model', 'fallback_when': 'never', 'max_workers': 1}))
        self.assertEqual(cfg['models']['worker'], 'provider-next-model')
        self.assertEqual(cfg['models']['fallback_when'], 'never')

    def test_non_luna_defaults_and_template_do_not_request_fast(self):
        template = json.loads((Path(helper.__file__).parent.parent / 'assets' / 'run.example.json').read_text(encoding='utf-8'))
        template['authority'] = self.request()['authority']
        for request in (self.request(), self.request(models={'worker': 'provider-next-model'}), template):
            with self.subTest(request=request):
                config = helper.validate(request)
                self.assertEqual(config['models']['tier'], 'default')
                self.assertEqual(helper.requested_tiers(config), {
                    'coordinator': 'default', 'worker': 'default',
                    'fallback_worker': 'default', 'reviewer': 'default'})

    def test_explicit_fast_request_applies_to_non_luna_roles(self):
        config = helper.validate(self.request(models={'tier': 'fast'}))
        self.assertEqual(helper.requested_tiers(config), {
            'coordinator': 'fast', 'worker': 'fast',
            'fallback_worker': 'fast', 'reviewer': 'fast'})

    def test_luna_always_requires_fast_in_each_role(self):
        roles = ('coordinator', 'worker', 'fallback_worker', 'reviewer')
        for role in roles:
            for model in ('gpt-5.6-luna', 'gpt-6-luna', 'provider/GPT-6-LUNA', 'gpt-6-luna-20261009'):
                with self.subTest(role=role, model=model):
                    config = helper.validate(self.request(models={role: model, 'tier': 'default'}))
                    self.assertEqual(helper.requested_tiers(config), {r: 'fast' if r == role else 'default' for r in roles})
        for model in ('provider/lunatic-model', 'luna/gpt-6-sol'):
            with self.subTest(model=model):
                config = helper.validate(self.request(models={'worker': model}))
                self.assertEqual(helper.requested_tiers(config)['worker'], 'default')
        config = helper.validate(self.request(models={'worker': 'gpt-6-luna', 'tier': 'standard'}))
        self.assertEqual(helper.requested_tiers(config)['worker'], 'fast')

    def test_fallback_model_change_recomputes_tier_without_inheriting_fast(self):
        for worker, fallback, expected in (
            ('gpt-6-luna', 'gpt-6.1-sol', 'default'),
            ('gpt-6.1-sol', 'gpt-6-luna', 'fast'),
        ):
            with self.subTest(worker=worker, fallback=fallback):
                config = helper.validate(self.request(models={'worker': worker, 'fallback_worker': fallback}))
                self.assertEqual(helper.requested_tiers(config)['fallback_worker'], expected)
                config['models']['worker'] = fallback
                self.assertEqual(helper.requested_tiers(config)['worker'], expected)
        config = helper.validate(self.request(models={'worker': 'gpt-6-luna', 'fallback_worker': 'gpt-6.1-sol', 'tier': 'fast'}))
        self.assertEqual(helper.requested_tiers(config)['fallback_worker'], 'fast')

    def test_render_and_cli_expose_mixed_requested_tiers_without_observed_claim(self):
        config = helper.validate(self.request(models={'worker': 'gpt-6-luna'}))
        expected = {'coordinator': 'default', 'worker': 'fast', 'fallback_worker': 'default', 'reviewer': 'default'}
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            result = helper.render(config, out)
            self.assertEqual(result['requested_tiers'], expected)
            content = (out / 'prompt.md').read_text(encoding='utf-8')
            blocks = [json.loads(part.split('\n```', 1)[0]) for part in content.split('```json\n')[1:]]
            self.assertIn(expected, blocks)
            receipt = json.loads((out / 'receipt.json').read_text(encoding='utf-8'))
            self.assertIsNone(receipt['observed_model'])
            self.assertFalse(helper.verify(out, result['prompt_sha256'])['runtime_verified'])
            cli = subprocess.run([sys.executable, str(Path(helper.__file__)), 'validate', '--config', str(out / 'request.json')], capture_output=True)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(json.loads(cli.stdout)['requested_tiers'], expected)

    def test_placeholder_authority_not_treated_as_real(self):
        with self.assertRaises(ValueError):
            helper.validate(self.request(authority={'implementation': 'Example only: replace with the actual current user instruction.'}))

    def test_cli_rejects_duplicate_keys_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / 'input.json'
            config.write_text('{"repository":"example/project","repository":"other/project"}')
            out = Path(temp) / 'run'
            result = subprocess.run([sys.executable, str(Path(helper.__file__)), 'render', '--config', str(config), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())

    def test_utf8_transfer_verifies_without_mutation_or_runtime_claim(self):
        scope = 'Inspect "quoted" paths, apostrophe\'s, `$HOME and $(not-a-command).\nPreserve café 🦊 日本語.'
        cfg = helper.validate(self.request(scope=scope))
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source'
            destination = Path(temp) / 'received'
            rendered = helper.render(cfg, source)
            shutil.copytree(source, destination)
            before = {p.name: p.read_bytes() for p in destination.iterdir()}
            verified = helper.verify(destination, rendered['prompt_sha256'])
            self.assertTrue(verified['artifacts_verified'])
            self.assertTrue(verified['independent_prompt_digest_matched'])
            self.assertFalse(verified['runtime_verified'])
            self.assertEqual(json.loads((destination / 'request.json').read_text(encoding='utf-8'))['scope'], scope)
            self.assertIn('café 🦊 日本語'.encode('utf-8'), (destination / 'prompt.md').read_bytes())
            self.assertEqual(before, {p.name: p.read_bytes() for p in destination.iterdir()})
            self.assertFalse(helper.verify(destination)['independent_prompt_digest_matched'])

    def test_verify_detects_changed_prompt_config_and_source_digest(self):
        for mutation in ('prompt', 'config', 'expected_digest', 'identity'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / 'run'
                rendered = helper.render(helper.validate(self.request()), out)
                expected = rendered['prompt_sha256']
                if mutation == 'prompt':
                    payload = (out / 'prompt.md').read_bytes().replace(b'Implement issue 7', b'Implement issue 8')
                    (out / 'prompt.md').write_bytes(payload)
                elif mutation == 'config':
                    config = json.loads((out / 'request.json').read_text(encoding='utf-8'))
                    config['repository'] = 'another/project'
                    (out / 'request.json').write_text(json.dumps(config), encoding='utf-8')
                elif mutation == 'identity':
                    receipt = json.loads((out / 'receipt.json').read_text(encoding='utf-8'))
                    receipt['contract_id'] = '01a1224e-828f-77f3-9f00-ee41f526bce4'
                    (out / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
                else:
                    expected = '0' * 64
                before = {p.name: p.read_bytes() for p in out.iterdir()}
                with self.assertRaises(ValueError):
                    helper.verify(out, expected)
                self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_verify_rejects_invalid_utf8_even_with_matching_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            helper.render(helper.validate(self.request()), out)
            payload = (out / 'prompt.md').read_bytes() + b'\xff'
            (out / 'prompt.md').write_bytes(payload)
            receipt = json.loads((out / 'receipt.json').read_text(encoding='utf-8'))
            receipt['prompt_sha256'] = hashlib.sha256(payload).hexdigest()
            (out / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
            with self.assertRaises(UnicodeDecodeError):
                helper.verify(out)

    def test_verify_requires_complete_receipt_and_rejects_duplicate_json(self):
        for mutation in ('missing_receipt', 'duplicate_key', 'bad_digest'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / 'run'
                helper.render(helper.validate(self.request()), out)
                receipt_path = out / 'receipt.json'
                if mutation == 'missing_receipt':
                    receipt_path.unlink()
                elif mutation == 'duplicate_key':
                    text = receipt_path.read_text(encoding='utf-8').replace('"version": 1', '"version": 1, "version": 1')
                    receipt_path.write_text(text, encoding='utf-8')
                else:
                    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                    receipt['prompt_sha256'] = 'not a digest'
                    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
                with self.assertRaises((ValueError, OSError)):
                    helper.verify(out)

    def test_cli_render_and_verify_with_unicode_path_and_ascii_console(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / 'input.json'
            config_path.write_text(json.dumps(self.request(scope='Preserve café 🦊.'), ensure_ascii=False), encoding='utf-8')
            out = Path(temp) / 'café 🦊'
            env = {**os.environ, 'PYTHONIOENCODING': 'ascii', 'PYTHONDONTWRITEBYTECODE': '1'}
            command = [sys.executable, str(Path(helper.__file__))]
            rendered = subprocess.run(command + ['render', '--config', str(config_path), '--out', str(out)], capture_output=True, env=env)
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            result = json.loads(rendered.stdout.decode('ascii'))
            verified = subprocess.run(command + ['verify', '--run', str(out), '--expected-prompt-sha256', result['prompt_sha256']], capture_output=True, env=env)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)['artifacts_verified'])

    def test_cli_rejects_mixed_modes_and_wrong_expected_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'run'
            helper.render(helper.validate(self.request()), out)
            command = [sys.executable, str(Path(helper.__file__))]
            for args in (
                ['verify'],
                ['verify', '--run', str(out), '--out', str(Path(temp) / 'new')],
                ['verify', '--run', str(out), '--expected-prompt-sha256', '0' * 64],
                ['validate', '--run', str(out)],
                ['render', '--out', str(Path(temp) / 'new')],
            ):
                with self.subTest(args=args):
                    result = subprocess.run(command + args, capture_output=True)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertNotIn(b'Traceback', result.stderr)
            self.assertFalse((Path(temp) / 'new').exists())


if __name__ == '__main__':
    unittest.main()
