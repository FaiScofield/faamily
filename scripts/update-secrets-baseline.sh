#!/usr/bin/env bash
# Rebuild .secrets.baseline safely.
#
# Why this script exists:
#   `detect-secrets scan --all-files` walks the whole working tree, including
#   .venv/ and cache dirs. That pulls thousands of false positives out of
#   third-party libraries into the baseline — and because the baseline stores
#   40-char hex fingerprints, those hashes then get flagged as fresh secrets
#   on the next run. The result is an ever-growing false-positive loop that
#   blocks every commit.
#
#   The safe recipe: scan ONLY files tracked by git, and never the baseline
#   file itself.
#
# Usage:  ./scripts/update-secrets-baseline.sh
#         (Windows Git Bash: bash scripts/update-secrets-baseline.sh)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASELINE=".secrets.baseline"

# Locate detect-secrets
if [ -x ".venv/Scripts/detect-secrets.exe" ]; then
  DS=".venv/Scripts/detect-secrets.exe"
elif [ -x ".venv/bin/detect-secrets" ]; then
  DS=".venv/bin/detect-secrets"
elif command -v detect-secrets >/dev/null 2>&1; then
  DS="detect-secrets"
else
  echo "❌ 未找到 detect-secrets，请先执行: pip install -r requirements-dev.txt" >&2
  exit 1
fi

# Only tracked files, excluding the baseline itself
FILES=$(git ls-files | grep -v '^\.secrets\.baseline$' || true)

if [ -z "$FILES" ]; then
  echo "❌ 没有可扫描的受版本控制文件" >&2
  exit 1
fi

echo "▶ 扫描 $(echo "$FILES" | wc -l | tr -d ' ') 个受版本控制的文件..."

# shellcheck disable=SC2086
"$DS" scan $FILES > "$BASELINE.tmp"

# Sanity check: the baseline must not reference .venv or cache dirs
if grep -qE '\.venv|pytest_cache|ruff_cache|site-packages' "$BASELINE.tmp"; then
  echo "❌ 生成的基线包含 .venv/缓存目录的条目，已中止" >&2
  rm -f "$BASELINE.tmp"
  exit 1
fi

mv "$BASELINE.tmp" "$BASELINE"

COUNT=$(grep -c '"type"' "$BASELINE" || true)
echo "✅ 基线已更新：$COUNT 条已审查条目"
echo ""
echo "请人工复核新增条目："
echo "  .venv/Scripts/detect-secrets.exe audit $BASELINE"
