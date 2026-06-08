# Purpose:
# - Nuke / Python 2.7 helpers: choose x/y for a new node on the root graph so it does not sit on the exact
#   same tile as an existing node. Runners use this when spawning Read nodes below a Group so repeated
#   executions stack diagonally instead of piling on identical coordinates.

_DEFAULT_STEP_X = 40
_DEFAULT_STEP_Y = -30  # Nuke y increases downward; negative step moves visually up.
_DEFAULT_MAX_ATTEMPTS = 500


def _is_excluded(node, exclude_nodes):
    if not exclude_nodes:
        return False
    for e in exclude_nodes:
        if e is node:
            return True
    return False


def node_tile_occupied(nuke_module, x, y, exclude_nodes=None):
    """
    True if some node in the current Node graph context shares this integer tile (xpos, ypos).
    Call while nuke.root().begin() is active so only root-level nodes are considered.
    """
    xi = int(x)
    yi = int(y)
    for n in nuke_module.allNodes():
        if _is_excluded(n, exclude_nodes):
            continue
        try:
            if int(n.xpos()) == xi and int(n.ypos()) == yi:
                return True
        except Exception:
            continue
    return False


def resolve_spawn_xy(
    nuke_module,
    base_x,
    base_y,
    exclude_nodes=None,
    step_x=_DEFAULT_STEP_X,
    step_y=_DEFAULT_STEP_Y,
    max_attempts=_DEFAULT_MAX_ATTEMPTS,
):
    """
    Starting from (base_x, base_y), nudge by (step_x, step_y) until tile is free.
    Returns (x, y) integers. exclude_nodes: nodes not treated as blocking (e.g. siblings in the same batch).
    """
    x = int(base_x)
    y = int(base_y)
    sx = int(step_x)
    sy = int(step_y)
    for _ in range(int(max_attempts)):
        if not node_tile_occupied(nuke_module, x, y, exclude_nodes=exclude_nodes):
            return x, y
        x += sx
        y += sy
    return x, y
