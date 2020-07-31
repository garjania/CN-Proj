import re
import socket
import threading
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
import math

HOST = 'localhost'
PORT8090 = 8090
PORT8091 = 8091
FIRST_ADDR = (HOST, PORT8090)
SECOND_ADDR = (HOST, PORT8091)
BUFF_SIZE = 4096


class Data:
    def __init__(self):
        self.n_req = 0
        self.n_res = 0
        self.mean_req = 0
        self.mean_res = 0
        self.mean_body = 0
        self.std_req = 0
        self.std_res = 0
        self.std_body = 0
        self.types_count = {'text/html': 0, 'text/plain': 0, 'image/png': 0, 'image/jpg': 0, 'image/jpeg': 0}
        self.status_count = {'200 OK': 0, '301 Moved Permanently': 0, '304 Not Modified': 0,
                             '400 Bad Request': 0, '404 Not Found': 0, '405 Method Not Allowed': 0,
                             '501 Not Implemented': 0}
        self.hosts = {}

    def increase_host_reqs(self, host):
        if host in self.hosts.keys():
            self.hosts[host] = self.hosts[host] + 1
        else:
            self.hosts[host] = 1

    def add_request(self, length):
        self.n_req += 1
        last_mean = self.mean_req
        self.mean_req = (self.mean_req * (self.n_req - 1) + length) / self.n_req
        if self.n_req > 1:
            self.std_req = \
                math.sqrt(((self.std_req ** 2 + last_mean ** 2) * (self.n_req - 1) + (length ** 2)) / self.n_req - self.mean_req ** 2)

    def add_response(self, length, body_length, status_code, msg_type):
        self.n_res += 1
        last_mean = self.mean_res
        last_mean_body = self.mean_body
        self.mean_res = (self.mean_res * (self.n_res - 1) + length) / self.n_res
        self.mean_body = (self.mean_body * (self.n_res - 1) + body_length) / self.n_res
        if self.n_res > 1:
            self.std_res = \
                math.sqrt(((self.std_res ** 2 + last_mean ** 2) * (self.n_res - 1) + (length ** 2)) / self.n_res - self.mean_res ** 2)
            self.std_body = \
                math.sqrt(((self.std_body ** 2 + last_mean_body ** 2) * (self.n_res - 1) + (body_length ** 2)) / self.n_res - self.mean_body ** 2)
        if status_code in self.status_count.keys():
            self.status_count[status_code] = self.status_count[status_code] + 1
        if msg_type in self.types_count.keys():
            self.types_count[msg_type] = self.types_count[msg_type] + 1

    def get_sorted_hosts(self):
        hosts_list = []
        for key in self.hosts.keys():
            hosts_list.append((key, self.hosts[key]))
        hosts_list.sort(key=lambda x: x[1], reverse=True)
        return hosts_list


class Client(threading.Thread):
    def __init__(self, sock, addr, data):
        threading.Thread.__init__(self)
        self.sock = sock
        self.addr = addr
        self.close = False
        self.hostname = ''
        self.host_port = 80
        self.data = data

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
        self.data.add_request(len(data))
        request_list = data.split('\r\n')
        hostname, port = self.get_hostname_and_port(request_list[0].split(" ")[1])
        log = 'Request: [{time}] [{client_ip}:{client_port}] [{host_name}:{host_port}] "{request_line}"' \
            .format(time=format_date_time(mktime(datetime.now().timetuple())),
                    client_ip=self.addr[0], client_port=self.addr[1],
                    host_name=hostname, host_port=port, request_line=request_list[0])
        print(log)
        self.data.increase_host_reqs(hostname)

    def process_response_for_telnet(self, response):
        headers = response[:response.find("\r\n\r\n")]
        header_lines = headers.split("\r\n")
        first_line_split = header_lines[0].split(" ")
        status = header_lines[0][len(first_line_split[0]) + 1:]
        msg_type = ""
        for i in range(1, len(header_lines)):
            header = header_lines[i].split(": ")
            if header[0] == 'Content-Type':
                msg_type = header[1]

        self.data.add_response(len(response), len(response) - len(headers) - 4, status, msg_type)

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
            except (socket.timeout, ConnectionResetError) as e:
                break
            if len(data) == 0:
                break
            if is_header:
                log = 'Response: [{time}] [{client_ip}:{client_port}] [{host_name}:{host_port}] "{status_line}" for ' \
                      '"{request_line}"' \
                    .format(time=format_date_time(mktime(datetime.now().timetuple())),
                            client_ip=self.addr[0], client_port=self.addr[1],
                            host_name=self.hostname, host_port=self.host_port,
                            status_line=data.decode ('utf-8', 'ignore').split("\r\n")[0], request_line=request_list[0])
                print(log)
                is_header = False
            response += bytearray(data)
        self.sock.send(response)
        socket_to_host.close()
        self.close = True
        self.process_response_for_telnet(response.decode ('utf-8', 'ignore'))

    def run(self):
        while not self.close:
            data = self.sock.recv(BUFF_SIZE)
            if not data:
                continue
            self.parse_request(str(data, 'utf-8'))
            self.forward_to_host(data)
        self.sock.close()
        # print("END")


class PORT8090(threading.Thread):
    def __init__(self, data):
        threading.Thread.__init__(self)
        self.data = data

    def run(self):
        proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy_server.bind(FIRST_ADDR)
        proxy_server.listen()
        while True:
            sock, addr = proxy_server.accept()
            client = Client(sock, addr, self.data)
            client.start()


class TelnetClient(threading.Thread):
    def __init__(self, sock, addr, data):
        threading.Thread.__init__(self)
        self.sock = sock
        self.addr = addr
        self.close = False
        self.data = data

    def packet_length_stat_response(self):
        response = 'Packet length received from server(mean, std): ({mean_res}, {std_res})\nPacket length received ' \
                   'from client(mean, std): ({mean_req}, {std_req})\nBody length received from server(mean, ' \
                   'std): ({mean_body}, {std_body})\n' \
            .format(mean_res=self.data.mean_res, std_res=self.data.std_res, mean_req=self.data.mean_req, std_req=self.
                    data.std_req, mean_body=self.data.mean_body, std_body=self.data.std_body)
        self.sock.send(bytearray(response, 'utf-8'))

    def type_count_response(self):
        response = ""
        for key in self.data.types_count.keys():
            response += (key + ": " + str(self.data.types_count[key]) + "\n")
        self.sock.send(bytearray(response, 'utf-8'))

    def status_count_response(self):
        response = ""
        for key in self.data.status_count.keys():
            response += (key + ": " + str(self.data.status_count[key]) + "\n")
        self.sock.send(bytearray(response, 'utf-8'))

    def top_k_visited_hosts_response(self, k):
        response = ""
        sorted_hosts = self.data.get_sorted_hosts()
        for i in range(len(sorted_hosts)):
            if i >= k:
                break
            response += '{num}. {host}\n'.format(num=i + 1, host=sorted_hosts[i][0])
        self.sock.send(bytearray(response, 'utf-8'))

    def exit_response(self):
        self.sock.send(bytearray('Bye\n', 'utf-8'))
        self.close = True

    def bad_request_response(self):
        self.sock.send(bytearray('Bad Request\n', 'utf-8'))

    def run(self):
        top_k_pattern = re.compile("top \\d+ visited hosts")
        while not self.close:
            data = self.sock.recv(BUFF_SIZE)
            if not data:
                continue
            try:
                string_data = str(data, 'utf-8')
                string_data = string_data[:len(string_data) - 2]
                if string_data != '\r\n':
                    if string_data == 'packet length stats':
                        self.packet_length_stat_response()
                    elif string_data == 'type count':
                        self.type_count_response()
                    elif string_data == 'status count':
                        self.status_count_response()
                    elif bool(top_k_pattern.match(string_data)):
                        self.top_k_visited_hosts_response(int(string_data.split(' ')[1]))
                    elif string_data == 'exit':
                        self.exit_response()
                    else:
                        self.bad_request_response()
            except UnicodeError:
                continue
        self.sock.close()


class PORT8091(threading.Thread):
    def __init__(self, data):
        threading.Thread.__init__(self)
        self.data = data

    def run(self):
        proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy_server.bind(SECOND_ADDR)
        proxy_server.listen()
        while True:
            sock, addr = proxy_server.accept()
            print("telnet connected")
            telnet_client = TelnetClient(sock, addr, self.data)
            telnet_client.start()


if __name__ == '__main__':
    data = Data()
    port8090_process = PORT8090(data)
    port8091_process = PORT8091(data)

    port8090_process.start()
    port8091_process.start()

    port8090_process.join()
    port8091_process.join()
