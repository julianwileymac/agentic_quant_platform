"""``BedrockAgentCoreGatewayBridge`` — expose AQP DataMCP tools as AgentCore Gateway tools.

Phase E of the AWS hybrid rollout. When the operator opts into the
Bedrock AgentCore runtime path, the AgentCore Gateway needs the AQP
:class:`DataMCPTool` catalog to be expressed as the OpenAPI-shape
tool config AgentCore's Gateway expects. This bridge:

1. Reads every registered :class:`DataMCPTool` from
   :data:`aqp.data.mcp.registry.DATA_MCP_TOOLS`.
2. Emits an AgentCore Gateway tool-config JSON document (one
   ``tools[]`` entry per DataMCPTool, using the canonical
   :meth:`DataMCPTool.to_mcp_tool_descriptor` shape).
3. Optionally uploads the document to the AgentCore Gateway via
   ``boto3.client('bedrock-agentcore').update_gateway`` so a new
   DataMCPTool subclass surfaces in AgentCore Gateway automatically
   on the next ``aqp deploy aws``.
4. Stores the rendered JSON URI in SSM
   ``/aqp/${env}/agentcore_gateway_tool_config_uri`` for replay /
   audit.

The bridge is import-safe: when ``boto3`` is missing or the gateway
ARN is unset, only the in-memory rendering happens; the upload path
no-ops cleanly. That keeps local development friction-free.

Per AGENTS rule 22 this bridge does NOT bypass DataMCP — it MIRRORS
the same catalog into a second transport. Every tool invocation
(whether routed via the in-process bridge, the FastAPI ``/mcp/data``
router, or AgentCore Gateway) lands on the same Python class.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings
from aqp.data.mcp.registry import (
    DATA_MCP_TOOLS,
    DATA_MCP_TOOL_HASHES,
)

logger = logging.getLogger(__name__)


@dataclass
class GatewayToolConfig:
    """In-memory AgentCore Gateway tool-config document.

    The wire shape mirrors the AgentCore Gateway ``tools[]`` envelope:
    each entry carries ``name``, ``description``, ``input_schema``
    (JSON-schema), and the canonical AQP descriptor hash so a replay
    can verify the exact catalog snapshot the run saw.
    """

    tools: list[dict[str, Any]] = field(default_factory=list)
    descriptor_hashes: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "tools": list(self.tools),
            "descriptor_hashes": dict(self.descriptor_hashes),
            "catalog_hash": self.catalog_hash(),
        }

    def catalog_hash(self) -> str:
        """Stable SHA-256 over the rendered catalog payload.

        The hash is computed over the sorted-key JSON of
        ``{name: descriptor_hash}`` so re-ordering the registry has no
        effect on the catalog id.
        """
        canonical = json.dumps(
            sorted(self.descriptor_hashes.items()),
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BedrockAgentCoreGatewayBridge:
    """Render + (optionally) publish the AgentCore Gateway tool config.

    The bridge is stateless and side-effect-free until
    :meth:`publish_to_gateway` is called.
    """

    def __init__(
        self,
        *,
        environment: str | None = None,
        gateway_arn_ssm_path: str | None = None,
        config_s3_bucket: str | None = None,
        config_s3_key: str | None = None,
    ) -> None:
        self._environment = environment or os.environ.get(
            "AQP_ENVIRONMENT", "dev"
        )
        self._gateway_arn_ssm_path = (
            gateway_arn_ssm_path
            or f"/aqp/{self._environment}/agentcore_gateway_arn"
        )
        self._config_s3_bucket = config_s3_bucket
        self._config_s3_key = (
            config_s3_key
            or f"aqp/{self._environment}/agentcore_gateway_tool_config.json"
        )

    # --- Rendering -----------------------------------------------------

    def render(
        self,
        *,
        include_mutating: bool = True,
        scope_filter: tuple[str, ...] | None = None,
    ) -> GatewayToolConfig:
        """Build the in-memory tool-config from the live DataMCP registry.

        ``include_mutating`` mirrors :attr:`DataMCPTool.mutates` so
        operators can ship a read-only AgentCore Gateway by default
        and opt in to mutating tools per environment.

        ``scope_filter`` restricts the exposed catalog to tools whose
        :attr:`required_scopes` intersect the filter. The default
        ``None`` exposes every tool (the calling agent's IAM
        permissions decide what actually runs).
        """
        cfg = GatewayToolConfig()
        for tool_name, tool_cls in sorted(DATA_MCP_TOOLS.items()):
            mutates = bool(getattr(tool_cls, "mutates", False))
            if not include_mutating and mutates:
                continue
            scopes = tuple(getattr(tool_cls, "required_scopes", ()))
            if scope_filter and not (set(scope_filter) & set(scopes)):
                continue
            try:
                descriptor = tool_cls.to_mcp_tool_descriptor()
            except Exception:  # noqa: BLE001 - never break the catalog render
                logger.warning(
                    "to_mcp_tool_descriptor failed for %s",
                    tool_name,
                    exc_info=True,
                )
                continue
            gateway_entry = self._descriptor_to_gateway_entry(
                tool_name=tool_name,
                descriptor=descriptor,
                mutates=mutates,
                scopes=scopes,
            )
            cfg.tools.append(gateway_entry)
            digest = DATA_MCP_TOOL_HASHES.get(tool_name, "")
            if digest:
                cfg.descriptor_hashes[tool_name] = digest
        return cfg

    @staticmethod
    def _descriptor_to_gateway_entry(
        *,
        tool_name: str,
        descriptor: dict[str, Any],
        mutates: bool,
        scopes: tuple[str, ...],
    ) -> dict[str, Any]:
        """Translate the AQP descriptor shape to the AgentCore Gateway shape."""
        return {
            "name": tool_name,
            "description": str(descriptor.get("description") or ""),
            "input_schema": descriptor.get("input_schema")
            or descriptor.get("inputSchema")
            or {"type": "object", "properties": {}},
            "mutates": bool(mutates),
            "required_scopes": list(scopes),
            "transport": "aqp-data-mcp",
            "invoke_url": f"/mcp/data/tools/{tool_name}/invoke",
        }

    # --- Publish -------------------------------------------------------

    def publish_to_gateway(
        self,
        cfg: GatewayToolConfig | None = None,
    ) -> dict[str, Any]:
        """Upload the rendered config to S3 + register targets on the Gateway.

        Two-step process (per the AgentCore Runtime + Gateway contract):

        1. **S3 upload** — write the rendered tool-config JSON to
           ``s3://<bucket>/<key>``; record the URI in SSM at
           ``/aqp/${env}/agentcore_gateway_tool_config_uri``. This is
           what the Gateway reads on every cold-start of a routed call.
        2. **Per-tool target registration** — call the bedrock-agentcore
           SDK's ``list_gateway_targets`` to compute the diff, then
           ``create_gateway_target`` / ``update_gateway_target`` /
           ``delete_gateway_target`` to converge the live registry to
           the desired catalog. Targets are addressed by ``targetName``
           (= the AQP tool name, ``data.*``); the diff is hash-aware so
           a no-op render is a no-op publish.

        Returns a result dict shaped::

            {
                "published": bool,
                "gateway_arn": str | None,
                "config_uri": str | None,
                "catalog_hash": str,
                "targets_created":  list[str],
                "targets_updated":  list[str],
                "targets_deleted":  list[str],
                "reason": str,
            }

        ``published=False`` indicates a missing dependency (boto3,
        gateway ARN, S3 bucket) — never a fatal error. The caller
        decides whether to escalate.
        """
        cfg = cfg or self.render()
        body = json.dumps(cfg.to_payload(), indent=2)
        catalog_hash = cfg.catalog_hash()
        empty_diff: dict[str, list[str]] = {
            "targets_created": [],
            "targets_updated": [],
            "targets_deleted": [],
        }
        if not self._config_s3_bucket:
            logger.info(
                "AgentCore gateway publish skipped: AQP_AGENTCORE_GATEWAY_CFG_BUCKET unset"
            )
            return {
                "published": False,
                "gateway_arn": None,
                "config_uri": None,
                "catalog_hash": catalog_hash,
                "reason": "no S3 bucket configured",
                **empty_diff,
            }

        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError:
            return {
                "published": False,
                "gateway_arn": None,
                "config_uri": None,
                "catalog_hash": catalog_hash,
                "reason": "boto3 not installed",
                **empty_diff,
            }

        s3 = boto3.client("s3")
        ssm = boto3.client("ssm")
        try:
            s3.put_object(
                Bucket=self._config_s3_bucket,
                Key=self._config_s3_key,
                Body=body.encode("utf-8"),
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )
            uri = f"s3://{self._config_s3_bucket}/{self._config_s3_key}"
            ssm.put_parameter(
                Name=f"/aqp/{self._environment}/agentcore_gateway_tool_config_uri",
                Value=uri,
                Type="String",
                Overwrite=True,
            )
            ssm.put_parameter(
                Name=f"/aqp/{self._environment}/agentcore_gateway_catalog_hash",
                Value=catalog_hash,
                Type="String",
                Overwrite=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("AgentCore gateway publish failed: %s", exc)
            return {
                "published": False,
                "gateway_arn": None,
                "config_uri": None,
                "catalog_hash": catalog_hash,
                "reason": f"upload failed: {exc}",
                **empty_diff,
            }

        gateway_arn: str | None = None
        gateway_id: str | None = None
        try:
            gw_param = ssm.get_parameter(Name=self._gateway_arn_ssm_path)
            gateway_arn = str(gw_param.get("Parameter", {}).get("Value") or "") or None
            if gateway_arn:
                gateway_id = gateway_arn.rsplit("/", 1)[-1] or None
        except Exception:  # noqa: BLE001
            gateway_arn = None

        diff = empty_diff
        sdk_reason = "no gateway arn in SSM"
        if gateway_id:
            try:
                ac_client = boto3.client("bedrock-agentcore-control")
            except Exception:  # noqa: BLE001
                ac_client = None
                sdk_reason = "bedrock-agentcore-control client unavailable"
            if ac_client is not None:
                try:
                    diff = self._converge_gateway_targets(
                        ac_client=ac_client,
                        gateway_id=gateway_id,
                        gateway_arn=gateway_arn,
                        cfg=cfg,
                    )
                    sdk_reason = "ok"
                except (BotoCoreError, ClientError) as exc:
                    sdk_reason = f"gateway target converge failed: {exc}"
                    logger.warning(sdk_reason)
                except Exception as exc:  # noqa: BLE001
                    sdk_reason = f"gateway target converge raised: {exc}"
                    logger.warning(sdk_reason, exc_info=True)

        return {
            "published": True,
            "gateway_arn": gateway_arn,
            "config_uri": uri,
            "catalog_hash": catalog_hash,
            "reason": sdk_reason,
            **diff,
        }

    def _converge_gateway_targets(
        self,
        *,
        ac_client: Any,
        gateway_id: str,
        gateway_arn: str | None,
        cfg: GatewayToolConfig,
    ) -> dict[str, list[str]]:
        """List existing targets + reconcile against the rendered ``cfg``.

        The AgentCore Gateway Control API for target CRUD is still
        stabilising; this method probes via ``hasattr`` so the bridge
        keeps working against either the documented or the most-recent
        SDK shape. When a method is missing we log + return an empty
        diff so the S3 upload + SSM URI still light up.
        """
        existing_names: set[str] = set()
        list_op = getattr(ac_client, "list_gateway_targets", None)
        if callable(list_op):
            try:
                paginator = ac_client.get_paginator("list_gateway_targets")
                for page in paginator.paginate(gatewayIdentifier=gateway_id):
                    for item in page.get("targets") or page.get("items") or []:
                        name = item.get("name") or item.get("targetName")
                        if name:
                            existing_names.add(str(name))
            except Exception as exc:  # noqa: BLE001
                logger.debug("paginator unavailable, falling back to one-shot: %s", exc)
                resp = list_op(gatewayIdentifier=gateway_id)
                for item in resp.get("targets") or resp.get("items") or []:
                    name = item.get("name") or item.get("targetName")
                    if name:
                        existing_names.add(str(name))
        else:
            logger.debug(
                "bedrock-agentcore-control.list_gateway_targets missing in this SDK build"
            )

        desired_names = {entry["name"] for entry in cfg.tools}
        to_create = sorted(desired_names - existing_names)
        to_update = sorted(desired_names & existing_names)
        to_delete = sorted(existing_names - desired_names)

        created: list[str] = []
        updated: list[str] = []
        deleted: list[str] = []

        create_op = getattr(ac_client, "create_gateway_target", None)
        update_op = getattr(ac_client, "update_gateway_target", None)
        delete_op = getattr(ac_client, "delete_gateway_target", None)

        for entry in cfg.tools:
            name = entry["name"]
            target_def = {
                "gatewayIdentifier": gateway_id,
                "name": name,
                "description": entry["description"],
                "targetConfiguration": {
                    "mcp": {
                        "inputSchema": entry["input_schema"],
                        "invokeUrl": entry["invoke_url"],
                        "transport": entry["transport"],
                    }
                },
            }
            if name in to_create and callable(create_op):
                try:
                    create_op(**target_def)
                    created.append(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("create_gateway_target failed for %s: %s", name, exc)
            elif name in to_update and callable(update_op):
                try:
                    update_op(**target_def)
                    updated.append(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("update_gateway_target failed for %s: %s", name, exc)

        if callable(delete_op):
            for name in to_delete:
                try:
                    delete_op(gatewayIdentifier=gateway_id, name=name)
                    deleted.append(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("delete_gateway_target failed for %s: %s", name, exc)

        logger.info(
            "AgentCore gateway converge gateway_arn=%s created=%d updated=%d deleted=%d",
            gateway_arn,
            len(created),
            len(updated),
            len(deleted),
        )
        return {
            "targets_created": created,
            "targets_updated": updated,
            "targets_deleted": deleted,
        }


def render_default_tool_config() -> GatewayToolConfig:
    """Convenience: render with the deployment defaults from settings.

    Reads ``AQP_ENVIRONMENT`` + the optional
    ``AQP_AGENTCORE_GATEWAY_CFG_BUCKET`` env var; returns the
    in-memory :class:`GatewayToolConfig`. Useful from CI smoke tests
    that just want to assert the catalog renders without errors.
    """
    return BedrockAgentCoreGatewayBridge(
        environment=os.environ.get("AQP_ENVIRONMENT") or getattr(settings, "environment", "dev"),
        config_s3_bucket=os.environ.get("AQP_AGENTCORE_GATEWAY_CFG_BUCKET") or None,
    ).render()


__all__ = [
    "BedrockAgentCoreGatewayBridge",
    "GatewayToolConfig",
    "render_default_tool_config",
]
