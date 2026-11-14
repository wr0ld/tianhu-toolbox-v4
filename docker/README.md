# Docker / Apple Silicon

此镜像提供天狐 PyQt6 主界面，使用 Xvfb + Openbox + x11vnc + noVNC，
在浏览器中显示 Linux 桌面，不需要在 Mac 安装 XQuartz。
基础镜像和 Debian PyQt6 包支持 ARM64 / AMD64；构建默认跟随主机架构。

## 启动

```bash
git clone https://github.com/stave888/tianhu-toolbox-v4.git
cd tianhu-toolbox-v4
# PR 合并前需要先切到包含 Dockerfile 的分支：
git switch codex/docker-arm64-gui
docker compose up -d --build
```

打开 http://localhost:6080/vnc.html?autoconnect=true&resize=scale 。
首次构建需要下载 Debian 与图形组件。此配置无登录认证，仅绑定本机
127.0.0.1，供单用户本机使用；不要将端口改为公网或局域网监听。

```bash
docker compose logs -f toolbox
docker compose down
```

配置和工具目录存放在两个 Docker 命名卷中，普通 `down` 不会删除。
应用日志同时输出到容器日志；/app/app.log 不持久化。
`docker compose down -v` 会删除这些数据。关闭应用窗口并选择退出后，
容器会停止；再次执行 `docker compose up -d` 即可重启。

也可单独使用 Dockerfile（不持久化数据）：

```bash
docker build -t tianhu-toolbox:local .
docker run --rm -p 127.0.0.1:6080:6080 --shm-size=256m tianhu-toolbox:local
```

## 当前限制

- 仓库是轻便版，没有附带 tools/ 工具或完整工具列表，空列表是预期行为。
- 当前 utils.py 的 Python、GUI、命令行等启动逻辑仍使用 Windows `cmd`，
  Java 环境路径也偏向 Windows。容器化主界面不代表这些工具启动功能已经移植。
- Windows EXE、批处理、PowerShell、winpty 终端和部分“打开目录”操作不受支持。
- 不包含 Java 8/11、Wine 或其他安全测试工具，也没有安装浏览器供“网页”工具使用。
  启动时原应用可能弹出“未检测到 JAVA8 运行环境”等提示，点击 OK 关闭；
  这不代表 Java 工具已可用。
- 本次仅添加运行容器及说明，不修改原有应用功能。完整 Linux 工具启动支持需单独改造。
- 镜像以普通用户运行。请使用兼容 Linux ARM64 的工具；macOS 程序不能在 Linux 容器运行。

依赖说明：https://packages.debian.org/bookworm/python3-pyqt6
显示方案：https://novnc.com/
