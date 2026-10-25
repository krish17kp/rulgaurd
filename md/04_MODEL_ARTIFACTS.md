\# M12-04 — Production Model Artifact Packaging and Loader

\#\# Goal  
Make validated ML/preprocessing artifacts reproducibly loadable in production without casually committing large ignored binaries.

Artifact manifest must record model name/version, feature schema version, preprocessing version, expected artifact filename/object key, checksum, supported adapter/domain, and runtime/library compatibility where relevant.

Create clean resolver/loader interfaces for local/development and deployment/remote artifacts. Avoid user-specific absolute paths.

Fail explicitly on missing/corrupt artifacts, checksum mismatch, feature schema mismatch, preprocessing mismatch, wrong model/domain, or incompatible runtime version.

Packaging/serialization optimization must not change model behavior.

Fresh-process acceptance:  
1\. read manifest  
2\. resolve artifacts  
3\. validate checksum/version  
4\. load preprocessing  
5\. load model  
6\. run known fixture  
7\. compare with frozen reference

Remote provisioning may remain credential-blocked, but local architecture/tests must still complete.

Use an isolated worktree and independent verifier.