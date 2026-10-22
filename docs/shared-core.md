# Shared runtime

Both packages independently ship the files listed in `shared-core.json`. Keep common files byte-identical and update their hashes when editing. The manifest includes public country data and the UI; product names/default generic roles remain separate in `product.py`. Public evidence can be exchanged explicitly; private tasks and instructions must stay in isolated workspaces.

Project memory, bounded context, document skills, run controls and usage receipts: [shared kernel guide](kernel.md).
