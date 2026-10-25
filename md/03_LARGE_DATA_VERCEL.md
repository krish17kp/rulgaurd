\# M12-03 — Large Dataset Upload, Chunking, Storage, and Cleanup

\#\# Goal  
Make large sensor datasets practical for the Vercel-only architecture without compromising scientific coverage.

\#\# Target architecture  
Browser → direct-to-storage upload → validated storage reference → analysis request → bounded-memory incremental processing → prediction → cleanup

\#\# Requirements  
\- Do not proxy large raw files through an unsuitable small serverless request body.  
\- Validate file type and size limits.  
\- Use safe storage/object identifiers.  
\- Do not allow arbitrary client-controlled object access.  
\- Provide upload/progress/error states where practical.  
\- Read large tabular/time-series data incrementally.  
\- Preserve temporal order and complete scientific windows.  
\- Never randomly drop rows merely to fit RAM.  
\- Clean temporary uploads after success and terminal failure where safe.  
\- Define bounded cleanup for abandoned uploads.  
\- One job must never read or delete another job's upload.

Run the same representative dataset with multiple chunk sizes and compare feature vectors, HI, and RUL with the trusted full/reference pipeline. Any unexplained divergence is a defect.

Measure peak memory. Add compute-size bounds where needed.

If Vercel/storage credentials are unavailable, implement the abstraction, local/test provider, production-compatible interfaces, lifecycle/security tests, and mark only remote provisioning as BLOCKED\_AUTH.

Do not stop the wider M12 queue.