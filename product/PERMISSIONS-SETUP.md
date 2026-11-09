# Fewer interruptions while you edit (permissions setup)

By default, Claude Code asks your permission before it changes a file or runs a command. That is a good
safety net. But this engine makes a LOT of small moves to build one reel (cut, caption, render, and so on),
so all those little "is this okay?" prompts can slow down a nap-time editing window. Here is how to turn
them down or off, your choice, and how to put them back.

You are always in control. Pick the comfort level that feels right.

## The quick way: switch the permission mode in Claude Code
Claude Code has a permission mode you can switch for the current session:

1. **Manual** (the default). Asks before edits and commands.
2. **Accept edits.** Stops asking before it edits your files. It will still ask before running some tools.
3. **Plan.** Claude only plans and makes no changes. Handy when you just want to talk it through.

The keyboard shortcut that cycles these modes has changed between Claude Code versions, so we do not print a
fixed key here (an out-of-date one would only mislead you). Two reliable ways to switch it:
- **The course video** walks the current way to change permissions, step by step.
- In Claude Code, the current mode shows at the bottom of your screen. If you are not sure of the shortcut on
  your version, just ask Claude "how do I turn on auto-accept mode?" and it will tell you the current way.

A session toggle lasts only for that session. Next time you open Claude Code you are back to the default
unless you set one (below), which is the sturdier option anyway.

## The set-once way: choose your default
If you want the same comfort level every time without pressing anything, set it once. Open the file
`.claude/settings.json` inside your engine folder. It already has a `permissions` block of the engine's own
(the rules that keep "set me up" on this engine's setup and protect your private files): add ONE
`defaultMode` line as the first line inside that block, right after `"permissions": {`, and leave every
other line exactly as it is. Easiest of all: ask Claude "set my default permission mode to accept edits"
(or bypass) and it adds the line for you. Engine updates keep your setting: the updater
saves it before it refreshes that file and puts it back right after.

### Option A. Smooth (recommended for most people)
Stops asking before file edits, still checks in before anything bigger.

```json
  "permissions": {
    "defaultMode": "acceptEdits",
    ...keep every line that was already here...
  },
```

Honest note: because this engine runs real video tools (ffmpeg, the render engine) to build your reel, this
mode will STILL pause to ask before those run. Great if you like a light safety check. If you want it to
stop asking entirely while you edit, use Option B.

### Option B. Fully hands-off (what most people want for batch editing)
Claude stops asking, period, and just builds. This is the smoothest editing experience.

```json
  "permissions": {
    "defaultMode": "bypassPermissions",
    ...keep every line that was already here...
  },
```

**What Bypass means, honestly:** Claude stops asking before it runs commands or changes files. The engine
mostly works on your own footage in your own folder, but a few features do read outside text: pulling an
inspo reel or your captions through Apify, and the update notes. In Bypass mode nothing stops to ask before a
command runs, so text from outside gets no second look from you. The first time you turn this on, Claude shows
a one-time warning you accept once per computer.

**What the engine adds to protect you, in every mode:** its settings block Claude from reading or changing your
private keys, password keychain and browser data, and from wiping your home folder. The engine also tells Claude
to treat any text it pulls from outside as information, never as instructions. Updates only install when they
carry the engine's own signature.

**The one habit to keep:** only ask it to work on your own reels and your own files. Do not paste in links or
files from people you do not know and tell it to run them. If you would rather keep a light safety check while
you edit, Option A is the safer choice; you will just click "yes" a little more.

### Prefer the command line?
You can also start Claude in a mode for one session without editing any file:

- `claude --permission-mode acceptEdits`
- `claude --permission-mode bypassPermissions` (or the same thing: `claude --dangerously-skip-permissions`)

## Putting it back
Changed your mind? Set `"defaultMode": "default"` in `.claude/settings.json` (or delete just that one line,
leaving the rest of the `permissions` block, which holds the engine's protections), and you are back to being asked every
time. Or press **Shift + Tab** to change modes on the spot.

## The short version
- Want a light safety check: **Accept edits** (Option A). Still asks before it renders.
- Want it to just build without interrupting: **Bypass** (Option B). Smoothest for batch reels.
- Bypass is the smoothest; Accept edits keeps a light safety check. The engine's protections stay on in both.
- Change your mind anytime with Shift + Tab, or by editing that one setting back.
