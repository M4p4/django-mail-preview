from __future__ import annotations

import django

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))


def inline_image(cid):
    """An inline PNG with a Content-ID, built the way each Django version documents it."""
    if django.VERSION >= (6, 0):
        from email.message import MIMEPart

        part = MIMEPart()
        part.set_content(
            PNG, maintype="image", subtype="png", disposition="inline", cid=f"<{cid}>"
        )
        return part
    from email.mime.image import MIMEImage

    image = MIMEImage(PNG, "png")
    image.add_header("Content-ID", f"<{cid}>")
    image.add_header("Content-Disposition", "inline")
    return image
