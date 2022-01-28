from util.obj_funcs import save_obj, load_obj

class RestartEngine(Exception):
    ''' Occurs when the arbitrage engine must restart to change the starting currency'''
    pass

class OrderTimeout(Exception):
    pass

class ConvergenceError(Exception):
    pass

class TradeFailed(Exception):
    pass

class TooManyRequests(Exception):
    ''' Raised when the API is request to rapidly'''
    pass

class SocketDisconnect(Exception):
    ''' Occurs when the websocket connection dies'''
    pass

class OrderVolumeDepthError(Exception):
    ''' Occurs when the book depth is not enough to cover the desired volume'''
    pass