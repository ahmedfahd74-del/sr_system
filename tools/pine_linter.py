#!/usr/bin/env python3
"""
Pine Script v6 Linter
Validates Pine Script code against v6 rules before TradingView compilation.
Reports ALL errors at once.
"""

import re
import sys
from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum


class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class LintIssue:
    line_num: int
    column: int
    severity: Severity
    code: str
    message: str
    suggestion: str = ""
    
    def __str__(self):
        sev = self.severity.value
        msg = f"Line {self.line_num}:{self.column} [{sev}] {self.code}: {self.message}"
        if self.suggestion:
            msg += f"\n    Suggestion: {self.suggestion}"
        return msg


class PineLinter:
    """Pine Script v6 Linter"""
    
    # Built-in functions that return tuples (need tuple declaration)
    TUPLE_FUNCTIONS = {
        'ta.bb': 3,
        'ta.dmi': 3,
        'ta.kc': 3,
        'ta.macd': 3,
        'ta.stoch': 2,
        'ta.supertrend': 2,
    }
    
    # Keywords that cannot be used as identifiers
    RESERVED_WORDS = {
        'if', 'else', 'for', 'while', 'switch', 'import', 'export',
        'var', 'varip', 'const', 'simple', 'series', 'type', 'method',
        'true', 'false', 'na', 'and', 'or', 'not',
        'int', 'float', 'bool', 'string', 'color', 'label', 'line',
        'box', 'table', 'array', 'matrix', 'map', 'polyline', 'linefill',
        'indicator', 'strategy', 'library',
    }
    
    # Valid type keywords
    TYPE_KEYWORDS = {
        'int', 'float', 'bool', 'string', 'color',
        'label', 'line', 'box', 'table', 'polyline', 'linefill',
        'array', 'matrix', 'map', 'chart.point',
    }
    
    # Valid qualifier keywords
    QUALIFIER_KEYWORDS = {'const', 'input', 'simple', 'series'}
    
    def __init__(self):
        self.issues: List[LintIssue] = []
        self.lines: List[str] = []
        self.in_function = False
        self.in_type_def = False
        self.declared_vars = set()
        self.declared_functions = set()
        self.declared_types = set()
    
    def lint(self, code: str) -> List[LintIssue]:
        """Lint Pine Script code and return all issues"""
        self.issues = []
        self.lines = code.split('\n')
        self.declared_vars = set()
        self.declared_functions = set()
        self.declared_types = set()
        
        # Run all checks
        self._check_version_annotation()
        self._check_declaration_statement()
        self._check_bracket_balance()
        self._check_variable_declarations()
        self._check_reassignment_operator()
        self._check_function_definitions()
        self._check_type_definitions()
        self._check_common_errors()
        self._check_string_literals()
        self._check_indentation()
        self._check_deprecated_syntax()
        
        # Sort by line number
        self.issues.sort(key=lambda x: (x.line_num, x.column))
        
        return self.issues
    
    def _add_issue(self, line_num: int, column: int, severity: Severity, 
                   code: str, message: str, suggestion: str = ""):
        self.issues.append(LintIssue(line_num, column, severity, code, message, suggestion))
    
    def _check_version_annotation(self):
        """Check for proper version annotation"""
        found_version = False
        version_line = -1
        
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if stripped.startswith('//@version='):
                found_version = True
                version_line = i + 1
                
                # Check version number
                match = re.match(r'//@version=(\d+)', stripped)
                if match:
                    version = int(match.group(1))
                    if version < 6:
                        self._add_issue(i + 1, 1, Severity.WARNING, "V001",
                            f"Using Pine Script v{version}, consider upgrading to v6",
                            "Change to //@version=6")
                    elif version > 6:
                        self._add_issue(i + 1, 1, Severity.ERROR, "V002",
                            f"Invalid version {version}, max is 6",
                            "Change to //@version=6")
                break
            elif stripped and not stripped.startswith('//'):
                # Non-comment code before version
                break
        
        if not found_version:
            self._add_issue(1, 1, Severity.ERROR, "V000",
                "Missing version annotation",
                "Add //@version=6 at the start of the script")
    
    def _check_declaration_statement(self):
        """Check for indicator/strategy/library declaration"""
        found_declaration = False
        
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if stripped.startswith(('indicator(', 'strategy(', 'library(')):
                found_declaration = True
                
                # Check for unclosed parenthesis on declaration
                open_count = stripped.count('(')
                close_count = stripped.count(')')
                if open_count != close_count:
                    # Multi-line declaration, find closing
                    j = i + 1
                    while j < len(self.lines) and open_count != close_count:
                        open_count += self.lines[j].count('(')
                        close_count += self.lines[j].count(')')
                        j += 1
                break
        
        if not found_declaration:
            self._add_issue(1, 1, Severity.ERROR, "D000",
                "Missing declaration statement",
                "Add indicator(), strategy(), or library() declaration")
    
    def _check_bracket_balance(self):
        """Check for balanced brackets and parentheses"""
        brackets = {'(': ')', '[': ']'}
        stack = []
        
        for i, line in enumerate(self.lines):
            # Skip comments
            code_line = self._remove_comments(line)
            # Skip string literals for bracket checking
            code_line = self._remove_strings(code_line)
            
            for j, char in enumerate(code_line):
                if char in brackets:
                    stack.append((char, i + 1, j + 1))
                elif char in brackets.values():
                    if not stack:
                        self._add_issue(i + 1, j + 1, Severity.ERROR, "B001",
                            f"Unmatched closing bracket '{char}'",
                            "Remove or add matching opening bracket")
                    else:
                        open_bracket, _, _ = stack.pop()
                        if brackets[open_bracket] != char:
                            self._add_issue(i + 1, j + 1, Severity.ERROR, "B002",
                                f"Mismatched brackets: expected '{brackets[open_bracket]}' but found '{char}'",
                                "Fix bracket pairing")
        
        # Check for unclosed brackets
        for bracket, line_num, col in stack:
            self._add_issue(line_num, col, Severity.ERROR, "B003",
                f"Unclosed bracket '{bracket}'",
                f"Add closing bracket '{brackets[bracket]}'")
    
    def _check_variable_declarations(self):
        """Check variable declaration syntax"""
        var_pattern = re.compile(
            r'^(\s*)(var\s+|varip\s+)?'
            r'(const\s+|simple\s+|series\s+)?'
            r'(int|float|bool|string|color|label|line|box|table|array|matrix|map)?'
            r'\s*(\w+)\s*='
        )
        
        tuple_pattern = re.compile(r'^\s*\[([^\]]+)\]\s*=')
        
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            
            # Skip comments and empty lines
            if not stripped or stripped.startswith('//'):
                continue
            
            # Check for var with tuple (not allowed)
            if re.match(r'^\s*(var|varip)\s+\[', line):
                self._add_issue(i + 1, 1, Severity.ERROR, "VAR001",
                    "Cannot use 'var' or 'varip' with tuple declarations",
                    "Remove var/varip keyword or use single variable")
            
            # Check for curly braces (not valid in Pine)
            if '{' in stripped and not stripped.startswith('//'):
                # Exception: map literals use {}
                if not re.search(r'map\.new<|=\s*\{', stripped):
                    self._add_issue(i + 1, stripped.index('{') + 1, Severity.ERROR, "SYN001",
                        "Curly braces {} are not used for code blocks in Pine Script",
                        "Use indentation for code blocks instead")
    
    def _check_reassignment_operator(self):
        """Check for incorrect use of = instead of :="""
        # First pass: collect all declared variables
        declared = set()
        
        assignment_pattern = re.compile(r'(\w+)\s*=\s*[^=]')
        reassign_pattern = re.compile(r'(\w+)\s*:=')
        
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('//'):
                continue
            
            # Track declarations
            match = assignment_pattern.search(stripped)
            if match:
                var_name = match.group(1)
                if var_name not in self.RESERVED_WORDS:
                    declared.add(var_name)
            
            # Check for := usage
            match = reassign_pattern.search(stripped)
            if match:
                var_name = match.group(1)
                if var_name not in declared:
                    self._add_issue(i + 1, match.start() + 1, Severity.WARNING, "OP001",
                        f"Variable '{var_name}' reassigned before declaration",
                        "Declare variable first with = before using :=")
    
    def _check_function_definitions(self):
        """Check function definition syntax"""
        func_pattern = re.compile(r'^(\w+)\s*\(([^)]*)\)\s*=>')
        
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('//'):
                continue
            
            # Check for function without =>
            if re.match(r'^\w+\s*\([^)]*\)\s*$', stripped):
                # Could be function call, check next line
                if i + 1 < len(self.lines):
                    next_line = self.lines[i + 1].strip()
                    if next_line and not next_line.startswith('=>'):
                        # Might be missing => for function definition
                        pass
            
            # Check for => without proper function signature
            if '=>' in stripped:
                before_arrow = stripped.split('=>')[0].strip()
                if before_arrow and not re.search(r'\)$', before_arrow):
                    if not re.search(r'switch|case|=>', before_arrow):
                        self._add_issue(i + 1, stripped.index('=>') + 1, Severity.WARNING, "FN001",
                            "'=>' should follow function parameters or switch/case",
                            "Check function definition syntax")
    
    def _check_type_definitions(self):
        """Check UDT (user-defined type) syntax"""
        in_type = False
        type_indent = 0
        
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            
            if stripped.startswith('type '):
                in_type = True
                type_indent = len(line) - len(line.lstrip())
                
                # Check type name
                match = re.match(r'type\s+(\w+)', stripped)
                if match:
                    type_name = match.group(1)
                    if not type_name[0].isupper():
                        self._add_issue(i + 1, 6, Severity.WARNING, "TYPE001",
                            f"Type name '{type_name}' should start with uppercase",
                            f"Rename to '{type_name[0].upper() + type_name[1:]}'")
                continue
            
            if in_type:
                if not stripped:
                    continue
                
                current_indent = len(line) - len(line.lstrip())
                
                # Check if still in type definition
                if current_indent <= type_indent and stripped:
                    in_type = False
                    continue
                
                # Check field syntax
                if not stripped.startswith('//'):
                    # Field should have type and name
                    if not re.match(r'^\w+\s+\w+', stripped):
                        self._add_issue(i + 1, current_indent + 1, Severity.ERROR, "TYPE002",
                            "Type field must have format: 'type fieldName'",
                            "Add type annotation before field name")
    
    def _check_common_errors(self):
        """Check for common Pine Script errors"""
        for i, line in enumerate(self.lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('//'):
                continue
            
            # Check for == vs = in conditions
            if re.search(r'\bif\s+\w+\s*=\s*[^=]', stripped):
                self._add_issue(i + 1, 1, Severity.WARNING, "CMP001",
                    "Using = in condition, did you mean == for comparison?",
                    "Use == for comparison, = is assignment")
            
            # Check for trailing commas in function calls (can cause issues)
            if re.search(r',\s*\)', stripped):
                match = re.search(r',\s*\)', stripped)
                if match:
                    self._add_issue(i + 1, match.start() + 1, Severity.WARNING, "SYN002",
                        "Trailing comma before closing parenthesis",
                        "Remove trailing comma")
            
            # Check for double operators (exclude valid Pine patterns)
            # Exclude: ==, !=, <=, >=, //, --, ++, **
            double_op_match = re.search(r'(?<![=!<>])[+\-*/]{2,}(?![=*/])', stripped)
            if double_op_match and '--' not in stripped and '//' not in stripped:
                self._add_issue(i + 1, 1, Severity.INFO, "OP002",
                    "Possible double operator detected (may be valid)",
                    "Check operator usage")
            
            # Check for missing space around operators (style)
            if re.search(r'\w[+\-*/]=\w', stripped):
                self._add_issue(i + 1, 1, Severity.INFO, "STYLE001",
                    "Consider adding spaces around operators for readability",
                    "Example: x += 1 instead of x+=1")
    
    def _check_string_literals(self):
        """Check for unclosed string literals"""
        for i, line in enumerate(self.lines):
            # Skip comment-only lines
            if line.strip().startswith('//'):
                continue
            
            # Remove comments for string checking
            code_part = self._remove_comments(line)
            
            # Count quotes (simple check)
            single_quotes = code_part.count("'") - code_part.count("\\'")
            double_quotes = code_part.count('"') - code_part.count('\\"')
            
            if single_quotes % 2 != 0:
                self._add_issue(i + 1, 1, Severity.ERROR, "STR001",
                    "Unclosed single-quoted string",
                    "Add missing closing quote '")
            
            if double_quotes % 2 != 0:
                self._add_issue(i + 1, 1, Severity.ERROR, "STR002",
                    "Unclosed double-quoted string",
                    'Add missing closing quote "')
    
    def _check_indentation(self):
        """Check for consistent indentation"""
        expected_indent = 0
        indent_size = 4  # Pine Script standard
        
        for i, line in enumerate(self.lines):
            if not line.strip():
                continue
            
            # Check for tabs (should use spaces)
            if '\t' in line:
                self._add_issue(i + 1, line.index('\t') + 1, Severity.WARNING, "IND001",
                    "Tab character found, Pine Script prefers spaces",
                    "Replace tabs with 4 spaces")
    
    def _check_deprecated_syntax(self):
        """Check for deprecated or v5 syntax that changed in v6"""
        deprecated = {
            'study(': ('indicator(', 'study() renamed to indicator() in v5+'),
        }
        
        for i, line in enumerate(self.lines):
            # Check for old security() without request. prefix
            if 'security(' in line and 'request.security(' not in line:
                self._add_issue(i + 1, line.index('security(') + 1, Severity.WARNING, "DEP001",
                    "security() moved to request.security()",
                    "Replace with request.security(")
            
            for old, (new, msg) in deprecated.items():
                if old in line:
                    suggestion = f"Replace with {new}" if new else "Consider alternative"
                    self._add_issue(i + 1, line.index(old) + 1, Severity.WARNING, "DEP001",
                        msg, suggestion)
    
    def _remove_comments(self, line: str) -> str:
        """Remove comments from a line"""
        # Remove single-line comments
        if '//' in line:
            # Be careful of // in strings
            in_string = False
            quote_char = None
            for i, char in enumerate(line):
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        quote_char = char
                    elif char == quote_char:
                        in_string = False
                elif line[i:i+2] == '//' and not in_string:
                    return line[:i]
        return line
    
    def _remove_strings(self, line: str) -> str:
        """Remove string literals from a line for bracket checking"""
        result = []
        in_string = False
        quote_char = None
        
        for char in line:
            if char in '"\'':
                if not in_string:
                    in_string = True
                    quote_char = char
                elif char == quote_char:
                    in_string = False
                continue
            
            if not in_string:
                result.append(char)
        
        return ''.join(result)


def lint_file(filepath: str) -> Tuple[List[LintIssue], str]:
    """Lint a Pine Script file"""
    with open(filepath, 'r') as f:
        code = f.read()
    
    linter = PineLinter()
    issues = linter.lint(code)
    
    return issues, code


def print_report(issues: List[LintIssue], filepath: str):
    """Print lint report"""
    print(f"\n{'='*60}")
    print(f"Pine Script Linter Report: {filepath}")
    print(f"{'='*60}\n")
    
    if not issues:
        print("✓ No issues found! Script is ready for TradingView.")
        return
    
    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]
    
    print(f"Found: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info\n")
    
    for issue in issues:
        print(issue)
        print()
    
    if errors:
        print(f"\n❌ {len(errors)} error(s) must be fixed before script will compile.")
    else:
        print(f"\n⚠ {len(warnings)} warning(s) found. Script may compile but review suggested.")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python pine_linter.py <script.pine>")
        print("       python pine_linter.py --test")
        sys.exit(1)
    
    if sys.argv[1] == '--test':
        # Run self-test
        test_code = '''
//@version=6
indicator("Test Script", overlay=true)

// Valid variable
float myVar = close

// Error: var with tuple
var [a, b] = ta.bb(close, 20, 2)

// Warning: = in condition
if myVar = 5
    label.new(bar_index, high, "test")

// Error: unclosed bracket
plot(close

// Error: curly braces
if true {
    x = 1
}
'''
        linter = PineLinter()
        issues = linter.lint(test_code)
        print_report(issues, "test_code")
    else:
        filepath = sys.argv[1]
        try:
            issues, _ = lint_file(filepath)
            print_report(issues, filepath)
            sys.exit(1 if any(i.severity == Severity.ERROR for i in issues) else 0)
        except FileNotFoundError:
            print(f"Error: File not found: {filepath}")
            sys.exit(1)


if __name__ == "__main__":
    main()
