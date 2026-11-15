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

## Linux 工具启动

镜像包含 ARM64/AMD64 原生 Java 8、Java 11 JRE 和 xterm。
Java 8 位于 `/opt/java8`，Java 11 位于 `/opt/java11`。
应用根据 JAVA8 / JAVA11 类型选择对应环境，图形化 JAR 使用同版本 java。
Python 默认使用应用自身的 `/usr/bin/python3`。
已有配置卷不需要删除；失效的 Windows Java 路径会回退到镜像中的环境。

- Python、JAVA8、JAVA11、命令行工具在独立 xterm 窗口运行，结束后保留输出。
- GUI应用、包含“图形化”的 Java 类型直接启动图形程序。
- `.sh` 文件选择“命令行”类型，使用 Bash 执行；Linux 二进制需要执行权限。
- 自定义 Java 路径支持 Java 根目录、bin 目录和 java 可执行文件。
- 参数遵循 Linux 引号规则；包含空格的参数用双引号包围。
  参数直接传给程序，不执行 `$()`、管道或重定向。如需组合命令，请编写 `.sh` 脚本。

将自己的工具复制到正在运行的容器工具卷（在仓库目录执行）：

```bash
docker compose cp ./my-tool.jar toolbox:/app/tools/my-tool.jar
```

在界面里添加工具，选择 JAVA8 或 JAVA11，路径填 `/app/tools/my-tool.jar`。
JVM 参数（例如 `-Xmx512m`）填“前置参数”，应用参数填“后置参数”。
工具所需的 Python 库及其他系统依赖需要另外安装到镜像中。

## 更新已运行的版本

```bash
git fetch https://github.com/stave888/tianhu-toolbox-v4.git codex/docker-arm64-gui
git switch --detach FETCH_HEAD
docker compose up -d --build
```

无需删除配置卷。如果切换提示有本地修改，请先保存修改，不要强制覆盖。

## 当前限制

- 仓库是轻便版，没有附带 tools/ 工具或完整工具列表，空列表是预期行为。
- Windows EXE、BAT、CMD、VBS 不支持，启动时会提示选择 Linux 版本。
- PowerShell 仅在另外安装 Linux `pwsh` 后可用；内置 Windows winpty 终端仍未移植。
- 部分原有“打开目录”操作及 Windows 记事本尚未适配。
- 没有安装浏览器供“网页”工具使用，也不包含 Wine 或安全测试工具。
- 镜像以普通用户运行。工具必须兼容 Linux 和容器 CPU 架构；macOS 程序不能直接运行。
- JRE 可运行 JAR，但不包含 javac 编译器。Java GUI 的第三方原生库需匹配 ARM64/AMD64。

## 验证

```bash
docker compose run --rm --entrypoint python3 toolbox -m unittest discover -s tests -v
```

依赖说明：https://packages.debian.org/bookworm/python3-pyqt6
Java 镜像：https://adoptium.net/installation/containers
显示方案：https://novnc.com/
