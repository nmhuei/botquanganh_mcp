#!/usr/bin/env bash
set -euo pipefail

echo "=================================================="
echo "      BotQuangAnh MCP & CLI Installer             "
echo "=================================================="

fail() {
    echo "[-] Error: $*" >&2
    exit 1
}

# Determine whether this is a local repository install or a piped remote install.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ] && [ -f "$SCRIPT_DIR/bin/bqa" ]; then
    ROOT_DIR="$SCRIPT_DIR"
elif [ -f "$PWD/pyproject.toml" ] && [ -f "$PWD/bin/bqa" ]; then
    # Supports: cat install.sh | bash while the shell is inside the repository.
    ROOT_DIR="$PWD"
else
    TARGET_REPO_URL="${BQA_REPO_URL:-https://github.com/nmhuei/botquanganh_mcp.git}"
    TARGET_INSTALL_DIR="${BQA_INSTALL_DIR:-$HOME/.botquanganh_mcp}"
    TARGET_BRANCH="${BQA_BRANCH:-main}"

    command -v git >/dev/null 2>&1 || fail "git is required for remote installation."
    git ls-remote --exit-code --heads "$TARGET_REPO_URL" "$TARGET_BRANCH" >/dev/null 2>&1 \
        || fail "branch '$TARGET_BRANCH' was not found in $TARGET_REPO_URL."

    if [ -e "$TARGET_INSTALL_DIR" ] && [ ! -d "$TARGET_INSTALL_DIR/.git" ]; then
        fail "$TARGET_INSTALL_DIR already exists but is not a Git repository."
    fi

    if [ -d "$TARGET_INSTALL_DIR/.git" ]; then
        echo "[*] Found existing repository at $TARGET_INSTALL_DIR. Updating safely..."
        EXISTING_ORIGIN="$(git -C "$TARGET_INSTALL_DIR" remote get-url origin 2>/dev/null || true)"
        [ -n "$EXISTING_ORIGIN" ] || fail "the existing installation has no origin remote."
        [ "$EXISTING_ORIGIN" = "$TARGET_REPO_URL" ] \
            || fail "the existing installation origin '$EXISTING_ORIGIN' does not match '$TARGET_REPO_URL'."
        if [ -n "$(git -C "$TARGET_INSTALL_DIR" status --porcelain --untracked-files=normal)" ]; then
            fail "the existing installation has uncommitted files; clean or move them before updating."
        fi
        git -C "$TARGET_INSTALL_DIR" fetch --prune origin \
            "+refs/heads/$TARGET_BRANCH:refs/remotes/origin/$TARGET_BRANCH"
        if git -C "$TARGET_INSTALL_DIR" show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
            git -C "$TARGET_INSTALL_DIR" checkout --quiet "$TARGET_BRANCH"
        else
            git -C "$TARGET_INSTALL_DIR" checkout --quiet -b "$TARGET_BRANCH" \
                --track "origin/$TARGET_BRANCH"
        fi
        git -C "$TARGET_INSTALL_DIR" merge --ff-only "origin/$TARGET_BRANCH"
    else
        echo "[*] Cloning repository from $TARGET_REPO_URL to $TARGET_INSTALL_DIR..."
        mkdir -p "$(dirname "$TARGET_INSTALL_DIR")"
        git clone --branch "$TARGET_BRANCH" --single-branch \
            "$TARGET_REPO_URL" "$TARGET_INSTALL_DIR"
    fi
    ROOT_DIR="$TARGET_INSTALL_DIR"
fi

cd "$ROOT_DIR"
[ -f pyproject.toml ] && [ -f bin/bqa ] || fail "$ROOT_DIR is not a valid BotQuangAnh MCP repository."
echo "[*] Repository location: $ROOT_DIR"

PYTHON_BIN="$(command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || fail "python3 is required but was not found in PATH."

UV_BIN="$(command -v uv || true)"
[ -n "$UV_BIN" ] || fail "uv is required but was not found in PATH. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"

if [ ! -d .venv ]; then
    echo "[*] Creating Python virtual environment in .venv..."
    "$UV_BIN" venv .venv --python "$PYTHON_BIN"
fi

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
[ -x "$VENV_PYTHON" ] \
    || fail "virtual environment Python at $VENV_PYTHON is missing or not executable."

if [ -f requirements.txt ]; then
    echo "[*] Installing runtime dependencies..."
    "$UV_BIN" pip install -r requirements.txt --python "$VENV_PYTHON" --quiet
fi

echo "[*] Installing bqa CLI package..."
"$UV_BIN" pip install -e . --no-deps --python "$VENV_PYTHON" --quiet

if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "[+] Created .env configuration from .env.example"
fi
if [ -f .env ]; then
    chmod 600 .env
fi

mkdir -p logs
chmod +x install.sh bin/bqa scripts/*.sh

TARGET_DIR="${BQA_BIN_DIR:-$HOME/.local/bin}"
TARGET_LINK="$TARGET_DIR/bqa"
SOURCE_BIN="$ROOT_DIR/bin/bqa"
[ -x "$SOURCE_BIN" ] || fail "CLI executable $SOURCE_BIN was not found."

mkdir -p "$TARGET_DIR"
ln -sfn "$SOURCE_BIN" "$TARGET_LINK"

RESOLVED_BIN="$(readlink -f "$TARGET_LINK" 2>/dev/null || true)"
[ "$RESOLVED_BIN" = "$SOURCE_BIN" ] \
    || fail "installed symlink resolves to '$RESOLVED_BIN' instead of '$SOURCE_BIN'."

echo "[*] Verifying CLI installation..."
CLI_VERSION="$("$TARGET_LINK" version)"
[ -n "$CLI_VERSION" ] || fail "verification failed when executing '$TARGET_LINK version'."
echo "[+] Verification SUCCESS: $CLI_VERSION installed at $TARGET_LINK"

echo ""
echo "=================================================="
echo "        Installation Completed Successfully!      "
echo "=================================================="
echo "CLI Executable : $TARGET_LINK"
echo "Project Path   : $ROOT_DIR"
echo ""

case ":${PATH:-}:" in
    *":$TARGET_DIR:"*) ;;
    *)
        echo "[!] NOTICE: $TARGET_DIR is not currently in your PATH."
        echo "    Add this line to ~/.bashrc or ~/.zshrc:"
        echo "    export PATH=\"$TARGET_DIR:\$PATH\""
        echo ""
        ;;
esac

echo "Quick Start Steps:"
echo "  1. Configure .env (set GATEWAY_TOKEN and HOST_WORKSPACE_DIR)"
echo "  2. Run 'bqa config validate'"
echo "  3. Run 'bqa doctor'"
echo "  4. Run 'bqa start' when you are ready to launch the service"
echo ""
