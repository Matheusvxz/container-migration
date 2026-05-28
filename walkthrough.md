# Walkthrough - CRI-O Container Checkpoint and Restore Troubleshooting & Guide

This document summarizes the troubleshooting process, the technical root causes, how they were resolved, and provides a clear, step-by-step guide with all commands to execute container checkpointing and restoration under CRI-O.

---

## 1. Problem Identification and Diagnosis

### Symptoms
When attempting to checkpoint the Redis container via `crictl checkpoint`, the operation failed immediately:
```
crictl checkpoint --export=/tmp/redis-checkpoint.tar 16046995bed00
```
Error:
```
`crun checkpoint` failed: could not load `libcriu.so.2`
```

### Root Cause Analysis
1. **Dynamic Linking & glibc Mismatch:** 
   The pre-installed `crio` and `/usr/libexec/crio/crun` binaries were compiled under a **Nix** environment, which hardcodes RPATH/RUNPATH searching within `/nix/store/...` paths.
   
   When trying to load the required library `libcriu.so.2` from `/usr/local/lib/x86_64-linux-gnu/libcriu.so.2` (compiled on the host Debian OS against the host's `/lib/x86_64-linux-gnu/libc.so.6`), the Nix dynamic linker loaded the host's `libc.so.6`.
   
   The co-existence of two different, conflicting `glibc` instances (Nix glibc 2.40 vs Host glibc 2.41) in the same process caused an immediate **Segmentation Fault (SIGSEGV)** inside `libcriu` initialization during the clone/fork phase.

2. **Outdated CRIU Version:**
   The host had outdated **CRIU 3.19** files manually placed in `/usr/local/lib` and `/usr/local/sbin`. This version has protocol conflicts and socket communication deadlocks when interacting with modern runtimes.

---

## 2. Resolving the Issue (Steps Taken)

To eliminate the double-glibc loading conflict and version mismatches, we switched to the system-native container runtime and libraries.

### Step 1: Install system-native `crun` and `libcriu2`
We installed the official dynamic `crun` and its dependencies from the Debian package repository:
```bash
sudo apt-get update && sudo apt-get install -y crun
```
This installed `crun` (v1.21 with built-in `+CRIU` support) and `libcriu2` (v4.1.1) aligned with the host `glibc`.

### Step 2: Clean up conflicting `/usr/local` files
We removed the outdated manual v3.19 files so the dynamic linker and path resolution fall back to the system packages:
```bash
sudo rm -f /usr/local/lib/x86_64-linux-gnu/libcriu* /usr/local/sbin/criu*
sudo ldconfig
```
This ensured `sudo which criu` points to `/usr/sbin/criu` (v4.1.1) and `ldconfig` resolves `libcriu.so.2` directly from `/lib/x86_64-linux-gnu/libcriu.so.2`.

### Step 3: Symlink CRI-O runtime to use the native `crun`
We backed up the Nix-compiled `crun` and pointed the CRI-O runtime path to the native `/usr/bin/crun`:
```bash
sudo mv /usr/libexec/crio/crun /usr/libexec/crio/crun.bak
sudo ln -s /usr/bin/crun /usr/libexec/crio/crun
```

### Step 4: Restart CRI-O Service
```bash
sudo systemctl restart crio
```

---

## 3. Step-by-Step Execution Guide (All Commands)

Here is the exact sequence of commands to perform container checkpoint and restore.

### Phase A: Checkpointing the Container

1. **Verify the running Redis container:**
   ```bash
   sudo crictl ps
   ```
   *(Let the container ID be `<container_id>`—e.g., `16046995bed00`)*

2. **Create the Checkpoint Archive:**
   Run the checkpoint command exporting the state directly to a `.tar` archive:
   ```bash
   sudo crictl checkpoint --export=/tmp/redis-checkpoint.tar <container_id>
   ```

3. **Verify the checkpoint archive exists:**
   ```bash
   sudo ls -lh /tmp/redis-checkpoint.tar
   ```
   *(You will see an archive of approximately 8.3 MB containing the serialized process memory, file descriptors, and OCI checkpoint state).*

---

### Phase B: Cleanup of the Old Container and Pod

Before restoring, we stop and delete the old pod to release ports (`6379`) and network namespaces:

1. **Stop and remove the running container:**
   ```bash
   sudo crictl stop <container_id>
   sudo crictl rm <container_id>
   ```

2. **Stop and remove the pod sandbox:**
   ```bash
   sudo crictl stopp <pod_id>
   sudo crictl rmp <pod_id>
   ```
   *(Check your Pod ID using `sudo crictl pods`)*

---

### Phase C: Restoring the Container From Checkpoint

1. **Start a new Pod Sandbox:**
   ```bash
   sudo crictl runp /tmp/pod2.json
   ```
   *(This command returns the new Pod Sandbox ID, e.g., `061f4274718fd6b9087db5466e0d81f5b754efd425d71355ae7bf96b3f9bb49c`)*
   *(Let it be `<new_pod_id>`)*

2. **Prepare the restoration configuration (`container-restore.json`):**
   In this configuration, we specify the checkpoint tar archive `/tmp/redis-checkpoint.tar` in the `image` field.
   ```json
   {
     "metadata": {
       "name": "redis"
     },
     "image": {
       "image": "/tmp/redis-checkpoint.tar"
     },
     "command": ["redis-server"],
     "log_path": "redis.log",
     "linux": {
       "security_context": {
         "privileged": false
       }
     }
   }
   ```
   *(This file has been successfully uploaded to the VM at `/tmp/container-restore.json`)*

3. **Create the restored container within the new Pod:**
   ```bash
   sudo crictl create <new_pod_id> /tmp/container-restore.json /tmp/pod2.json
   ```
   *(This command returns the restored container ID, e.g., `448c042d59f22e9608079cbfaf5f654c9ed2a7204f36206eab4a7feae4f96dbc`)*
   *(Let it be `<new_container_id>`)*

4. **Start the restored container:**
   ```bash
   sudo crictl start <new_container_id>
   ```

---

## 4. Verification Results

We verified that the restored container is successfully up and running by performing the following checks:

1. **Verify container status:**
   ```bash
   sudo crictl ps
   ```
   *Output:*
   ```
   CONTAINER           IMAGE          CREATED             STATE               NAME                ATTEMPT             POD ID              POD
   448c042d59f22       <hash>         29 seconds ago      Running             redis               0                   061f4274718fd       unknown
   ```
   The container has been restored to `Running` state!

2. **Verify host processes:**
   ```bash
   ps aux | grep redis
   ```
   *Output:*
   ```
   root   4911  0.3  0.4  41460  9084 ?   Ssl  03:33   0:00 redis-server *:6379
   ```
   The `redis-server` process was successfully restored under the runtime's `--restore` invocation and is listening on port `6379`.
