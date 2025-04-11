# Container Migration Environment Setup

This repository is designed to set up an environment for running containers using `runc` and performing checkpoint/restore operations with `CRIU`. It serves as a foundation for experiments involving container migration.

This repository is a complement to the article "Migração de Contêineres Utilizando runC e CRIU em Ambiente de Nuvem" submitted to ERAD-SP 2025.

## Objectives

The primary goals of this repository are:
1. Install all necessary dependencies to run containers with `runc`.
2. Set up `CRIU` (Checkpoint/Restore In Userspace) to enable checkpointing and restoring container states.
3. Provide a base environment for conducting experiments related to container migration.

## Prerequisites

Before proceeding, ensure you have the following:
- Debian 12 operating system.
- Root or sudo access to install dependencies and configure the environment.

## Setup Instructions

Follow these steps to prepare the environment:

1. **Clone the Repository**
   ```bash
   git clone https://github.com/Matheusvxz/container-migration.git
   cd container-migration
   ```

1. **Install Make**
   ```bash
   sudo apt install -y make
   ```

1. **Install Dependencies**
   Run the provided script to install all necessary dependencies, including `runc` and `CRIU`, this can take several minutes:
   ```bash
   make
   ```

1. **Verify Installation**
   After running the script, verify that `runc` and `CRIU` are installed correctly:
   ```bash
   sudo runc --version
   sudo criu --version
   ```
1. **Prepare images**
   Create the container filesystem for each application
   ```bash
   cd app-client && make
   cd app-server && make
   cd redis && make
   ```

1. **Server Application**
   Starting server application
   ```bash
      cd app-server
   ```

   1. **Create Unix Domain Socket**
      Create a new terminal and run the command to create a unix domain socket to receive all the sdtout of the container:
      ```bash
      make create-socket
      ```
   1. **Create a temporary filesystem**
      Create a tmpfs folder to improve read and write operations:
      ```bash
      make create-tmpfs
      ```
   1. **Start the container**
      Open a new terminal and start the server container running:
      ```bash
      sudo make run
      ```

1. **Client Application**
   Starting client application
   ```bash
      cd app-client
   ```

   1. **Create Unix Domain Socket**
      Create a new terminal and run the command to create a unix domain socket to receive all the sdtout of the container:
      ```bash
      make create-socket
      ```
   1. **Create a temporary filesystem**
      Create a tmpfs folder to improve read and write operations:
      ```bash
      make create-tmpfs
      ```
   1. **Start the container**
       Open a new terminal and start the client container running:
       ```bash
         sudo make run
      ```

1. **Create a checkpoint**
    Create the checkpoint dump of the server container:
    ```bash
    cd app-server
    sudo make checkpoint
   ```

1. **Create a new socket**
    Close the older server socket and create a new one:
    ```bash
    make create-socket
   ```

1. **Restore the container**
    Restore the container with the dump images:
    ```bash
    sudo make restore
   ```

1. **Validate restauration**
    Check the terminal running the client app to verify if the counter and messages continue from where they were frozen

1. **Redis Application**
   Running experiments with Redis
   ```bash
      cd redis
   ```

   1. **Create Unix Domain Socket**
      Create a new terminal and run the command to create a unix domain socket to receive all the sdtout of the container:
      ```bash
      make create-socket
      ```
   1. **Create a temporary filesystem**
      Create a tmpfs folder to improve read and write operations:
      ```bash
      make create-tmpfs
      ```
   1. **Start the container**
       Open a new terminal and start the client container running:
       ```bash
         sudo make run
      ```

   1. **Load Data into Redis**
      Use the provided script to write data into the Redis container:
      ```bash
      ./load_data.sh
      ```

   1. **Create a Checkpoint**
      Create the checkpoint dump of the Redis container:
      ```bash
      sudo make checkpoint
      ```
      
   1. **Create a new socket**
      Close the older server socket and create a new one:
      ```bash
      make create-socket
      ```

   1. **Restore the Container**
      Restore the Redis container with the dump images:
      ```bash
      sudo make restore
      ```

   1. **Validate Restoration**
      Verify that the data persists in Redis after restoration by connecting to the Redis container and checking the data.

## Notes

- This repository is intended for research and experimentation purposes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
