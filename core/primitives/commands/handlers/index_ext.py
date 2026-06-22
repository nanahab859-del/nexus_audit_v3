from core.primitives.commands.context import OPERATOR
from core.infra.audit_index import rebuild_index
import logging

logger = logging.getLogger(__name__)

def register(registry) -> None:
    from core.primitives.commands.registry import Command

    registry.register(Command(
        name="audit:rebuild-index",
        description="Rebuild the SQLite audit index from all job summaries.",
        usage="audit:rebuild-index",
        handler=_handle_rebuild_index,
        required_privilege=OPERATOR,
    ))

async def _handle_rebuild_index(ctx, params):
    ctx.write("Rebuilding global audit index...")
    try:
        result = await rebuild_index()
        runs = result.get("runs_indexed", 0)
        ctx.write(f"Index rebuilt: {runs} run(s) indexed across all projects.")
    except Exception as e:
        logger.exception("Failed to rebuild index")
        ctx.write_error(f"Failed to rebuild index: {e}")
