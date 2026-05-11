# 天狐渗透工具箱-社区版V4.0 项目分析文档

## 项目概述

**项目名称**: 天狐渗透工具箱-社区版V4.0 (ONE-FOX Tools V4.0)  
**开发团队**: One-Fox安全团队 (By.狐狸)  
**官网**: https://www.one-fox.cn/  
**许可证**: GPL v3  
**技术栈**: Python 3.12 + PyQt6 (GUI框架)  
**运行平台**: Windows  

本项目是一个渗透测试工具集成管理平台，提供工具的分类管理、一键启动、环境注入、截图标注、内嵌终端等功能。

---

## 项目启动流程

1. **用户双击** `天狐渗透工具箱-社区版V4.0.vbs` → 隐藏CMD窗口调用 `python3\python.exe loader.py`
2. **loader.py** → 显示流体粒子动画启动画面（2秒），同时在后台线程预加载 `main.py` 模块；动画结束后启动 `main.py`
3. **main.py** → 初始化 `MainWindow`，加载工具/分类/设置/主题，进入主界面
4. **启动工具箱.bat** → 使用 `pythonw.exe launcher.py` 启动简化版启动器（无动画）

---

## 目录结构（排除 tools/, python3/, notepad/, Java_path/）

```
ONE-FOX-toolsV4.0/
├── main.py                  # 主程序入口 & MainWindow 主窗口类
├── loader.py                # 启动加载器（流体粒子动画）
├── launcher.py              # 简化版启动器（传统分类列表UI）
├── config.py                # 配置管理（主题/设置/工具/分类 读写）
├── utils.py                 # 工具函数（工具运行/环境检查/收藏/搜索/单实例/动画）
├── widgets.py               # 自定义控件（TitleBar/SearchBar/CategoryPanel/ToolDialog/SettingsDialog）
├── core/
│   ├── __init__.py          # 空文件
│   ├── env_manager.py       # 环境管理器（Python/Java路径解析 & 环境变量注入）
│   ├── modern_grid.py       # 现代化工具卡片网格（Model/Delegate/ListView）
│   ├── screenshot.py        # 截图叠加层（选区/标注/画笔/箭头/文字/马赛克/橡皮）
│   └── window_effect.py     # 窗口特效（Windows Acrylic/Mica 背景效果）
├── services/
│   └── tool_health.py       # 工具健康检查（路径是否存在检测）
├── views/
│   ├── terminal_tab_widget.py   # 终端标签页管理器
│   └── terminal_widget.py       # 终端模拟器（基于 pyte + winpty）
├── config/
│   ├── settings.json        # 用户设置
│   ├── tools.json           # 工具列表数据
│   ├── categories.json      # 分类列表数据
│   ├── shortcuts.ini        # 快捷键映射
│   ├── fox.ico              # 程序图标
│   └── fox.png              # Logo图片
├── __pycache__/             # Python字节码缓存
├── 启动工具箱.bat            # 简化启动脚本（启动launcher.py）
├── 创建桌面快捷方式.bat      # 创建桌面快捷方式脚本
├── 天狐渗透工具箱-社区版V4.0.vbs  # 主启动脚本（隐藏窗口启动loader.py）
├── 免责声明.txt              # 法律免责声明
├── LICENSE                  # GPL v3 许可证
└── app.log                  # 运行日志
```

---

## 核心文件详解

### 1. main.py — 主程序

**关键类与功能**:

- **`MainWindow(QMainWindow)`** — 主窗口，负责整体UI布局与交互逻辑
  - 窗口标题: "天狐渗透工具箱-社区版V4.0"
  - 无边框窗口 (`FramelessWindowHint`)，自定义标题栏
  - 默认尺寸 1400×800
  - 支持拖拽文件添加工具（仅限 .vbs/.bat/.py/.jar/.exe）

- **UI布局**:
  - 顶部: `TitleBar`（标题 + 性能监控 + 最小化/最大化/关闭按钮）
  - 左侧: `CategoryPanel`（分类导航，固定宽度240px）
  - 右侧上方: 搜索栏 + 功能按钮（添加工具/记事本/设置/终端/批量模式/导入/导出）
  - 右侧中央: `ModernToolGrid`（工具卡片网格）
  - 右侧下方: 分页控件（支持滚动/分页两种模式）
  - 可弹出: 终端面板 (`TerminalTabWidget`)

- **核心功能方法**:
  - `add_tool()` / `edit_tool()` / `delete_tool()` — 工具增删改
  - `run_tool()` / `run_tools_batch()` — 单个/批量运行工具
  - `apply_theme()` — 应用主题样式
  - `init_tray()` — 系统托盘
  - `init_shortcuts()` / `register_hotkey()` — 全局热键注册（使用 keyboard 库）
  - `check_tools_health()` — 工具健康检查
  - `toggle_terminal()` — 内嵌终端开关
  - `take_screenshot()` — 截图功能
  - `restart_application()` — 重启应用
  - `import_data()` / `export_data()` — 数据导入导出
  - `closeEvent()` — 退出确认（支持最小化到托盘/直接退出/询问三种模式）

- **`_RateLimitingHandler`** — 日志限速处理器，防止日志刷屏

- **`ButtonHoverCursorFilter`** — 全局事件过滤器，按钮悬停时显示手型光标

- **版本号**: `CURRENT_VERSION = '3.0'`（代码内硬编码）

---

### 2. config.py — 配置管理

**默认分类**:
- 最近启动、我的收藏、WebShell管理工具、信息收集工具、抓包与代理工具、漏洞扫描与利用工具、框架漏洞利用工具、爆破工具、免杀工具、后渗透工具、其他工具、网页工具

**工具类型** (`TOOL_TYPES`):
- Python, JAVA8, JAVA11, GUI应用, 命令行, 批处理, PowerShell, 网页

**主题系统** (`THEMES`): 支持10种主题
| 主题键 | 名称 | 特点 |
|---|---|---|
| `dark` | 深色 | 经典暗黑主题 |
| `light` | 浅色 | 白色明亮主题 |
| `eye_care` | 护眼 | 绿色调护眼 |
| `pink` | 粉色 | 粉色系 |
| `blue` | 蓝色 | 蓝色系 |
| `cyberpunk` | 赛博朋克 | 紫+青 荧光风格 |
| `red_blue_glass` | 红蓝渐变 | 半透明毛玻璃+渐变 |
| `Titanium_silver` | 钛银金属 | 金属灰质感 |
| `sandstone_gray` | 砂岩暖灰 | 暖灰色浅色主题 |
| `liquid_glass` | 清爽 | iOS风格毛玻璃效果 |
| `custom_image` | 自定义背景 | 用户自定义背景图 |

**默认设置** (`DEFAULT_SETTINGS`):
- 主题: liquid_glass
- 退出模式: ask（每次询问）
- 显示模式: scroll（滚动）
- Python路径: python3/python.exe
- Java8路径: Java_path/Java_8_win/bin
- Java11路径: Java_path/Java_11_win/bin
- 终端默认Shell: cmd

**数据文件路径**:
- `config/settings.json` — 用户设置
- `config/tools.json` — 工具数据
- `config/categories.json` — 分类数据
- `config/hotkeys.json` — 热键数据

**关键函数**:
- `load_settings()` / `save_settings()` — 设置读写（原子写入，自动备份）
- `load_tools()` / `save_tools()` — 工具数据读写（自动字段标准化、路径相对化）
- `load_categories()` / `save_categories()` — 分类读写
- `export_all_data()` / `import_all_data()` — 全量导入导出（支持合并/覆盖）
- `_atomic_write_json()` — 原子JSON写入（先写临时文件，再rename，原文件备份为.bak）

**工具数据字段标准化映射**:
- tool_name/title/tool_title → name
- tool_category/cate → category
- tool_type/env/env_type → type
- tool_path/file/filepath → path
- tool_params/param/args → params
- tool_url/link → url
- tool_desc/desc → description
- priority/order → weight

**动态样式表** (`STYLESHEET`): 根据当前主题生成完整的QSS样式，涵盖 QMainWindow、QPushButton、QMenu、QLineEdit、QComboBox、QScrollBar、QDialog、QTabWidget、QGroupBox、QCheckBox、QSpinBox 等所有控件。

---

### 3. loader.py — 启动加载器

**`FluidParticle`** — 流体粒子类
- 140个粒子围绕中心旋转，红/蓝/白三色阵营
- 带拖尾轨迹、径向渐变光晕
- 粒子会随时间衰减半径，到达最小值后重生

**`FluidLoader(QWidget)`** — 启动画面窗口
- 580×380 无边框置顶透明窗口
- 2秒动画：中央光球 + 粒子环绕 + Logo + "天狐渗透工具箱-社区版V4.0" 标题 + "SYSTEM INITIALIZING" 加载提示
- 后台线程预加载 `main.py` 模块
- 加载 `config/fox.png` 作为Logo
- 动画结束后启动 `main.py` 并退出自身

---

### 4. launcher.py — 简化版启动器

**`LauncherWindow`** — 传统风格的工具启动器
- 使用菜单栏 + 搜索 + 分类折叠面板布局
- 工具以按钮网格排列（每行6个）
- 分类有映射合并显示（如"信息收集工具"和"爆破工具"合并为"渗透利器工具"）
- 支持添加自定义工具
- 浅色主题，独立于主界面的主题系统

---

### 5. utils.py — 工具函数库

**单实例控制** (`ensure_single_instance`):
- 基于 socket 端口监听实现
- 启动时绑定随机端口，将端口号写入 `config/.instance.lock`
- 二次启动时探测已有实例，提示"程序已经在运行中"

**工具运行** (`run_tool`):
- 支持的类型: 网页、Python(自定义解释器)、Java(自定义解释器)、JAVA8/JAVA11、GUI应用、命令行、批处理、PowerShell
- 每种类型使用对应的命令模板启动
- 自动记录最近启动历史

**环境检查** (`check_environment`):
- JAVA8/JAVA11: 检查Java路径是否存在
- Python: 检查Python解释器是否存在
- 命令行/GUI应用/批处理/PowerShell: 直接通过
- 有缓存机制避免重复弹窗 (`ENV_WARNED`)

**搜索** (`fuzzy_search`): 在工具名称、描述、分类、标签中模糊匹配（不区分大小写）

**收藏系统**: `is_tool_favorited` / `add_favorite_tool` / `remove_favorite_tool` / `get_favorite_tools`
- 存储在 settings.json 的 favorite_tools 字段，以 [name, category] 对标识

**最近启动**: `add_recent_tool` / `get_recent_tools`
- 存储在 settings.json 的 recent_tools 字段，最多保留10条

**窗口状态**: `save_main_window_geometry` / `load_main_window_geometry` / `save_main_window_state` / `load_main_window_state`
- 使用 base64 编码存储在 settings.json 中

**Liquid Glass 动画系统**:
- `_LiquidGlassAnimFilter` — 事件过滤器，为按钮/输入框/下拉框添加 hover/focus/press 光晕脉冲动画
- `_PopupBlurFilter` — 弹出菜单毛玻璃效果（仅 red_blue_glass 主题）
- `install_liquid_glass_animations()` — 安装动画过滤器
- `install_red_blue_glass_popup_blur()` — 安装弹出模糊过滤器
- `animate_liquid_glass_fade()` — 淡入动画
- `animate_liquid_glass_menu()` — 菜单弹出动画

**搜索线程** (`SearchWorker`): 异步搜索，使用 pyqtSignal 返回结果

---

### 6. widgets.py — 自定义控件

**`TitleBar(QWidget)`**:
- 显示标题"天狐渗透工具箱-社区版V4.0"
- 团队信息 "ONE-FOX安全团队 By.狐狸 官网: https://www.one-fox.cn/"
- CPU/内存性能监控标签
- 最小化/最大化/关闭按钮
- 支持拖拽移动窗口、双击切换最大化

**`SearchBar(QFrame)`**:
- 搜索图标 + 输入框
- 300ms 防抖

**`CategoryButton(QPushButton)`**:
- 可选中样式
- 右键菜单: 新建/重命名/删除/上移/下移分类
- 带 `_AnimatedMenuItem` 动画菜单项

**`CategoryPanel(QFrame)`**:
- 信号: category_selected / category_renamed / category_deleted / category_added / category_move
- "全部工具" 按钮 + 分类列表 + 滚动区域
- 分类显示格式: "📁 分类名 (数量)"

**`ToolDialog(QDialog)`**:
- 添加/编辑工具对话框（无边框）
- 字段: 名称/类型/路径/URL/分类/参数/描述/标签(最多3个)/权重(0-10)/快捷键
- 类型下拉支持动态添加自定义 Python/Java 解释器选项
- 快捷键录入: 直接按键捕获，禁止系统快捷键冲突（Ctrl+C/V/X/Z/Y/F）
- 标签验证: 最多3个，每个≤10字符

**`SettingsDialog(QDialog)`**:
- 4个选项卡: 常规 / 主题 / 环境 / 高级
- **常规**: 退出确认、退出模式、显示模式、健康检查
- **主题**: 10种主题切换，自定义背景图
- **环境**: Python路径、Java8/11路径
- **高级**: 自定义Python/Java解释器管理、截图快捷键、快捷启动面板快捷键、终端设置

---

### 7. core/env_manager.py — 环境管理器

**`EnvManager`** — 单例模式
- 解析 Python/Java 路径优先级: 用户自定义 > 内置 > 系统PATH
- `get_python_path()` — 获取Python解释器路径
- `get_java_home(version)` / `get_java_exe(version, gui)` — 获取Java路径
- `get_injected_env(env_type)` — 构建注入环境变量的字典
  - 注入 PATH (Python目录 + Java bin目录)
  - 设置 PYTHONHOME / JAVA_HOME / CLASSPATH
  - 支持自定义解释器名称解析 (Python(name) / Java(name))
- `open_cmd()` / `open_powershell()` — 打开带环境注入的终端
- `identify_version(path)` — 识别 Java/Python 版本号
- `run_tool_command()` — 带环境注入的命令执行

---

### 8. core/modern_grid.py — 工具卡片网格

**`TooltipPopup(QWidget)`** — 自定义工具提示弹窗
- 带阴影、圆角、淡入+上移动画
- HTML格式显示工具详细信息

**`ToolModel(QAbstractListModel)`** — 工具数据模型

**`ToolDelegate(QStyledItemDelegate)`** — 卡片绘制代理
- 卡片尺寸: 200×140
- 绘制内容: 健康状态指示灯(绿/红)、工具名、权重徽章、收藏星标、标签、描述、类型徽章、分类、运行按钮
- Liquid Glass 主题: 带渐变揭示动画、悬停光晕、滚动渐显
- 批量选择模式: 显示选中勾标

**`ModernToolGrid(QListView)`** — 工具网格视图
- IconMode + 自适应布局
- 卡片大小根据视口自动调整 (`adjust_card_size`)
- 右键菜单: 运行/编辑/删除/打开文件夹/打开CMD/打开PowerShell
- 悬停3秒显示详细工具提示
- Liquid Glass 主题: 悬停渐变、揭示动画、滚动渐显、菜单动画
- **`LiquidGlassMenu(QMenu)`** — 带悬停高亮动画的自定义菜单

---

### 9. core/screenshot.py — 截图工具

**`ScreenshotOverlay(QWidget)`** — 全屏截图叠加层
- **选区**: 鼠标拖拽选择区域，8个控制手柄可调整大小，可移动
- **标注工具**: 画笔/箭头/文字/马赛克/橡皮
- **颜色**: 6色循环 (红/橙/黄/绿/白/黑)
- **操作**: 撤销(Ctrl+Z)、保存到剪贴板(Enter)、另存为(Ctrl+S)、取消(Esc)
- **DPR适配**: 正确处理高DPI屏幕截图
- **工具栏**: 选区下方浮动工具栏

---

### 10. core/window_effect.py — 窗口特效

**`WindowEffect`** — Windows DWM API 调用
- `set_acrylic_effect(hwnd, is_dark)` — 设置亚克力/Mica 毛玻璃背景效果
- `remove_background_effect(hwnd)` — 移除背景效果
- 使用 `dwmapi.DwmSetWindowAttribute` 设置 `DWMWA_SYSTEMBACKDROP_TYPE`

---

### 11. services/tool_health.py — 工具健康检查

**`ToolHealthChecker`**:
- `check_tool(tool_data)` — 检查单个工具路径是否存在
  - 网页类型: 始终返回 "ok"
  - 无路径: 返回 "missing"
  - 路径不存在: 返回 "missing"
  - 路径存在: 返回 "ok"
- `check_all(tools)` — 批量检查
- `get_missing_tools(tools)` — 获取缺失工具列表
- `get_summary(tools)` — 获取统计摘要

---

### 12. views/terminal_tab_widget.py — 终端标签管理

**`TerminalTabWidget(QWidget)`**:
- 标签式终端管理
- 新建终端: CMD / PowerShell / CMD(管理员) / PowerShell(管理员)
- 管理员模式: 使用 `ShellExecuteW` 以 runas 提权
- 关闭标签时: 根据设置提示保存（有内容时询问/总是询问/自动保存/自动丢弃）
- 保存会话: 导出到文本文件
- 状态栏: 显示标签数/运行中数

---

### 13. views/terminal_widget.py — 终端模拟器

**`TerminalWidget(QWidget)`**:
- 基于 **pyte** (VT220终端模拟) + **winpty** (Windows伪终端)
- 支持 CMD / PowerShell 两种Shell
- 功能按钮: 重启/清屏/保存会话
- 命令历史: 上下方向键浏览
- 快捷键: Ctrl+C中断、Ctrl+L清屏、Tab补全
- 终端显示: `_TermDisplay` 自绘组件
  - 字体: Consolas 11pt
  - 16色 ANSI 颜色支持（含 bright 变体）
  - 鼠标选择文本、右键复制
  - 滚动条 + 回滚缓冲区 (9999行)
- 自动注入环境变量 (通过 `EnvManager.get_injected_env("cli_default")`)
- PowerShell 自动设置 UTF-8 编码
- 窗口resize自动调整终端行列数

---

### 14. 启动脚本

**`天狐渗透工具箱-社区版V4.0.vbs`**:
```vbs
Set ws = CreateObject("Wscript.Shell")
ws.run "cmd /c .\python3\python.exe loader.py", vbhide
```
隐藏CMD窗口启动 loader.py

**`启动工具箱.bat`**:
```bat
start "" python3\pythonw.exe launcher.py
```
使用 pythonw 无窗口启动 launcher.py（简化版启动器）

**`创建桌面快捷方式.bat`**:
- 创建指向 VBS 启动脚本的桌面快捷方式
- 使用 fox.ico 作为图标
- 创建后打开官网

---

### 15. 免责声明与许可证

**免责声明.txt**:
- 声明工具仅供学习和测试，禁止商业用途
- 禁止复制分发传播
- 禁止反向工程
- 使用者需遵守网络安全法
- 作者不承担任何责任

**LICENSE**: GPL v3，版权归属 One-Fox Security Team by Fox (2022-2026)

---

## 数据流

```
用户操作 → MainWindow → config.py (读写JSON) → config/*.json
                     → utils.py (run_tool) → core/env_manager.py (环境注入) → subprocess
                     → core/modern_grid.py (卡片渲染)
                     → widgets.py (对话框交互)
                     → core/screenshot.py (截图)
                     → views/terminal_*.py (终端)
                     → services/tool_health.py (健康检查)
```

## 编码规范与约定

### 批处理文件（.bat）编写规则
- **只写命令本身**，不添加 `@echo off`、`cd /d "%~dp0"`、`pause` 等额外内容
- 除非有特殊需求，否则保持批处理文件内容最简化
- 示例：启动一个 jar 工具，批处理文件内容只需 `java -jar xxx.jar`

---

## 关键依赖

| 库 | 用途 |
|---|---|
| PyQt6 | GUI框架 |
| keyboard | 全局热键注册 |
| psutil | CPU/内存监控（可选） |
| pyte | VT220终端模拟 |
| winpty | Windows伪终端 |
| ctypes (dwmapi) | Windows窗口特效 |
