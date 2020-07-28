import socket
import threading
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time

HOST = 'localhost'
PORT8090 = 8090
PORT8091 = 8091
FIRST_ADDR = (HOST, PORT8090)
SECOND_ADDR = (HOST, PORT8091)
BUFF_SIZE = 4096


class Client(threading.Thread):
    def __init__(self, sock, addr):
        threading.Thread.__init__(self)
        self.sock = sock
        self.addr = addr
        self.timer = None
        self.close = False
        self.hostname = ''
        self.host_port = 80

    def get_hostname_and_port(self, url):
        start = url.find("://")
        if start == -1:
            rest = url
        else:
            rest = url[(start + 3):]
        port_pos = rest.find(":")
        end = rest.find("/")
        if end == -1:
            end = len(rest)

        if port_pos == -1 or end < port_pos:
            self.hostname = rest[:end]
            self.host_port = 80
        else:
            self.hostname = rest[:port_pos]
            self.host_port = int((rest[(port_pos + 1):])[:end - port_pos - 1])
        return self.hostname, self.host_port

    def parse_request(self, data):
        request_dict = dict()
        request_list = data.split('\r\n')
        # print(request_list)
        hostname, port = self.get_hostname_and_port(request_list[0].split(" ")[1])
        log = 'Request: [{time}] [{client_ip}:{client_port}] [{host_name}:{host_port}] "{request_line}"' \
            .format(time=format_date_time(mktime(datetime.now().timetuple())),
                    client_ip=self.addr[0], client_port=self.addr[1],
                    host_name=hostname, host_port=port, request_line=request_list[0])
        print(log)
        return request_dict

    def forward_to_host(self, request):
        socket_to_host = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_to_host.connect((self.hostname, self.host_port))
        socket_to_host.settimeout(2)
        socket_to_host.sendall(request)
        request_list = str(request, 'utf-8').split("\r\n")

        response = bytearray()
        is_header = True

        while True:
            try:
                data = socket_to_host.recv(BUFF_SIZE)
            except socket.timeout:
                break
            # print(data)
            if len(data) == 0:
                break
            if is_header:
                log = 'Response: [{time}] [{client_ip}:{client_port}] [{host_name}:{host_port}] "{status_line}" for "{request_line}"' \
                    .format(time=format_date_time(mktime(datetime.now().timetuple())),
                            client_ip=self.addr[0], client_port=self.addr[1],
                            host_name=self.hostname, host_port=self.host_port,
                            status_line=str(data, 'utf-8').split("\r\n")[0], request_line=request_list[0])
                print(log)
                is_header = False
            response += bytearray(data)
        # print(response)
        self.sock.send(response)
        socket_to_host.close()
        self.close = True

    def run(self):
        while not self.close:
            data = self.sock.recv(BUFF_SIZE)
            if not data:
                continue
            self.parse_request(str(data, 'utf-8'))
            self.forward_to_host(data)
        self.sock.close()
        # print("END")


if __name__ == '__main__':
    proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_server.bind(FIRST_ADDR)
    proxy_server.listen()
    while True:
        sock, addr = proxy_server.accept()
        client = Client(sock, addr)
        client.start()
