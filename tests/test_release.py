import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from configuration import load_settings
from bootstrap import requirements_hash, setup_lock
from diagnostics import collect
from scripts.package_source import validate_files


class ReleaseTests(unittest.TestCase):
    def test_env_file_preserves_explicit_environment_and_literal_values(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'VIDEO_AI_API_KEY':'existing'}):
            (Path(root)/'.env').write_text('VIDEO_AI_API_KEY=from-file\nVIDEO_RELEASE_TEST=literal$dollar\n',encoding='utf-8')
            try:
                load_settings(root)
                self.assertEqual(os.environ['VIDEO_AI_API_KEY'],'existing')
                self.assertEqual(os.environ['VIDEO_RELEASE_TEST'],'literal$dollar')
            finally:os.environ.pop('VIDEO_RELEASE_TEST',None)

    def test_dependency_marker_tracks_constraints_as_well_as_requirements(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/'requirements.txt').write_text('demo>=1')
            (root/'constraints.txt').write_text('demo==1')
            before=requirements_hash(root)
            (root/'constraints.txt').write_text('demo==2')
            self.assertNotEqual(before,requirements_hash(root))

    def test_setup_lock_excludes_second_launcher(self):
        with tempfile.TemporaryDirectory() as root:
            with setup_lock(Path(root)):
                with self.assertRaises(RuntimeError):
                    with setup_lock(Path(root)):pass

    def test_private_files_cannot_enter_source_package(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/'app.py').write_text('pass')
            self.assertEqual(validate_files(root,['app.py']),[root/'app.py'])
            for name in ['.env','.env.local','.data/result.json','clip.mp4','private.key','REFACTOR_REPORT.md','../outside.py']:
                with self.subTest(name=name),self.assertRaises(ValueError):validate_files(root,[name])

    def test_diagnostics_never_reports_credentials_urls_or_paths(self):
        with patch.dict(os.environ,{'VIDEO_AI_API_KEY':'secret-diagnostic-sentinel',
                                   'VIDEO_AI_BASE_URL':'https://private-host.invalid/v1',
                                   'VIDEO_AI_MODEL':'private-model',
                                   'VIDEO_DATA_DIR':str(Path(tempfile.gettempdir())/'private-folder-sentinel')}):
            text=json.dumps(collect())
            for value in ['secret-diagnostic-sentinel','private-host','private-model','private-folder-sentinel']:
                self.assertNotIn(value,text)


if __name__=='__main__':unittest.main()
