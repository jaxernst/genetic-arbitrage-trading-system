def order_volume_sizer(owned_amount, book_prices, book_sizes, p_guess=None):
    convergence_tol = .001 # The tes_volume has to be within .5% of the real_volume
    # Check how levels we need to go over to cover the test_volume, then determine the average fill price
    if len(book_prices) != len(book_sizes):
        raise Exception("Book sizes and prices mmust be the same length")
    
    if not p_guess:
        p_guess = book_prices[0]

    test_volume = owned_amount / p_guess # How much ethereum to buy
    i = 0
    while sum(book_sizes[:i+1]) < test_volume:
        i += 1
        if i > len(book_sizes):
            raise Exception("Volume depth is not enough to cover required volume (You must be a damn whale)")

    remaining_volume = (test_volume - sum(book_sizes[:i]))
    fill_price = (sum([price*vol for price,vol in zip(book_prices[:i], book_sizes[:i])]) + remaining_volume*book_prices[i]) / (test_volume)
    real_volume = owned_amount / fill_price
    print('iter')
    # Check that the real volume can be covered by the same depth as the test volume
    if real_volume > sum(book_sizes[:i+1]):
        # Repeat this process until the correct deph is found
        return order_volume_sizer(owned_amount, book_prices, book_sizes, fill_price)
    elif abs((real_volume - test_volume)/test_volume) < .005:
        return fill_price
    else:
        return order_volume_sizer(owned_amount, book_prices, book_sizes, fill_price)

    

book_prices= [5000,5100,5200,5301.4,5533,5600, 6000,6100,6200,6301.4,6533,6600, 7000,7100,7200,7301.4,7533,8600]
book_volumes = [2,1,5,2,8,3,2,1,5,2,8,3,2,1,5,2,8,3]

real_fill = order_volume_sizer(58800, book_prices, book_volumes)
print(real_fill)