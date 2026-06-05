from collections import defaultdict
from typing import Any
from core.dna_builder import ProjectDNA
from core.models import Finding, finding_to_dict

def generate_coupling_matrix(dna: ProjectDNA, boundary_findings: list[Finding]) -> dict[str, Any]:
    """
    Generates an NxN matrix of cross-app couplings and violations.
    
    Returns:
    {
        "apps": ["app1", "app2", ...],
        "matrix": [
            [ {"imports": 0, "violations": 0}, {"imports": 5, "violations": 2}, ... ],
            [ ... ],
            ...
        ],
        "violations": [...] # drill-down data
    }
    """
    apps = sorted(dna.apps)
    app_index = {app: i for i, app in enumerate(apps)}
    n = len(apps)
    
    # Initialize matrix
    matrix = [[{"imports": 0, "violations": 0} for _ in range(n)] for _ in range(n)]
    
    # Count cross-app imports
    for mod in dna.modules.values():
        source_app = mod.app
        if source_app not in app_index:
            continue
            
        for imp in mod.imports:
            # We assume imp is an absolute dotted path, e.g. "target_app.models.user"
            target_app = imp.split(".")[0]
            if target_app in app_index and target_app != source_app:
                matrix[app_index[source_app]][app_index[target_app]]["imports"] += 1
                
    # Count violations
    for finding in boundary_findings:
        # We need to extract source and target app from the finding.
        # Boundary findings should ideally contain this in metadata, 
        # but for now we can infer from file path or description.
        source_app = finding.file.split("/")[0] if "/" in finding.file else finding.file.split("\\")[0]
        
        # Try to infer target app from description: "App 'X' directly imports from 'Y'"
        # or from some metadata. If not, we just count it against source_app broadly.
        # Here we do a simple check.
        target_app = None
        for app in apps:
            if app != source_app and f"'{app}'" in finding.description:
                target_app = app
                break
                
        if source_app in app_index and target_app in app_index:
            matrix[app_index[source_app]][app_index[target_app]]["violations"] += 1
            
    return {
        "apps": apps,
        "matrix": matrix,
        "violations": [finding_to_dict(f) for f in boundary_findings]
    }
