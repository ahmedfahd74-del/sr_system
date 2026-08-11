# Pine Script v6 Linter

Validates Pine Script v6 code **before** TradingView compilation. Reports all
issues in one pass instead of one error at a time.

## Usage

```bash
# Lint a script
python3 tools/pine_linter.py pinescripts/ti_smc_v6.pine

# Run the built-in self-test (seeded errors + intentional warnings)
python3 tools/pine_linter.py --test
```

Exit code: `0` if no errors (warnings allowed), `1` if errors or file not found.

## What it checks

| Code    | Check                                                       |
|---------|-------------------------------------------------------------|
| V000-2  | Missing / wrong `//@version` annotation (v6 expected)       |
| D000    | Missing `indicator()` / `strategy()` / `library()`          |
| B001-3  | Unmatched, mismatched, or unclosed brackets `( ) [ ]`       |
| VAR001  | `var` / `varip` used with a tuple declaration               |
| SYN001  | Curly braces `{}` used as code blocks                       |
| SYN002  | Trailing comma before `)`                                   |
| OP001   | `:=` used before the variable was declared                  |
| OP002   | Possible double operator                                    |
| FN001   | `=>` not following a function signature or switch/case      |
| TYPE001 | UDT type name not capitalized                               |
| TYPE002 | UDT field missing `type name` format                        |
| CMP001  | `=` in a condition (did you mean `==`?)                     |
| STR001-2| Unclosed string literals                                    |
| IND001  | Tab characters (Pine prefers spaces)                        |
| DEP001  | Deprecated syntax (`study(`, bare `security(`)              |
| STYLE001| Missing spaces around operators                             |

## Known false positives (by design — review, don't blindly fix)

- **`{{ticker}}` / `{{interval}}` alert placeholders** — the curly-brace
  check (SYN001) flags `{{...}}` inside `alertcondition()` messages. These
  are valid Pine placeholders; ignore those findings.
- **UDT field mutations** — `ob.boxObj := ...` style writes on `type`
  instances (with `array.set` write-back) can trigger OP001 because the
  linter tracks plain variables, not user-defined-type fields.

Pine still only compiles inside TradingView's editor — the linter catches
the common structural errors but is not a substitute for a successful
compile.
