#!/usr/bin/env python3
"""Quick diagnostic test to verify all components connect properly."""

import asyncio
import sys
from pathlib import Path

async def run_diagnostics():
    """Test if all components import and connect correctly."""
    print("=" * 60)
    print("NEXUS AUDIT V3 - DIAGNOSTIC TEST")
    print("=" * 60)
    
    # Test 1: Import all core modules
    print("\n[1/6] Importing core modules...")
    try:
        from core.dna_builder import build_dna, ProjectDNA
        from core.rules_engine import RulesEngine
        from core.boundary_engine import BoundaryEngine
        from core.scoring_engine import ScoringEngine
        from core.fix_queue import FixQueue
        from core.timeline import load_score_history, compute_violation_persistence
        from core.git_context import get_git_context
        from core.coupling import generate_coupling_matrix
        from core.models import Finding, Severity, Category, Settings
        from core.events import bus
        from core.atomic import read_json, write_json
        from ai.prompts import build_system_prompt
        print("✅ All core modules imported successfully")
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Test 2: Check if orchestrator connects properly
    print("\n[2/6] Checking orchestrator...")
    try:
        from orchestrator import Orchestrator
        orc = Orchestrator()
        print(f"✅ Orchestrator instantiated, status: {orc.status()}")
    except Exception as e:
        print(f"❌ Orchestrator error: {e}")
        return False
    
    # Test 3: Check if API routes are wired
    print("\n[3/6] Checking API routes...")
    try:
        from api.routes_data import get_status, get_data
        from api.routes_run import post_run, post_cancel
        from api.routes_rules import get_rules, post_rules_validate
        from api.routes_fixqueue import get_fixqueue, post_fixqueue
        from api.routes_trends import get_trends
        from api.routes_report import get_report_markdown
        from api.server import create_app
        print("✅ All API routes imported")
        
        # Try creating app
        app = create_app(orc)
        print("✅ App created successfully")
    except Exception as e:
        print(f"❌ API routes error: {e}")
        return False
    
    # Test 4: Check if default rules exist and load
    print("\n[4/6] Checking default rules...")
    try:
        rules_file = Path("default_rules.yaml")
        if not rules_file.exists():
            print(f"❌ default_rules.yaml not found at {rules_file.absolute()}")
            return False
        
        engine = RulesEngine(rules_file)
        rules = engine.load()
        errors = engine.validate()
        
        if errors:
            print(f"⚠️  Rules validation errors:")
            for err in errors:
                print(f"   - {err}")
        else:
            print(f"✅ Default rules valid ({len(rules)} rules loaded)")
    except Exception as e:
        print(f"❌ Rules error: {e}")
        return False
    
    # Test 5: Check if settings.json exists
    print("\n[5/6] Checking settings...")
    try:
        settings_file = Path("settings.json")
        if not settings_file.exists():
            print(f"⚠️  settings.json not found (this is OK if it's created on first run)")
        else:
            settings = read_json(settings_file)
            if settings:
                print(f"✅ Settings loaded: project_path={settings.get('project_path', 'N/A')}")
    except Exception as e:
        print(f"❌ Settings error: {e}")
        return False
    
    # Test 6: Check frontend files
    print("\n[6/6] Checking frontend files...")
    try:
        frontend_dir = Path("frontend")
        index_html = frontend_dir / "index.html"
        css_dir = frontend_dir / "css"
        js_dir = frontend_dir / "js"
        
        if not index_html.exists():
            print(f"❌ frontend/index.html not found")
            return False
        if not (css_dir / "variables.css").exists():
            print(f"❌ frontend/css/variables.css not found")
            return False
        if not (js_dir / "main.js").exists():
            print(f"❌ frontend/js/main.js not found")
            return False
            
        print(f"✅ All frontend files present")
    except Exception as e:
        print(f"❌ Frontend error: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ ALL DIAGNOSTICS PASSED - System ready for audit")
    print("=" * 60)
    return True

if __name__ == "__main__":
    result = asyncio.run(run_diagnostics())
    sys.exit(0 if result else 1)
