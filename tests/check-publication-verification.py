#!/usr/bin/python3 -B
"""Publication control-flow regressions; no network, uploads or physical media."""
from pathlib import Path
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publisher', ROOT / 'scripts/publish-split-release.py')
publisher = importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)


class TemporaryListingError(Exception):
    pass


class PublicationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='publication-verification-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        (self.base / 'publication').mkdir()
        self.raw = b'public catalog fixture'
        self.plan = {'version': 'rc1-test', 'catalog_sha256': hashlib.sha256(self.raw).hexdigest()}
        self.visible = [{'version': 'rc1-test', 'installer_catalog': True}]
        self.client = Mock()
        self.client.releases.return_value = self.visible
        def download(*args, **kwargs):
            destination = args[2];destination.mkdir()
            (destination / 'petalos-release.json').write_bytes(self.raw)
        self.client.download.side_effect = download
        self.factory = Mock(return_value=self.client)
        self.verify = Mock(return_value=({'version': 'rc1-test'}, {'id': 'base'}))
        self.sleep = self.enterContext(patch.object(publisher.time, 'sleep'))
        self.enterContext(redirect_stdout(io.StringIO()))

    def verify_public(self):
        publisher.public_download(self.plan, self.base, self.factory, self.verify,
                                  retry_errors=(TemporaryListingError,))

    def test_empty_listing_then_visible_downloads_without_authentication(self):
        self.client.releases.side_effect = [[], self.visible]
        self.verify_public()
        self.factory.assert_called_once_with(publisher.REPO, token=None)
        self.assertEqual(self.client.releases.call_count, 2)
        self.sleep.assert_called_once_with(10)
        self.client.download.assert_called_once()

    def test_temporary_api_error_then_visible(self):
        self.client.releases.side_effect = [TemporaryListingError('not ready'), self.visible]
        self.verify_public()
        report = json.loads((self.base / 'publication/public-listing-check.json').read_text())
        self.assertFalse(report['authenticated'])
        self.assertEqual(report['attempts'][0]['error'], 'not ready')
        self.assertTrue(report['attempts'][1]['visible'])

    def test_missing_release_stops_after_bounded_retries(self):
        self.client.releases.return_value = []
        with self.assertRaisesRegex(RuntimeError, 'Release is published'):
            self.verify_public()
        self.assertEqual(self.client.releases.call_count, 7)
        self.assertEqual(self.sleep.call_count, 6)
        self.client.download.assert_not_called()

    def test_release_without_catalog_is_not_a_pass(self):
        self.client.releases.return_value = [{'version': 'rc1-test', 'installer_catalog': False}]
        with self.assertRaises(RuntimeError):
            self.verify_public()
        self.client.download.assert_not_called()

    def test_downloaded_catalog_must_match_the_prepared_digest(self):
        self.plan['catalog_sha256'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            self.verify_public()

    def test_existing_verified_download_is_reused(self):
        destination = self.base / 'public-download-check';destination.mkdir()
        (destination / 'petalos-release.json').write_bytes(self.raw)
        self.verify_public()
        self.client.download.assert_not_called()
        self.verify.assert_called_once_with(destination)

    def test_published_resume_skips_git_github_writes_and_uploads(self):
        plan_path = self.base / 'publication-plan.json';plan_path.write_text('{}\n')
        state = {'published': True, 'plan_sha256': publisher.digest(plan_path)}
        (self.base / 'publication/state.json').write_text(json.dumps(state))
        forbidden = AssertionError('published resume must not mutate GitHub or Git')
        with patch.object(sys, 'argv', ['publisher', '--plan', str(plan_path)]), \
             patch.object(publisher, 'check_plan', return_value=(self.plan, [], self.base / 'snapshot')), \
             patch.object(publisher, 'gh_json', side_effect=forbidden), \
             patch.object(publisher, 'git', side_effect=forbidden), \
             patch.object(publisher, 'run', side_effect=forbidden), \
             patch.object(publisher, 'finish_public_verification') as verify:
            publisher.main()
        verify.assert_called_once()
        self.assertTrue(verify.call_args.args[-1]['published'])


if __name__ == '__main__':
    unittest.main()
