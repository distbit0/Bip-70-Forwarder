import bitcash
import hashlib
from cashaddress import convert
poolUserID = "pool"
seed = open("seed.txt").read()


def calculateAddress(userID):
    key = bitcash.Key()
    concatonatedString = seed + str(userID)
    hashedData = hashlib.sha224(concatonatedString.encode()).hexdigest()
    priv = key.from_hex(hashedData)
    return priv.address
    
    
def calculatePrivHex(userID):
    concatonatedString = seed + str(userID)
    hashedData = hashlib.sha224(concatonatedString.encode()).hexdigest()
    return hashedData

    
def getAddressBalance(address):
    networkApi = bitcash.network.NetworkAPI()
    addressBalance = sum([utxo.amount for utxo in networkApi.get_unspent(address)])
    return addressBalance/100000000
    
    
def createTransaction(senderUserID, outputs):
    key = bitcash.Key()
    senderPrivHex = calculatePrivHex(senderUserID)
    priv = key.from_hex(senderPrivHex)
    outputs = [(out[0], out[1], "bch") for out in outputs]
    priv.create_transaction(outputs)
    
    

    
pooladdy = calculateAddress(poolUserID)
print(pooladdy)
print("pool bal: " + str(getAddressBalance(pooladdy)))

print(bitcash.network.satoshi_to_currency(100000000, "usd"))

