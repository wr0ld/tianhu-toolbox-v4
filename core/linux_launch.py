"""Linux tool launch specifications shared by execution and command preview."""
from dataclasses import dataclass
import os
import re
import shlex
import shutil
import subprocess


@dataclass
class Launch:
    argv: list
    cwd: str
    env: dict
    terminal: bool


def java_home(path):
    """Accept a Java home, bin directory or java executable."""
    path = os.path.realpath(path)
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if os.path.basename(path) == 'bin':
        path = os.path.dirname(path)
    return path


def find_java_home(version, configured=''):
    candidates = [configured, os.environ.get('JAVA' + version + '_HOME'), os.environ.get('JAVA_HOME'), shutil.which('java')]
    for candidate in candidates:
        if not candidate:
            continue
        home = java_home(candidate)
        exe = os.path.join(home, 'bin', 'java')
        if not os.path.isfile(exe) or not os.access(exe, os.X_OK):
            continue
        try:
            result = subprocess.run([exe, '-version'], capture_output=True, text=True, timeout=5)
            match = re.search(r'version\s+"(?:1\.)?(\d+)', result.stdout + result.stderr)
            if result.returncode == 0 and match and match.group(1) == str(version):
                return home
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ''


def build_launch(tool, manager):
    kind = tool.get('type', '')
    path = str(tool.get('path', '')).strip()
    if not path:
        raise ValueError('请先选择工具文件')
    if re.match(r'^[A-Za-z]:', path) or path.lower().endswith(('.exe', '.bat', '.cmd', '.vbs')) or kind == '批处理':
        raise ValueError('Linux 不支持 Windows EXE/BAT/CMD/VBS；请选择 Linux 版本或 Shell 脚本')
    if not os.path.isabs(path):
        path = os.path.abspath(os.path.join('tools', path))
    pre = shlex.split(str(tool.get('params_pre') or ''))
    post = shlex.split(str(tool.get('params') or ''))
    env_type = 'all'
    terminal = kind != 'GUI应用' and '图形化' not in kind
    if kind == 'Python' or kind.startswith('Python('):
        exe = manager.get_python_path()
        env_type = 'python'
        if kind.startswith('Python('):
            name = tool.get('custom_interpreter_name') or kind[7:-1]
            item = manager._find_cli_interpreter('python', name)
            if not item:
                raise ValueError('未找到自定义 Python 解释器: ' + name)
            exe = manager._resolve_path(item.get('path', ''))
            env_type = 'Python(' + name + ')'
            if not os.path.isfile(exe) or not os.access(exe, os.X_OK):
                raise ValueError('Python 解释器不存在或不可执行: ' + exe)
        argv = [exe] + pre + [path] + post
    elif kind.startswith('JAVA') or kind.startswith('Java('):
        version = '8' if '8' in kind else '11'
        env_type = 'java' + version
        if kind.startswith('Java('):
            name = tool.get('custom_interpreter_name') or kind[5:-1]
            item = manager._find_cli_interpreter('java', name)
            if not item:
                raise ValueError('未找到自定义 Java 环境: ' + name)
            home = java_home(manager._resolve_path(item.get('path', '')))
            exe = os.path.join(home, 'bin', 'java')
            if not os.path.isfile(exe) or not os.access(exe, os.X_OK):
                raise ValueError('Java 不存在或不可执行: ' + exe)
            env_type = 'Java(' + name + ')'
        else:
            exe = manager.get_java_exe(version, gui=not terminal)
        argv = [exe] + pre + ['-jar', path] + post
    elif kind in ('GUI应用', '命令行'):
        argv = (['/bin/bash', path] if path.endswith('.sh') else [path]) + pre + post
    elif kind == 'PowerShell':
        exe = shutil.which('pwsh')
        if not exe:
            raise ValueError('Linux PowerShell 需要另行安装 pwsh')
        argv = [exe, '-NoLogo', '-File', path] + pre + post
    else:
        raise ValueError('Linux 不支持的工具类型: ' + kind)
    return Launch(argv, os.path.dirname(path), manager.get_injected_env(env_type), terminal)


def start_launch(spec):
    argv = spec.argv
    if spec.terminal:
        terminal = shutil.which('xterm')
        if not terminal:
            raise RuntimeError('请安装 xterm 以显示命令行工具输出')
        argv = [terminal, '-fa', 'monospace', '-fs', '11', '-hold', '-e'] + argv
    return subprocess.Popen(argv, cwd=spec.cwd, env=spec.env)
