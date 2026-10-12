# Implementation Plan — Cycle 04

Record a rate-limit metric at the exact rejection point in `TokenAuthMiddleware`. Add an ASGI-level regression that verifies one increment, a 429 response, and no downstream call.
