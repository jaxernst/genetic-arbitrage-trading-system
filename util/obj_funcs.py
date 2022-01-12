import pickle
import json

def save_obj(obj, name):
    with open('obj/'+ name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_obj(name):
    with open('obj/' + name + '.pkl', 'rb') as f:
        return pickle.load(f)

def save_pairs(PairsDict):
    out = {}
    for key, val in PairsDict.items():
        out[key] = (val.bid, val.ask)
    save_obj(out, "pairs")

def load_json(filename):
    with open(filename) as f:
        dict_ = json.load(f)
    return dict_

def save_json(data, name):
    if isinstance(data, dict):
        str_keys = {str(key):data for key,data in data.items()}
    if isinstance(data, list):
        str_keys = {f"{i}":{str(key):item for key,item in d.items()} for i, d in enumerate(data)}
    with open('obj/'+ name + '.json', 'w') as f:
        json.dump(str_keys, f)

