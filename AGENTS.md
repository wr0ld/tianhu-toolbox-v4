# AGENTS.md — 天狐渗透工具箱-社区版V4.0

## 启动方式

三个入口（全部使用自带 `python3/` 解释器，无 pip/venv 依赖管理）：

| 文件 | 用途 | 启动方式 |
|---|---|---|
| `main.py` | 完整主窗口（frameless PyQt6） | `天狐...V4.0.vbs`（隐藏控制台） |
| `loader.py` | 启动动画 → 预加载后启动 main.py | VBS（目前被注释掉） |
| `launcher.py` | 简化版经典菜单启动器 | `启动工具箱.bat` 通过 `pythonw.exe` 启动 |

## Bat 文件规则（源自 `.cursorrules`）

保持最简：不加 `@echo off`、`cd /d "%~dp0"`、`pause`。启动 GUI 程序且不留黑窗口：
```bat
start "" "程序路径" 参数
exit
```

## Python 代码风格

本仓库使用**非常规空格风格**（冒号、逗号、点号、括号、等号前有空格）。不要"修正"格式化，保持现有风格。

## 已禁用功能（不要重新启用）

- `keyboard` 库（全局热键） — import 已在 `main.py:5` 注释掉
- `TerminalTabWidget`（集成终端） — import 已在 `main.py:37` 注释掉

## 配置

运行态数据在 `config/` 下（JSON，运行时读写）：
- `settings.json` — 用户偏好（主题、路径、收藏、窗口几何）
- `tools.json` — 约 200+ 工具定义
- `.instance.lock` — 单实例运行锁（socket 端口）；手动删除可清除过期锁

## 环境

- `core/env_manager.py` — 单例 `EnvManager`，解析自带 Python/Java 路径
- 自带运行时：`python3/`、`Java_path/Java_8_win/`、`Java_path/Java_11_win/`
- 可在设置中配置自定义解释器

## Git

.gitignore 中忽略的目录：`tools/`、`python3/`、`notepad/`、`java_path/`（注意小写，实际目录是 `Java_path/`）、图片文件（`.jpg`、`.png`、`.ico`）、`.pyc`。

## 无测试/检查基础设施

没有测试、linter、typechecker、CI。不要尝试运行 `pytest`、`flake8`、`mypy` 等。

## 自动化渗透测试工作流

当用户要求对域名进行测试时，按以下流程实现 `auto_scan.py`：

```
Phase 1: 子域名收集 → OneForALL / ENScan → subdomains.txt
Phase 2: 存活探测 + 端口 + 指纹 → Httpx → Kscan → Ehole
Phase 3: 漏洞扫描 → Afrog / EZ / Fscan（可并行）
Phase 4: 汇总报告 → results/域名_时间戳/ 目录
```

- 脚本放在项目根目录，用 Python + subprocess 调工具
- 工具路径通过 `config/tools.json` 或 `EnvManager` 解析
- 输出按阶段分目录，最终生成摘要
