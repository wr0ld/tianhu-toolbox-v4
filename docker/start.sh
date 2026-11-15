#!/bin/bash
set -Eeuo pipefail
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
pids=()
cleanup() {
    trap - EXIT TERM INT
    if ((${#pids[@]})); then
        kill "${pids[@]}" 2>/dev/null || true
        wait "${pids[@]}" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 0' TERM INT
Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp &
pids+=("$!")
ready=false
for ((i=0; i<100; i++)); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 0.1
done
if [[ "$ready" != true ]]; then
    echo 'Virtual display failed to start' >&2
    exit 1
fi
openbox &
pids+=("$!")
# Only websockify inside this container can reach the VNC server.
x11vnc -display "$DISPLAY" -localhost -rfbport 5900 -forever -shared -nopw &
pids+=("$!")
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &
pids+=("$!")
"$@" &
pids+=("$!")
# Stop the container if the GUI or any display service exits.
wait -n "${pids[@]}"
