#!/usr/bin/env bash
# Copy the project's Markdown documents into chat-service before building its image, so the intro-page
# guide chat (chat_service.guide, its own pod) can answer from them. The image build context is
# services/, which does not include the repository docs. Run from the repository root:
#   bash deploy/copy-guide-docs.sh
# The copy (services/chat-service/guide_docs/) is git-ignored. Sensitive values are masked at load time.
set -euo pipefail
cd "$(dirname "$0")/.."
dest=services/chat-service/guide_docs
rm -rf "$dest"
mkdir -p "$dest/docs" "$dest/deploy"
cp README.md AGENTS.md "$dest/"
cp docs/*.md "$dest/docs/"
cp deploy/README.md "$dest/deploy/"
echo "guide docs: $(find "$dest" -name '*.md' | wc -l) files → $dest"
