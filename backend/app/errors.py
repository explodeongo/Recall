class PermanentError(Exception):
    """A failure that retrying will not fix, such as a scanned PDF with no text layer.

    The message is shown to the user on the item, so write it for them.
    """
