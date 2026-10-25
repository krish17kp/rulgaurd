\# M12-06 — Frontend Automated Testing

\#\# Goal  
Add a real automated testing layer for the Next.js product.

Cover upload UI, inspection display, compatibility states, validation errors, unsupported dataset, adapter-required, retrain-required, loading/progress, API failure, timeout/retry, RUL rendering, HI/degradation rendering, navigation, empty states, and no fake fallback values.

Add browser/E2E testing where practical. Include at least one path against the real local backend if practical.

Component mocks must accurately reflect the real API schema. The UI must never invent RUL or success when backend returns failure/incomplete data.

Run frontend tests, lint, and production build.

Before acceptance:  
1\. intentionally perturb one important behavior  
2\. prove a relevant test fails  
3\. restore implementation  
4\. rerun green

Implementation agent cannot self-approve. Use an independent verifier.