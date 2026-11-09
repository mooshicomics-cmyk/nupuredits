---
name: reuse-prompt
description: Hand back the recipe behind a finished reel as one paste-ready prompt, so the next reel gets built the same way without re-explaining it. Use when the creator says "turn this into a prompt I can reuse", "give me the prompt for this", "save this as a recipe", "how do I get this again", "make the next one like this one", or has just approved a reel she loves.
user-invocable: true
argument-hint: "[job name, or blank for the reel we just finished]"
---

# Reuse prompt — the recipe behind a reel she loves

She nailed one and wants the next built the same way. Hand her the recipe as a prompt she can paste.

## Do this

1. Work out which job she means. Usually the reel just finished in this session; otherwise ask, one line.
2. Run `python3 product/reel_recipe.py <job>`. It reads only what the job RECORDED (its plan, shot plan,
   what was exported, the pack) and saves `projects/<job>/reuse-prompt.md`. Nothing is guessed.
3. Before you hand it over, add the decisions from THIS conversation that no file holds (a sound rule she
   gave, "no summary card", a color grade she asked for by name). Add them as plain lines in the matching
   section. Never add hook copy, timestamps or placement numbers: those belong to that footage.
4. Give it to her as ONE copyable block (not fragments), and say in one line where the file is saved.

## What it deliberately leaves out, and why (say it if she asks)

- **The hook's words.** A hook is written for its own reel and must never repeat the spoken opener. The
  recipe keeps the hook's SHAPE and how long it stays up; the tension it names is a [bracket].
- **Her saved preferences** (`/learn`, "learn this style", favorite sounds). Those already apply to every
  build on their own, so repeating them would only drift out of date.
- **Anything timed to that footage.** Timestamps and placements are measured fresh on each reel.
