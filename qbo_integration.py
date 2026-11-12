"""QuickBooks Online OAuth and Accounting API helpers for a single-company pilot."""
import base64
import datetime
import json
import os
import re
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from cryptography.fernet import Fernet

AUTH_URL='https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL='https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'

def config():
    client=os.environ.get('FLOWCAPTURE_QBO_CLIENT_ID','').strip()
    secret=os.environ.get('FLOWCAPTURE_QBO_CLIENT_SECRET','').strip()
    redirect=os.environ.get('FLOWCAPTURE_QBO_REDIRECT_URI','').strip()
    encryption=os.environ.get('FLOWCAPTURE_QBO_ENCRYPTION_KEY','').strip()
    mode=os.environ.get('FLOWCAPTURE_QBO_ENV','sandbox')
    parsed=urllib.parse.urlsplit(redirect)
    local=parsed.hostname in ('localhost','127.0.0.1')
    if not client or not secret or not encryption or mode not in ('sandbox','production') or not parsed.netloc or parsed.path!='/api/qbo/callback' or parsed.query or parsed.fragment or (parsed.scheme!='https' and not (parsed.scheme=='http' and local)):
        raise ValueError('QuickBooks hosting settings are incomplete or invalid.')
    try: cipher=Fernet(encryption.encode('ascii'))
    except (ValueError,UnicodeError):raise ValueError('Invalid QuickBooks encryption key.')
    return {'client':client,'secret':secret,'redirect':redirect,'mode':mode,'cipher':cipher}

def authorization_url(state):
    cfg=config();q=urllib.parse.urlencode({'client_id':cfg['client'],'scope':'com.intuit.quickbooks.accounting','redirect_uri':cfg['redirect'],'response_type':'code','state':state})
    return AUTH_URL+'?'+q

def token_request(params):
    cfg=config();auth=base64.b64encode((cfg['client']+':'+cfg['secret']).encode()).decode()
    req=urllib.request.Request(TOKEN_URL,data=urllib.parse.urlencode(params).encode(),headers={'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded','Authorization':'Basic '+auth},method='POST')
    with urllib.request.urlopen(req,timeout=25) as response:result=json.load(response)
    if not isinstance(result.get('access_token'),str) or not isinstance(result.get('refresh_token'),str):raise ValueError('QuickBooks authorization failed.')
    return result

def save_token(c,realm,token):
    if not re.fullmatch(r'[0-9]{1,40}',realm):raise ValueError('Invalid QuickBooks company.')
    cfg=config();expiry=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=max(0,int(token.get('expires_in',3600))-120))).isoformat()
    secret=cfg['cipher'].encrypt(json.dumps(token).encode()).decode()
    c.execute("INSERT INTO qbo_connection(id,realm,environment,token,expires) VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET realm=excluded.realm,environment=excluded.environment,token=excluded.token,expires=excluded.expires",(realm,cfg['mode'],secret,expiry));c.commit()

def access(c):
    cfg=config();row=c.execute('SELECT * FROM qbo_connection WHERE id=1').fetchone()
    if not row or row['environment']!=cfg['mode']:raise ValueError('Connect QuickBooks Online first.')
    token=json.loads(cfg['cipher'].decrypt(row['token'].encode()))
    if row['expires']<=datetime.datetime.now(datetime.timezone.utc).isoformat():
        token=token_request({'grant_type':'refresh_token','refresh_token':token['refresh_token']});save_token(c,row['realm'],token)
    return row['realm'],token['access_token'],cfg['mode']

def api(c,method,path,payload=None):
    realm,token,mode=access(c);base='https://sandbox-quickbooks.api.intuit.com' if mode=='sandbox' else 'https://quickbooks.api.intuit.com'
    req=urllib.request.Request(base+'/v3/company/'+realm+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Authorization':'Bearer '+token,'Accept':'application/json','Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def list_active(c,entity):
    if entity not in ('Customer','Item'):raise ValueError('Unsupported entity')
    query=urllib.parse.quote('SELECT * FROM '+entity+' WHERE Active = true MAXRESULTS 1000')
    result=api(c,'GET','/query?query='+query)
    return [{'id':str(x['Id']),'name':str(x.get('DisplayName') or x.get('FullyQualifiedName') or x.get('Name') or x['Id'])} for x in result.get('QueryResponse',{}).get(entity,[]) if x.get('Id')]

def invoice_payload(ticket,customer_id,item_id):
    qty=Decimal(ticket['quantity']);rate=Decimal(ticket['rate']);amount=(qty*rate).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    return {'CustomerRef':{'value':customer_id},'TxnDate':ticket['date'],'PrivateNote':'FlowCapture ticket '+ticket['number'],'EmailStatus':'NotSet','AllowOnlineCreditCardPayment':False,'AllowOnlineACHPayment':False,'Line':[{'Description':ticket['material'] or 'Service','Amount':float(amount),'DetailType':'SalesItemLineDetail','SalesItemLineDetail':{'ItemRef':{'value':item_id},'Qty':float(qty),'UnitPrice':float(rate)}}]}
