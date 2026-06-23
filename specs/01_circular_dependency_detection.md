# Feature 01: Circular Dependency Detection
## Implementation Specification

**Branch:** `feature/f01-cycle-detection-grimp`
**Status:** Specification — ready for implementation
**Priority:** High (Phase 1 — makes the audit trustworthy)

---

## 1. What This Feature Does

Detects when two or more Python modules import each other in a circle — A imports B, B imports A, or longer chains. This is a real architectural problem in Django projects: circular imports cause `ImportError` at startup, create hidden coupling that makes refactoring extremely difficult, and indicate that module boundaries have not been thought through properly.

The output is a list of violations, one per cycle found, each showing the full import chain so the developer knows exactly which files are involved.

---

## 2. Why the Current Implementation Must Be Replaced (Not Patched)

There are two separate problems in v3 today. Both must be fixed. Patching one and leaving the other is not an option — they compound each other.

### Problem A: Recursive DFS in `rules_engine.py::_evaluate_cycle`

The current implementation (lines 270–315 of `rules_engine.py`) builds an adjacency graph from `ProjectDNA.modules` and walks it with a recursive inner function `dfs(node, stack)` that calls itself on each unvisited neighbour:

```python
def dfs(node: str, stack: list[str]) -> None:
    visited.add(node)
    in_stack.add(node)
    stack.append(node)
    for neighbour in graph.get(node, []):
        if neighbour not in visited:
            dfs(neighbour, stack)   # <-- recursive call
```

Python has a default recursion limit of 1,000 frames. On any project where DFS walks a path deeper than ~1,000 modules before backtracking — not necessarily a 1,000-module cycle, just a long chain of unrelated imports — this raises `RecursionError` and crashes the entire rules evaluation step, silently dropping all rule findings for that run. The legacy tool hit this exact problem on the Nexus codebase and explicitly rewrote the function to be iterative. v3 reintroduced it.

This is not a hypothetical. It has already happened once on this codebase.

### Problem B: `_parse_python_imports` in `dna_builder.py` does not exclude `TYPE_CHECKING` imports

The current import parser uses `ast.walk(tree)` which visits every node in the AST unconditionally, including imports inside `if TYPE_CHECKING:` blocks:

```python
# This import is type-hint-only — it creates NO runtime dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nexus_economy.models import Wallet
```

At runtime, `TYPE_CHECKING` is always `False`, so this import never executes. It exists purely to let type checkers (mypy, pyright) understand the code. There is no actual coupling at runtime. But `dna_builder.py` currently counts it as a real import — which means `_evaluate_cycle` can detect "cycles" that do not actually exist at runtime, and `boundary_engine.py` can flag "violations" for import relationships that never actually happen. Both are false positives.

On a Django codebase that uses type hints for cross-model relationships (which Nexus does), this means every type-annotated cross-app model reference is currently showing up as an architecture violation, when it is not one.

### Problem C: No `cycle` rule in `default_rules.yaml`

Even if both A and B were fixed, the cycle detector would still never run. `rules_engine.py` only evaluates a cycle rule if a rule of `type: cycle` appears in the loaded rules. `default_rules.yaml` currently contains two rules (`no-eval` and `ghost-file`), neither of which is a cycle rule. The detector is inert regardless of its internal correctness.

---

## 3. The Permanent Solution: grimp

### What grimp is

`grimp` is a Python library purpose-built for one thing: constructing a queryable graph of the imports within one or more Python packages. It is:
- BSD-2-Clause licensed
- Actively maintained (latest release: 2025, changelog shows consistent monthly updates)
- Available as a pre-built `cp310` wheel (matching v3's actual Python 3.10.12 interpreter in `.venv`)
- The graph engine that powers `import-linter` (a widely used architectural linting tool), meaning its import-parsing logic has been tested against a very large number of real-world Python codebases

grimp builds its graph by reading real files from disk, parsing Python AST correctly, and resolving import references into module paths. It handles all the cases the current hand-rolled parser struggles with:
- Relative imports (`from . import x`, `from .. import y`) — correctly resolved against the file's position in the package
- `TYPE_CHECKING`-guarded imports — excluded via `exclude_type_checking_imports=True` (one parameter)
- Wildcard imports — tracked separately
- `__init__.py` package-level imports — handled as part of package graph

The key API surface we use:

```python
import grimp

# Build the graph for one or more root packages
graph = grimp.build_graph(
    "nexus_core", "nexus_economy", "nexus_gaming", "nexus_gateway",
    exclude_type_checking_imports=True,
)

# Get all modules in a package and its subpackages
modules = graph.find_descendants("nexus_core") | {"nexus_core"}

# Get every module this module imports directly
imported_by_this = graph.find_modules_directly_imported_by("nexus_economy.views")

# Get exact line number and line content for each import edge
details = graph.get_import_details(
    importer="nexus_economy.views",
    imported="nexus_gaming.leaderboard"
)
# Returns: [{"importer": ..., "imported": ..., "line_number": 3, "line_contents": "from nexus_gaming..."}]
```

### Why not the simpler fix (keep hand-rolled parser, fix only the algorithm)

The simpler fix — convert `dfs()` to iterative, leave `_parse_python_imports` alone — would fix Problem A but leave Problems B and C. More importantly, it would mean doing this work twice: once now to fix the algorithm, then again later when the `TYPE_CHECKING` false positives are finally addressed and the import parser needs to be replaced anyway. The permanent solution costs only slightly more effort now and eliminates both root causes together.

### Why not use the existing tree-sitter dependency

v3 already depends on `tree-sitter` with Python, JavaScript, and Go grammars. Building import-graph construction on tree-sitter would avoid a new dependency. It was seriously considered and rejected for this reason: tree-sitter produces a concrete syntax tree. Turning that into a queryable import graph — with transitive closure queries, shortest-chain reporting, exact line/content per edge, and correct relative-import resolution — means building and maintaining the graph abstraction layer by hand. That is approximately what `grimp` already provides, tested. Adding grimp costs less long-term than maintaining the equivalent graph layer on top of raw tree-sitter output.

---

## 4. Scope of Changes

Four files change. Nothing else.

| File | What changes |
|---|---|
| `pyproject.toml` | Add `grimp` to `dependencies` |
| `core/engines/dna_builder.py` | Replace `_parse_python_imports` with grimp-backed import discovery for Python files only |
| `core/engines/rules_engine.py` | Replace recursive `dfs()` in `_evaluate_cycle` with iterative Tarjan's SCC |
| `default_rules.yaml` | Add one `cycle`-type rule entry to activate the detector |

Files that do **not** change:
- `core/engines/boundary_engine.py` — unchanged, already correctly designed
- `core/engines/scoring_engine.py` — unchanged, reads `ModuleEntry.imports` which stays the same shape
- `core/engines/coupling.py` — unchanged, same reason
- `core/engines/timeline.py` — unchanged
- `plugins/` — unchanged
- `frontend/` — unchanged
- `api/` — unchanged
- `_parse_js_imports` inside `dna_builder.py` — unchanged (grimp is Python-only)

---

## 5. Detailed Implementation

### 5.1 `pyproject.toml`

Add `grimp` to the `dependencies` list:

```toml
[project]
dependencies = ["click", "prompt-toolkit", "grimp"]
```

Note: `pyproject.toml`'s `dependencies` list is currently incomplete relative to what is actually installed in `.venv` (it lists only `click` and `prompt-toolkit`, while `.venv` contains ~100 packages including `aiohttp`, `bandit`, `semgrep`, etc.). That is a pre-existing inconsistency unrelated to this work. This change adds only `grimp` — it does not attempt to reconcile the rest of the list.

---

### 5.2 `core/engines/dna_builder.py`

#### What changes

The `_parse_python_imports(source, module_path)` function is replaced. Instead of being called file-by-file inside the `for f in files:` loop, import discovery for Python files is handled by a single `grimp.build_graph()` call that processes the entire project at once, then per-module edges are looked up from the resulting graph.

The call must happen **after** the file-discovery loop determines which root packages exist in the project, and **before** the per-module `ModuleEntry` objects are constructed — because `ModuleEntry.imports` is populated from the grimp graph.

#### What does not change

- `_parse_js_imports` — untouched. grimp is Python-only.
- `_count_loc` — untouched.
- App assignment logic — untouched.
- `defined_names` extraction (AST walk for function/class defs) — untouched. grimp does not provide this.
- `has_wildcard_imports` detection — untouched (the existing AST check is correct for this specific purpose; grimp tracks wildcards separately and we do not need to replace this).
- `ModuleEntry` field shape — untouched. `imports: dict[str, int]` stays exactly the same.
- `build_dna` function signature — untouched.
- `EventBus` progress publishing — untouched.

#### The `ModuleEntry.imports` contract

This is what everything downstream reads. It must not change shape:

```python
# Current contract — must stay identical
imports: dict[str, int]   # {imported_module_path: line_number}
```

grimp's `get_import_details` returns the line number for each import edge, so this contract is satisfied.

#### Error handling: `SourceSyntaxError`

grimp raises `grimp.exceptions.SourceSyntaxError` on files it cannot parse (instead of the current `except SyntaxError: return {}` approach). This must be caught at the `build_graph()` call. When it fires, the affected module's `parse_status` should be set to `"error"` and a warning logged, matching the graceful-degradation philosophy already present elsewhere in `build_dna`. The rest of the project continues to be analyzed — one bad file must not abort the whole DNA build.

#### Django `migrations` packages

grimp's current version analyzes `migrations/` packages like any other package (a previous version special-cased them; that was removed). Django migration files contain auto-generated import chains that are not architectural decisions and would produce noise. Exclude them explicitly by filtering out any module path containing `.migrations.` before constructing `ModuleEntry` objects.

#### Determining root packages for `grimp.build_graph()`

grimp's `build_graph()` requires the names of the root packages to analyze. These are derived from `app_mappings` if provided, otherwise from the top-level directory names discovered in the file-discovery step — the same logic already used for app assignment in the current code.

#### Pseudocode (implementation guide, not final code)

```python
# After file discovery, before building ModuleEntry objects:

# 1. Determine root packages
root_packages = _derive_root_packages(project_root, files, app_mappings)

# 2. Build grimp graph (once, for all Python files)
grimp_graph = None
try:
    import grimp
    grimp_graph = grimp.build_graph(
        *root_packages,
        exclude_type_checking_imports=True,
    )
except grimp.exceptions.SourceSyntaxError as e:
    logger.warning("grimp: syntax error in source, partial graph: %s", e)
except Exception as e:
    logger.warning("grimp: graph build failed, falling back to AST: %s", e)
    grimp_graph = None   # fallback to existing _parse_python_imports

# 3. Per file, get imports:
if lang == "python":
    if grimp_graph is not None and module_path in grimp_graph.modules:
        imports = _imports_from_grimp(grimp_graph, module_path)
    else:
        imports = _parse_python_imports(source, module_path)  # fallback

def _imports_from_grimp(graph, module_path: str) -> dict[str, int]:
    imports = {}
    for target in graph.find_modules_directly_imported_by(module_path):
        details = graph.get_import_details(importer=module_path, imported=target)
        if details:
            imports[target] = details[0]["line_number"]
    return imports
```

Note the fallback: if grimp fails for any reason (unexpected error, missing wheel, etc.), `_parse_python_imports` is still present and used as a fallback. grimp is the primary path; the AST parser is the safety net. This means the feature degrades gracefully rather than breaking the whole tool if something goes wrong with grimp.

---

### 5.3 `core/engines/rules_engine.py` — `_evaluate_cycle`

#### The algorithm: Iterative Tarjan's SCC

Tarjan's Strongly Connected Components algorithm finds all SCCs in a directed graph in a single pass, in O(V+E) time. Any SCC containing more than one node is a cycle. This is the correct algorithm for this problem.

The critical implementation requirement: **it must be iterative, not recursive**. A recursive Tarjan's has the exact same stack-depth ceiling as the current recursive DFS. The algorithm choice and the recursion-safety are separate concerns. Only an iterative implementation — using an explicit work stack instead of the Python call stack — is safe on graphs of unbounded depth.

The iterative pattern replaces the recursive `strongconnect()` inner function with a `work_stack` of `(node, iterator_over_successors)` tuples. Each iteration of the outer loop either pushes a new node (when an unvisited successor is found) or pops the current node and performs the SCC-root check (when all successors have been visited). This is the standard technique for converting any recursive DFS to iterative, applied to Tarjan's specifically.

#### Django `models` self-cycle suppression

Django projects commonly have modules inside an app that import from the same app's `models.py` file, which in turn imports from the same app. These are intra-app imports that happen to form a technical cycle due to how Django's ORM loads models. They are not architectural violations and flagging them produces noise. Any SCC whose member modules all belong to the same app AND whose member module paths all contain `models` should be classified as severity `INFO` rather than the rule's configured severity, and should include a note in the description explaining why it is informational. The finding is still emitted — just at a lower severity — so it is visible but not treated as a violation.

#### Finding output

The finding for each cycle should include:
- The full import chain as a string: `moduleA → moduleB → moduleA`
- The file path of the first module in the cycle (as the "location" of the finding)
- Line number 1 (cycles are a graph-level property, not tied to a specific line; line 1 is the conventional placeholder)
- Severity and category from the rule definition, except for the Django-models suppression case above

#### Pseudocode (implementation guide, not final code)

```python
def _evaluate_cycle(self, rule: RuleDefinition, dna: ProjectDNA) -> List[Finding]:
    # Build adjacency from ProjectDNA — same as current, this part is correct
    graph: dict[str, set] = {mp: set() for mp in dna.modules}
    for mp, mod in dna.modules.items():
        for imp in mod.imports:
            if imp in dna.modules:
                graph[mp].add(imp)

    # Iterative Tarjan's SCC
    index_counter = [0]
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    tarjan_stack: list[str] = []
    work_stack: list[tuple[str, Iterator]] = []
    sccs: list[list[str]] = []

    for start in dna.modules:
        if start in index:
            continue

        index[start] = lowlink[start] = index_counter[0]
        index_counter[0] += 1
        tarjan_stack.append(start)
        on_stack[start] = True
        work_stack.append((start, iter(graph.get(start, []))))

        while work_stack:
            node, it = work_stack[-1]
            pushed = False

            for successor in it:
                if successor not in index:
                    index[successor] = lowlink[successor] = index_counter[0]
                    index_counter[0] += 1
                    tarjan_stack.append(successor)
                    on_stack[successor] = True
                    work_stack.append((successor, iter(graph.get(successor, []))))
                    pushed = True
                    break
                elif on_stack.get(successor):
                    lowlink[node] = min(lowlink[node], index[successor])

            if pushed:
                continue

            # All successors visited — pop and check SCC root
            work_stack.pop()
            if work_stack:
                parent = work_stack[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

            if lowlink[node] == index[node]:
                scc: list[str] = []
                while True:
                    w = tarjan_stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == node:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

    # Convert SCCs to findings
    findings: list[Finding] = []
    for scc in sccs:
        scc_sorted = sorted(scc)

        # Django-models self-cycle suppression
        apps_in_scc = {dna.modules[m].app for m in scc if m in dna.modules}
        is_intra_app_models = (
            len(apps_in_scc) == 1
            and all("models" in m for m in scc)
        )

        chain = " → ".join(scc_sorted + [scc_sorted[0]])
        first_mod = dna.modules.get(scc_sorted[0])
        severity = "INFO" if is_intra_app_models else rule.severity
        description = (
            f"Import cycle detected: {chain}"
            + (" (intra-app models pattern — informational)" if is_intra_app_models else "")
        )

        findings.append(create_finding(
            scanner="rules_engine",
            rule_id=rule.id,
            file=first_mod.relative_path if first_mod else scc_sorted[0],
            line=1, column=1,
            severity=severity,
            category=rule.category,
            title=rule.name,
            description=description,
            suggestion=rule.suggestion or "Break the cycle by extracting shared logic into a new module.",
        ))

    return findings
```

---

### 5.4 `default_rules.yaml`

Add a `cycle`-type rule. Without this, the detector never runs regardless of how correct the implementation is.

```yaml
rules:
  - id: no-eval
    name: "Use of eval()"
    type: pattern
    severity: HIGH
    category: security
    languages: ["python"]
    description: "The eval() function can execute arbitrary code"
    suggestion: "Replace eval() with a safer alternative"
    config:
      pattern: "(call function: (identifier) @func (#eq? @func \"eval\"))"

  - id: ghost-file
    name: "Ghost File"
    type: ghost
    severity: LOW
    category: quality
    languages: ["*"]
    description: "File is never imported by any other module"
    suggestion: "Remove the file or integrate it into the codebase"

  - id: import-cycle
    name: "Circular Import"
    type: cycle
    severity: HIGH
    category: architecture
    languages: ["python"]
    description: "Two or more modules import each other in a cycle, creating tight coupling and potential import errors"
    suggestion: "Extract the shared dependency into a new module that neither participant imports from"
```

---

## 6. Testing Requirements

All tests go in the `tests/` tree of the worktree, following v3's existing conventions. No test files exist in the main repo until merge.

### 6.1 `tests/engines/test_dna_builder.py` — new cases

The existing file already uses `tmp_path` to write real Python files to disk and call `build_dna()`. New cases to add:

- **`test_type_checking_import_excluded`** — write a file containing `if TYPE_CHECKING: from other_app.models import X`, build DNA, assert `other_app.models` is NOT in that module's `imports`. This is the core regression test for Problem B.
- **`test_regular_import_included`** — write a file with a normal `from other_app.models import X`, assert it IS in `imports`.
- **`test_relative_import_resolved`** (currently empty stub) — write two files in the same package, one importing from the other with `from . import sibling`, assert the resolved path is in `imports`.
- **`test_alias_discarded`** (currently empty stub) — write `import nexus_core.models as m`, assert `nexus_core.models` is in `imports` (the alias `m` is not what we track — we track the source module path).
- **`test_syntax_error_degrades_gracefully`** — write a file containing invalid Python syntax, build DNA, assert the build completes (no exception raised), and the bad file's module entry has `parse_status == "error"`.
- **`test_migrations_excluded`** — write a file at `some_app/migrations/0001_initial.py`, build DNA, assert no module entry exists for it.

### 6.2 `tests/engines/test_rules_engine.py` — new cases

- **`test_cycle_detected`** — build a `ProjectDNA` fixture with two modules that import each other. Load the `import-cycle` rule. Assert one finding is returned with `rule_id == "import-cycle"` and the cycle chain in the description.
- **`test_no_false_positive_on_clean_graph`** — build a `ProjectDNA` fixture with no cycles. Assert zero findings.
- **`test_deep_chain_no_recursion_error`** — build a `ProjectDNA` fixture with a linear chain of 2,000 modules (A imports B imports C... imports Z). Assert the cycle detector completes without raising `RecursionError` and returns zero findings (no cycle).
- **`test_long_cycle_no_recursion_error`** — build a `ProjectDNA` fixture with a single cycle 2,000 modules long. Assert the cycle detector completes without raising `RecursionError` and returns exactly one finding.
- **`test_django_models_cycle_is_informational`** — build a `ProjectDNA` fixture where two modules both named `*.models` in the same app import each other. Assert the finding has `severity == "INFO"`.
- **`test_cycle_rule_not_in_yaml_means_no_findings`** — confirm that if `default_rules.yaml` has no `cycle` rule, `_evaluate_cycle` is never called (existing behavior, guard against regression).

---

## 7. Verification Checklist

When implementation is complete, verify each item before marking this feature done:

- [ ] `pip show grimp` in the `.venv` confirms it is installed
- [ ] `python -c "import grimp; print(grimp.__version__)"` works without error
- [ ] `build_dna()` completes successfully on the real Nexus project root
- [ ] A file containing `if TYPE_CHECKING:` imports does NOT show those imports in the resulting DNA
- [ ] A file containing normal imports DOES show those imports
- [ ] Running the audit against Nexus produces cycle findings (real cycles exist in the codebase, per legacy tool history)
- [ ] No `RecursionError` is raised during cycle evaluation on the real Nexus codebase
- [ ] All six new `test_dna_builder.py` test cases pass
- [ ] All six new `test_rules_engine.py` test cases pass
- [ ] Full existing test suite still passes (no regressions: `pytest tests/`)

---

## 8. Merge Condition

This branch (`feature/f01-cycle-detection-grimp`) is ready to merge into `feature/legacy-feature-integration` when:
1. All items in §7 are checked off
2. `git diff feature/legacy-feature-integration...feature/f01-cycle-detection-grimp -- tests/` shows only new test files (no modifications to existing tests)
3. `git diff feature/legacy-feature-integration...feature/f01-cycle-detection-grimp -- core/ plugins/ api/ frontend/` shows only the four files listed in §4

After merge into `feature/legacy-feature-integration`, that branch is ready to merge into `main` for this feature.
