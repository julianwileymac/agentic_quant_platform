"""Pull DataHub aspects into AQP's entity_aspects store."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from aqp.config import settings
from aqp.data.datahub.aspect_mapping import ASPECT_TO_DATAHUB_CLASS
from aqp.data.datahub.client import get_client
from aqp.data.datahub.mapping import parse_urn as parse_datahub_urn
from aqp.metadata import make_urn, write_aspect
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)

_SDK_UNAVAILABLE_ERROR = "datahub SDK unavailable"

_DATAHUB_CLASS_TO_ASPECT_NAME: dict[str, str] = {
    "MLModelPropertiesClass": "mlModelMetadata",
    "DatasetPropertiesClass": "datasetProperties",
    "GlobalTagsClass": "businessMetadata",
    "SchemaMetadataClass": "dataContract",
    "InstitutionalMemoryClass": "documentMetadata",
    "UpstreamLineageClass": "lineageEdge",
    "MLModelTrainingDataClass": "mlTestResult",
    "DataJobInfoClass": "pipelineMetadata",
}


class _GenericAspectPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


def pull_aspect(*, datahub_urn: str, aspect_class_name: str) -> dict[str, Any]:
    """Pull one DataHub aspect into ``entity_aspects`` via ``write_aspect``."""
    parsed = parse_datahub_urn(datahub_urn)
    if str(parsed.get("kind") or "unknown") == "unknown":
        return {"pulled": False, "error": f"invalid DataHub URN: {datahub_urn}"}

    client, client_error = _resolve_aspect_client()
    if client_error or client is None:
        return {"pulled": False, "error": client_error or _SDK_UNAVAILABLE_ERROR}

    try:
        raw_aspect = _call_get_aspect(
            client,
            datahub_urn=datahub_urn,
            aspect_class_name=aspect_class_name,
        )
    except Exception as exc:  # noqa: BLE001
        return {"pulled": False, "error": str(exc)}

    try:
        aqp_urn = _to_aqp_urn(datahub_urn)
        aspect_name = _aspect_name_for_class(aspect_class_name)
        payload = _aspect_payload_dict(raw_aspect)
        return _persist_aspect(
            datahub_urn=datahub_urn,
            aqp_urn=aqp_urn,
            aspect_name=aspect_name,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("DataHub aspect pull failed for %s: %s", datahub_urn, exc)
        return {"pulled": False, "error": str(exc)}


def pull_all_aspects(*, datahub_urn: str) -> dict[str, Any]:
    """Pull every available DataHub aspect for an entity URN."""
    parsed = parse_datahub_urn(datahub_urn)
    if str(parsed.get("kind") or "unknown") == "unknown":
        return {"pulled": False, "error": f"invalid DataHub URN: {datahub_urn}"}

    client, client_error = _resolve_aspect_client()
    if client_error or client is None:
        return {"pulled": False, "error": client_error or _SDK_UNAVAILABLE_ERROR}

    try:
        latest = _call_get_latest_aspects(client, datahub_urn=datahub_urn)
    except Exception as exc:  # noqa: BLE001
        return {"pulled": False, "error": str(exc)}

    pairs = _iter_class_payload_pairs(latest)
    if not pairs:
        return {
            "pulled": True,
            "pulled_count": 0,
            "datahub_urn": datahub_urn,
            "results": [],
            "errors": [],
        }

    aqp_urn = _to_aqp_urn(datahub_urn)
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    pulled_count = 0

    for class_name, payload in pairs:
        aspect_name = _aspect_name_for_class(class_name)
        try:
            result = _persist_aspect(
                datahub_urn=datahub_urn,
                aqp_urn=aqp_urn,
                aspect_name=aspect_name,
                payload=payload,
            )
            results.append(result)
            pulled_count += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{class_name}: {exc}")
            results.append(
                {
                    "pulled": False,
                    "aqp_urn": aqp_urn,
                    "aspect_name": aspect_name,
                    "error": str(exc),
                }
            )

    return {
        "pulled": len(errors) == 0,
        "pulled_count": pulled_count,
        "datahub_urn": datahub_urn,
        "aqp_urn": aqp_urn,
        "results": results,
        "errors": errors,
    }


def _normalise_env(env: str | None) -> str:
    raw = str(env or settings.datahub_env or "PROD").strip().lower()
    aliases = {
        "prod": "prod",
        "production": "prod",
        "staging": "staging",
        "stage": "staging",
        "dev": "dev",
        "test": "test",
        "qa": "test",
    }
    return aliases.get(raw, "prod")


def _sanitize_entity_id(raw_id: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
    clean = "".join(ch if ch in allowed else ":" for ch in str(raw_id or "").strip())
    clean = clean.strip(":")
    return clean or "unknown"


def _extract_pipeline_name(datahub_urn: str) -> tuple[str, str]:
    if datahub_urn.startswith("urn:li:dataJob:("):
        body = datahub_urn[len("urn:li:dataJob:(") : -1]
        flow_urn, job_name = body.rsplit(",", 1)
        env = "PROD"
        if flow_urn.startswith("urn:li:dataFlow:("):
            flow_body = flow_urn[len("urn:li:dataFlow:(") : -1]
            flow_parts = flow_body.split(",")
            if len(flow_parts) >= 3:
                env = flow_parts[2]
        return job_name, env
    if datahub_urn.startswith("urn:li:dataFlow:("):
        body = datahub_urn[len("urn:li:dataFlow:(") : -1]
        parts = body.split(",")
        flow_name = parts[1] if len(parts) >= 2 else "pipeline"
        env = parts[2] if len(parts) >= 3 else "PROD"
        return flow_name, env
    return "pipeline", str(settings.datahub_env or "PROD")


def _to_aqp_urn(datahub_urn: str) -> str:
    parsed = parse_datahub_urn(datahub_urn)
    kind = str(parsed.get("kind") or "unknown")

    if kind == "dataset":
        name = str(parsed.get("name") or "")
        env = _normalise_env(str(parsed.get("env") or settings.datahub_env or "PROD"))
        entity_type = "dataset"
        if name.startswith("document/"):
            entity_type = "document"
            name = name[len("document/") :]
        return make_urn(entity_type, env, _sanitize_entity_id(name))

    if kind == "mlModel":
        name = str(parsed.get("name") or "")
        env = _normalise_env(str(parsed.get("env") or settings.datahub_env or "PROD"))
        return make_urn("mlmodel", env, _sanitize_entity_id(name))

    if kind in {"dataJob", "dataFlow"}:
        pipeline_name, env = _extract_pipeline_name(datahub_urn)
        return make_urn("pipeline", _normalise_env(env), _sanitize_entity_id(pipeline_name))

    raise ValueError(f"Unsupported DataHub URN kind for pull: {kind}")


def _load_schema_class(aspect_class_name: str) -> Any | None:
    try:
        from datahub.metadata import schema_classes
    except ImportError:
        return None
    except Exception:
        return None
    return getattr(schema_classes, aspect_class_name, None)


def _resolve_aspect_client() -> tuple[Any | None, str | None]:
    client = get_client()
    if hasattr(client, "get_aspect") or hasattr(client, "get_latest_aspects"):
        return client, None

    try:
        from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig
    except ImportError:
        return None, _SDK_UNAVAILABLE_ERROR
    except Exception:
        return None, _SDK_UNAVAILABLE_ERROR

    gms_url = str(getattr(client, "gms_url", "") or settings.datahub_gms_url or "").strip()
    if not gms_url:
        return None, _SDK_UNAVAILABLE_ERROR

    # Token resolution mirrors the DataHubClient pattern (rule 26 grandfathered
    # for the legacy aqp/data/datahub/ tree). Prefer the already-resolved client
    # token over a fresh settings read so credential rotation only happens in
    # one place inside this module.
    try:
        token = str(getattr(client, "token", "") or settings.datahub_token or "")
        config = DatahubClientConfig(
            server=gms_url,
            token=(token or None),
        )
        return DataHubGraph(config), None
    except Exception:
        return None, _SDK_UNAVAILABLE_ERROR


def _call_get_aspect(client: Any, *, datahub_urn: str, aspect_class_name: str) -> Any:
    if not hasattr(client, "get_aspect"):
        raise RuntimeError("client does not expose get_aspect")

    aspect_type = _load_schema_class(aspect_class_name) or aspect_class_name
    call_patterns = (
        lambda: client.get_aspect(entity_urn=datahub_urn, aspect_type=aspect_type),
        lambda: client.get_aspect(datahub_urn, aspect_type),
        lambda: client.get_aspect(datahub_urn, aspect_class_name),
        lambda: client.get_aspect(entity_urn=datahub_urn, aspect=aspect_class_name),
        lambda: client.get_aspect(urn=datahub_urn, aspect_name=aspect_class_name),
    )
    last_error: Exception | None = None
    for call in call_patterns:
        try:
            return call()
        except TypeError as exc:
            last_error = exc
            continue
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc
    raise RuntimeError(str(last_error or "unable to call get_aspect"))


def _call_get_latest_aspects(client: Any, *, datahub_urn: str) -> Any:
    if hasattr(client, "get_latest_aspects"):
        aspect_types: list[Any] = []
        for class_name in sorted(set(ASPECT_TO_DATAHUB_CLASS.values())):
            resolved = _load_schema_class(class_name)
            if resolved is not None:
                aspect_types.append(resolved)
        call_patterns = (
            lambda: client.get_latest_aspects(entity_urn=datahub_urn, aspect_types=aspect_types),
            lambda: client.get_latest_aspects(datahub_urn, aspect_types),
            lambda: client.get_latest_aspects(entity_urn=datahub_urn),
            lambda: client.get_latest_aspects(datahub_urn),
        )
        for call in call_patterns:
            try:
                return call()
            except TypeError:
                continue
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(str(exc)) from exc

    if hasattr(client, "get_entity"):
        return client.get_entity(datahub_urn)
    raise RuntimeError("client does not expose get_latest_aspects or get_entity")


def _to_json_friendly(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _to_json_friendly(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_friendly(v) for v in value]
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)

    for method_name in ("to_obj", "to_dict", "dict", "model_dump"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                payload = method()
                return _to_json_friendly(payload)
            except Exception:
                continue

    if hasattr(value, "__dict__"):
        return _to_json_friendly({k: v for k, v in vars(value).items() if not k.startswith("_")})
    return str(value)


def _aspect_payload_dict(raw_aspect: Any) -> dict[str, Any]:
    payload = _to_json_friendly(raw_aspect)
    if isinstance(payload, dict):
        if isinstance(payload.get("aspect"), dict):
            return dict(payload["aspect"])
        if isinstance(payload.get("value"), dict):
            return dict(payload["value"])
        return dict(payload)
    return {"value": payload}


def _aspect_name_for_class(class_name: str) -> str:
    if class_name in _DATAHUB_CLASS_TO_ASPECT_NAME:
        return _DATAHUB_CLASS_TO_ASPECT_NAME[class_name]
    for aspect_name, mapped_class in ASPECT_TO_DATAHUB_CLASS.items():
        if mapped_class == class_name:
            return aspect_name
    return "entityProperties"


def _persist_aspect(
    *,
    datahub_urn: str,
    aqp_urn: str,
    aspect_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    payload_model = _GenericAspectPayload.model_validate(payload)
    with get_session() as session:
        row = write_aspect(
            session,
            aqp_urn,
            aspect_name,
            payload_model,
            created_by="datahub_aspect_puller",
            system_metadata={
                "source": "datahub",
                "datahub_urn": datahub_urn,
                "pulled_at": datetime.utcnow().isoformat(),
            },
        )
        return {
            "pulled": True,
            "aqp_urn": aqp_urn,
            "aspect_id": str(row.id),
            "version": int(row.version),
            "aspect_name": aspect_name,
        }


def _iter_class_payload_pairs(result: Any) -> list[tuple[str, dict[str, Any]]]:
    pairs: list[tuple[str, dict[str, Any]]] = []

    if isinstance(result, dict):
        if isinstance(result.get("aspects"), dict):
            for aspect_name, raw_value in result["aspects"].items():
                class_name = ASPECT_TO_DATAHUB_CLASS.get(str(aspect_name), str(aspect_name))
                pairs.append((class_name, _aspect_payload_dict(raw_value)))
            return pairs

        for key, raw_value in result.items():
            class_name = key.__name__ if hasattr(key, "__name__") else str(key)
            if class_name in {"urn", "entityUrn", "value", "errors"}:
                continue
            if class_name in ASPECT_TO_DATAHUB_CLASS:
                class_name = ASPECT_TO_DATAHUB_CLASS[class_name]
            pairs.append((class_name, _aspect_payload_dict(raw_value)))

        if pairs:
            return pairs

        value_node = result.get("value")
        if isinstance(value_node, dict):
            return _iter_class_payload_pairs(value_node)

    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            class_name = str(
                item.get("aspect_class_name")
                or item.get("aspectName")
                or item.get("__typename")
                or "entityProperties"
            )
            if class_name in ASPECT_TO_DATAHUB_CLASS:
                class_name = ASPECT_TO_DATAHUB_CLASS[class_name]
            payload = _aspect_payload_dict(item.get("aspect") or item.get("value") or item)
            pairs.append((class_name, payload))
    return pairs


__all__ = ["pull_all_aspects", "pull_aspect"]
