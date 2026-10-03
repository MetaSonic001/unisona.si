import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const devModeAllowed = process.env.NODE_ENV !== "production" && process.env.DEV_MODE === "true";

export default clerkMiddleware(async (auth, req) => {
  if (!req.nextUrl.pathname.startsWith("/app")) return NextResponse.next();
  // Local dev mode (cookie set from the sign-in page) skips Clerk; the API still checks the dev token + loopback.
  if (devModeAllowed && req.cookies.get("unisona_dev")?.value === "1") return NextResponse.next();
  await auth.protect();
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|mp3|wav)).*)",
    "/__clerk/:path*",
    "/(api|trpc)(.*)",
  ],
};
