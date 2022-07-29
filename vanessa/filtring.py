def message_filtering(msg: str):
    """filters the message from the values specified in filterable_text"""
    filterable_text = {
        'ванесса'
        'ванесса,'
        '[club212138773|@vanessakapustovna]'
        '[club212138773|@vanessakapustovna],'
    }
    msg = msg.lower().split(' ')
    for word in msg:
        if word in filterable_text:
            msg.remove(word)
    return ' '.join(msg)
