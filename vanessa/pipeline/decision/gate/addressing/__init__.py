# Addressing helpers live in sibling modules. This package is not a barrel:
# importing ``addressing.bot_names`` must not load ``addressing.addressing``,
# which back-imports the intent detector.
