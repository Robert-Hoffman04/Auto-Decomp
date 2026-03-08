# Auto-Decomp

This repository is scaffolded from [`encounter/dtk-template`](https://github.com/encounter/dtk-template) and is intended to be used with [`encounter/decomp-toolkit`](https://github.com/encounter/decomp-toolkit).

## Quick start

1. Put your game image or extracted files in the template location:

   ```text
   orig/GAMEID
   ```

2. Configure the project for your game ID (e.g. `GLZE01`):

   ```bash
   scripts/setup_project.sh <GAMEID>
   ```

   The setup script renames template paths and auto-populates as much config data as possible from files found in `orig/<GAMEID>` (DOL/REL hashes, modules list, and `build.sha1`).

3. Review and adjust:

   ```text
   config/<GAMEID>/config.yml
   ```

4. Start the initial configure + analysis run:

   ```bash
   scripts/initial_run.sh <GAMEID>
   ```

## Notes

- `ninja` will download tool dependencies automatically via `tools/download_tool.py` when needed.
- Use the generated `config/<GAMEID>/symbols.txt` and `config/<GAMEID>/splits.txt` as the basis for decomp progress.
- For full configuration details, see the `docs/` directory from `dtk-template`.
