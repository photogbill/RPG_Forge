"""Night 4 plug-in job types: tileable (CPU, F7), icon_batch (GPU, F4), photo_plate (GPU, F6). Lazy handler imports."""
from __future__ import annotations
from forge.night4 import specs as _specs

DEPENDS = ("forge.night4.specs", "forge.night4.tileable", "forge.night4.icons", "forge.night4.photo")


def tileable(job, ctx, out):
    from forge.night4 import tileable as t
    return t.run(job, ctx, out)


def icon_batch(job, ctx, out):
    from forge.night4 import icons
    return icons.run(job, ctx, out)


def photo_plate(job, ctx, out):
    from forge.night4 import photo
    return photo.run(job, ctx, out)


JOB_TYPES = {"tileable": _specs.TILEABLE, "icon_batch": _specs.ICON_BATCH, "photo_plate": _specs.PHOTO_PLATE}
HANDLERS = {"tileable": tileable, "icon_batch": icon_batch, "photo_plate": photo_plate}
