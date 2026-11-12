import http.client, json, os, tempfile, threading, unittest
from pathlib import Path
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
        parts={'number':'3631110','vendor':'Conrad','date':'2026-10-05','customer':'Preferred','quantity':'24.26'}; boundary='flowcapture-boundary';body=b''
        for k,v in parts.items():body+=f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        body+=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="ticket.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()+b'%PDF-1.4\nexample\r\n'+f'--{boundary}--\r\n'.encode();ct='multipart/form-data; boundary='+boundary
        status,_,data=self.req('POST','/api/tickets',body,driver,dcsrf,ct);self.assertEqual(status,201);tid=json.loads(data)['id']
        status,_,_=self.req('POST','/api/tickets',body,driver,dcsrf,ct);self.assertEqual(status,409)
        status,_,data=self.req('GET','/api/tickets',token=office);self.assertEqual(json.loads(data)['tickets'][0]['id'],tid)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'24.26','rate':'12.50'},driver,dcsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST',f'/api/tickets/{tid}/review',{'quantity':'24.26','rate':'12.50'},office,ocsrf);self.assertEqual(status,200)
        status,_,data=self.req('GET','/api/tickets',token=admin);self.assertEqual(json.loads(data)['tickets'][0]['status'],'Ready')
        status,_,raw=self.req('GET',f'/api/tickets/{tid}/file',token=office);self.assertEqual(status,200);self.assertTrue(raw.startswith(b'%PDF-'))
        status,_,_=self.req('POST','/api/users',{'username':'intruder','password':'testing-password-456','role':'admin'},office,ocsrf);self.assertEqual(status,403)
        status,_,_=self.req('POST','/api/users',{'username':'intruder','password':'testing-password-456','role':'admin'},admin,'bad');self.assertEqual(status,403)
if __name__=='__main__':unittest.main()
