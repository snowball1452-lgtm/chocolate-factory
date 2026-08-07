# docs/agent-control/compiler/parser.py

import ast
import json
import re
from typing import Dict, Any, Tuple, Optional
from compiler.operators import ABSENT

def parse_policy_line(line: str) -> Optional[Tuple[str, Any]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    if "=" not in line:
        return None

    lhs, rhs = line.split("=", 1)
    path = lhs.strip()
    val_str = rhs.strip()

    if not path.startswith("/"):
        return None

    if val_str.lower() == "true":
        return path, True
    elif val_str.lower() == "false":
        return path, False
    elif val_str.lower() == "absent":
        return path, ABSENT
    
    # Try JSON first (handles lists, dicts, numbers, strings)
    try:
        val = json.loads(val_str)
        return path, val
    except json.JSONDecodeError:
        pass
    
    # Try ast.literal_eval (handles Python-style literals)
    try:
        val = ast.literal_eval(val_str)
        return path, val
    except Exception:
        pass

    # Fallback to raw string if literal_eval fails
    if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
        val_str = val_str[1:-1]
    return path, val_str

def parse_policy_text(text: str) -> Dict[str, Any]:
    policies = {}
    lines = text.splitlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        
        # Check if this line starts a path=value
        if "=" in line and line.split("=", 1)[0].strip().startswith("/"):
            lhs, rhs = line.split("=", 1)
            path = lhs.strip()
            val_str = rhs.strip()
            
            # If the value starts a JSON array/object but doesn't close on this line,
            # consume continuation lines until brackets balance
            if val_str and val_str[0] in "[{" and not _is_balanced(val_str):
                full_val = val_str
                i += 1
                while i < len(lines):
                    full_val += " " + lines[i].strip()
                    if _is_balanced(full_val):
                        break
                    i += 1
                parsed = parse_policy_line(f"{path} = {full_val}")
            else:
                parsed = parse_policy_line(line)
            
            if parsed is not None:
                policies[parsed[0]] = parsed[1]
        i += 1
    return policies

def _is_balanced(s: str) -> bool:
    """Check if brackets/braces are balanced in a string."""
    stack = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch in '"\'':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "[{(":
            stack.append(ch)
        elif ch in "]})":
            if not stack:
                return True  # unbalanced close = end of value
            opener = stack.pop()
            if opener == "[" and ch != "]": return False
            if opener == "{" and ch != "}": return False
            if opener == "(" and ch != ")": return False
    return len(stack) == 0

def parse_policy_file(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        return parse_policy_text(f.read())
