# Container Migration Environment Setup

This repository is designed to set up an environment for running containers using `runc` and performing checkpoint/restore operations with `CRIU`. It serves as a foundation for experiments involving container migration.

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

2. **Install Dependencies**
   Run the provided script to install all necessary dependencies, including `runc` and `CRIU`, this can take several minutes:
   ```bash
   make
   ```

3. **Verify Installation**
   After running the script, verify that `runc` and `CRIU` are installed correctly:
   ```bash
   runc --version
   criu --version
   ```
4. **Prepare conteiner root filesystem**
   Using Skopeo to download the busybox image and umoci to unpack, build a demo app for client and server:
   ```bash
   cd container/
   make
   ```

5. **Create Unix Domain Socket**
    Create a unix domain socket to receive all the sdtout of the container
    ```bash
   make create-socket -f Makefile.runc
   ```

6. **Start container**
   Open a new terminal and start the server container running:
   ```bash
   make run-server -f Makefile.runc
   ```

7. **Connect to the server**
   Start the server container demo running:
   ```bash
   ./app/main client 3000 $(cat runc/.ip)
   ```

8. **Create a tmpfs folder**
    Create a tmpfs folder to store the checkpoint dump:
    ```bash
    make create-tmpfs -f Makefile.runc
   ```

9. **Create a checkpoint**
    Create the checkpoint dump of the server container:
    ```bash
    make checkpoint -f Makefile.runc
   ```

10. **Create a new socket**
    Create the checkpoint dump of the server container:
    ```bash
    make create-socket -f Makefile.runc
   ```
11. **Restore the container**
    Restore the container with the dump images:
    ```bash
    make restore -f Makefile.runc
   ```

12. **Validate restauration**
    Check the terminal running the client app to verify if the counter and messages continue from where they were frozen

## Notes

- This repository is intended for research and experimentation purposes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.