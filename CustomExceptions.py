from util.obj_funcs import save_obj, load_obj

class TooManyRequests(Exception):
    ''' Raised when the API is request to rapidly'''
    pass

class OrderVolumeDepthError(Exception):
    ''' Occurs when the book depth is not enough to cover the desired volume'''
    def __init__(self, coin_name, ExchangeData):
        L = load_obj("banned_coins")
        L.append(coin_name)
        save_obj(L, "banned_coins")
        print("\n Order Volume deph not sufficient")
        print(f"Banning {coin_name} \n")

        keys = ExchangeData.Pairs.keys()
        for pair in keys:
            if coin_name in pair:
                del ExchangeData.Pairs[pair]

