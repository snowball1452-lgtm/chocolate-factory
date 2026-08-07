# docs/agent-control/adapters/snowdrift_bridge.py

import urllib.request
import urllib.error
import json
from typing import Dict, Any, Optional

class SnowDriftBridge:
    """
    Bridge between desktop (Odysseus/OpenClaw) and mobile (SnowDrift).
    SnowDrift runs a FastAPI daemon on the device.
    """
    def __init__(self, device_url: str = "http://localhost:8000"):
        self.device_url = device_url.rstrip('/')

    def sync_memory(self, agent_id: str) -> Dict[str, Any]:
        """
        Synchronizes memory with the mobile daemon.
        """
        url = f"{self.device_url}/sync"
        payload = {"agent_id": agent_id}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                return json.loads(body)
        except Exception as e:
            raise RuntimeError(f"SnowDrift sync_memory failed: {e}")

    def push_policy_epd(self, agent_id: str, epd: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pushes Effective Policy Document to mobile.
        """
        url = f"{self.device_url}/policy"
        payload = {
            "agent_id": agent_id,
            "epd": epd
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                return json.loads(body)
        except Exception as e:
            raise RuntimeError(f"SnowDrift push_policy_epd failed: {e}")

    def get_mobile_status(self, device_id: str) -> Dict[str, Any]:
        """
        Queries status of the mobile device.
        """
        url = f"{self.device_url}/status/{device_id}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                return json.loads(body)
        except Exception as e:
            raise RuntimeError(f"SnowDrift get_mobile_status failed: {e}")

    def send_task_to_mobile(self, agent_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a task to the mobile device for execution.
        """
        url = f"{self.device_url}/tasks"
        payload = {
            "agent_id": agent_id,
            "task": task
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                return json.loads(body)
        except Exception as e:
            raise RuntimeError(f"SnowDrift send_task_to_mobile failed: {e}")

    def receive_mobile_result(self, task_id: str) -> Dict[str, Any]:
        """
        Retrieves the result of a delegated mobile task by ID.
        """
        url = f"{self.device_url}/tasks/{task_id}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                return json.loads(body)
        except Exception as e:
            raise RuntimeError(f"SnowDrift receive_mobile_result failed: {e}")
