---
name: proactive-research
description: Ensures all technical implementations are grounded in official documentation and verified against specifications. Use when starting any implementation task (plugins, core, etc.) to verify tool capabilities and best practices.
---

# Skill: Proactive Implementation Research & Verification

## Purpose
Ensure all technical implementations are grounded in official documentation and verified against the user's specification.

## Workflow (Mandatory for all implementation directives)

### 1. Initial Review
Read the provided specification thoroughly.

### 2. Search & Verify
- Perform a web search (using `google_web_search`) for the official documentation of the tools, APIs, or frameworks involved.
- Verify if the provided spec aligns with current best practices and tool capabilities.

### 3. Decision Matrix
- **If spec is unclear/missing details**: Adopt the best practice found in the documentation.
- **If spec is explicit but suboptimal**: Implement the spec as requested, but identify the better alternative found during research.

### 4. Execution & Reporting
- Implement the requested code.
- In the **Confirmation Report**, include a new section: `### Research & Deviations`.
    - Explicitly state if you followed the spec or implemented a better alternative.
    - Provide citations to the official documentation.
    - If you intentionally deviated from a spec recommendation, note why (e.g., "Performance improvement", "Security best practice").
