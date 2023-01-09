import sqlite3
import grpc
import bchrpc_pb2 as pb
import bchrpc_pb2_grpc as bchrpc
import time
import json
import requests
import bitcash
from time import gmtime, strftime
import traceback

def returnBCHDConnection():
    channel = grpc.secure_channel('bchd.greyh.at:8335', grpc.ssl_channel_credentials())
    stub = bchrpc.bchrpcStub(channel)
    return stub
    
bchd = returnBCHDConnection()


def returnDBCOnnection():
    conn = sqlite3.connect('coinTextRouterDB')
    c = conn.cursor()
    return c
    
db = returnDBCOnnection()


##############SETTINGS################
scanIntervalSeconds = 300 #execute the scan loop every 5 minutes
fee = 0.02 #fee taken from each transaction
baseTxFee = 500 #generous estimate of base tx fee
txFeePerOutputSats = 200 #generous estimate of bytes per output
minimumUsablePercentageOfPayment = 0.5 #at least 50% of any payment must be sent to the invoices and not spent on tx fees
minimumOutputAmountSats = 546 #minimum dust limit on output sizes, built into protocol
feeAddressIndex = -1 
##############SETTINGS################
    
    
def logError(errorName, exception, details): #exception is result of traceback.format_exc()
    timeString = strftime("%Y-%m-%d %H:%M:%S", gmtime())
    
    errorText = "NEW EXCEPTION: \n TIME: " + timeString + "\n\nTRACEBACK:\n" + str(exception) + "\n\nDETAILS: " + str(details) + "############################\n\n\n\n"
    with open("errorLog.txt", "a") as errorFile:
        errorFile.write(errorText)
    print(errorText)
    
    
def getBestBlockHeight():
    req = pb.GetBlockchainInfoRequest()
    resp = bchd.GetBlockchainInfo(req)
    return resp.best_height
    
    
def getLastCheckedBlockHeight():
    cursor = db.execute('SELECT lastCheckedBlockHeight FROM persistence')
    lastCheckedBlockHeight = [row for row in cursor][0][0]
    return lastCheckedBlockHeight
    
    
def getAllMonitoredAddresses():
    cursor = db.execute('SELECT bchAddress FROM transactions')
    monitoredAddresses = [row[0] for row in cursor]
    return monitoredAddresses 

    
def getBlock(blockHeight):
    req = pb.GetBlockRequest()
    req.height = blockHeight
    req.full_transactions = True
    resp = bchd.GetBlock(req)
    return resp
    
    
def isUTXOSpent(txid, index, address):
    resp = requests.get("https://rest.bitcoin.com/v2/address/utxo/" + address).json()
    for utxo in resp:
        if utxo["txid"] == txid and utxo["vout"] == index:
            return False
    return True
    
    
def getPhoneNumbers(address):
    args = (address,) #sql injection-proof arguments
    cursor = db.execute('SELECT phoneNumbers FROM transactions WHERE bchAddress=?', args)
    phoneNumbersJSON = [row for row in cursor][0][0]
    phoneNumbers = json.loads(phoneNumbersJSON)
    return phoneNumbers
    
    
def generateCoinTextInvoices(phoneNumbers, amountPerInvoiceSats):
    outputs = []
    for phoneNumber in phoneNumbers:
        headers = {'content-type': 'application/json'}
        url = "https://pay.cointext.io/p/" + phoneNumber + "/" + str(amountPerInvoiceSats)
        coinTextInvoice = requests.get(url, headers=headers).json()
        bchAddress = coinTextInvoice["outputs"]["address"]
        bchAmount = coinTextInvoice["outputs"]["amount"]
        outputs.append([bchAddress, bchAmount])
    return outputs
        
        
def calcInvoiceAndFeeAmount(totalAmount, phoneNumberCount):
    totalTxFeeAmount = baseTxFee + phoneNumberCount*txFeePerOutputSats
    usableAmount = totalAmount - totalTxFeeAmount
    feeAmount = round(usableAmount*fee, 1)
    payableAmount = usableAmount - feeAmount
    amountPerInvoice = int(payableAmount / phoneNumberCount)
    return [amountPerInvoice, feeAmount]
    
    
def calculateKey(index):
    key = bitcash.Key()
    concatonatedString = seed + str(index)
    hashedData = hashlib.sha224(concatonatedString.encode()).hexdigest()
    key = key.from_hex(hashedData)
    return key
    
    
def calculateAddress(index):
    key = bitcash.Key()
    concatonatedString = seed + str(index)
    hashedData = hashlib.sha224(concatonatedString.encode()).hexdigest()
    key = key.from_hex(hashedData)
    return key.address
    
    
def getIndex(address):
    args = (address,) #sql injection-proof arguments
    cursor = db.execute('SELECT index FROM transactions WHERE bchAddress=?', args)
    index = [row for row in cursor][0][0]
    return index   
    

def broadcastInvoicesPaymentTransaction(invoiceOutputs, key, feeAmountSats):
    key.get_unspents()
    feeAddress = calculateAddress(feeAddressIndex)
    outputs = [(out[0], out[1]/100000000, "bch") for output in invoiceOutputs]
    outputs.append((feeAddress, feeAmountSats/100000000))
    key.send(outputs, fee=1) #one is current sats/byte enforce by cointext bip70 api


def addRetryScanRecord(objectType, objectData):
    if objectType == "tx" or objectType == "utxo":
        objectData = json.dumps(objectData)
    args = (str(objectType), str(objectData), 0,) #sql injection-proof arguments
    cursor = db.execute('INSERT INTO retryScan (objectType,object,attemptCount) VALUES(?,?,?)', args)
    return
    
    
def deleteRetryScanRecord(objectType, objectData):
    if objectType == "tx" or objectType == "utxo":
        objectData = json.dumps(objectData)
    args = (str(objectType), str(objectData),) #sql injection-proof arguments
    cursor = db.execute('DELETE FROM retryScan WHERE objectType=? AND object=?', args)
    return
    
    
def deleteTransaction(address):
    args = (address,) #sql injection-proof arguments
    cursor = db.execute('DELETE FROM trasactions WHERE address=?', args)
    return
    
    
def updateLastCheckedBlockHeight(lastCheckedBlockHeight):
    args = (int(lastCheckedBlockHeight),) #sql injection-proof arguments
    cursor = db.execute('UPDATE persistence SET lastCheckedBlockHeight=? WHERE id=?', args)


def processBlock(blockHeight, monitoredAddresses):
    block = getBlock(blockHeight)
    for tx in block.block.transaction_data:
        try:
            txid = bytearray(tx.transaction.hash[::-1]).hex()
            outputs = [[txid, txOutput.index, txOutput.address, txOutput.value] for txOutput in tx.transaction.outputs]
            processTransactionOutputs(outputs, monitoredAddresses)
        except:
            logError("Transaction processing error", traceback.format_exc(), "block height: ": str(blockHeight) + " txid: " + str(txid))
            addRetryScanRecord("utxo", outputs)


def processTransactionOutputs(outputs, monitoredAddresses):
    for txOutput in outputs:
        txid, index, address, value = txOutput
        if address in monitoredAddresses:
            try:
                processUTXO(txOutput)
            except:
                logError("UTXO processing error", traceback.format_exc(), "txid: ": str(txid) + " index: " + str(index))
                addRetryScanRecord("utxo", txOutput)


def processUTXO(txOutput):
    txid, index, address, value = txOutput
    if isUTXOSpent(txid, index, address):
        return
    phoneNumbers = getPhoneNumbers(address)
    phoneNumberCount = len(phoneNumbers)
    amountPerInvoiceSats, feeAmountSats = calcInvoiceAndFeeAmount(value, phoneNumberCount)
    if amountPerInvoiceSats <= minimumOutputAmountSats: #payment too small to fund each invoice with at least minimumOutputAmountSats satoshis
        logError("amountPerInvoiceSats smaller than minimum", "NO TRACEBACK", "txid: ": str(txid) + " index: " + str(index) + "amountPerInvoiceSats": str(amountPerInvoiceSats) + "minimumOutputAmountSats": str(minimumOutputAmountSats))
        return
    try:
        invoiceOutputs = generateCoinTextInvoices(phoneNumbers, amountPerInvoiceSats)
    except:
        
        logError("Cointext API error", traceback.format_exc(), "phoneNumbers: ": str(phoneNumbers) + " amountPerInvoiceSats: " + str(amountPerInvoiceSats) + " REFUND TXID: " + )
        raise Exception("Cointext API error, traceback above")
    index = getIndex(address)
    key = calculateKey(index)
    try:
        broadcastInvoicesPaymentTransaction(invoiceOutputs, key, feeAmountSats)
    except:
        logError("Invoice paying tx broadcast error", traceback.format_exc(), "invoiceOutputs: ": str(invoiceOutputs) + " feeAmountSats: " + str(feeAmountSats))
        raise Exception("Invoice paying tx broadcast error, traceback above")
    deleteTransaction(address)

    
def loop(): 
    while True:
        monitoredAddresses = getAllMonitoredAddresses()
        bestBlockheight = getBestBlockHeight()
        lastCheckedBlockHeight = getLastCheckedBlockHeight()
        blocksToScan = range(lastCheckedBlockHeight-6,bestBlockheight)
        for blockHeight in blocksToScan:
            try:
                processBlock(blockHeight, monitoredAddresses)
            except:
                logError("Block processing error", traceback.format_exc(), "blockHeight: ": str(blockHeight))
                addRetryScanRecord("block", blockHeight)
            updateLastCheckedBlockHeight(blockHeight)
        time.sleep(scanIntervalSeconds)


if __name__ == "__main__":
    #loop()
    pass
    
