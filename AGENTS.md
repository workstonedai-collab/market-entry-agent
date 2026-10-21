# Contributor guidance

Keep the runtime standard-library only and independently runnable. Publish only PUBLIC_FILES.json entries. Keep operator-owned instructions, private knowledge, customer documents, credentials, runtime state and archives outside the repository. New examples must use synthetic or attributed public data. Run the public-release checker before packaging. Common files must match the peer manifest. Test actual recovery, scope and saved/exported results. Do not enable external sending or background jobs by default. Use GitHub noreply commit identities.
