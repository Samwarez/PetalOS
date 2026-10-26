from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petal_installer.cli import dispatch, parser
from petal_installer.presentation import local_build_message, release_choices, variant_title


class PresentationTests(unittest.TestCase):
    def test_empty_and_unprepared_release_lists_explain_why(self):
        choices, message = release_choices([])
        self.assertEqual(choices, []);self.assertIn('No releases are published', message)
        choices, message = release_choices([{'version': 'old', 'installer_catalog': False}])
        self.assertEqual(choices, []);self.assertIn('none has installer-ready', message)
        ready = {'version': 'new', 'installer_catalog': True}
        choices, message = release_choices([{'version': 'old', 'installer_catalog': False}, ready])
        self.assertEqual(choices, [ready]);self.assertIn('local AI', message)

    def test_build_names_distinguish_local_ai_variant(self):
        self.assertEqual(variant_title({'name': 'Base', 'local_ai': False}), 'Base')
        self.assertEqual(variant_title({'name': 'Agent', 'local_ai': True}), 'Agent · local AI agent')

    def test_local_build_explains_raw_output_and_wrong_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertIn('ISO', local_build_message(root))
            (root / 'manifest.json').write_text('{}')
            self.assertIn('exported for the installer', local_build_message(root))
            (root / 'petalos-release.json').write_text('{}');(root / 'selection.json').write_text('{}')
            self.assertIsNone(local_build_message(root))

    def test_gui_token_stays_out_of_environment_and_is_only_passed_to_client(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'environment-test-token'}), patch('petal_installer.cli.GitHub') as github:
            dispatch(parser().parse_args(['releases']), github_token='session-test-token')
            self.assertEqual(github.call_args.kwargs['token'], 'session-test-token')
            self.assertEqual(os.environ['GH_TOKEN'], 'environment-test-token')
            dispatch(parser().parse_args(['releases']))
            self.assertEqual(github.call_args.kwargs['token'], 'environment-test-token')


if __name__ == '__main__':unittest.main()
