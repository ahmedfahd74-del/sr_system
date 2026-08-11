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
| GLOB001 | Function reassigns a global variable (banned in Pine)       |
| SEC001  | Mutable/`var` variable used inside `request.security` expr  |
| SEC002  | Drawing / `strategy.*` / `request.*` / `runtime.error` call |
|         | inside a `request.security` expression                      |

## Semantic checks (errors TradingView catches that syntax checks miss)

- **GLOB001 — global reassignment inside a function.** Pine raises "Cannot
  modify global variable ..." when a user-defined function reassigns a
  global (with `:=`, `+=`, etc.), even one declared with `var`. A local
  declaration inside the function shadows the global and is *not* flagged.
- **SEC001 / SEC002 — `request.security()` expression restrictions.** The
  expression argument cannot contain mutable variables (anything declared
  with `var`/`varip`, or any global reassigned after initialization),
  nested `request.*()` calls, chart-drawing calls, or `strategy.*` /
  `runtime.error()` calls. User-defined functions used as the expression
  are scanned too, because their bodies must obey the same rules.

## False positives handled

- `{{ticker}}` / `{{interval}}` alert placeholders no longer trigger
  SYN001 (string contents are stripped before the curly-brace check).
- UDT field mutations (`ob.mitigated := ...`, `boxObj := ...` with
  `array.set` write-back) no longer trigger OP001.
- Operators inside string literals (e.g. `"A+++ framework"`) no longer
  trigger OP002 / STYLE001.

Pine still only compiles inside TradingView's editor — the linter catches
the common structural and semantic errors but is not a substitute for a
successful compile.
