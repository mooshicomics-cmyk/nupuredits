// source-size.cjs: added by Homewell LLC, 2026, for The Reels Editing Engine (not part of HyperFrames).
// The canvas a caption project gets when its theme.json / cinematic.json names no width and height: the
// source video's own shape, short side 1080 (a 9:16 phone clip -> 1080x1920), instead of a fixed landscape
// size that would crop a portrait reel sideways. Falls back to the caller's default when the video cannot be
// read.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function sourceSize(project, fallbackW, fallbackH) {
  for (const name of ["source.mp4", "clip.mp4"]) {
    const p = path.join(project, name);
    if (!fs.existsSync(p)) continue;
    const r = spawnSync("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries",
      "stream=width,height:stream_side_data=rotation", "-of", "json", p], { encoding: "utf8", timeout: 30000 });
    try {
      const s = JSON.parse(r.stdout).streams[0];
      let w = s.width, h = s.height;
      const rot = Math.abs(((s.side_data_list || []).find((d) => d.rotation != null) || {}).rotation || 0);
      if (rot === 90 || rot === 270) [w, h] = [h, w];   // a phone clip stored sideways plays upright
      if (!(w > 0 && h > 0)) continue;
      const k = 1080 / Math.min(w, h);
      const even = (x) => Math.max(2, 2 * Math.round((x * k) / 2));
      return { W: even(w), H: even(h) };
    } catch (_) { /* unreadable: try the next name, then the fallback */ }
  }
  return { W: fallbackW, H: fallbackH };
}

module.exports = { sourceSize };
