CRIU_VERSION = 4.1
TMP_DIR = /tmp/criu

GO_VERSION = 1.23.7
GO_TARBALL = go$(GO_VERSION).linux-amd64.tar.gz
GO_INSTALL_DIR = /usr/local

RUNC_VERSION = 1.2.6

NETNS_VERSION = 0.5.3
NETNS_SHA256= 8a3a48183ed5182a0619b18f05ef42ba5c4c3e3e499a2e2cb33787bd7fbdaa5c

UMOCI_VERSION = 0.4.7
UMOCI_SHA256= 6abecdbe7ac96a8e48fdb73fb53f08d21d4dc5e040f7590d2ca5547b7f2b2e85

.PHONY: default
default: 
	make install-deps
	@if ! command -v sudo criu >/dev/null 2>&1; then \
		echo "CRIU is not installed. Installing CRIU..."; \
		make install-criu; \
	else \
		echo "CRIU is already installed. Skipping installation."; \
	fi
	@if ! command -v go >/dev/null 2>&1; then \
		echo "Go is not installed. Installing Go..."; \
		make install-go; \
	else \
		echo "Go is already installed. Skipping installation."; \
	fi
	@if ! command -v sudo runc >/dev/null 2>&1; then \
		echo "runC is not installed. Installing runC..."; \
		make install-runc; \
	else \
		echo "runC is already installed. Skipping installation."; \
	fi
	@if ! command -v netns >/dev/null 2>&1; then \
		echo "netns is not installed. Installing netns..."; \
		make install-netns; \
	else \
		echo "netns is already installed. Skipping installation."; \
	fi
	@if ! command -v umoci >/dev/null 2>&1; then \
		echo "umoci is not installed. Installing umoci..."; \
		make install-umoci; \
	else \
		echo "umoci is already installed. Skipping installation."; \
	fi

.PHONY: update-apt
update-apt:
	@echo "Updating apt repository..."
	sudo apt update

.PHONY: install-deps
install-deps: update-apt
	@echo "Installing CRIU dependencies..."
	sudo apt install -y --no-install-recommends build-essential libprotobuf-dev libprotobuf-c-dev \
	protobuf-c-compiler protobuf-compiler python3-protobuf pkg-config uuid-dev libnl-3-dev libseccomp-dev \
	iproute2 libnftables-dev libcap-dev libnet1-dev libgnutls28-dev asciidoc xmlto linux-libc-dev git tmux \
	skopeo;
	

$(TMP_DIR)/criu-$(CRIU_VERSION).tar.gz:
	mkdir -p $(TMP_DIR); \
	curl -o $(TMP_DIR)/criu-$(CRIU_VERSION).tar.gz -L http://github.com/checkpoint-restore/criu/archive/v$(CRIU_VERSION)/criu-$(CRIU_VERSION).tar.gz; \

$(TMP_DIR)/criu-$(CRIU_VERSION)/Makefile: $(TMP_DIR)/criu-$(CRIU_VERSION).tar.gz
	tar -xzf $(TMP_DIR)/criu-$(CRIU_VERSION).tar.gz -C $(TMP_DIR)

.PHONY: build-criu
build-criu: $(TMP_DIR)/criu-$(CRIU_VERSION)/Makefile
	@if ! command -v criu >/dev/null 2>&1; then \
		cd $(TMP_DIR)/criu-$(CRIU_VERSION)/; \
		make; \
	else \
		echo "CRIU is already installed."; \
	fi

.PHONY: install-criu
install-criu: $(TMP_DIR)/criu-$(CRIU_VERSION)/criu
	make build-criu; 
	echo "Installing CRIU...";
	cd $(TMP_DIR)/criu-$(CRIU_VERSION);
	sudo make install;
	echo "CRIU installation complete.";
	make clean;

.PHONY: clean
clean:
	@echo "Cleaning up..."
	rm -rf $(TMP_DIR)
	echo "Cleanup complete."

# GO installation
.PHONY: setup-go-env
setup-go-env:
	@echo "Setting up Go environment variables..."
	@if ! echo $$PATH | grep -q "$(GO_INSTALL_DIR)/go/bin"; then \
		echo "export PATH=$(GO_INSTALL_DIR)/go/bin:$$PATH" >> ~/.profile; \
		echo "export GOPATH=$(GO_INSTALL_DIR)/go/bin" >> ~/.profile; \
		echo "Go environment variables added to ~/.profile"; \
		source ~/.profile; \
	else \
		echo "Go is already in the PATH."; \
	fi

.PHONY: install-go
install-go:
	@echo "Downloading and installing Go $(GO_VERSION)..."
	curl -O https://dl.google.com/go/$(GO_TARBALL)
	sudo tar -C $(GO_INSTALL_DIR) -xzf $(GO_TARBALL)
	rm -f $(GO_TARBALL)
	echo "Go $(GO_VERSION) installation complete."
	@echo "Setting up Go environment..."
	make setup-go-env
	rm -f $(GO_TARBALL)

# runC installation
.PHONY: install-runc
install-runc:
	@echo "Installing runC..."
	sudo mkdir -p $(GOPATH)/src/github.com/opencontainers/runc
	sudo chmod 777 $(GOPATH)/src/github.com/opencontainers/runc
	git clone --depth 1 --branch v$(RUNC_VERSION) https://github.com/opencontainers/runc.git $(GOPATH)/src/github.com/opencontainers/runc
	cd $(GOPATH)/src/github.com/opencontainers/runc && make && sudo make install

# netns installation
.PHONY: install-netns
install-netns:
	@echo "Installing netns..."
	sudo curl -fSL "https://github.com/genuinetools/netns/releases/download/v$(NETNS_VERSION)/netns-linux-amd64" -o "/usr/local/bin/netns" \
		&& echo "$(NETNS_SHA256)  /usr/local/bin/netns" | sha256sum -c - \
		&& sudo chmod a+x "/usr/local/bin/netns"
	echo "netns installation complete."

# umoci install
.PHONY: install-umoci
install-umoci:
	@echo "Installing umoci..."
	sudo curl -fSL "https://github.com/opencontainers/umoci/releases/download/v$(UMOCI_VERSION)/umoci.amd64" -o "/usr/local/bin/umoci" \
		&& echo "$(UMOCI_SHA256)  /usr/local/bin/umoci" | sha256sum -c - \
		&& sudo chmod a+x "/usr/local/bin/umoci"
	echo "umoci installation complete."