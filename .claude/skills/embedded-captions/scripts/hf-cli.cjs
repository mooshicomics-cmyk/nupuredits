// Modified by Homewell LLC, 2026, for The Reels Editing Engine: inside the engine this copy hands out the engine's pinned HyperFrames (product/hf_npx.cjs) when no checkout was named. Original: HyperFrames v0.8.181, skills/embedded-captions/scripts/hf-cli.cjs.
// Resolve CLI ownership once for matting, transcription, and shell rendering.
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
function hfCli(checkout) {
  const root = path.resolve(__dirname, "../../..");
  for (const dir of [checkout, process.env.HYPERFRAMES_ROOT].filter(Boolean)) {
    const cli = path.join(dir, "packages/cli/dist/cli.js");
    if (fs.existsSync(cli)) return cli;
  }
  // Inside The Reels Editing Engine: its own pinned HyperFrames, run through npx (product/hf_npx.cjs).
  const engineRoot = path.resolve(__dirname, "../../../..");   // <engine>/.claude/skills/embedded-captions/scripts
  const engine = path.join(engineRoot, "product", "hf_npx.cjs");
  if (fs.existsSync(engine) && fs.existsSync(path.join(engineRoot, "product.json"))) return engine;
  const manifests = [
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    "gemini-extension.json",
  ];
  if (
    !fs.existsSync(path.join(root, "packages/cli/dist/cli.js")) &&
    manifests.some((p) => fs.existsSync(path.join(root, p)))
  ) {
    return path.join(root, "skills/hyperframes/scripts/plugin-cli.mjs");
  }
  for (const dir of [root, path.join(os.homedir(), "Downloads/hyperframes")].filter(Boolean)) {
    const cli = path.join(dir, "packages/cli/dist/cli.js");
    if (fs.existsSync(cli)) return cli;
  }
  throw new Error(
    "HyperFrames CLI unavailable: install the full plugin or set HYPERFRAMES_ROOT to a built checkout.",
  );
}
/** The browser the CLI launches (`hyperframes browser path`), so these scripts never pick their own; without a CLI,
 * the system Chrome they used before. */
function hfBrowser() {
  const { execFileSync } = require("node:child_process");
  const asks = [
    () => [process.execPath, [hfCli(), "browser", "path"]],
    () => ["hyperframes", ["browser", "path"]],
  ];
  for (const ask of asks) {
    try {
      const [command, args] = ask();
      const out = execFileSync(command, args, {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      });
      const found = out.trim().split("\n").pop();
      if (found && fs.existsSync(found)) return found;
    } catch {}
  }
  const chrome =
    process.platform === "darwin"
      ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
      : "/usr/bin/google-chrome";
  return fs.existsSync(chrome) ? chrome : undefined;
}
module.exports = { hfCli, hfBrowser };
if (require.main === module) console.log(hfCli(process.argv[2]));
