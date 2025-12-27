1. Project Overview

The project executes a client-server messaging application that was created during the B205 Computer Networks module. The system shows fundamental networking principles such as socket-based communication, routing of messages and file transfer through TCP/IP. The software enables real time text messaging, file sharing and simple user management among more than two clients that are connected.

It is also the practical foundation of the project towards analysing the network behaviour and security considerations when needed in Task 2 of the assessment.

2. System Architecture

The architecture is a client server architecture:

Server
Handles clients, routes messages, file transfer and logs.

Client
Connections to server, sends/ receives messages, and transfers files.

The communication is practiced with the help of TCP sockets, which guarantees the safe transfer of data between endpoints.

4. Features Implemented

TCP client-server architecture.

Real-time text messaging

Chunk-based transmission of file transfer.

Management of connection with clients.

Logging of server activity

Connection failure error management.

Basic command line user interface.

6. Usage Instructions

Start the server prior to its being connected by any clients.

Clients are entered by typing a username.

Use provided menu options to:

Send messages

Transfer files

View system responses

Connection and message activity are logged in the server.

7. Security and Limitations

There is no encryption (plaintext TCP).

This is intended to be used in education.

Not to be deployed in a public network.

Enhancements might be incorporated in the future such as encryption (TLS), authentication tokens and access control.
