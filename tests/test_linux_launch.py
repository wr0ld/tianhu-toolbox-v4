import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from core.env_manager import EnvManager


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.manager = EnvManager()
        self.settings = self.root / 'settings.json'
        self.settings.write_text('{}')
        self.old_settings = self.manager.settings_file
        self.manager.settings_file = str(self.settings)
        self.addCleanup(setattr, self.manager, 'settings_file', self.old_settings)

    def java(self, version):
        home = self.root / ('java ' + version)
        (home / 'bin').mkdir(parents=True)
        java = home / 'bin/java'
        java.write_text('#!/bin/sh\necho \'openjdk version "' + version + '"\' >&2\n')
        java.chmod(0o755)
        return home

    def test_linux_python_uses_current_interpreter_without_pythonhome(self):
        with patch('sys.platform', 'linux'):
            self.assertEqual(self.manager.get_python_path(), sys.executable)
            env = self.manager.get_injected_env('python')
            self.assertNotIn('PYTHONHOME', env)
            subprocess.run([self.manager.get_python_path(), '-c', 'import encodings'], env=env, check=True)

    def test_linux_ignores_retained_windows_python_and_directories(self):
        windows_python = self.root / 'python.exe'
        windows_python.write_bytes(b'MZ')
        windows_python.chmod(0o755)
        for path in (windows_python, self.root):
            self.settings.write_text(json.dumps({'python_path': str(path)}))
            with patch('sys.platform', 'linux'):
                self.assertEqual(self.manager.get_python_path(), sys.executable)

    def test_custom_java_bin_path_matches_launch_environment(self):
        from core.linux_launch import build_launch
        home = self.java('11.0.30')
        self.settings.write_text(json.dumps({'cli_java_interpreters': [{'name':'custom','path':str(home/'bin')}]}))
        with patch('sys.platform', 'linux'):
            spec = build_launch({'type':'Java(custom)','path':'/tmp/a.jar'}, self.manager)
        self.assertEqual(spec.argv[0], str(home/'bin/java'))
        self.assertEqual(spec.env['JAVA_HOME'], str(home))
        self.assertEqual(spec.env['PATH'].split(os.pathsep)[0], str(home/'bin'))

    def test_version_specific_java_home_and_gui_executable(self):
        home = self.java('1.8.0_482')
        with patch('sys.platform', 'linux'), patch.dict(os.environ, {'JAVA8_HOME': str(home)}, clear=True):
            self.assertEqual(self.manager.get_java_home('8'), str(home))
            self.assertEqual(self.manager.get_java_exe('8', gui=True), str(home / 'bin/java'))
            env = self.manager.get_injected_env('java8')
            self.assertEqual(env['JAVA_HOME'], str(home))
            self.assertEqual(env['PATH'].split(os.pathsep)[0], str(home / 'bin'))
            self.assertNotIn('CLASSPATH', env)

    def test_wrong_java_version_is_not_accepted(self):
        home = self.java('11.0.30')
        with patch('sys.platform', 'linux'), patch.dict(os.environ, {'JAVA8_HOME': str(home)}, clear=True):
            self.assertEqual(self.manager.get_java_home('8'), '')

    def test_java_setting_accepts_home_bin_and_executable(self):
        home = self.java('11.0.30')
        for path in (home, home / 'bin', home / 'bin/java'):
            self.settings.write_text(json.dumps({'java11_path': str(path)}))
            with patch('sys.platform', 'linux'), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(self.manager.get_java_home('11'), str(home))


class LaunchTests(unittest.TestCase):
    def test_python_arguments_are_literal_and_cwd_is_tool_directory(self):
        from core.linux_launch import build_launch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / 'hello world.py'
            script.write_text('import sys,json,pathlib; pathlib.Path("result.json").write_text(json.dumps(sys.argv[1:]))')
            spec = build_launch({'type': 'Python', 'path': str(script), 'params': '"hello world" ";touch BAD" "$(touch BAD)"'}, EnvManager())
            subprocess.run(spec.argv, cwd=spec.cwd, env=spec.env, check=True)
            self.assertEqual(json.loads((root / 'result.json').read_text()), ['hello world', ';touch BAD', '$(touch BAD)'])
            self.assertFalse((root / 'BAD').exists())
            self.assertTrue(spec.terminal)

    def test_java_pre_arguments_precede_jar(self):
        from core.linux_launch import build_launch
        manager = EnvManager()
        with patch.object(manager, 'get_java_exe', return_value='/jdk/bin/java'), patch.object(manager, 'get_injected_env', return_value={}):
            spec = build_launch({'type':'JAVA8', 'path':'/tmp/a b.jar', 'params_pre':'-Xmx256m', 'params':'"a b"'}, manager)
        self.assertEqual(spec.argv, ['/jdk/bin/java', '-Xmx256m', '-jar', '/tmp/a b.jar', 'a b'])

    def test_gui_does_not_require_terminal(self):
        from core.linux_launch import build_launch
        spec = build_launch({'type':'GUI应用', 'path':'/tmp/app', 'params':'--flag'}, EnvManager())
        self.assertEqual(spec.argv, ['/tmp/app','--flag'])
        self.assertFalse(spec.terminal)

    def test_windows_formats_and_empty_paths_are_rejected(self):
        from core.linux_launch import build_launch
        for kind, path in [('批处理','/tmp/a.bat'), ('GUI应用','/tmp/a.exe'), ('命令行','C:\\tool.exe'), ('Python','')]:
            with self.subTest(kind=kind, path=path), self.assertRaises(ValueError):
                build_launch({'type':kind, 'path':path}, EnvManager())

    def test_invalid_quoting_reports_error(self):
        from core.linux_launch import build_launch
        with self.assertRaises(ValueError):
            build_launch({'type':'Python','path':'/tmp/a.py','params':'"unclosed'}, EnvManager())

    def test_terminal_argv_keeps_arguments_separate(self):
        from core.linux_launch import build_launch, start_launch
        spec = build_launch({'type':'命令行','path':'/tmp/a b','params':'"c d"'}, EnvManager())
        with patch('core.linux_launch.shutil.which', return_value='/usr/bin/xterm'), patch('core.linux_launch.subprocess.Popen') as popen:
            start_launch(spec)
            self.assertEqual(popen.call_args.args[0], ['/usr/bin/xterm','-fa','monospace','-fs','11','-hold','-e','/tmp/a b','c d'])
            self.assertFalse(popen.call_args.kwargs.get('shell', False))


if __name__ == '__main__':
    unittest.main()
