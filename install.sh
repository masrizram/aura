#!/usr/bin/env bash
# =============================================================================
# AURA Audit Engine — Universal Installer
# =============================================================================
# Installs or bootstraps the AURA audit engine into a target project.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/aura/aura-audit/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/aura/aura-audit/main/install.sh | bash -s -- --target /path/to/project
# =============================================================================
set -euo pipefail

# ── Colour helpers ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { printf "${GREEN}[AURA]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[AURA WARN]${NC} %s\n" "$*"; }
err()   { printf "${RED}[AURA ERROR]${NC} %s\n" "$*" >&2; }

# ── Defaults ─────────────────────────────────────────────────────────────────
AURA_VERSION="2.1.2"
TARGET_DIR=""
AURA_REPO="https://github.com/aura/aura-audit.git"
AURA_TARBALL="https://github.com/aura/aura-audit/archive/refs/tags/v${AURA_VERSION}.tar.gz"
INSTALL_SYMLINKS=true
QUIET=false

# ── Detect OS ────────────────────────────────────────────────────────────────
detect_os() {
    local os=""
    case "$(uname -s)" in
        Linux*)     os="linux" ;;
        Darwin*)    os="macos" ;;
        CYGWIN*|MINGW*|MSYS*) os="windows" ;;
        *)          os="unknown" ;;
    esac
    printf "%s" "$os"
}

OS=$(detect_os)

# ── PowerShell detection ─────────────────────────────────────────────────────
find_powershell() {
    if command -v pwsh &>/dev/null; then
        printf "pwsh"
    elif command -v powershell &>/dev/null; then
        printf "powershell"
    else
        printf ""
    fi
}

check_requirements() {
    local ps_ok=false
    local git_ok=false
    local errors=0

    PS_EXE=$(find_powershell)
    if [[ -n "$PS_EXE" ]]; then
        ps_ok=true
    else
        err "PowerShell not found."
    fi

    if command -v git &>/dev/null; then
        git_ok=true
    else
        err "git not found."
    fi

    if ! $ps_ok; then
        err ""
        err "Install PowerShell 7+ (pwsh):"
        case "$OS" in
            macos)  err "  brew install powershell" ;;
            linux)  err "  sudo apt install powershell  OR  see https://aka.ms/powershell" ;;
            windows) err "  winget install Microsoft.PowerShell  OR  see https://aka.ms/powershell" ;;
        esac
        ((errors++))
    fi

    if ! $git_ok; then
        err ""
        err "Install git:"
        case "$OS" in
            macos)  err "  brew install git" ;;
            linux)  err "  sudo apt install git" ;;
            windows) err "  winget install Git.Git" ;;
        esac
        ((errors++))
    fi

    return $errors
}

# ── Usage ────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
AURA Audit Engine v${AURA_VERSION} — Universal Installer

Usage: install.sh [OPTIONS]

Options:
  --target DIR        Target project directory (default: current directory)
  --no-symlinks       Copy bin scripts instead of creating symlinks
  --quiet             Suppress informational output
  --help, -h          Show this help

Examples:
  ./install.sh
  ./install.sh --target /home/user/my-project
  ./install.sh --target /home/user/my-project --no-symlinks

Environment:
  AURA_TARGET         Set target directory (overridden by --target)
EOF
}

# ── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            if [[ -z "${2:-}" ]]; then
                err "--target requires a path argument"
                exit 1
            fi
            TARGET_DIR="$2"
            shift 2
            ;;
        --no-symlinks)
            INSTALL_SYMLINKS=false
            shift
            ;;
        --quiet)
            QUIET=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# ── Resolve target ───────────────────────────────────────────────────────────
if [[ -n "${AURA_TARGET:-}" && -z "$TARGET_DIR" ]]; then
    TARGET_DIR="$AURA_TARGET"
fi

if [[ -z "$TARGET_DIR" ]]; then
    TARGET_DIR="$(pwd)"
fi

mkdir -p "$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

# ── Resolve source (the AURA engine directory) ───────────────────────────────
resolve_source() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

    if [[ -f "$script_dir/src/engine/run-audit.ps1" ]]; then
        printf "%s" "$script_dir"
    elif [[ -f "$script_dir/../src/engine/run-audit.ps1" ]]; then
        printf "%s" "$(cd "$script_dir/.." && pwd)"
    else
        printf ""
    fi
}

SOURCE_DIR=$(resolve_source)

# ── Download source if not running from a local checkout ─────────────────────
if [[ -z "$SOURCE_DIR" ]]; then
    TEMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'aura-install')
    # shellcheck disable=SC2064
    trap "rm -rf '$TEMP_DIR'" EXIT

    info "Downloading AURA v${AURA_VERSION}..."
    if command -v git &>/dev/null; then
        git clone --depth 1 --branch "v${AURA_VERSION}" "$AURA_REPO" "$TEMP_DIR/aura" 2>/dev/null || {
            err "git clone failed; falling back to tarball."
            curl -fsSL "$AURA_TARBALL" -o "$TEMP_DIR/aura.tar.gz" || {
                err "Failed to download AURA."
                exit 1
            }
            tar -xzf "$TEMP_DIR/aura.tar.gz" -C "$TEMP_DIR"
            mv "$TEMP_DIR/aura-audit-${AURA_VERSION}" "$TEMP_DIR/aura"
        }
    else
        curl -fsSL "$AURA_TARBALL" -o "$TEMP_DIR/aura.tar.gz" || {
            err "Failed to download AURA."
            exit 1
        }
        tar -xzf "$TEMP_DIR/aura.tar.gz" -C "$TEMP_DIR"
        mv "$TEMP_DIR/aura-audit-${AURA_VERSION}" "$TEMP_DIR/aura"
    fi
    SOURCE_DIR="$TEMP_DIR/aura"
    info "Downloaded to $SOURCE_DIR"
fi

# ── Verify source integrity ──────────────────────────────────────────────────
if [[ ! -f "$SOURCE_DIR/src/engine/run-audit.ps1" ]]; then
    err "Engine entry point not found at $SOURCE_DIR/src/engine/run-audit.ps1"
    exit 1
fi

# ── Bootstrap .aura/ ─────────────────────────────────────────────────────────
bootstrap_aura() {
    local src="$1"
    local dst="$2"

    if [[ -d "$dst/.aura" ]]; then
        warn ".aura/ already exists at $dst; backing up..."
        local backup="$dst/.aura.bak.$(date +%Y%m%d_%H%M%S)"
        mv "$dst/.aura" "$backup"
        info "Backed up to $backup"
    fi

    cp -r "$src/.aura" "$dst/.aura"
    info ".aura/ bootstrap copied to $dst/.aura"

    if [[ ! -f "$dst/.aura/run-audit.ps1" ]]; then
        cp "$src/.aura/run-audit.ps1" "$dst/.aura/run-audit.ps1"
    fi
}

# ── Bootstrap .githooks/ ─────────────────────────────────────────────────────
bootstrap_githooks() {
    local src="$1"
    local dst="$2"

    if [[ -d "$src/.githooks" ]]; then
        if [[ ! -d "$dst/.githooks" ]]; then
            cp -r "$src/.githooks" "$dst/.githooks"
            info ".githooks/ copied to $dst/.githooks"
        fi
    fi
}

# ── Install bin scripts ──────────────────────────────────────────────────────
install_bin_scripts() {
    local src="$1"
    local dst="$2"

    if [[ -d "$dst/bin" ]]; then
        warn "bin/ already exists at $dst; skipping bin installation."
        return 0
    fi

    mkdir -p "$dst/bin"

    if $INSTALL_SYMLINKS; then
        if [[ -f "$src/bin/aura.sh" ]]; then
            ln -sf "$src/bin/aura.sh" "$dst/bin/aura.sh" 2>/dev/null || {
                warn "Could not create symlink; falling back to copy."
                cp "$src/bin/aura.sh" "$dst/bin/aura.sh"
            }
        fi
        if [[ -f "$src/bin/aura.ps1" ]]; then
            ln -sf "$src/bin/aura.ps1" "$dst/bin/aura.ps1" 2>/dev/null || {
                cp "$src/bin/aura.ps1" "$dst/bin/aura.ps1"
            }
        fi
    else
        cp "$src/bin/aura.sh" "$dst/bin/aura.sh"
        cp "$src/bin/aura.ps1" "$dst/bin/aura.ps1"
    fi

    chmod +x "$dst/bin/aura.sh" 2>/dev/null || true
    info "Bin scripts installed to $dst/bin/"
}

# ── Copy run-audit.sh ────────────────────────────────────────────────────────
install_run_script() {
    local src="$1"
    local dst="$2"

    if [[ -f "$dst/run-audit.sh" ]]; then
        warn "run-audit.sh already exists at $dst; skipping."
        return 0
    fi

    cp "$src/run-audit.sh" "$dst/run-audit.sh"
    chmod +x "$dst/run-audit.sh" 2>/dev/null || true
    info "run-audit.sh copied to $dst/"
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    info "AURA Audit Engine v${AURA_VERSION} — Universal Installer"
    info "OS detected: ${OS}"
    info "Target: ${TARGET_DIR}"
    $QUIET || info ""

    check_requirements || {
        err "Missing required dependencies. Please install them and try again."
        exit 1
    }

    $QUIET || info "PowerShell found: ${PS_EXE}"

    # If target is the same as source, skip copying to avoid clobbering
    if [[ "$(cd "$SOURCE_DIR" && pwd)" == "$TARGET_DIR" ]]; then
        info "Source and target directories are the same; skipping copy."
        info ""
        info "  aura status     — Show convergence status"
        info "  aura run        — Run next audit cycle"
        info "  aura push       — Stage, commit, and push"
        return 0
    fi

    boostrap_aura "$SOURCE_DIR" "$TARGET_DIR"
    bootstrap_githooks "$SOURCE_DIR" "$TARGET_DIR"
    install_bin_scripts "$SOURCE_DIR" "$TARGET_DIR"
    install_run_script "$SOURCE_DIR" "$TARGET_DIR"

    echo ""
    info "──────────────────────────────────────────"
    info " AURA Audit Engine v${AURA_VERSION} installed!"
    info "──────────────────────────────────────────"
    echo ""
    info "Quick start:"
    info "  cd ${TARGET_DIR}"
    info "  ./run-audit.sh status"
    info "  ./run-audit.sh run"
    echo ""
    info "Or via bin scripts:"
    info "  ./bin/aura.sh status"
    info "  ./bin/aura.sh run"
    echo ""
    info "For full documentation, see README.md"
    echo ""
}

main "$@"