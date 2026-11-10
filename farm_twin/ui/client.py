"""Python HTTP client for Streamlit; keeps transport concerns outside UI pages."""
from __future__ import annotations
from typing import Any
import httpx

class APIClient:
    def __init__(self, base_url: str, token: str|None=None, timeout_s: float=15.) -> None:
        self.base_url=base_url.rstrip("/")
        self.headers={"Authorization":f"Bearer {token}"} if token else {}
        self.timeout=httpx.Timeout(timeout_s)
    def request(self, method: str, path: str, *, json: Any=None, files: Any=None, extra_headers: dict[str, str]|None=None) -> Any:
        headers={**self.headers, **(extra_headers or {})}
        response=httpx.request(method,self.base_url+path,json=json,files=files,headers=headers,timeout=self.timeout)
        response.raise_for_status()
        return response.json() if response.content else None
    def get(self,path: str) -> Any: return self.request("GET",path)
    def post(self,path: str,payload: Any,idempotency_key: str|None=None) -> Any:
        headers={"Idempotency-Key":idempotency_key} if idempotency_key else {}
        return self.request("POST",path,json=payload,extra_headers=headers)
