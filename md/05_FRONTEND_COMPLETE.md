\# M12-05 — Complete the Next.js Predictive-Maintenance Product

\#\# Goal  
Turn the existing Next.js scaffold into the real capstone product interface and make Streamlit non-essential to the production path.

Required user flow:  
1\. upload/select dataset  
2\. dataset inspection  
3\. compatibility state  
4\. provide missing metadata where allowed  
5\. start analysis  
6\. stage progress  
7\. validation/unsupported failures  
8\. RUL  
9\. Health Indicator/degradation  
10\. FFT/signal diagnostics where available  
11\. extracted/important features  
12\. model/version  
13\. reliability/warnings where supported  
14\. history where supported

Required UI states:  
idle, uploading, uploaded, inspecting, validating, processing, success, unsupported, adapter\_required, retrain\_required, timeout, server\_error, retrying.

Design must be polished, responsive, accessible, and driven by real API data only.

Never display fake RUL, placeholder production predictions, fabricated confidence, or unsupported certainty.

Audit Streamlit and preserve scientifically meaningful capabilities until parity is demonstrated.

Prefer changes inside frontend/. Avoid scientific backend changes unless coordinated.

Use a fresh independent verifier.