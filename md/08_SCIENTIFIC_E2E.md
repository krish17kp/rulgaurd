\# M12-08 — Scientific Parity and True End-to-End Verification

\#\# Goal  
Prove the production-oriented path remains scientifically equivalent to the trusted offline/reference pipeline.

For frozen supported fixtures compare preprocessing outputs, segment/window boundaries, time-domain/statistical features, RMS, kurtosis, FFT/frequency features, feature ordering/schema, Health Indicator, degradation stage, routed model/version, and final RUL.

Compare full/reference processing against chunked production-oriented processing.

Leakage audit:  
\- scaler/PCA not fitted on uploaded prediction data when training state should be reused  
\- no improper future lifecycle information  
\- no tuning on final test data  
\- no future-derived labels  
\- no incorrect temporal reordering

Compatibility matrix must include FULLY\_SUPPORTED, ADAPTER\_REQUIRED, RETRAIN\_REQUIRED, UNSUPPORTED, INVALID\_INPUT. Only FULLY\_SUPPORTED may reach normal production RUL inference.

Create SCIENTIFIC\_PARITY\_REPORT.md with fixture, reference value, production value, difference, tolerance, PASS/FAIL, and explanations for intentional differences.

Any unexplained scientific mismatch blocks release.