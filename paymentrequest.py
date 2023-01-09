from requests import get
url = 'https://pay.cointext.io/p/61401488380/1'
resp = get(url, headers={'Accept' : 'application/payment-request'}).json()
print(resp)
