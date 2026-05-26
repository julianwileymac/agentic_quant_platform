"""Higher-level Terraform spec builders.

The CP-side codegen (:mod:`aqp_cp.terraform.codegen`) renders individual
module bodies; the builders here compose them into a complete
:class:`aqp_platform_core.models.terraform.TerraformStackSpec` ready to
hand to :meth:`TerraformRuntime.execute`.

The first bundled builder is the tenant-namespace bundle — invoked
from :class:`aqp_cp.providers.aws.AwsProvider.provision_tenant_namespace`
and from the admin BFF's "promote tenant link" flow.
"""

from aqp_cp.terraform.builders.manifests import build_tenant_namespace_spec

__all__ = ["build_tenant_namespace_spec"]
