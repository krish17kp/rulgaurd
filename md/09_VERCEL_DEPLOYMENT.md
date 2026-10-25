\# M12-09 — Vercel-Only Production Readiness and Deployment

\#\# Goal  
Prepare and, when credentials permit, verify the complete integrated product on the selected Vercel-only architecture.

Verify:  
\- clean Next.js production build  
\- Python/FastAPI Vercel entry  
\- environment variables  
\- no hard-coded localhost production URLs  
\- API routing/prefix behavior  
\- CORS  
\- artifact resolver  
\- storage resolver  
\- large-file/direct-storage architecture  
\- temporary filesystem assumptions  
\- cleanup  
\- serverless statelessness assumptions  
\- truthful history behavior  
\- timeout/error behavior  
\- request logging/health

Do not claim in-memory state is durable across independent serverless instances.

Smoke test:  
frontend → upload/reference → backend → raw processing → model → result.

If authenticated Vercel access exists and deployment is permitted:  
\- deploy  
\- run supported-dataset smoke prediction  
\- run unsupported-dataset rejection  
\- verify logs/health  
\- record evidence

If authentication is unavailable:  
REMOTE\_DEPLOYMENT \= BLOCKED\_AUTH

Continue all other readiness work.

Create VERCEL\_READINESS.md with LOCAL\_VERIFIED, DEPLOYMENT\_EQUIVALENT\_VERIFIED, REQUIRES\_AUTH, BLOCKED, and exact remaining action.

Never claim DEPLOYED without actual deployment evidence.