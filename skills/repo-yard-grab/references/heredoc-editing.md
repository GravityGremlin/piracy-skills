# Session text-mangling: safe editing procedure

Some Hermes CLI sessions mangle text in tool inputs AND tool outputs:
strips `=`, `#` comment prefixes, leading indent spaces, `{`, `=>`, and
small words (from/as/on/so/is/be/the/will/with). Displayed file content
can look broken while the file on disk is fine — and code you type into
execute_code literals can land broken on disk even when write_file
reports verified.

## Detect

- `ast.parse` every Python file after ANY edit; a SyntaxError at a line
  whose displayed text looks fine means the DISPLAY is lying, not the file.
- `md5sum file` vs `git show HEAD:file | md5sum` distinguishes "my edit
  broke it" from "HEAD was already like this".
- `od -c` / `cat -A` a suspect region to see real bytes — but remember
  the tool RESULT text is mangled too, so od output through the same
  channel is also suspect.

## Safe channels (proven, in order of preference)

1. `terminal` with `python3 - <<'EOF'` heredoc (quoted delimiter): the
   script reaches the interpreter intact. All file splices, AST checks,
   and code generation go through this.
2. `write_file` for whole-file content (it verifies the written hash),
   then IMMEDIATELY ast-parse / run to confirm the content survived —
   verification, not trust.

## Splice procedure (insert a block into an existing file)

1. `git checkout -- <file>` first if the working tree is suspect; verify
   md5 matches HEAD.
2. Write the insertion script via heredoc: locate the anchor with
   `src.find(marker)`, compute the target block's indentation from
   `ast.parse` structure (col_offset / parent-function body indent) —
   NEVER from displayed text.
3. Insert, `ast.parse` the result, write back. For YAML (compose files)
   `yaml.safe_load` after every edit.
4. Loop reset on a mangled mess: `git checkout -- <file>` and redo from
   the clean HEAD copy; do not hand-patch a corrupted region.

## Ground-truth reads

When you must know exact bytes (indentation, presence of a char), have
Python print `repr()` or base64 of the region via heredoc and decode
mentally — repr of an intact string survives the mangle because the
mangle eats literal spaces/pounds, and escaped `\n` + explicit quote
marks make stripped whitespace visible.
