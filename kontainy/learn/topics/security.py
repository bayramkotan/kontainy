"""Security — the layers, in the order they are usually skipped."""

TOPICS = [
    {
        "title": "The threat model, stated plainly",
        "body": (
            "A container is not a security boundary in the way a virtual "
            "machine is: everything shares one kernel, and a kernel "
            "vulnerability reachable from inside a container is a host "
            "compromise.\n\n"
            "What containers do give is defence in depth — namespaces, "
            "capabilities, seccomp, read-only filesystems — and each layer "
            "is cheap. Where the boundary must hold against hostile code, "
            "use a virtual machine or a sandboxed runtime."),
        "table": {
            "headers": ["Layer", "Stops", "Cost"],
            "rows": [
                ["rootless", "root on the host", "some features"],
                ["`--cap-drop=ALL`", "most privileged operations", "none, usually"],
                ["`--read-only`", "changes to the image", "needs tmpfs for /tmp"],
                ["seccomp", "unusual system calls", "none by default"],
                ["user namespace", "UID reuse across containers", "mapping care"],
                ["a VM (kata, firecracker)", "kernel exploits", "startup time"],
            ]},
    },
    {
        "title": "The docker socket is root",
        "body": (
            "Anything that can talk to /var/run/docker.sock can start a "
            "privileged container that mounts the host's root filesystem. "
            "Membership of the docker group is therefore root, and a "
            "container with the socket mounted owns the machine.\n\n"
            "Tools that \"need Docker access\" in CI are the usual place this "
            "is granted without anyone deciding to."),
        "snippet": (
            "ls -l /var/run/docker.sock\n"
            "getent group docker\n\n"
            "# rootless Docker instead\n"
            "dockerd-rootless-setuptool.sh install\n"
            "export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock"),
        "language": "bash",
        "rule_id": "SEC01",
    },
    {
        "title": "Rootless, and what it actually prevents",
        "body": (
            "Rootless means the engine and the containers run as your user. "
            "A breakout reaches your account, not root — a real difference, "
            "and not the same as safety.\n\n"
            "The costs are known: no ports below 1024 without a sysctl, no "
            "host network devices, and some storage drivers fall back to "
            "slower userspace implementations."),
        "snippet": (
            "podman info --format '{{.Host.Security.Rootless}}'\n"
            "podman unshare cat /proc/self/uid_map\n\n"
            "sudo sysctl net.ipv4.ip_unprivileged_port_start=80"),
        "language": "bash",
        "rule_id": "POD03",
    },
    {
        "title": "Drop capabilities, add back what is needed",
        "body": (
            "Almost nothing needs the default set. Dropping everything and "
            "adding one or two back costs nothing and removes most of what "
            "an exploit would reach for.\n\n"
            "`--privileged` is the opposite: every capability, every "
            "device, no seccomp. It is a debugging switch that ends up in "
            "production because something once failed without it."),
        "snippet": (
            "docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE nginx\n"
            "docker inspect web --format '{{.HostConfig.Privileged}}'\n\n"
            "# what a running container really holds\n"
            "grep CapEff /proc/$(docker inspect -f '{{.State.Pid}}' web)/status\n"
            "capsh --decode=$(grep CapEff /proc/1/status | awk '{print $2}')"),
        "language": "bash",
        "setting_key": "cap-add",
    },
    {
        "title": "Do not run as root inside the container",
        "body": (
            "Root inside a container is not root on the host unless "
            "something else went wrong — but it is one fewer barrier, and "
            "it turns a file-write bug into an image-wide one.\n\n"
            "`USER` in the Dockerfile is the right place; `--user` at run "
            "time is the escape hatch for images that did not bother."),
        "snippet": (
            "# in the Dockerfile\n"
            "RUN adduser -D -u 10001 app\n"
            "USER 10001\n\n"
            "# at run time\n"
            "docker run --user 10001:10001 myapp\n"
            "docker run --security-opt no-new-privileges myapp"),
        "language": "bash",
        "tip": (
            "`no-new-privileges` stops a setuid binary inside the container "
            "from regaining what you dropped. kontainy's create dialog adds "
            "it by default."),
    },
    {
        "title": "Read-only root filesystem",
        "body": (
            "Most services never need to write outside a few directories. "
            "Making the root filesystem read-only turns \"the attacker "
            "dropped a binary\" into an error message.\n\n"
            "The work is finding what does need to be writable: /tmp, a "
            "cache, a pid file. tmpfs mounts cover those without "
            "persisting anything."),
        "snippet": (
            "docker run --read-only \\\n"
            "  --tmpfs /tmp:rw,noexec,nosuid,size=64m \\\n"
            "  --tmpfs /run \\\n"
            "  -v app-data:/data \\\n"
            "  myapp"),
        "language": "bash",
    },
    {
        "title": "Seccomp and AppArmor or SELinux",
        "body": (
            "Seccomp filters system calls; AppArmor and SELinux restrict "
            "what paths and operations a process may use. Both engines "
            "apply a default seccomp profile and, on distributions that "
            "have them, a default MAC profile too.\n\n"
            "Turning them off is the fastest way to make a stubborn "
            "container work and the most expensive way to keep it working."),
        "snippet": (
            "docker inspect web --format '{{.HostConfig.SecurityOpt}}'\n"
            "aa-status | head\n"
            "getenforce\n\n"
            "# narrow, not off\n"
            "docker run --security-opt seccomp=./profile.json myapp"),
        "language": "bash",
    },
    {
        "title": "Secrets: what not to do",
        "body": (
            "`ENV` and `ARG` end up in `docker history`. A file copied in "
            "and deleted later is still in the earlier layer. An "
            "environment variable is visible to anything that can inspect "
            "the container.\n\n"
            "Build secrets exist for build time, and a mounted file or a "
            "secret manager for run time. For Compose and Kubernetes, a "
            "secret mounted as a file beats one injected as an environment "
            "variable."),
        "snippet": (
            "# build time, leaves no layer\n"
            "RUN --mount=type=secret,id=token,target=/run/secrets/token \\\n"
            "    ./fetch-private-deps.sh\n"
            "# docker build --secret id=token,src=token.txt .\n\n"
            "# run time\n"
            "docker run -v /etc/myapp/secrets:/secrets:ro myapp\n"
            "docker history myimage | grep -i -e pass -e token   # check"),
        "language": "bash",
    },
    {
        "title": "Scanning images, and what a CVE list means",
        "body": (
            "Scanners compare the packages in an image against "
            "vulnerability databases. A long list is normal for a "
            "distribution base image and mostly irrelevant: what matters is "
            "whether the vulnerable code is reachable in your context.\n\n"
            "The useful habits are scanning in CI with a threshold, and "
            "choosing smaller bases so there is less to scan."),
        "snippet": (
            "trivy image myapp:1.4\n"
            "trivy image --severity HIGH,CRITICAL --exit-code 1 myapp:1.4\n"
            "grype myapp:1.4\n\n"
            "docker scout cves myapp:1.4"),
        "language": "bash",
    },
    {
        "title": "Signing and verifying images",
        "body": (
            "A tag proves nothing about origin. Signing binds an image "
            "digest to a key or, with keyless signing, to an identity and a "
            "transparency log entry.\n\n"
            "Verification has to happen where it matters — in the cluster's "
            "admission controller or in the engine's policy — otherwise it "
            "is a step in CI that nobody enforces."),
        "snippet": (
            "cosign sign ghcr.io/me/app@sha256:...\n"
            "cosign verify ghcr.io/me/app@sha256:... \\\n"
            "  --certificate-identity-regexp '.*' "
            "--certificate-oidc-issuer https://token.actions.githubusercontent.com\n\n"
            "# Podman's policy file\n"
            "cat /etc/containers/policy.json"),
        "language": "bash",
    },
    {
        "title": "SBOM and provenance",
        "body": (
            "An SBOM lists what is inside an image. Its value is not the "
            "file itself but the question it answers on the day a library "
            "is found vulnerable: which of our images contain it, and which "
            "version.\n\n"
            "Generate it at build time, store it next to the image, and "
            "make it searchable."),
        "snippet": (
            "syft myapp:1.4 -o spdx-json > sbom.json\n"
            "docker buildx build --sbom=true --provenance=true -t myapp:1.4 "
            ".\n\n"
            "grype sbom:sbom.json"),
        "language": "bash",
    },
    {
        "title": "Base images: smaller is safer, to a point",
        "body": (
            "Fewer packages means fewer vulnerabilities and less to attack. "
            "distroless and static images have no shell at all, which stops "
            "a whole class of exploitation — and makes debugging need a "
            "sidecar.\n\n"
            "Alpine is small but uses musl, which occasionally breaks "
            "software that assumed glibc. The honest ranking is: pick the "
            "smallest base your application actually works on."),
        "table": {
            "headers": ["Base", "Size", "Trade"],
            "rows": [
                ["`scratch`", "0", "static binaries only"],
                ["distroless", "~20 MB", "no shell, no package manager"],
                ["alpine", "~8 MB", "musl, not glibc"],
                ["debian-slim", "~75 MB", "familiar, more to patch"],
            ]},
        "snippet": (
            "docker images --format '{{.Repository}}:{{.Tag}}\\t{{.Size}}' | "
            "sort -k2 -h | head"),
        "language": "bash",
    },
    {
        "title": "Registries: credentials and where they are stored",
        "body": (
            "`docker login` writes ~/.docker/config.json. Without a "
            "credential helper, the token is base64 in that file — readable "
            "by anything that can read your home directory, and frequently "
            "copied into CI images by accident.\n\n"
            "A credential helper stores it in the system keyring instead."),
        "snippet": (
            "cat ~/.docker/config.json\n"
            "# \"credsStore\": \"secretservice\"  (or pass, osxkeychain, wincred)\n\n"
            "docker logout ghcr.io\n"
            "podman login --authfile ./auth.json ghcr.io"),
        "language": "bash",
    },
    {
        "title": "The checklist that fits on one screen",
        "body": (
            "Most of the value is in a handful of flags and habits, applied "
            "everywhere rather than perfectly in one place. None of them "
            "costs measurable performance, and each removes a whole class "
            "of mistake.\n\n"
            "If only three are taken: do not mount the socket, drop "
            "capabilities, and do not run as root inside."),
        "table": {
            "headers": ["Do", "Why"],
            "rows": [
                ["run rootless where you can", "a breakout is not root"],
                ["`--cap-drop=ALL`, add back", "removes most privileged paths"],
                ["`USER` in the image", "no root inside either"],
                ["`--read-only` plus tmpfs", "nothing can be dropped in"],
                ["`no-new-privileges`", "setuid cannot regain it"],
                ["pin by digest", "the tag can move under you"],
                ["scan in CI with a threshold", "known holes, known answer"],
                ["never mount the socket", "that is handing over the host"],
            ]},
        "snippet": (
            "docker run -d --name api \\\n"
            "  --user 10001:10001 --cap-drop=ALL \\\n"
            "  --security-opt no-new-privileges \\\n"
            "  --read-only --tmpfs /tmp \\\n"
            "  --memory 512m --pids-limit 200 \\\n"
            "  myapi@sha256:..."),
        "language": "bash",
        "tip": (
            "kontainy's create dialog starts from these defaults, so the "
            "safe version is the one you get without asking."),
    },
]
