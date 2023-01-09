from requests import get
url = 'https://bitpay.com/i/BITPAYINVOICEID'
resp = get(url, headers={'Accept' : 'application/payment-request'}).json()
print(resp)
