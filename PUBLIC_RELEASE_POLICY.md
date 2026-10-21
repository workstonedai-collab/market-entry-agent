# Public release policy

Publish only the files explicitly listed in `PUBLIC_FILES.json`. Keep runtime workspaces, credentials, operator-owned instructions, customer documents, private knowledge, internal planning and local archives outside the repository. Public examples must be synthetic or based only on attributed redistributable public sources.

Run `scripts/check_public_release.py` before packaging and pushing. The checker validates the file list, public-data schema and prohibited credential/path patterns. CI runs it as well as runtime tests. Check source archives, wheels, release notes and images before publishing. Use the account's GitHub noreply identity for commits; never embed a personal contact email in commit metadata.

The project includes generic role and output instructions only. Some specialized research methods, prompts and knowledge resources are not open source. Contact the author through the linked GitHub profile or a non-sensitive issue for further discussion. Do not post private material in public issues.
