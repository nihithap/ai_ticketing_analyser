"""
Git Repository & Stacktrace Code Analyzer.

When a support ticket cannot be resolved via historical ticket similarity
or contains a runtime stacktrace, this module connects to the application's
Git repository, locates the exact source code file and line number, analyzes
the root cause of the error, and synthesizes a concrete code-level fix.
"""
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class GitCodeAnalyzer:
    def __init__(self, repos_dir: Path = settings.REPOS_DIR):
        self.repos_dir = repos_dir
        self.app_mappings = settings.APP_REPO_MAPPINGS

    # -------------------------------------------------------------------------
    # 1. Stacktrace Detection & Parsing
    # -------------------------------------------------------------------------
    def parse_stacktrace(self, text: str) -> Optional[Dict]:
        """
        Extracts stacktrace frames, error type, and exception details from text.
        Supports Python, Java/Kotlin, JS/Node.js, and generic error formats.
        """
        if not text:
            return None

        # Clean text
        text_clean = text.replace("\r\n", "\n")

        # 1. Python traceback regex: File "...", line 12, in func
        py_frame_pattern = re.compile(
            r'File\s+["\']?(?P<file>[^"\'\n,]+)["\']?,\s*line\s+(?P<line>\d+)(?:,\s*in\s+(?P<func>\w+))?(?:\n\s*(?P<code>.+))?',
            re.IGNORECASE,
        )
        py_frames = []
        for match in py_frame_pattern.finditer(text_clean):
            py_frames.append({
                "file": match.group("file").strip(),
                "line": int(match.group("line")),
                "func": match.group("func") or "<module>",
                "code": (match.group("code") or "").strip(),
            })

        # Python exception message: e.g. KeyError: 'user' or ZeroDivisionError: division by zero
        py_err_pattern = re.compile(
            r'(?P<type>[A-Za-z]+Error|[A-Za-z]+Exception|UnhandledException):\s*(?P<msg>[^\n]+)',
            re.MULTILINE,
        )
        err_match = py_err_pattern.search(text_clean)
        error_type = err_match.group("type") if err_match else None
        error_msg = err_match.group("msg").strip() if err_match else None

        # 2. Java stacktrace regex: at com.package.Class.method(File.java:123)
        java_frame_pattern = re.compile(
            r'at\s+(?P<class>[\w\.$]+)\.(?P<method>\w+)\((?P<file>[\w\.\-]+):(?P<line>\d+)\)',
            re.IGNORECASE,
        )
        java_frames = []
        for match in java_frame_pattern.finditer(text_clean):
            java_frames.append({
                "file": match.group("file").strip(),
                "line": int(match.group("line")),
                "func": f"{match.group('class')}.{match.group('method')}",
                "code": "",
            })

        java_err_pattern = re.compile(
            r'(?P<type>java\.[\w\.]+|[\w]+Exception|[\w]+Error):\s*(?P<msg>[^\n]+)',
            re.MULTILINE,
        )
        java_err_match = java_err_pattern.search(text_clean)
        if not error_type and java_err_match:
            error_type = java_err_match.group("type").split(".")[-1]
            error_msg = java_err_match.group("msg").strip()

        # 3. JavaScript / Node / TypeScript traceback: at func (file.js:12:34) or at file.js:12:34
        js_frame_pattern = re.compile(
            r'at\s+(?:(?P<func>[\w\.$<>]+)\s+\()?(?P<file>[A-Za-z0-9_\-\/\.\\]+\.(?:js|ts|jsx|tsx|py)):(?P<line>\d+)(?::(?P<col>\d+))?\)?',
            re.IGNORECASE,
        )
        js_frames = []
        for match in js_frame_pattern.finditer(text_clean):
            js_frames.append({
                "file": match.group("file").strip(),
                "line": int(match.group("line")),
                "func": match.group("func") or "<anonymous>",
                "code": "",
            })

        # 4. Generic error pattern: e.g. file.py:45 or file.py line 45
        generic_pattern = re.compile(
            r'(?P<file>[A-Za-z0-9_\-\/\.\\]+\.(?:py|js|ts|java|go|cpp|c|cs)):(?P<line>\d+)',
            re.IGNORECASE,
        )
        generic_frames = []
        for match in generic_pattern.finditer(text_clean):
            generic_frames.append({
                "file": match.group("file").strip(),
                "line": int(match.group("line")),
                "func": "<unknown>",
                "code": "",
            })

        all_frames = py_frames or java_frames or js_frames or generic_frames

        if not all_frames and not error_type:
            return None

        # Innermost frame is usually the last one in Python tracebacks
        target_frame = all_frames[-1] if all_frames else None

        return {
            "error_type": error_type or "RuntimeError",
            "error_message": error_msg or "Unhandled runtime exception",
            "frames": all_frames,
            "target_frame": target_frame,
            "raw_stacktrace": text_clean,
        }

    # -------------------------------------------------------------------------
    # 2. Repository & File Resolution
    # -------------------------------------------------------------------------
    def resolve_application(self, app_name: Optional[str], text: str = "") -> Tuple[str, dict]:
        """Resolves application name and its repository metadata."""
        if app_name and app_name.strip():
            target_key = app_name.strip()
            # Exact match
            if target_key in self.app_mappings:
                return target_key, self.app_mappings[target_key]
            # Case-insensitive match
            for k, v in self.app_mappings.items():
                if k.lower() == target_key.lower():
                    return k, v

        # Infer from text if not explicitly provided
        text_lower = text.lower()
        for k, v in self.app_mappings.items():
            if k.lower() in text_lower or v.get("local_path", "").lower() in text_lower:
                return k, v

        # Default fallback application
        return "CoreService", {
            "name": app_name or "CoreService",
            "repo_url": "https://github.com/org/core-service.git",
            "local_path": app_name or "CoreService",
            "description": "General application codebase repository",
            "language": "Python",
        }

    def locate_source_file(self, app_meta: dict, file_hint: str) -> Optional[Path]:
        """Searches local repo directories or workspace for the referenced source file."""
        base_name = Path(file_hint).name
        local_dir_name = app_meta.get("local_path", "")

        candidates_dirs = [
            self.repos_dir / local_dir_name,
            self.repos_dir,
            settings.BASE_DIR,
        ]

        for c_dir in candidates_dirs:
            if not c_dir.exists():
                continue
            # Direct match
            direct = c_dir / file_hint
            if direct.is_file():
                return direct
            # Recursive filename match
            matches = list(c_dir.rglob(base_name))
            if matches:
                return matches[0]

        return None

    def read_code_context(
        self, file_path: Path, target_line: int, window: int = 6
    ) -> Tuple[Optional[str], Optional[str]]:
        """Reads surrounding lines of source code and highlights the target line."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if not lines:
                return None, None

            start = max(0, target_line - window - 1)
            end = min(len(lines), target_line + window)

            context_lines = []
            target_line_text = ""

            for i in range(start, end):
                curr_line_num = i + 1
                line_content = lines[i].rstrip("\n")
                if curr_line_num == target_line:
                    target_line_text = line_content.strip()
                    context_lines.append(f"-> {curr_line_num:4d} | {line_content}")
                else:
                    context_lines.append(f"   {curr_line_num:4d} | {line_content}")

            return "\n".join(context_lines), target_line_text
        except Exception as exc:
            logger.warning(f"Could not read code context from {file_path}: {exc}")
            return None, None

    # -------------------------------------------------------------------------
    # 3. Root Cause Diagnosis & Code Fix Synthesis
    # -------------------------------------------------------------------------
    def diagnose_and_suggest_fix(
        self,
        error_type: str,
        error_message: str,
        offending_line: str,
        code_context: str,
        filename: str,
        line_num: int,
    ) -> Tuple[str, str]:
        """
        Diagnoses root cause from AST patterns/heuristics and generates a code patch.
        """
        error_type_lower = (error_type or "").lower()

        # 1. KeyError
        if "keyerror" in error_type_lower:
            key_name = error_message.strip("'\"") if error_message else "key"
            root_cause = (
                f"A `KeyError: '{key_name}'` occurred at line {line_num} in `{filename}`. "
                f"The code attempted a direct dictionary subscript access `dict['{key_name}']` "
                f"without checking if the key exists or providing a fallback default value."
            )
            suggested_fix = (
                f"// Recommended Code Patch in {filename} (line {line_num}):\n"
                f"- # Offending code:\n"
                f"- {offending_line or f'val = data[\"{key_name}\"]'}\n"
                f"+ # Fixed with safe .get() guard:\n"
                f"+ val = data.get(\"{key_name}\")\n"
                f"+ if val is None:\n"
                f"+     logger.warning(\"Missing required key '{key_name}' in payload; using default\")\n"
                f"+     val = default_fallback_value"
            )
            return root_cause, suggested_fix

        # 2. ZeroDivisionError
        if "zerodivision" in error_type_lower or "division by zero" in (error_message or "").lower():
            root_cause = (
                f"A `ZeroDivisionError: division by zero` occurred at line {line_num} in `{filename}`. "
                f"The divisor variable evaluated to 0.0 or was uninitialized during calculation."
            )
            suggested_fix = (
                f"// Recommended Code Patch in {filename} (line {line_num}):\n"
                f"- # Offending code:\n"
                f"- {offending_line or 'result = numerator / rate'}\n"
                f"+ # Fixed with divisor guard check:\n"
                f"+ if rate == 0 or rate is None:\n"
                f"+     logger.error(\"Invalid exchange rate or divisor: 0. Defaulting to 1.0\")\n"
                f"+     rate = 1.0\n"
                f"+ result = numerator / rate"
            )
            return root_cause, suggested_fix

        # 3. IndexError
        if "indexerror" in error_type_lower or "out of range" in (error_message or "").lower():
            root_cause = (
                f"An `IndexError: list index out of range` occurred at line {line_num} in `{filename}`. "
                f"The code attempted to access an array/list index without verifying the sequence length."
            )
            suggested_fix = (
                f"// Recommended Code Patch in {filename} (line {line_num}):\n"
                f"- # Offending code:\n"
                f"- {offending_line or 'item = parts[1]'}\n"
                f"+ # Fixed with length boundary check:\n"
                f"+ if len(parts) > 1:\n"
                f"+     item = parts[1]\n"
                f"+ else:\n"
                f"+     raise InvalidPayloadError(\"Malformed header/input: insufficient elements\")"
            )
            return root_cause, suggested_fix

        # 4. TypeError / NullPointerException
        if "typeerror" in error_type_lower or "nullpointer" in error_type_lower or "nonetype" in (error_message or "").lower():
            root_cause = (
                f"A `{error_type}` occurred at line {line_num} in `{filename}`. "
                f"An operation was performed on a `None` (null) object reference or mismatched data type."
            )
            suggested_fix = (
                f"// Recommended Code Patch in {filename} (line {line_num}):\n"
                f"- # Offending code:\n"
                f"- {offending_line or 'val = obj.property'}\n"
                f"+ # Fixed with null-safety guard:\n"
                f"+ if obj is None:\n"
                f"+     logger.error(\"Object reference is None; aborting pipeline\")\n"
                f"+     return None\n"
                f"+ val = obj.property"
            )
            return root_cause, suggested_fix

        # 5. AttributeError
        if "attributeerror" in error_type_lower or "has no attribute" in (error_message or "").lower():
            root_cause = (
                f"An `AttributeError` occurred at line {line_num} in `{filename}`. "
                f"The object passed does not have the expected attribute or method."
            )
            suggested_fix = (
                f"// Recommended Code Patch in {filename} (line {line_num}):\n"
                f"- # Offending code:\n"
                f"- {offending_line or 'obj.execute()'}\n"
                f"+ # Fixed with hasattr validation:\n"
                f"+ if hasattr(obj, 'execute'):\n"
                f"+     obj.execute()\n"
                f"+ else:\n"
                f"+     logger.error(f'Unsupported object type: {{type(obj)}}')"
            )
            return root_cause, suggested_fix

        # Generic Fallback
        root_cause = (
            f"Runtime exception `{error_type}: {error_message}` identified at line {line_num} in `{filename}`. "
            f"Offending statement: `{offending_line or 'N/A'}`."
        )
        suggested_fix = (
            f"// Recommended Code Patch in {filename} (line {line_num}):\n"
            f"- {offending_line or 'execute_task()'}\n"
            f"+ try:\n"
            f"+     {offending_line or 'execute_task()'}\n"
            f"+ except {error_type} as exc:\n"
            f"+     logger.error(f\"Handled exception in {filename}: {{exc}}\")\n"
            f"+     # Apply recovery or safe fallback logic"
        )
        return root_cause, suggested_fix

    # -------------------------------------------------------------------------
    # 4. Main Analysis Workflow
    # -------------------------------------------------------------------------
    def analyze_ticket_code(
        self,
        application_name: Optional[str],
        title: str,
        description: str,
    ) -> Optional[Dict]:
        """
        Full Git & Stacktrace code inspection workflow.
        Returns detailed diagnosis if stacktrace/code error is detected.
        """
        combined_text = f"{title}\n{description}"
        st_data = self.parse_stacktrace(combined_text)

        if not st_data:
            return None

        app_name_resolved, app_meta = self.resolve_application(application_name, combined_text)
        target_frame = st_data.get("target_frame")

        filename = target_frame["file"] if target_frame else "app.py"
        line_num = target_frame["line"] if target_frame else 1
        func_name = target_frame["func"] if target_frame else "<module>"

        # Attempt to locate source file in Git repo
        source_file = self.locate_source_file(app_meta, filename)
        code_context = None
        offending_line = target_frame.get("code") or ""

        if source_file and source_file.exists():
            code_context, file_offending_line = self.read_code_context(source_file, line_num)
            if file_offending_line:
                offending_line = file_offending_line

        root_cause, suggested_fix = self.diagnose_and_suggest_fix(
            error_type=st_data["error_type"],
            error_message=st_data["error_message"],
            offending_line=offending_line,
            code_context=code_context or "",
            filename=filename,
            line_num=line_num,
        )

        return {
            "application_name": app_name_resolved,
            "repo_url": app_meta.get("repo_url"),
            "language": app_meta.get("language", "Python"),
            "stacktrace_detected": True,
            "error_type": st_data["error_type"],
            "error_message": st_data["error_message"],
            "file_path": filename,
            "line_number": line_num,
            "function_name": func_name,
            "offending_code": offending_line,
            "code_context": code_context,
            "root_cause": root_cause,
            "suggested_fix": suggested_fix,
        }
