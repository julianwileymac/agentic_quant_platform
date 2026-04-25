import { NextResponse } from "next/server";

const COOKIE_NAME = "aqp_session";

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const sessionCookie = cookieHeader
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${COOKIE_NAME}=`));
  const sessionId = sessionCookie ? sessionCookie.split("=")[1] : null;

  return NextResponse.json({
    user: { id: "local", name: "Local User", role: "owner" },
    session_id: sessionId,
    authenticated: Boolean(sessionId) || true, // local-first: always authenticated
  });
}

export async function POST() {
  const sessionId = crypto.randomUUID();
  const response = NextResponse.json({
    user: { id: "local", name: "Local User", role: "owner" },
    session_id: sessionId,
    authenticated: true,
  });
  response.cookies.set({
    name: COOKIE_NAME,
    value: sessionId,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(COOKIE_NAME);
  return response;
}
