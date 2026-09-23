"""Launch Claude Code in a repo directory, primed with a task prompt.

Opens a new PowerShell console in the chosen repo. In paste mode the prompt
is placed on the Windows clipboard and a hidden helper waits for Claude Code
to start, refocuses the terminal, and sends Ctrl+V — so the prompt lands in
the input box and the user only presses Enter. In auto mode the prompt is
passed straight to the claude CLI and it starts working immediately.
"""

import os
import subprocess
import tempfile


def build_prompt(title, notes="", instructions=""):
    parts = [f"Task: {(title or '').strip()}"]
    if notes and notes.strip():
        parts.append("Task notes:\n" + notes.strip())
    if instructions and instructions.strip():
        parts.append("Instructions:\n" + instructions.strip())
    return "\n\n".join(parts)


def launch_claude_code(repo_path, prompt, auto_submit=False):
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        raise ValueError(f"Not a folder: {repo_path}")

    # The prompt goes into a temp file so no shell escaping is ever needed.
    work_dir = tempfile.mkdtemp(prefix="claude_task_")
    prompt_file = os.path.join(work_dir, "prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    helper_file = None
    if not auto_submit:
        helper_file = os.path.join(work_dir, "paste_helper.ps1")
        with open(helper_file, "w", encoding="utf-8-sig") as f:
            f.write(_PASTE_HELPER)

    script_file = os.path.join(work_dir, "launch_claude.ps1")
    with open(script_file, "w", encoding="utf-8-sig") as f:
        f.write(_build_script(repo_path, prompt_file, auto_submit, helper_file))

    subprocess.Popen(
        [
            "powershell",
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_file,
        ],
        cwd=repo_path,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _ps_quote(text):
    return "'" + text.replace("'", "''") + "'"


# Seconds the hidden helper waits for Claude Code to finish starting before
# it refocuses the terminal and sends Ctrl+V.
PASTE_DELAY_SECONDS = 5

# Captures the currently focused window (the terminal, at launch time), waits
# for Claude Code to start, brings that window back to front, and pastes.
_PASTE_HELPER = """param([int]$Delay = 5)
Add-Type -Namespace Win -Name Native -MemberDefinition @'
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@
$target = [Win.Native]::GetForegroundWindow()
Start-Sleep -Seconds $Delay
[Win.Native]::SetForegroundWindow($target) | Out-Null
Start-Sleep -Milliseconds 300
$shell = New-Object -ComObject WScript.Shell
$shell.SendKeys('^v')
"""


def _build_script(repo_path, prompt_file, auto_submit, helper_file=None):
    lines = [
        f"Set-Location -LiteralPath {_ps_quote(repo_path)}",
        f"$prompt = Get-Content -Raw -LiteralPath {_ps_quote(prompt_file)}",
        "if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {",
        "    Write-Host 'Could not find the claude command on PATH.' -ForegroundColor Red",
        "    Write-Host 'Install Claude Code (https://claude.com/claude-code) and try again.'",
        "    return",
        "}",
    ]
    if auto_submit:
        lines += [
            "Write-Host 'Starting Claude Code with the task...' -ForegroundColor Green",
            "claude $prompt",
        ]
    else:
        lines += [
            "Set-Clipboard -Value $prompt",
            "Write-Host 'The task prompt will be pasted automatically in a few "
            "seconds - just press Enter.' -ForegroundColor Green",
            "Write-Host '(It is also on the clipboard: Ctrl+V if it does not "
            "appear.)' -ForegroundColor DarkGray",
            "Start-Process powershell -WindowStyle Hidden -ArgumentList "
            "'-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "
            f"{_ps_quote(chr(34) + helper_file + chr(34))}, "
            f"'-Delay', '{PASTE_DELAY_SECONDS}'",
            "claude",
        ]
    return "\n".join(lines) + "\n"
