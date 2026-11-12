import http.client, json, os, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import ThreadingHTTPServer
import app

class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); app.DATA=Path(cls.tmp.name); app.DB=app.DATA/'test.db'; app.FILES=app.DATA/'files'
        os.environ['FLOWCAPTURE_ADMIN_USER']='admin';os.environ['FLOWCAPTURE_ADMIN_PASSWORD']='testing-password-123'
        app.init();cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.port=cls.server.server_address[1]
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    def req(self,method,path,body=None,token=None,csrf=None,ctype=None):
        con=http.client.HTTPConnection('127.0.0.1',self.port);h={}
        if token:h['Cookie']=token
        if csrf:h['X-CSRF-Token']=csrf
        if isinstance(body,dict):body=json.dumps(body);h['Content-Type']='application/json'
        if ctype:h['Content-Type']=ctype
        con.request(method,path,body,h);res=con.getresponse();raw=res.read(); headers=dict(res.getheaders()); status=res.status;con.close();return status,headers,raw
    def login(self,name,pw):
        status,h,_=self.req('POST','/api/login',{'username':name,'password':pw});self.assertEqual(status,200);token=h['Set-Cookie'].split(';')[0]
        _,_,data=self.req('GET','/api/me',token=token);return token,json.loads(data)['csrf']
    def test_workflow(self):
        status,_,_=self.req('GET','/api/tickets');self.assertEqual(status,401)
        admin,acsrf=self.login('admin','testing-password-123')
        for name,role in [('driver','front'),('office','office')]:
            status,_,_=self.req('POST','/api/users',{'username':name,'password':'testing-password-456','role':role},admin,acsrf);self.assertEqual(status,201)
        driver,dcsrf=self.login('driver','testing-password-456');office,ocsrf=self.login('office','testing-password-456')
        status,_,_=self.req('GET','/api/company-settings',token=driver);self.assertEqual(status,403)
        status,_,_=self.req('POST','/api/company-settings',{'office_email':'office@example.com'},office,ocsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST','/api/company-settings',{'office_email':'bad'},admin,acsrf);self.assertEqual(status,400)
        status,_,_=self.req('POST','/api/company-settings',{'office_email':'office@example.com'},admin,acsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/company-settings',token=admin);settings=json.loads(data);self.assertEqual(settings['office_email'],'office@example.com');self.assertFalse(settings['quickbooks_connected']);self.assertFalse(settings['email_configured'])
        template={'version':1,'name':'Hauling','industry':'Hauling','doc_type':'Ticket','shared':True,'fields':[{'key':'job_code','label':'Job code','type':'text','required':True}]}
        status,_,_=self.req('POST','/api/templates',template,driver,dcsrf);self.assertEqual(status,403)
        status,_,data=self.req('POST','/api/templates',template,admin,acsrf);self.assertEqual(status,201);template_id=json.loads(data)['id']
        status,_,data=self.req('GET','/api/templates',token=driver);self.assertEqual(json.loads(data)['templates'][0]['id'],template_id)
        private=dict(template,shared=False,name='Private')
        status,_,data=self.req('POST','/api/templates',private,driver,dcsrf);self.assertEqual(status,201)
        status,_,data=self.req('GET','/api/templates',token=office);self.assertEqual(len(json.loads(data)['templates']),1)
        _,_,data=self.req('GET','/api/users',token=admin);driver_id=next(x['id'] for x in json.loads(data)['users'] if x['username']=='driver')
        status,_,_=self.req('POST','/api/invitations',{'user_id':driver_id},office,ocsrf);self.assertEqual(status,403)
        status,_,data=self.req('POST','/api/invitations',{'user_id':driver_id},admin,acsrf);self.assertEqual(status,201);invite=json.loads(data)['token']
        status,h,_=self.req('POST','/api/invitation/accept',{'token':invite});self.assertEqual(status,200);linked=h['Set-Cookie'].split(';')[0]
        status,_,_=self.req('POST','/api/invitation/accept',{'token':invite});self.assertEqual(status,400)
        status,_,_=self.req('POST','/api/devices/revoke',{'user_id':driver_id},admin,acsrf);self.assertEqual(status,200)
        status,_,_=self.req('GET','/api/me',token=linked);self.assertEqual(status,401)
        driver,dcsrf=self.login('driver','testing-password-456')
        status,_,_=self.req('POST','/api/messages',{'recipient':driver_id,'subject':'Missing ticket','body':'Please send ticket 3631111.'},office,ocsrf);self.assertEqual(status,201)
        status,_,data=self.req('GET','/api/messages',token=driver);messages=json.loads(data)['messages'];self.assertEqual(messages[0]['subject'],'Missing ticket')
        status,_,_=self.req('POST','/api/messages/acknowledge',{'id':messages[0]['id']},driver,dcsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/messages',token=office);self.assertEqual(json.loads(data)['messages'][0]['status'],'Acknowledged')
        status,_,_=self.req('POST','/api/messages/complete',{'id':messages[0]['id']},driver,dcsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/messages',token=office);self.assertEqual(json.loads(data)['messages'][0]['status'],'Completed')
        status,_,_=self.req('POST','/api/messages/acknowledge',{'id':messages[0]['id']},driver,dcsrf);self.assertEqual(status,404)
        status,_,_=self.req('POST','/api/messages',{'recipient':driver_id,'subject':'Test','body':'No'},driver,dcsrf);self.assertEqual(status,403)
        parts={'template_id':template_id,'custom_job_code':'ABC-5','number':'3631110','vendor':'Conrad','date':'2026-10-05','customer':'Preferred','quantity':'24.26'}; boundary='flowcapture-boundary';body=b''
        for k,v in parts.items():body+=f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        body+=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="ticket.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()+b'%PDF-1.4\nexample\r\n'+f'--{boundary}--\r\n'.encode();ct='multipart/form-data; boundary='+boundary
        status,_,_=self.req('POST','/api/ai-extract',body,driver,dcsrf,ct);self.assertEqual(status,403)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-not-a-real-key','FLOWCAPTURE_AI_MODEL':'test-model'}), patch('app.urlopen') as client:
            response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({k:('3631110' if k=='number' else '') for k in app.AI_FIELDS})}]}]}
            client.return_value.__enter__.return_value=MagicMock(read=MagicMock(return_value=json.dumps(response).encode()))
            status,_,_=self.req('POST','/api/company-settings',{'office_email':'office@example.com','ai_enabled':True},admin,acsrf);self.assertEqual(status,200)
            status,_,data=self.req('POST','/api/ai-extract',body,driver,dcsrf,ct);self.assertEqual(status,200);self.assertEqual(json.loads(data)['fields']['number'],'3631110');self.assertTrue(json.loads(data)['review_required'])
            request=client.call_args.args[0];payload=json.loads(request.data);self.assertFalse(payload['store']);self.assertEqual(payload['input'][0]['content'][1]['type'],'input_file')
        status,_,_=self.req('POST','/api/company-settings',{'office_email':'office@example.com','ai_enabled':False},admin,acsrf);self.assertEqual(status,200)
        status,_,data=self.req('POST','/api/tickets',body,driver,dcsrf,ct);self.assertEqual(status,201);tid=json.loads(data)['id']
        with patch.dict(os.environ,{'FLOWCAPTURE_GMAIL_ADDRESS':'sender@example.com','FLOWCAPTURE_GMAIL_APP_PASSWORD':'example app password'}), patch('app.smtplib.SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            with app.db() as c:self.assertEqual(app.deliver_office_email(c,tid,b'%PDF-1.4\nexample','application/pdf','ticket.pdf'),'Sent')
            mail=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
            self.assertEqual(mail['To'],'office@example.com');self.assertEqual(len(list(mail.iter_attachments())),2)
        with patch.dict(os.environ,{'FLOWCAPTURE_GMAIL_ADDRESS':'sender@example.com','FLOWCAPTURE_GMAIL_APP_PASSWORD':'example app password'}), patch('app.smtplib.SMTP_SSL',side_effect=OSError('offline')):
            with app.db() as c:self.assertEqual(app.deliver_office_email(c,tid,b'%PDF-1.4\nexample','application/pdf','ticket.pdf'),'Failed')
        status,_,_=self.req('POST','/api/tickets',body,driver,dcsrf,ct);self.assertEqual(status,409)
        status,_,data=self.req('GET','/api/tickets',token=office);self.assertEqual(json.loads(data)['tickets'][0]['id'],tid);self.assertEqual(json.loads(data)['tickets'][0]['extra_fields']['Job code'],'ABC-5')
        status,_,data=self.req('GET','/api/tickets',token=office);ticket=json.loads(data)['tickets'][0];ticket['customer']='Preferred Asphalt corrected'
        status,_,_=self.req('POST',f'/api/tickets/{tid}/edit',ticket,driver,dcsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/edit',ticket,office,ocsrf);self.assertEqual(status,200)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/edit',ticket,office,ocsrf);self.assertEqual(status,409)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'24.26','rate':'12.50'},driver,dcsrf);self.assertEqual(status,403)
        status,_,data=self.req('GET','/api/tickets',token=office);latest=json.loads(data)['tickets'][0]
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'24.26','rate':'12.50','updated':latest['updated']},office,ocsrf);self.assertEqual(status,200)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'24.26','rate':'12.50','updated':latest['updated']},office,ocsrf);self.assertEqual(status,409)
        status,_,data=self.req('GET','/api/tickets',token=admin);self.assertEqual(json.loads(data)['tickets'][0]['status'],'Ready')
        status,_,data=self.req('GET','/api/tickets',token=driver);self.assertNotIn('rate',json.loads(data)['tickets'][0])
        status,_,raw=self.req('GET',f'/api/tickets/{tid}/summary.pdf',token=driver);self.assertEqual(status,200);self.assertTrue(raw.startswith(b'%PDF-'));self.assertNotIn(b'Rate per ton',raw)
        status,_,raw=self.req('GET',f'/api/tickets/{tid}/summary.pdf',token=office);self.assertEqual(status,200);self.assertIn(b'303.25',raw)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'1e9999','rate':'12','updated':'x'},office,ocsrf);self.assertEqual(status,400)
        status,_,data=self.req('GET','/api/tickets',token=office);current=json.loads(data)['tickets'][0]
        status,_,_=self.req('POST',f'/api/tickets/{tid}/edit',current,office,ocsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/tickets',token=office);current=json.loads(data)['tickets'][0]
        status,_,_=self.req('POST',f'/api/tickets/{tid}/reject',{'updated':current['updated'],'reason':'Please add the PO'},driver,dcsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/reject',{'updated':current['updated'],'reason':'Please add the PO'},office,ocsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/tickets',token=driver);rejected=json.loads(data)['tickets'][0];self.assertEqual(rejected['status'],'Rejected')
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'1','rate':'12','updated':rejected['updated']},office,ocsrf);self.assertEqual(status,409)
        status,_,data=self.req('GET','/api/messages',token=driver);self.assertTrue(any(m['subject'].startswith('Ticket rejected') for m in json.loads(data)['messages']))
        status,_,data=self.req('GET','/api/ticket-events',token=driver);self.assertEqual(json.loads(data)['events'][0]['reason'],'Please add the PO')
        status,_,_=self.req('POST',f'/api/tickets/{tid}/resubmit',{'updated':rejected['updated'],'reason':'PO 42'},office,ocsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/resubmit',{'updated':rejected['updated'],'reason':'PO 42'},driver,dcsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/ticket-events',token=driver);self.assertEqual(len(json.loads(data)['events']),1)
        status,_,data=self.req('GET','/api/tickets',token=office);self.assertEqual(json.loads(data)['tickets'][0]['status'],'Needs Review')
        status,_,raw=self.req('GET',f'/api/tickets/{tid}/file',token=office);self.assertEqual(status,200);self.assertTrue(raw.startswith(b'%PDF-'))
        status,_,_=self.req('POST','/api/users',{'username':'intruder','password':'testing-password-456','role':'admin'},office,ocsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST','/api/users',{'username':'intruder','password':'testing-password-456','role':'admin'},admin,'bad');self.assertEqual(status,403)
        status,_,_=self.req('POST','/api/password',{'current':'wrong','password':'new-testing-password-789'},driver,dcsrf);self.assertEqual(status,400)
        status,_,_=self.req('POST','/api/password',{'current':'testing-password-456','password':'new-testing-password-789'},driver,dcsrf);self.assertEqual(status,200)
        status,_,_=self.req('POST','/api/login',{'username':'driver','password':'testing-password-456'});self.assertEqual(status,401)
        driver,dcsrf=self.login('driver','new-testing-password-789')
        status,_,_=self.req('POST','/api/users/access',{'user_id':driver_id,'active':False},office,ocsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST','/api/users/access',{'user_id':driver_id,'active':False},admin,acsrf);self.assertEqual(status,200)
        status,_,_=self.req('GET','/api/me',token=driver);self.assertEqual(status,401)
        status,_,_=self.req('POST','/api/users/access',{'user_id':driver_id,'active':True},admin,acsrf);self.assertEqual(status,200)
        self.login('driver','new-testing-password-789')
if __name__=='__main__':unittest.main()
