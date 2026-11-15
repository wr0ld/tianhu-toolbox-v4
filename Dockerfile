FROM eclipse-temurin:8-jre-jammy AS java8
FROM eclipse-temurin:11-jre-jammy AS java11

FROM debian:bookworm-slim

# Debian provides native PyQt6 packages for both arm64 and amd64.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pyqt6 xvfb x11vnc novnc websockify openbox \
    x11-utils fonts-noto-cjk ca-certificates tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 toolbox

RUN apt-get update && apt-get install -y --no-install-recommends qt6-qpa-plugins xterm xdg-utils libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=java8 /opt/java/openjdk /opt/java8
COPY --from=java11 /opt/java/openjdk /opt/java11
ENV JAVA8_HOME=/opt/java8 \
    JAVA11_HOME=/opt/java11 \
    JAVA_HOME=/opt/java8 \
    PATH=/opt/java8/bin:$PATH
RUN java -version && /opt/java11/bin/java -version

ENV DISPLAY=:99 \
    QT_QPA_PLATFORM=xcb \
    QT_X11_NO_MITSHM=1 \
    PYTHONUNBUFFERED=1 \
    XDG_RUNTIME_DIR=/tmp/runtime-toolbox
WORKDIR /app
COPY --chown=toolbox:toolbox . /app
RUN chmod +x /app/docker/start.sh \
    && mkdir -p /app/tools /app/logs \
    && chown -R toolbox:toolbox /app
USER toolbox
EXPOSE 6080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6080/vnc.html', timeout=3)" || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/start.sh"]
CMD ["python3", "main.py"]
