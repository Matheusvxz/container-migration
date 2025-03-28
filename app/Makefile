# Nome do executável
TARGET = main

# Flags de compilação
CFLAGS = -Wall -Wextra -pedantic -std=c99

# Arquivos objeto
OBJS = $(TARGET).o

# Regra padrão para compilar o executável
all: $(TARGET)

# Regra para compilar o executável
$(TARGET): $(OBJS)
	gcc $(CFLAGS) $(OBJS) -o $(TARGET)

# Regra para compilar os arquivos objeto
%.o: %.c
	gcc $(CFLAGS) -c $< -o $@

# Regra para limpar os arquivos objeto e o executável
clean:
	rm -f $(OBJS) $(TARGET)
