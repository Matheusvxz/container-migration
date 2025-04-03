DOCKER_IMAGE = busybox:1.37-glibc
OUTPUT_FOLDER = ../runc
TAG = test

CURRENT_DIR = $(shell pwd)
TEMP_DIR = "/tmp/skopeo"
ABS_OUTPUT_FOLDER = $(shell realpath $(CURRENT_DIR)/$(OUTPUT_FOLDER))


.PHONY: all
all: $(ABS_OUTPUT_FOLDER)/rootfs/app/main
	
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

.PHONY: clean-runc
clean-runc:
	sudo rm -r $(ABS_OUTPUT_FOLDER)

.PHONY: clean-skopeo
clean-skopeo:
	rm -r $(TEMP_DIR)