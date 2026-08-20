class AuraAudit < Formula
  desc "Autonomous Engineering Audit Engine — continuous audit-remediate-verify loop with strict state machine enforcement"
  homepage "https://github.com/aura/aura-audit"
  url "https://github.com/aura/aura-audit/archive/refs/tags/v2.1.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "MIT"
  head "https://github.com/aura/aura-audit.git", branch: "main"

  depends_on "powershell"

  def install
    bin.install "bin/aura.sh" => "aura"
    bin.install "bin/aura.ps1" => "aura-ps"
    bin.install "run-audit.sh" => "aura-audit"

    (pkgshare/"src").install Dir["src/*"]
    (pkgshare/"config").install Dir["config/*"]
    (pkgshare/".aura").install Dir[".aura/*"]
    (pkgshare/".githooks").install Dir[".githooks/*"]

    ohai "AURA Audit Engine v2.1.0 installed."
    ohai ""
    ohai "Bootstrap into a project:"
    ohai "  cp -r #{pkgshare}/.aura /path/to/your-project/"
    ohai "  cp -r #{pkgshare}/.githooks /path/to/your-project/"
    ohai ""
    ohai "Run an audit:"
    ohai "  aura status"
    ohai "  aura run"
  end

  test do
    system "#{bin}/aura", "--help" rescue system "true"
    assert_match "AURA", shell_output("#{bin}/aura --help 2>&1 || true")
  end
end