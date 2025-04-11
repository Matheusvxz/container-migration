DOCKER_IMAGE = busybox:1.37-glibc
OUTPUT_FOLDER = ./bundle
TAG = test
ID = "client"

CURRENT_DIR = $(shell pwd)
TEMP_DIR = "/tmp/skopeo"
ABS_OUTPUT_FOLDER = $(shell realpath $(CURRENT_DIR)/$(OUTPUT_FOLDER))
CHECKPOINT_PATH := $(CURRENT_DIR)/tmp

.PHONY: all
all: $(ABS_OUTPUT_FOLDER)/config.json
	
$(TEMP_DIR)/index.json:
	skopeo copy docker://docker.io/$(DOCKER_IMAGE) oci:$(TEMP_DIR):$(TAG)

$(ABS_OUTPUT_FOLDER)/umoci.json: $(TEMP_DIR)/index.json
	umoci unpack --image $(TEMP_DIR):$(TAG) $(ABS_OUTPUT_FOLDER) --rootless
	rm $(ABS_OUTPUT_FOLDER)/config.json
	make clean-skopeo

$(CURRENT_DIR)/../app/main:
	cd $(CURRENT_DIR)/../app && make

$(ABS_OUTPUT_FOLDER)/rootfs/app/main: $(CURRENT_DIR)/../app/main $(ABS_OUTPUT_FOLDER)/umoci.json
	mkdir -p $(ABS_OUTPUT_FOLDER)/rootfs/app
	cp $(CURRENT_DIR)/../app/main $(ABS_OUTPUT_FOLDER)/rootfs/app/main
	chmod +x $(ABS_OUTPUT_FOLDER)/rootfs/app/main

$(ABS_OUTPUT_FOLDER)/config.json: $(ABS_OUTPUT_FOLDER)/rootfs/app/main
	cp $(CURRENT_DIR)/config.json $(ABS_OUTPUT_FOLDER)/config.json
	echo "$(ID)" > $(ABS_OUTPUT_FOLDER)/.id 

.PHONY: clean-bundle
clean-bundle:
	sudo rm -r $(ABS_OUTPUT_FOLDER)

.PHONY: clean-skopeo
clean-skopeo:
	rm -r $(TEMP_DIR)

# Spawining container targets

.PHONY: create-socket
create-socket:
	@echo "Creating socket..."
	@if [ -e console.sock ]; then \
		echo "Socket already exists. Removing..."; \
		$(make) clean-socket; \
	fi
	clear
	recvtty -m single $(ABS_OUTPUT_FOLDER)/console.sock

.PHONY: clean-socket
clean-socket:
	@echo "Cleaning up socket..."
	rm -f $(ABS_OUTPUT_FOLDER)/console.sock

.PHONY: run
run:
	@echo "Running server..."
	runc run --console-socket ./console.sock -b $(ABS_OUTPUT_FOLDER) -d "$$(cat $(ABS_OUTPUT_FOLDER)/.id)"

.PHONY: checkpoint
checkpoint:
	@echo "Creating checkpoint..."
	@mkdir -p tmp/
	runc checkpoint --image-path $(CHECKPOINT_PATH)/checkpoint/ \
		--work-path $(CHECKPOINT_PATH)/criu/ \
		--tcp-established \
		"$$(cat $(ABS_OUTPUT_FOLDER)/.id)"

.PHONY: restore
restore:
	@echo "Restoring container..."
	runc restore --image-path $(CHECKPOINT_PATH)/checkpoint/ \
	--work-path $(CHECKPOINT_PATH)/criu/ \
	--tcp-established \
	-b $(ABS_OUTPUT_FOLDER) \
	--console-socket ./console.sock \
	-d "$$(cat $(ABS_OUTPUT_FOLDER)/.id)"

.PHONY: kill
kill:
	@echo "Killing container..."
	runc kill "$$(cat $(ABS_OUTPUT_FOLDER)/.id)" 9 &> /dev/null

.PHONY: delete
delete: kill
	@echo "Deleting container..."
	runc delete "$$(cat $(ABS_OUTPUT_FOLDER)/.id)"

.PHONY: create-tmpfs
create-tmpfs:
	mkdir -p $(CHECKPOINT_PATH)
	sudo mount -t tmpfs none $(CHECKPOINT_PATH)

.PHONY: clean
clean:
	@echo "Cleaning up..."
	umount $(CHECKPOINT_PATH)
	rm -rf $(CHECKPOINT_PATH)
	rm -rf $(ABS_OUTPUT_FOLDER)/console.sock
	@echo "Cleanup complete."