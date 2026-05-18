import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type { TerraformStackSummary } from "@/lib/api/terraform";

/**
 * Stack spec catalog — list every Terraform stack registered in the
 * `terraform_stack_specs` table. Click a row to see version history.
 */
export function TerraformStacksRoute() {
  const stacks = useApiQuery<{ items: TerraformStackSummary[]; total: number }>({
    queryKey: ["terraform", "stacks"],
    path: "/terraform/stacks",
    refetchInterval: 60_000,
    select: (raw) => raw as { items: TerraformStackSummary[]; total: number },
  });

  const items = stacks.data?.items ?? [];

  return (
    <PageContainer
      title="Terraform stacks"
      subtitle="Hash-locked TerraformStackSpec catalog. New versions are written on every spec change."
      data-mode="infra"
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {items.length === 0 ? (
          <Card className="col-span-full">
            <CardContent className="py-12 text-center text-sm text-[var(--text-secondary)]">
              No stack specs yet. Register one via <code>POST /terraform/stacks</code>.
            </CardContent>
          </Card>
        ) : (
          items.map((stack) => (
            <Card key={stack.id}>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="font-mono">{stack.slug}</span>
                  <Badge variant="outline">v{stack.current_version}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-[var(--text-secondary)]">module_kind</span>
                  <Badge variant="outline">{stack.module_kind}</Badge>
                </div>
                {stack.description ? (
                  <p className="text-[var(--text-secondary)]">{stack.description}</p>
                ) : null}
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </PageContainer>
  );
}
