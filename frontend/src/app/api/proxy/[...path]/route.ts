/**
 * Authenticated proxy to the FastAPI backend.
 *
 * Every browser call to the backend goes through here, which buys three things:
 *
 *  1. **Trustworthy identity.** `actor_id` / `actor_role` are stamped from the
 *     server-side session, overwriting anything the client sent. The client
 *     therefore cannot claim to be an ADMIN — role checks in the backend
 *     (playbook writes, approval gate, contract deletion) receive the real role.
 *  2. **One origin.** No CORS preflight on every request, and the backend URL
 *     never appears in the client bundle.
 *  3. **Working SSE.** Streaming responses are passed through untouched, with
 *     buffering explicitly disabled, so the Agent Theater renders live rather
 *     than arriving in one lump at the end.
 */

import { getServerSession } from "next-auth/next";
import { type NextRequest, NextResponse } from "next/server";

import { authOptions } from "@/lib/auth";

const BACKEND_URL =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

/** Never forward hop-by-hop or client-controlled identity headers. */
const STRIPPED_REQUEST_HEADERS = new Set([
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
  "keep-alive",
  "upgrade",
  "cookie",
]);

const STREAMING_CONTENT_TYPE = "text/event-stream";

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const session = await getServerSession(authOptions);

  const targetUrl = new URL(`${BACKEND_URL}/${path.join("/")}`);

  // Copy caller query params, then overwrite identity from the session so it
  // cannot be spoofed by the client.
  request.nextUrl.searchParams.forEach((value, key) => {
    if (key !== "actor_id" && key !== "actor_role") {
      targetUrl.searchParams.append(key, value);
    }
  });

  const actorId = session?.user?.email ?? "anonymous";
  const actorRole = session?.user?.role ?? "BUSINESS_USER";
  targetUrl.searchParams.set("actor_id", actorId);
  targetUrl.searchParams.set("actor_role", actorRole);

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!STRIPPED_REQUEST_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  headers.set("X-Dharma-Actor", actorId);
  headers.set("X-Dharma-Role", actorRole);

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    const contentType = request.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      // JSON bodies carry actor fields too (they map to Pydantic `ActorContext`),
      // so re-stamp them from the session for the same reason as the query params.
      const raw = await request.text();
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as Record<string, unknown>;
          init.body = JSON.stringify({
            ...parsed,
            actor_id: actorId,
            actor_role: actorRole,
          });
        } catch {
          init.body = raw;
        }
      }
    } else if (contentType.includes("multipart/form-data")) {
      // Re-read the form so the actor fields are authoritative on upload too.
      const form = await request.formData();
      form.set("actor_id", actorId);
      form.set("actor_role", actorRole);
      form.delete("content-type");
      init.body = form;
      // Let fetch regenerate the multipart boundary for the rebuilt body.
      headers.delete("content-type");
    } else {
      const buffer = await request.arrayBuffer();
      if (buffer.byteLength) init.body = buffer;
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, init);
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          "Cannot reach the Dharma AI backend. Start it with `docker compose up` " +
          `or \`uvicorn app.main:app\`. (${String(error)})`,
      },
      { status: 502 },
    );
  }

  const upstreamContentType = upstream.headers.get("content-type") ?? "";

  // Stream SSE straight through, unbuffered.
  if (upstreamContentType.includes(STREAMING_CONTENT_TYPE) && upstream.body) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": STREAMING_CONTENT_TYPE,
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  }

  const body = await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
  responseHeaders.set("cache-control", "no-store");

  return new Response(body, { status: upstream.status, headers: responseHeaders });
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;

// Streams must not be statically optimised or collected at build time.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
