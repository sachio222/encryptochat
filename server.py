#!/usr/bin/ python3

import socket
import sys
from threading import Thread, Lock

import chatutils.xfer as xfer
import chatutils.utils as utils
from chatutils.chatio import ChatIO
from chatutils.channel import Channel

sockets = {}
sock_nick_dict = {}
nick_addy_dict = {}

lock = Lock()


class Server(ChatIO, Channel):
    """Server class"""

    def __init__(self):
        super(Server, self).__init__()
        self.BFFR = 1
        self.RECIP_SOCK = None
        self.SENDER_SOCK = None
        self.file_transfer = False

    def accepting(self):
        """Continuous Thread that listens for and accepts new socket cnxns.
        
        """
        # Accept connections.
        while True:
            client_cnxn, client_addr = sock.accept()
            print(f'-+- Connected... to {client_addr}')
            sockets[client_cnxn] = client_addr  # Create cnxn:addr pairings.
            Thread(target=self.handle_clients, args=(client_cnxn,)).start()

    def handle_clients(self, client_cnxn):
        # Get username.
        user_name = self.init_client_data(client_cnxn)
        announcement = f"{user_name} is in the house!"
        print(announcement)
        self.pack_n_send(client_cnxn, 'S', announcement)

        # Start listening.
        while True:
            data = client_cnxn.recv(1)  # Receive data as chunks.

            if not data:
                del (nick_addy_dict[sock_nick_dict[client_cnxn]])
                del (sock_nick_dict[client_cnxn])
                del (sockets[client_cnxn])  # remove address
                break

            self.data_router(client_cnxn, data)

    def data_router(self, client_cnxn, data):
        """Handles incoming data based on its message type."""
        # Send confirm dialog to recip if user is sending file.
        if data == "/".encode():
            # Drain socket of controller message so it doesn't print.
            control = self.unpack_msg(client_cnxn).decode()

            if control == 'status':
                status = self.get_status(nick_addy_dict)
                status = self.pack_message('S', status)
                print(status)
                self.broadcast(status, sockets, client_cnxn, target="all")

        elif data == b'M':
            sender = sock_nick_dict[client_cnxn]
            buff_text = self.unpack_msg(client_cnxn)
            print(f'{sender}: {buff_text.decode()}')
            data = self.pack_message(data, buff_text)
            self.broadcast(data, sockets, client_cnxn, sender=sender)

            # U-type handler
        elif data == b'U':
            self._serv_u_hndlr(client_cnxn)

        elif data == b'F':
            buff_text = self.unpack_msg(client_cnxn)
            data = self.pack_message(data, buff_text)
            self.broadcast(data,
                           sockets,
                           client_cnxn,
                           target='recip',
                           recip_socket=self.RECIP_SOCK)

        elif data == b'A':
            buff_text = self.unpack_msg(client_cnxn)
            data = self.pack_message(data, buff_text)
            self.broadcast(data,
                           sockets,
                           client_cnxn,
                           target='recip',
                           recip_socket=self.SENDER_SOCK)

        elif data == b'X':
            self._serv_x_hndlr(data, client_cnxn)

        else:
            buff_text = self.unpack_msg(client_cnxn)
            data = self.pack_message(data, buff_text)
            self.broadcast(data, sockets, client_cnxn)

    def _serv_u_hndlr(self, sock):
        """ U-type msgs used by SERVER and SENDER for user lookup exchanges.

        A U-type message tells the server to call lookup_user() method to
        search for a connected user by name. It sends the result back to
        SENDER.
        
        """
        username = self.unpack_msg(sock)
        if username != b'cancel':

            # Check for address.
            match = self.lookup_user(sock, username)

            # Send U type to sender.
            self.pack_n_send(sock, 'U', str(match))
        else:

            cancel_msg = 'x-x Send file cancelled. Continue chatting.'
            self.pack_n_send(sock, 'M', cancel_msg)

    def _serv_x_hndlr(self, data, client_cnxn):
        recd_bytes = 0
        buff_text = self.unpack_msg(client_cnxn)

        file_info = buff_text.decode().split('::')
        filesize = int(file_info[0])

        data = self.pack_message(data, buff_text)
        self.broadcast(data, sockets, client_cnxn, 'recip', self.RECIP_SOCK)

        while recd_bytes < filesize:
            chunk = client_cnxn.recv(4096)
            recd_bytes += len(chunk)
            self.broadcast(chunk, sockets, client_cnxn, 'recip',
                           self.RECIP_SOCK)

    def lookup_user(self, sock, user_query):
        """Checks if user exists. If so, returns user and address.

        Args: 
            sock: (socket) Incoming socket object (from sender)
            user_query: (str) Name of user to look up.
        
        Returns
            match: (bool) True if user found
            user_addr: (str) ip:port of user.
        """
        match = False
        self.RECIP_SOCK = None
        self.SENDER_SOCK = sock

        try:
            user_query = user_query.decode()
        except:
            pass

        for s, n in sock_nick_dict.items():
            if s != sock:  # Avoid self match.
                if n == user_query:
                    match = True
                    self.RECIP_SOCK = s

                    break
                else:
                    match = False

        return match

    def init_client_data(self, sock):
        """Sets nick and addr of user."""
        unique = False
        PROMPT = '-+- Enter nickname:'

        self.pack_n_send(sock, 'M', PROMPT)
        while not unique:
            # sock.recv(1)  # Shed first byte.
            user_name = self.unpack_msg(sock, shed_byte=True).decode()

            if user_name not in sock_nick_dict.values():
                sock_nick_dict[sock] = user_name  # Create socket:nick pair.
                nick_addy_dict[user_name] = sockets[
                    sock]  # Create nick:addr pair.
                unique = True
            else:
                ERR = f"=!= They're already here! Pick something else:"
                print(ERR)
                self.pack_n_send(sock, 'M', ERR)

        # TODO: Fix formatting.
        return user_name

    def start(self):
        Thread(target=self.accepting).start()


if __name__ == "__main__":
    # TODO: Add inputs.
    server = Server()

    addy = ('127.0.0.1', 1515)
    sock = socket.socket()
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(addy)
    except Exception as e:
        print(f'-x- {e}')
        utils.countdown(90)

    sock.listen(5)
    print(f'-+- Listening...')
    server.start()
