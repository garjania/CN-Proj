import socket
import threading
import os
import gzip
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime

HOST = 'localhost'
PORT = 8080
ADDR = (HOST,PORT)
BUFSIZE = 4096
MSSG = {'400': 'Bad Request',
        '501': 'Not Implemented',
        '405': 'Method Not Allowed',
        '404': 'Not Found',
        '200': 'OK'}
CONTENTS = {'400': 'BITCH',
            '501': 'UWU',
            '405': 'NUT',
            '404': 'NIGGA'}
TYPES = {'html': 'text/html',
         'txt': 'text/plain',
         'png': 'image/png',
         'jpeg': 'image/jpeg',
         'jpg': 'image/jpg'}

class Client(threading.Thread):
    def __init__(self, sock, addr):
        threading.Thread.__init__(self)
        self.addr = addr
        self.sock = sock
        self.log = '[{date}] "{request}" "{response}"'
        self.timer = None
        self.close = False
    
    def analyze_http_req(self, request):
        headers = request.split('\r\n')
        request_dict = dict()
        self.log = '"{request}"'.format(request=headers[0])
        request_info =  headers[0].split()
        if len(request_info) != 3:
            raise Exception('400')
        request_dict['METHOD'] = request_info[0]
        request_dict['URL'] = request_info[1]
        request_dict['VERSION'] = request_info[2]
        if request_dict['METHOD'] not in ['DELETE', 'PUT', 'POST', 'HEAD', 'GET']:
            raise Exception('501')
        if request_dict['METHOD'] != 'GET':
            raise Exception('405')
        accepted_headers = ['Host', 'Accept-Encoding', 'Connection', 'Keep-Alive']
        for i in range(1, len(headers)):
            if len(headers[i]) == 0:
                break
            splitted = headers[i].split(': ')
            if len(splitted) != 2:
                raise Exception('400')
            if splitted[0] in accepted_headers:
                request_dict[splitted[0]] = splitted[1]
        request_dict['Accept-Encoding'] = request_dict['Accept-Encoding'].split(', ')
        if 'Keep-Alive' in request_dict:
            request_dict['Keep-Alive'] = int(request_dict['Keep-Alive'])
        else:
            request_dict['Keep-Alive'] = 60
        return request_dict
    
    def fetch_url(self, request):
        url = request['URL']
        if not os.path.isfile('.{}'.format(url)):
            raise Exception('404')
        url = url[1:]
        f = open(url, 'rb')
        content = f.read()
        encoded = False
        if 'gzip' in request['Accept-Encoding']:
            content = gzip.compress(content)
            encoded = True
        file_type = url.split('.')[1]
        content_type = TYPES[file_type]
        return content, content_type, encoded
    
    def http_response(self, code, request):
        encoded = False
        if code != '200':
            content = CONTENTS[code]
            content_type = 'text/html'
        else:
            try:
                content, content_type, encoded = self.fetch_url(request)
            except Exception as e:
                code = str(e)
                content = CONTENTS[code]
                content_type = 'text/html'
        return self.build_response(code, content, content_type, encoded)

    def build_response(self, code, content, content_type, encoded):
        date = format_date_time(mktime(datetime.now().timetuple()))
        self.log = '[{date}] '.format(date=date) + self.log
        self.log = self.log + ' "HTTP/1.0 {code} {message}"'.format(code=code, message=MSSG[code])
        response = 'HTTP/1.0 {code} {message}\r\n'.format(code=code, message=MSSG[code])
        response += 'Connection: close\r\n'
        response += 'Content-Length: {length}\r\n'.format(length=len(content))
        response += 'Content-Type: {type}\r\n'.format(type=content_type)
        if encoded:
            response += 'Content-Encoding: gzip\r\n'
        response += 'Date: {date}\r\n\r\n'.format(date=date)
        response = bytearray(response, 'utf-8')
        if type(content) == str:
            content = bytearray(content, 'utf-8')
        response += content
        return response
    
    def close_socket(self):
        self.close = True

    def setup_timer(self, request):
        if self.timer is None:
            self.timer = threading.Timer(request['Keep-Alive'], self.close_socket)
        elif request['Keep-Alive'] > 0 :
            self.timer.cancle()
            self.timer = threading.Timer(request['Keep-Alive'], self.close_socket)
        self.timer.start()

    def run(self):
        while not self.close:
            data = self.sock.recv(BUFSIZE)
            if not data: 
                continue
            code = '200'
            request = None
            try:
                request = self.analyze_http_req(str(data, 'utf-8'))
            except Exception as e:
                code = str(e)
            self.setup_timer(request)
            self.sock.send(self.http_response(code, request))
            print(self.log)
            self.log = ''
        self.sock.close()

if __name__=='__main__':
    serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serv.bind(ADDR)
    serv.listen()
    while True:
        sock, addr = serv.accept()
        client = Client(sock, addr)
        client.start()