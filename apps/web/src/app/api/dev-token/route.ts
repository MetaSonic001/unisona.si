import { NextRequest, NextResponse } from "next/server";

// Hands the local dev token to the browser, only in development, only on localhost.
export async function GET(req: NextRequest) {
  const host = req.headers.get("host") || "";
  const local = host.startsWith("localhost") || host.startsWith("127.0.0.1");
  if (process.env.NODE_ENV === "production" || process.env.DEV_MODE !== "true" || !local || !process.env.DEV_TOKEN) {
    return NextResponse.json({ error: "Dev mode is disabled" }, { status: 404 });
  }
  return NextResponse.json({ token: `dev:${process.env.DEV_TOKEN}` });
}
