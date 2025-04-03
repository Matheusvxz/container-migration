#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>


int main(int argc, char const *argv[]) {
    int port;
    char *ip = "127.0.0.1";

    if (argc < 3) {
        fprintf(stderr, "Uso: %s <server|client> <porta> <IP>\n", argv[0]);
        exit(EXIT_FAILURE);
    }

    port = atoi(argv[2]);

    if(argc == 4) {
        ip = argv[3];
    }

    if (strcmp(argv[1], "server") == 0) {
        printf("Server mode selected\n");

        // Código do servidor
        int server_fd, client_socket, valread;
        struct sockaddr_in address;
        int opt = 1;
        int addrlen = sizeof(address);
        char buffer[1024] = {0};
        char *hello = "Mensagem recebida, aqui está a resposta!";
        int msgCounter = 0;

        // Criando socket do servidor
        if ((server_fd = socket(AF_INET, SOCK_STREAM, 0)) == 0) {
            perror("Falha na criação do socket");
            exit(EXIT_FAILURE);
        }

        // Configurando opções do socket
        if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt))) {
            perror("Falha em setsockopt");
            exit(EXIT_FAILURE);
        }
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = INADDR_ANY;
        address.sin_port = htons(port);

        // Binding do socket
        if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
            perror("Falha no bind");
            exit(EXIT_FAILURE);
        }

        // Escutando por conexões
        if (listen(server_fd, 3) < 0) {
            perror("Falha em listen");
            exit(EXIT_FAILURE);
        }

        // Aceitando conexões
        if ((client_socket = accept(server_fd, (struct sockaddr *)&address, (socklen_t*)&addrlen)) < 0) {
            perror("Falha em accept");
            exit(EXIT_FAILURE);
        }

        while (1) {
            // Limpando o buffer
            memset(buffer, 0, sizeof(buffer));

            // Recebendo mensagem
            valread = read(client_socket, buffer, 1024);
            printf("Mensagem recebida: %s\n", buffer);
            printf("Message counter: %d\n", msgCounter);

            // Enviando resposta
            send(client_socket, hello, strlen(hello), 0);
            printf("Resposta enviada.\n");
            msgCounter = msgCounter + 1;
        }

        // Fechando sockets (o código nunca chega aqui no loop infinito)
        close(client_socket);
        close(server_fd);

    } else if (strcmp(argv[1], "client") == 0) {
        printf("Client mode selected\n");
        // Código do cliente
        int sock = 0, valread;
        struct sockaddr_in serv_addr;
        char *hello = "Olá do cliente!";
        char buffer[1024] = {0};
        int msgCounter = 0;

        // Criando socket
        if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
            printf("\n Socket creation error \n");
            return -1;
        }

        serv_addr.sin_family = AF_INET;
        serv_addr.sin_port = htons(port);

        // Convertendo endereço IPv4 de texto para binário
        if(inet_pton(AF_INET, ip, &serv_addr.sin_addr)<=0) {
            printf("\nInvalid address/ Address not supported \n");
            return -1;
        }

        // Conectando ao servidor
        if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
            printf("\nConnection Failed \n");
            return -1;
        }

        while(1) {
            // Enviando mensagem
            printf("Message counter: %d\n", msgCounter);
            send(sock , hello , strlen(hello) , 0 );
            printf("Mensagem enviada\n");

            // Recebendo resposta
            valread = read( sock , buffer, 1024);
            printf("Resposta do servidor: %s\n",buffer );

            sleep(1);
            msgCounter = msgCounter + 1;
        }

        // Fechando o socket
        close(sock);

    } else {
        fprintf(stderr, "Argumento inválido. Use 'server' ou 'client'.\n");
        exit(EXIT_FAILURE);
    }

    return 0;
}