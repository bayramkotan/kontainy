"""Images & Registries — what you pull, what you push, and what it costs."""

TOPICS = [
    {
        "title": "Manifest, config, layers",
        "body": (
            "An image is three kinds of object addressed by digest: layer "
            "blobs (the filesystem), a config blob (entrypoint, env, "
            "architecture) and a manifest that lists them.\n\n"
            "A multi-architecture image adds one level: a manifest LIST "
            "that points at one manifest per platform, which is why "
            "`docker pull` on an arm64 laptop and an amd64 server fetch "
            "different bytes from the same name."),
        "snippet": (
            "docker manifest inspect nginx:alpine | head -30\n"
            "skopeo inspect --raw docker://nginx:alpine | "
            "python3 -m json.tool | head -20\n\n"
            "docker image inspect nginx:alpine --format "
            "'{{.Architecture}} {{.Os}} {{.Size}}'"),
        "language": "bash",
    },
    {
        "title": "Tags move, digests do not",
        "body": (
            "A tag is a mutable pointer. Pull `myapp:1.4` twice, six months "
            "apart, and you may get two different images with no warning; "
            "that is not a bug, it is what a tag is.\n\n"
            "`name@sha256:...` names one exact image forever. Use it "
            "wherever a build or a deployment must be reproducible, and "
            "tags everywhere else because they are readable."),
        "snippet": (
            "docker images --digests myapp\n"
            "docker inspect myapp:1.4 --format '{{index .RepoDigests 0}}'\n\n"
            "FROM nginx@sha256:0c6b0a...     # pinned\n"
            "docker pull nginx@sha256:0c6b0a..."),
        "language": "bash",
    },
    {
        "title": "Naming: registry, namespace, repository, tag",
        "body": (
            "`ghcr.io/bayramkotan/kontainy:0.1.3` is registry, namespace, "
            "repository and tag. Leave the registry out and Docker assumes "
            "docker.io; leave the namespace out and it assumes `library`, "
            "the official images.\n\n"
            "Podman does not assume: it searches a configured list, which "
            "is safer and is why short names sometimes fail there and work "
            "here."),
        "snippet": (
            "docker pull nginx             # docker.io/library/nginx:latest\n"
            "podman pull docker.io/library/nginx:alpine\n\n"
            "grep -A5 unqualified-search-registries "
            "/etc/containers/registries.conf"),
        "language": "bash",
        "setting_key": "short-name-mode",
    },
    {
        "title": "Multi-architecture images",
        "body": (
            "buildx builds for several platforms and pushes one manifest "
            "list, so one tag serves arm64 laptops and amd64 servers.\n\n"
            "Building for a foreign architecture without native hardware "
            "goes through qemu emulation, which is correct and slow — "
            "minutes become tens of minutes for anything that compiles."),
        "snippet": (
            "docker buildx create --use --name multi\n"
            "docker buildx build --platform linux/amd64,linux/arm64 \\\n"
            "  -t ghcr.io/me/app:1.4 --push .\n\n"
            "docker buildx imagetools inspect ghcr.io/me/app:1.4"),
        "language": "bash",
    },
    {
        "title": "What actually makes an image large",
        "body": (
            "Three things, in order: the base image, build tools left in "
            "the final stage, and package manager caches. A `RUN apt-get "
            "install` without cleaning in the SAME layer keeps the lists "
            "forever, because a later `rm` only hides them.\n\n"
            "`history` shows the cost per instruction, which is where to "
            "look before optimising anything."),
        "snippet": (
            "docker history myapp:1.4 --no-trunc | head\n"
            "docker images --format '{{.Repository}}:{{.Tag}}\\t{{.Size}}' | "
            "sort -k2 -h | tail\n\n"
            "# one layer, cleaned in the same layer\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            "curl \\\n"
            "    && rm -rf /var/lib/apt/lists/*"),
        "language": "bash",
    },
    {
        "title": "Multi-stage, and copying only the result",
        "body": (
            "The compiler, the headers and the test suite do not belong in "
            "the image you ship. A build stage produces the artefact; the "
            "final stage copies it into something minimal.\n\n"
            "It is also the only reliable way to keep a build secret out of "
            "the final image, because a discarded stage is not in it at "
            "all."),
        "snippet": (
            "FROM rust:1.81 AS build\n"
            "WORKDIR /src\n"
            "COPY . .\n"
            "RUN cargo build --release\n\n"
            "FROM gcr.io/distroless/cc\n"
            "COPY --from=build /src/target/release/app /app\n"
            "USER nonroot\n"
            "ENTRYPOINT [\"/app\"]"),
        "language": "bash",
    },
    {
        "title": "Layer caching, and the order that decides it",
        "body": (
            "Each instruction is cached on its inputs, and one miss "
            "invalidates everything after it. So dependencies come before "
            "source, and rarely-changing things come before often-changing "
            "ones.\n\n"
            "`--mount=type=cache` goes further: the package cache survives "
            "between builds without becoming a layer in the image."),
        "snippet": (
            "# syntax=docker/dockerfile:1.7\n"
            "COPY requirements.txt .\n"
            "RUN --mount=type=cache,target=/root/.cache/pip \\\n"
            "    pip install -r requirements.txt\n"
            "COPY . .\n\n"
            "docker build --progress=plain .   # what was cached"),
        "language": "bash",
    },
    {
        "title": "Running your own registry",
        "body": (
            "The registry is a container. Two lines give a local one, which "
            "is enough for a lab, a CI runner or an air-gapped network — "
            "and a pull-through cache removes Docker Hub's rate limit for "
            "everyone behind it.\n\n"
            "Plain HTTP needs the engine told it is insecure, which is the "
            "usual first stumble."),
        "snippet": (
            "docker run -d -p 5000:5000 --name registry -v reg:/var/lib/"
            "registry registry:2\n"
            "docker tag myapp:1.4 localhost:5000/myapp:1.4\n"
            "docker push localhost:5000/myapp:1.4\n\n"
            "# daemon.json, for a registry without TLS\n"
            "{\"insecure-registries\": [\"10.0.0.5:5000\"]}"),
        "language": "bash",
        "setting_key": "insecure-registries",
    },
    {
        "title": "Mirrors and rate limits",
        "body": (
            "Anonymous pulls from Docker Hub are limited per IP address, "
            "and on a shared network the budget is spent by other people. "
            "Logging in raises it; a mirror removes it for the whole "
            "network.\n\n"
            "A mirror is also the answer to slow pulls in CI: the second "
            "job fetches from the machine next door."),
        "snippet": (
            "# daemon.json\n"
            "{\"registry-mirrors\": [\"https://mirror.internal:5000\"]}\n\n"
            "# a pull-through cache\n"
            "docker run -d -p 5000:5000 \\\n"
            "  -e REGISTRY_PROXY_REMOTEURL=https://registry-1.docker.io \\\n"
            "  --name mirror registry:2"),
        "language": "json",
        "setting_key": "registry-mirrors",
    },
    {
        "title": "Credentials and where they are kept",
        "body": (
            "`login` writes ~/.docker/config.json. Without a credential "
            "helper the token sits there base64-encoded, which is not "
            "encryption — and that file gets copied into images and CI "
            "artefacts more often than anyone would like.\n\n"
            "Podman keeps its own auth file, and both accept an explicit "
            "path, which is what CI should use."),
        "snippet": (
            "cat ~/.docker/config.json\n"
            "# \"credsStore\": \"pass\" | \"secretservice\" | \"osxkeychain\"\n\n"
            "podman login --authfile ./auth.json ghcr.io\n"
            "echo $TOKEN | docker login ghcr.io -u me --password-stdin"),
        "language": "bash",
    },
    {
        "title": "Housekeeping: what to delete and when",
        "body": (
            "Dangling images are layers no tag points at — usually the "
            "previous build of something. `image prune` removes those; "
            "`-a` removes every image no container uses, which on a "
            "development machine is most of them.\n\n"
            "A filter by age is the version that keeps the working set: "
            "remove what has not been touched for a month."),
        "snippet": (
            "docker image prune\n"
            "docker image prune -a --filter 'until=720h'\n"
            "docker images -f dangling=true\n\n"
            "podman image prune -a --filter 'until=30d'"),
        "language": "bash",
    },
    {
        "title": "OCI, and why any engine can run any image",
        "body": (
            "The image format, the distribution protocol and the runtime "
            "behaviour are specifications, not one vendor's product. That "
            "is why Podman runs images built by Docker, Buildah pushes to "
            "any registry, and Kubernetes pulls from all of them.\n\n"
            "In practice the only portability problems are architecture and "
            "the assumptions inside the image, not the format."),
        "snippet": (
            "skopeo copy docker://nginx:alpine oci:nginx-oci:alpine\n"
            "ls nginx-oci/                    # blobs, index.json, oci-layout\n\n"
            "podman run docker.io/library/nginx:alpine   # built by anyone"),
        "language": "bash",
        "links": [("OCI Image Spec",
                   "https://github.com/opencontainers/image-spec")],
    },
]
