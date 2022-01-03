def remove_single_swapabble_coins(pairList) -> list:
    # Remove singled swappable currencies
    alts, qoutes = zip(*pairList)
    remove = []
    for top, bottom in pairList:
        # check if the top has only one occurance in the alts
        if alts.count(top) == 1:
            # Check if any more occurances exist in the qoutes
            if not qoutes.count(top):
                remove.append(top)
        # check that the bottom has only occurance in the qoutes
        if qoutes.count(bottom) == 1:
            # Check if any more occurances exist in the alts
            if not alts.count(bottom):
                remove.append(bottom)

    return [pair for pair in pairList if pair[0] not in remove and pair[1] not in remove]