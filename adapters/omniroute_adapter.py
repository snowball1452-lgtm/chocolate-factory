# docs/agent-control/adapters/omniroute_adapter.py

import urllib.request
import urllib.error
import json
from typing import List, Dict, Any, Optional

class OmniRouteAdapter:
    """
    Adapter for the OmniRoute model router.
    OmniRoute is an OpenAI-compatible endpoint at localhost:18789.
    """
    def __init__(self, base_url: str = "http://localhost:18789"):
        self.base_url = base_url.rstrip('/')

    def get_available_models(self) -> List[str]:
        """
        Queries localhost:18789/v1/models and returns available model IDs.
        """
        url = f"{self.base_url}/v1/models"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                data = json.loads(body)
                # OpenAI standard models response: {"data": [{"id": "model_id", ...}]}
                models = [model["id"] for model in data.get("data", [])]
                return models
        except Exception as e:
            raise RuntimeError(f"OmniRoute get_available_models failed: {e}")

    def route_request(self, model_preference: str, prompt: str) -> Dict[str, Any]:
        """
        Routes an OpenAI-compatible chat completion request to the base_url endpoint.
        """
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": model_preference,
            "messages": [{"role": "user", "content": prompt}]
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        
        try:
            with urllib.request.urlopen(req) as response:
                body = response.read().decode('utf-8')
                return json.loads(body)
        except Exception as e:
            raise RuntimeError(f"OmniRoute request failed for model '{model_preference}': {e}")

    def fallback_chain(self, models: List[str], prompt: str) -> Dict[str, Any]:
        """
        Tries to route the request to each model in the list in order.
        If a model fails, it falls back to the next one.
        Returns the first successful response.
        Raises RuntimeError if all models fail.
        """
        errors = []
        for model in models:
            try:
                return self.route_request(model, prompt)
            except Exception as e:
                errors.append(f"{model}: {e}")
                
        raise RuntimeError(f"All models in fallback chain failed: {', '.join(errors)}")
