# ChatGPT Prompts for VS Code
## Start / resume
Act as the engineering orchestrator. Read AGENTS.md, MASTER_ORCHESTRATOR.md, PLAN.md, PROGRESS.md and the active phase file. First summarize current state and give a small execution plan. Implement ONLY the current phase. Execute the required tests and report real outputs. Update PROGRESS.md only when acceptance criteria are verified. Stop and ask before proceeding.

## Review
Review changes against the active phase's acceptance criteria. Look for leakage, incorrect evaluation, unsafe file operations, missing tests and Apple Silicon compatibility. List findings by severity with file paths. Do not modify code unless asked.

## Next phase
Read PROGRESS.md and verify the previous phase's tests. If complete, read the next phase document, outline the work and begin only that phase.
