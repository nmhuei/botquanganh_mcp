#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

RESULT_FILE="$ROOT_DIR/logs/installer_manual_test_results.txt"
mkdir -p logs
: > "$RESULT_FILE"

TMP_DIR="$(mktemp -d -t bqa-installer-test-XXXXXX)"
PASS_COUNT=0
CURRENT_TEST="initialization"

log() {
    printf '%s\n' "$*" | tee -a "$RESULT_FILE"
}

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    log "PASS: $1"
}

fail() {
    local line="${1:-unknown}" command="${2:-unknown}"
    log "FAIL: $CURRENT_TEST"
    log "FAIL_LINE=$line"
    log "FAIL_COMMAND=$command"
    exit 1
}

trap 'fail "$LINENO" "$BASH_COMMAND"' ERR
trap 'rm -rf "$TMP_DIR"' EXIT

snapshot_repo() {
    local destination="$1"
    mkdir -p "$destination"
    tar \
        --exclude='./.git' \
        --exclude='./.venv' \
        --exclude='./.env' \
        --exclude='./logs' \
        --exclude='./artifacts' \
        --exclude='./manual_test_workspace_*' \
        --exclude='./.cli_manual_test_*' \
        --exclude='*/__pycache__' \
        --exclude='*.pyc' \
        -C "$ROOT_DIR" -cf - . | tar -C "$destination" -xf -
}

install_env() {
    local home_dir="$1" bin_dir="$2"
    shift 2
    env \
        HOME="$home_dir" \
        BQA_BIN_DIR="$bin_dir" \
        BQA_SKIP_PIP_UPGRADE=true \
        PIP_DISABLE_PIP_VERSION_CHECK=1 \
        "$@"
}

verify_install() {
    local repo="$1" bin_dir="$2"
    [ -x "$repo/.venv/bin/python" ]
    [ -f "$repo/.env" ]
    [ "$(stat -c '%a' "$repo/.env")" = "600" ]
    [ -L "$bin_dir/bqa" ]
    [ "$(readlink -f "$bin_dir/bqa")" = "$repo/bin/bqa" ]
    [ "$("$bin_dir/bqa" version)" = "bqa 1.0.0" ]
    "$repo/.venv/bin/python" -m pip check >/dev/null
}

CURRENT_TEST="local install"
LOCAL_REPO="$TMP_DIR/local-repo"
LOCAL_HOME="$TMP_DIR/local-home"
LOCAL_BIN="$LOCAL_HOME/.local/bin"
snapshot_repo "$LOCAL_REPO"
install_env "$LOCAL_HOME" "$LOCAL_BIN" "$LOCAL_REPO/install.sh" \
    > "$TMP_DIR/local-install.log"
verify_install "$LOCAL_REPO" "$LOCAL_BIN"
printf '\nINSTALLER_SENTINEL=preserved\n' >> "$LOCAL_REPO/.env"
install_env "$LOCAL_HOME" "$LOCAL_BIN" "$LOCAL_REPO/scripts/install_basic.sh" \
    > "$TMP_DIR/local-delegate.log"
grep -q '^INSTALLER_SENTINEL=preserved$' "$LOCAL_REPO/.env"
verify_install "$LOCAL_REPO" "$LOCAL_BIN"
pass "local install, legacy delegate, env preservation, permissions, symlink, CLI"

CURRENT_TEST="piped install inside repository"
PIPE_REPO="$TMP_DIR/pipe-repo"
PIPE_HOME="$TMP_DIR/pipe-home"
PIPE_BIN="$PIPE_HOME/.local/bin"
snapshot_repo "$PIPE_REPO"
(
    cd "$PIPE_REPO"
    cat install.sh | install_env "$PIPE_HOME" "$PIPE_BIN" bash
) > "$TMP_DIR/pipe-install.log"
verify_install "$PIPE_REPO" "$PIPE_BIN"
pass "cat install.sh pipe mode inside repository"

CURRENT_TEST="remote clone install"
SOURCE_REPO="$TMP_DIR/source-repo"
BARE_REPO="$TMP_DIR/source.git"
REMOTE_HOME="$TMP_DIR/remote-home"
REMOTE_BIN="$REMOTE_HOME/.local/bin"
REMOTE_TARGET="$REMOTE_HOME/.botquanganh_mcp"
OUTSIDE_DIR="$TMP_DIR/outside"
snapshot_repo "$SOURCE_REPO"
git init --quiet --initial-branch=main "$SOURCE_REPO"
git -C "$SOURCE_REPO" config user.name "Installer Test"
git -C "$SOURCE_REPO" config user.email "installer-test@example.invalid"
git -C "$SOURCE_REPO" add .
git -C "$SOURCE_REPO" commit --quiet -m "installer fixture"
git init --quiet --bare "$BARE_REPO"
git -C "$SOURCE_REPO" remote add origin "$BARE_REPO"
git -C "$SOURCE_REPO" push --quiet -u origin main
mkdir -p "$OUTSIDE_DIR"
(
    cd "$OUTSIDE_DIR"
    cat "$SOURCE_REPO/install.sh" | env \
        HOME="$REMOTE_HOME" \
        BQA_BIN_DIR="$REMOTE_BIN" \
        BQA_INSTALL_DIR="$REMOTE_TARGET" \
        BQA_REPO_URL="$BARE_REPO" \
        BQA_BRANCH=main \
        BQA_SKIP_PIP_UPGRADE=true \
        PIP_DISABLE_PIP_VERSION_CHECK=1 \
        bash
) > "$TMP_DIR/remote-install.log"
verify_install "$REMOTE_TARGET" "$REMOTE_BIN"
[ "$(git -C "$REMOTE_TARGET" branch --show-current)" = "main" ]
pass "remote pipe clone and CLI verification"

CURRENT_TEST="safe remote update"
printf 'installer-update-ok\n' > "$SOURCE_REPO/installer-update-marker.txt"
git -C "$SOURCE_REPO" add installer-update-marker.txt
git -C "$SOURCE_REPO" commit --quiet -m "installer update fixture"
git -C "$SOURCE_REPO" push --quiet origin main
(
    cd "$OUTSIDE_DIR"
    cat "$SOURCE_REPO/install.sh" | env \
        HOME="$REMOTE_HOME" \
        BQA_BIN_DIR="$REMOTE_BIN" \
        BQA_INSTALL_DIR="$REMOTE_TARGET" \
        BQA_REPO_URL="$BARE_REPO" \
        BQA_BRANCH=main \
        BQA_SKIP_PIP_UPGRADE=true \
        PIP_DISABLE_PIP_VERSION_CHECK=1 \
        bash
) > "$TMP_DIR/remote-update.log"
grep -q '^installer-update-ok$' "$REMOTE_TARGET/installer-update-marker.txt"
verify_install "$REMOTE_TARGET" "$REMOTE_BIN"
pass "existing installation fast-forward update"

CURRENT_TEST="dirty installation protection"
printf 'customer data\n' > "$REMOTE_TARGET/customer-untracked.txt"
if (
    cd "$OUTSIDE_DIR"
    cat "$SOURCE_REPO/install.sh" | env \
        HOME="$REMOTE_HOME" \
        BQA_BIN_DIR="$REMOTE_BIN" \
        BQA_INSTALL_DIR="$REMOTE_TARGET" \
        BQA_REPO_URL="$BARE_REPO" \
        BQA_BRANCH=main \
        BQA_SKIP_PIP_UPGRADE=true \
        bash
) > "$TMP_DIR/dirty.out" 2> "$TMP_DIR/dirty.err"; then
    DIRTY_EXIT=0
else
    DIRTY_EXIT=$?
fi
[ "$DIRTY_EXIT" -ne 0 ]
grep -q 'uncommitted files' "$TMP_DIR/dirty.err"
grep -q '^customer data$' "$REMOTE_TARGET/customer-untracked.txt"
pass "dirty existing installation is preserved and rejected"

CURRENT_TEST="origin mismatch protection"
rm -f "$REMOTE_TARGET/customer-untracked.txt"
OTHER_BARE_REPO="$TMP_DIR/other-source.git"
git init --quiet --bare "$OTHER_BARE_REPO"
git -C "$REMOTE_TARGET" remote set-url origin "$OTHER_BARE_REPO"
if (
    cd "$OUTSIDE_DIR"
    cat "$SOURCE_REPO/install.sh" | env \
        HOME="$REMOTE_HOME" \
        BQA_BIN_DIR="$REMOTE_BIN" \
        BQA_INSTALL_DIR="$REMOTE_TARGET" \
        BQA_REPO_URL="$BARE_REPO" \
        BQA_BRANCH=main \
        BQA_SKIP_PIP_UPGRADE=true \
        bash
) > "$TMP_DIR/origin.out" 2> "$TMP_DIR/origin.err"; then
    ORIGIN_EXIT=0
else
    ORIGIN_EXIT=$?
fi
[ "$ORIGIN_EXIT" -ne 0 ]
grep -q "does not match" "$TMP_DIR/origin.err"
git -C "$REMOTE_TARGET" remote set-url origin "$BARE_REPO"
pass "existing installation origin mismatch is rejected"

CURRENT_TEST="invalid remote inputs"
if (
    cd "$OUTSIDE_DIR"
    cat "$SOURCE_REPO/install.sh" | env \
        HOME="$TMP_DIR/invalid-home" \
        BQA_BIN_DIR="$TMP_DIR/invalid-bin" \
        BQA_INSTALL_DIR="$TMP_DIR/invalid-target" \
        BQA_REPO_URL="$BARE_REPO" \
        BQA_BRANCH=missing-branch \
        BQA_SKIP_PIP_UPGRADE=true \
        bash
) > "$TMP_DIR/missing.out" 2> "$TMP_DIR/missing.err"; then
    MISSING_EXIT=0
else
    MISSING_EXIT=$?
fi
[ "$MISSING_EXIT" -ne 0 ]
grep -q "branch 'missing-branch' was not found" "$TMP_DIR/missing.err"
pass "missing remote branch fails clearly"

log "TOTAL_PASS=$PASS_COUNT"
log "ALL_INSTALLER_MANUAL_TESTS=PASS"
