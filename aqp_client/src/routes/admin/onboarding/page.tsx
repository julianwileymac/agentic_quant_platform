import { useState } from "react";

import { EntraTenantLinkWizard } from "@/components/onboarding/EntraTenantLinkWizard";
import { OrgCreateWizard } from "@/components/onboarding/OrgCreateWizard";
import { UserInviteWizard } from "@/components/onboarding/UserInviteWizard";
import { PageContainer } from "@/components/shell/PageContainer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

/**
 * /admin/onboarding — single page hosting the three onboarding wizards.
 *
 * Multi-tenant Entra ID enrolment + organization create + user invite
 * all live behind ``tenancy:admin`` / ``tenancy:invite`` scopes.
 */
export function OnboardingRoute() {
  const [tab, setTab] = useState<"org" | "tenant" | "invite">("org");

  return (
    <PageContainer
      title="Onboarding"
      subtitle="Org + tenant + user onboarding wizards. See configs/tenants/*.yaml for defaults."
    >
      <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)}>
        <TabsList>
          <TabsTrigger value="org">Create organization</TabsTrigger>
          <TabsTrigger value="tenant">Link Entra tenant</TabsTrigger>
          <TabsTrigger value="invite">Invite user</TabsTrigger>
        </TabsList>
        <TabsContent value="org">
          <Card>
            <CardHeader>
              <CardTitle>Create a new AQP organization</CardTitle>
            </CardHeader>
            <CardContent>
              <OrgCreateWizard />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="tenant">
          <Card>
            <CardHeader>
              <CardTitle>Link an Entra ID tenant to an org</CardTitle>
            </CardHeader>
            <CardContent>
              <EntraTenantLinkWizard />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="invite">
          <Card>
            <CardHeader>
              <CardTitle>Invite a user</CardTitle>
            </CardHeader>
            <CardContent>
              <UserInviteWizard />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
