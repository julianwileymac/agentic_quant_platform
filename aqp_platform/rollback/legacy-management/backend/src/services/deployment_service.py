"""
Deployment management service.

Provides operations for creating, scaling, and managing deployments.
"""

import logging
from datetime import datetime
from typing import Optional

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from ..config import Settings
from ..models.deployments import (
    DeploymentConfig,
    DeploymentInfo,
    DeploymentStatus,
)
from .kubernetes_service import KubernetesService

logger = logging.getLogger(__name__)


class DeploymentService:
    """Service for deployment operations."""

    def __init__(self, settings: Settings, k8s_service: KubernetesService):
        """Initialize the deployment service."""
        self.settings = settings
        self.k8s = k8s_service

    async def list_deployments(
        self,
        namespace: Optional[str] = None,
    ) -> list[DeploymentInfo]:
        """List all deployments."""
        if namespace:
            deployments = self.k8s.apps_api.list_namespaced_deployment(namespace)
        else:
            deployments = self.k8s.apps_api.list_deployment_for_all_namespaces()

        result = []
        for deploy in deployments.items:
            # Determine status
            status = DeploymentStatus.PENDING
            ready = deploy.status.ready_replicas or 0
            desired = deploy.spec.replicas or 0

            if ready == desired and ready > 0:
                status = DeploymentStatus.RUNNING
            elif ready < desired and ready > 0:
                status = DeploymentStatus.SCALING
            elif deploy.status.conditions:
                for condition in deploy.status.conditions:
                    if condition.type == "Progressing" and condition.status == "True":
                        status = DeploymentStatus.UPDATING
                    elif condition.type == "Available" and condition.status == "False":
                        status = DeploymentStatus.FAILED

            # Get image from first container
            image = ""
            if deploy.spec.template.spec.containers:
                image = deploy.spec.template.spec.containers[0].image

            # Parse conditions
            conditions = []
            for cond in deploy.status.conditions or []:
                conditions.append({
                    "type": cond.type,
                    "status": cond.status,
                    "reason": cond.reason,
                    "message": cond.message,
                    "last_update": cond.last_update_time.isoformat() if cond.last_update_time else None,
                })

            info = DeploymentInfo(
                name=deploy.metadata.name,
                namespace=deploy.metadata.namespace,
                status=status,
                replicas=desired,
                ready_replicas=ready,
                available_replicas=deploy.status.available_replicas or 0,
                image=image,
                created_at=deploy.metadata.creation_timestamp,
                labels=deploy.metadata.labels or {},
                conditions=conditions,
            )
            result.append(info)

        return result

    async def get_deployment(
        self,
        name: str,
        namespace: str,
    ) -> Optional[DeploymentInfo]:
        """Get a specific deployment."""
        try:
            deployments = await self.list_deployments(namespace=namespace)
            for deploy in deployments:
                if deploy.name == name:
                    return deploy
            return None
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    async def create_deployment(self, config: DeploymentConfig) -> DeploymentInfo:
        """Create a new deployment."""
        # Build container spec
        container = client.V1Container(
            name=config.name,
            image=config.image,
            ports=[client.V1ContainerPort(container_port=config.port)]
            if config.port
            else None,
            env=[
                client.V1EnvVar(name=k, value=v)
                for k, v in config.env.items()
            ],
        )

        # Add resource limits if specified
        if config.resources:
            container.resources = client.V1ResourceRequirements(
                requests=config.resources.get("requests"),
                limits=config.resources.get("limits"),
            )

        # Build pod template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": config.name, **config.labels}),
            spec=client.V1PodSpec(
                containers=[container],
                node_selector=config.node_selector,
            ),
        )

        # Build deployment spec
        spec = client.V1DeploymentSpec(
            replicas=config.replicas,
            selector=client.V1LabelSelector(
                match_labels={"app": config.name},
            ),
            template=template,
        )

        # Build deployment
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=config.name,
                namespace=config.namespace,
                labels={"app": config.name, **config.labels},
            ),
            spec=spec,
        )

        # Create deployment
        try:
            self.k8s.apps_api.create_namespaced_deployment(
                namespace=config.namespace,
                body=deployment,
            )
            logger.info(f"Created deployment {config.name} in {config.namespace}")
        except ApiException as e:
            logger.error(f"Failed to create deployment: {e}")
            raise

        # Create service if requested
        if config.create_service and config.port:
            await self._create_service(config)

        # Return deployment info
        return await self.get_deployment(config.name, config.namespace)

    async def _create_service(self, config: DeploymentConfig) -> None:
        """Create a service for a deployment."""
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=config.name,
                namespace=config.namespace,
            ),
            spec=client.V1ServiceSpec(
                type=config.service_type,
                selector={"app": config.name},
                ports=[
                    client.V1ServicePort(
                        port=config.port,
                        target_port=config.port,
                    )
                ],
            ),
        )

        try:
            self.k8s.core_api.create_namespaced_service(
                namespace=config.namespace,
                body=service,
            )
            logger.info(f"Created service {config.name} in {config.namespace}")
        except ApiException as e:
            logger.error(f"Failed to create service: {e}")
            raise

    async def scale_deployment(
        self,
        name: str,
        namespace: str,
        replicas: int,
    ) -> DeploymentInfo:
        """Scale a deployment to the specified number of replicas."""
        try:
            # Patch the deployment
            body = {"spec": {"replicas": replicas}}
            self.k8s.apps_api.patch_namespaced_deployment_scale(
                name=name,
                namespace=namespace,
                body=body,
            )
            logger.info(f"Scaled deployment {name} to {replicas} replicas")

            # Return updated info
            return await self.get_deployment(name, namespace)

        except ApiException as e:
            logger.error(f"Failed to scale deployment: {e}")
            raise

    async def delete_deployment(
        self,
        name: str,
        namespace: str,
        delete_service: bool = True,
    ) -> bool:
        """Delete a deployment and optionally its service."""
        try:
            self.k8s.apps_api.delete_namespaced_deployment(
                name=name,
                namespace=namespace,
            )
            logger.info(f"Deleted deployment {name}")

            if delete_service:
                try:
                    self.k8s.core_api.delete_namespaced_service(
                        name=name,
                        namespace=namespace,
                    )
                    logger.info(f"Deleted service {name}")
                except ApiException as e:
                    if e.status != 404:
                        logger.warning(f"Failed to delete service: {e}")

            return True

        except ApiException as e:
            if e.status == 404:
                return False
            logger.error(f"Failed to delete deployment: {e}")
            raise

    async def restart_deployment(
        self,
        name: str,
        namespace: str,
    ) -> DeploymentInfo:
        """Restart a deployment by triggering a rolling restart."""
        try:
            # Patch with a restart annotation
            now = datetime.utcnow().isoformat()
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": now,
                            }
                        }
                    }
                }
            }
            self.k8s.apps_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            logger.info(f"Restarted deployment {name}")

            return await self.get_deployment(name, namespace)

        except ApiException as e:
            logger.error(f"Failed to restart deployment: {e}")
            raise

    async def rollback_deployment(
        self,
        name: str,
        namespace: str,
        revision: Optional[int] = None,
    ) -> DeploymentInfo:
        """Rollback a deployment to a previous revision."""
        try:
            # Get the deployment
            deploy = self.k8s.apps_api.read_namespaced_deployment(name, namespace)

            # For now, we'll use kubectl-style rollback by patching
            # In production, you'd want to manage ReplicaSets properly
            body = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/rollback": "true",
                            }
                        }
                    }
                }
            }

            self.k8s.apps_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=body,
            )
            logger.info(f"Rolled back deployment {name}")

            return await self.get_deployment(name, namespace)

        except ApiException as e:
            logger.error(f"Failed to rollback deployment: {e}")
            raise
