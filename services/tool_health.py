import os
import logging
from typing import Dict, Any, List, Tuple
logger = logging.getLogger(__name__)


class ToolHealthChecker:
    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir or os.path.abspath("tools")

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return os.path.abspath(path)
        return os.path.abspath(os.path.join(self._base_dir, path))
    def check_tool(self, tool_data: Dict[str, Any]) -> str:
        path = tool_data.get("path", "")
        tool_type = tool_data.get("type", "")
        if tool_type == "网页":
            url = tool_data.get("url", "")
            if url:
                safe_url = str(url).replace('\n', '').replace('\r', '').strip()
                if safe_url.lower().startswith(("http://", "https://")):
                    return "ok"
                else:
                    return "ok"
            return "ok"
        if not path:
            return "missing"
        abs_path = self._resolve_path(path)
        if os.path.isfile(abs_path):
            return "ok"
        if os.path.isdir(abs_path):
            return "ok"
        return "missing"
    def check_all(self, tools: List[Dict[str, Any]]) -> Dict[str, str]:
        results = {}
        for tool in tools:
            name = tool.get("name", "")
            status = self.check_tool(tool)
            if name:
                results[name] = status
        return results
    def get_missing_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [t for t in tools if self.check_tool(t) == "missing"]
    def get_summary(self, tools: List[Dict[str, Any]]) -> Dict[str, int]:
        total = len(tools)
        ok_count = sum(1 for t in tools if self.check_tool(t) == "ok")
        missing_count = total - ok_count
        return {"total": total, "ok": ok_count, "missing": missing_count}
