import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  meKeys,
  type MeProfile,
  type UpdateMePayload,
  useMeProfileQuery,
  useUpdateMeProfileMutation,
} from "@/lib/api/me";
import { toast } from "@/components/ui/toast";

export function ProfileTab() {
  const queryClient = useQueryClient();
  const profileQuery = useMeProfileQuery();
  const updateProfile = useUpdateMeProfileMutation();

  const [displayName, setDisplayName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");

  useEffect(() => {
    if (!profileQuery.data) return;
    setDisplayName(profileQuery.data.display_name ?? "");
    setAvatarUrl(profileQuery.data.avatar_url ?? "");
  }, [profileQuery.data]);

  const handleSave = async () => {
    const payload: UpdateMePayload = { display_name: displayName.trim() };
    const normalizedAvatar = avatarUrl.trim();
    if (normalizedAvatar) {
      payload.avatar_url = normalizedAvatar;
      payload.picture = normalizedAvatar;
    }
    const previous = queryClient.getQueryData<MeProfile>(meKeys.profile);
    if (previous) {
      queryClient.setQueryData<MeProfile>(meKeys.profile, {
        ...previous,
        display_name: payload.display_name ?? previous.display_name,
        avatar_url: payload.avatar_url ?? null,
        picture: payload.picture ?? null,
      });
    }
    try {
      const saved = await updateProfile.mutateAsync(payload);
      queryClient.setQueryData(meKeys.profile, saved);
      toast.success("Profile updated.");
    } catch (error) {
      if (previous) queryClient.setQueryData(meKeys.profile, previous);
      toast.error(error instanceof Error ? error.message : "Profile update failed.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <Label>Email</Label>
          <Input value={profileQuery.data?.email ?? ""} readOnly />
        </div>

        <div className="space-y-1">
          <Label>Display name</Label>
          <Input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="Your display name"
          />
        </div>

        <div className="space-y-1">
          <Label>Avatar URL</Label>
          <Input
            value={avatarUrl}
            onChange={(event) => setAvatarUrl(event.target.value)}
            placeholder="https://..."
          />
        </div>

        <div className="flex items-center gap-2">
          <Label>Provider</Label>
          <Badge variant="outline">{profileQuery.data?.auth_provider ?? "auth0"}</Badge>
        </div>

        <div className="pt-2">
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={updateProfile.isPending || profileQuery.isPending}
          >
            {updateProfile.isPending ? "Saving..." : "Save profile"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
