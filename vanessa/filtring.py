filterable_text = {
    'ванесса'
    'ванесса,'
    '[club212138773|@vanessakapustovna]'
    '[club212138773|@vanessakapustovna],'
}


def message_filtering(msg):
    msg = msg.lower().split(' ')
    for word in msg:
        if word in filterable_text:
            msg.remove(word)
    return ' '.join(msg)
