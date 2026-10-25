\# M12-07 — Production API Hardening

\#\# Goal  
Make FastAPI safe, bounded, observable, and truthful for production/demo use.

Audit request IDs, structured error codes, body/compute limits, timeout behavior, CORS, storage-reference validation, model/artifact failures, prediction history behavior, logging, validation, compatibility gates, and health/version endpoints.

Adversarial tests:  
malformed JSON, NaN/Infinity, wrong types, huge metadata, oversized requests, bad storage reference, missing object, corrupt/missing model artifact, unsupported schema, incompatible machine/domain, validation-bypass attempts, and repeated resource-abuse requests.

Rules:  
\- Do not unnecessarily log secrets or raw sensor payloads.  
\- Backend failures must never become HTTP success with plausible fake predictions.  
\- Unsupported input must fail before normal inference.  
\- Missing/corrupt model must return an availability failure, not fallback prediction.  
\- Review duplicate/misleading history side effects.  
\- Health/version endpoints must describe actual loaded state.

Independent verifier must actively attempt validation and compatibility bypasses.