"""Client that wraps the management-backend ``/flink`` endpoints.

Backend routes reference:

    GET    /flink/deployments
    GET    /flink/sessionjobs
    GET    /flink/sessionjobs/{name}
    POST   /flink/sessionjobs                # body = FlinkSessionJobCreate
    PATCH  /flink/sessionjobs/{name}         # body = FlinkSessionJobPatch
    POST   /flink/sessionjobs/{name}/activate
    POST   /flink/sessionjobs/{name}/suspend
    POST   /flink/sessionjobs/{name}/savepoint
    POST   /flink/sessionjobs/{name}/scale?parallelism=N
    DELETE /flink/sessionjobs/{name}
    GET    /flink/jobs
    GET    /flink/jobs/{job_id}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class ManagementFlinkClient:
    def __init__(
        self,
        base_url: str = "http://management-api.management.svc.cluster.local:8080/api",
        *,
        timeout: float = 15.0,
        token: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers)

    def __enter__(self) -> "ManagementFlinkClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Deployments + session jobs
    # ------------------------------------------------------------------

    def list_deployments(self) -> List[Dict[str, Any]]:
        return self._client.get("/flink/deployments").raise_for_status().json()  # type: ignore[no-any-return]

    def list_session_jobs(self) -> List[Dict[str, Any]]:
        return self._client.get("/flink/sessionjobs").raise_for_status().json()  # type: ignore[no-any-return]

    def get_session_job(self, name: str) -> Dict[str, Any]:
        return self._client.get(f"/flink/sessionjobs/{name}").raise_for_status().json()  # type: ignore[no-any-return]

    def create_session_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.post("/flink/sessionjobs", json=payload).raise_for_status().json()  # type: ignore[no-any-return]

    def patch_session_job(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._client.patch(f"/flink/sessionjobs/{name}", json=payload).raise_for_status().json()  # type: ignore[no-any-return]

    def delete_session_job(self, name: str) -> None:
        self._client.delete(f"/flink/sessionjobs/{name}").raise_for_status()

    # ---- convenience helpers (just hit the dedicated endpoints) ----

    def activate(self, name: str) -> Dict[str, Any]:
        return self._client.post(f"/flink/sessionjobs/{name}/activate").raise_for_status().json()  # type: ignore[no-any-return]

    def suspend(self, name: str) -> Dict[str, Any]:
        return self._client.post(f"/flink/sessionjobs/{name}/suspend").raise_for_status().json()  # type: ignore[no-any-return]

    def savepoint(self, name: str) -> Dict[str, Any]:
        return self._client.post(f"/flink/sessionjobs/{name}/savepoint").raise_for_status().json()  # type: ignore[no-any-return]

    def scale(self, name: str, parallelism: int) -> Dict[str, Any]:
        return (
            self._client.post(f"/flink/sessionjobs/{name}/scale", params={"parallelism": parallelism})
            .raise_for_status()
            .json()
        )

    # ------------------------------------------------------------------
    # Flink REST proxy
    # ------------------------------------------------------------------

    def list_jobs(self) -> List[Dict[str, Any]]:
        return self._client.get("/flink/jobs").raise_for_status().json()  # type: ignore[no-any-return]

    def job_metrics(self, job_id: str) -> Dict[str, Any]:
        return self._client.get(f"/flink/jobs/{job_id}").raise_for_status().json()  # type: ignore[no-any-return]
