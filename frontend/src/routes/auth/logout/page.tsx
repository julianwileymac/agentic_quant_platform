import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LogoutRoute() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--bg-app)] p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>You've been signed out</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button asChild className="w-full">
            <Link to="/auth/login">Sign back in</Link>
          </Button>
          <Button asChild variant="outline" className="w-full">
            <Link to="/">Go to homepage</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
