<div align="center">

# 🐳 kontainy

**Containers and virtualisation — in one window, or one command**
Docker, Podman, Kubernetes, KVM/libvirt, Hyper-V, Incus and LXD. Every target
selectable, every setting explained, every command shown before it runs.

![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS-f9e2af?style=for-the-badge)

</div>

---

## 🎯 Why kontainy exists

Run Docker and Podman on the same machine for a week and you will meet all of
this: `docker context use` reports success and changes nothing, containers
"disappear" after installing Docker Desktop, a memory limit is accepted and
silently ignored, a log file quietly fills the root disk, and `podman pull
nginx` fails on a name that works everywhere else.

None of these produce an error message. That is the problem kontainy is built
around.

**kontainy does not trust the context system.** It connects to *every* socket
it finds, separately, and shows them all in one table with an Engine column. A
container is never lost — you can see which engine holds it.

<p align="center">
</p>

The `docker` CLI resolves its target through five layers, and the top one wins:

```
1. -H / --host flag
2. DOCKER_HOST environment variable
3. DOCKER_CONTEXT environment variable
4. ~/.docker/config.json → currentContext
5. unix:///var/run/docker.sock
```

If `DOCKER_HOST` is set, the context is ignored completely — which is why
`docker context use` can say "success" and do nothing at all. kontainy shows
this chain layer by layer and marks the winner.

---

## 🧭 Technologies

Every container and virtualisation technology has the same shape under a
different name: a set of **targets**, one of them **active**, each holding
**objects**. kontainy gives each one the same page — a dropdown of targets
at the top, the active one selected, and tabs underneath — and the same
`ky` commands.

| Technology | Target | Objects | 🐧 Linux | 🪟 Windows | 🍎 macOS |
|:---|:---|:---|:---:|:---:|:---:|
| 🐳 **Docker** | contexts | containers | ✅ | ✅ | ✅ |
| 🦭 **Podman** | system connections | containers | ✅ | ✅ | ✅ |
| ☸ **Kubernetes** | kubeconfig contexts | pods | ✅ | ✅ | ✅ |
| 🖥 **KVM / libvirt** | connection URIs | virtual machines, networks | ✅ | ✅ *via WSL 2* | ✅ |
| 🪟 **Hyper-V** | hosts, local and remote | virtual machines, virtual switches | — | ✅ | — |
| 🧱 **Incus** | remotes | instances | ✅ | ✅ *via WSL 2* | — |
| 📦 **LXD** | remotes | instances | ✅ | ✅ *via WSL 2* | — |

A technology that cannot exist on your system is not shown at all.

On every page you can **switch the active target**, **add**, **remove** and
**test** one; **start, stop, restart and remove** objects one at a time or
**all at once**; manage the **system services** a technology depends on;
**install** it with the command for your own distribution; and pin new
terminals to a target through your **shell profile**. The line under the
dropdown says what the active target really is — *rootful · system socket
(root)*, *rootless · your user socket*, *Docker Desktop · Linux engine in
WSL 2*, *remote over SSH*.

### 🪟 On Windows, WSL is the vehicle

WSL is not something kontainy asks you to manage for its own sake. It is
what Docker Desktop and podman machine run their Linux engines in — and what
kontainy uses to bring the Linux tools to Windows:

- **KVM/libvirt, Incus and LXD** run inside a WSL 2 distribution. Their
  pages say *via WSL · Ubuntu-24.04* and show every command exactly as it
  runs: `wsl -d Ubuntu-24.04 -- virsh list --all`. Installing them uses that
  distribution's own package manager, as root inside WSL — no Windows
  administrator rights needed.
- **KVM inside WSL** needs Windows 11 with nested virtualization. Without it
  there is no `/dev/kvm` and QEMU falls back to slow emulation; the KVM page
  tells you, and how to turn it on (`nestedVirtualization=true` in
  `.wslconfig`).
- **Docker and Podman** pages carry a *Backend* tab showing the distribution
  their engine lives in (`docker-desktop`, `podman-machine-default`), with
  restart, `wsl --shutdown` and `.wslconfig` — the usual cures when Docker
  Desktop stops answering.
- Which distribution carries the Linux tools is kontainy's own setting
  (`ky wsl use NAME`). Your default distribution is never changed, and
  `docker-desktop` is never used for it.

## 🎓 Educational by Design

kontainy never hides the command it is running. Create a container, change a
setting, apply a fix — the **exact shell command** appears in the command strip
at the bottom of every page, ready to copy. Every command is also written to a
persistent history you can export as a shell script.

The point is not convenience. The point is that you should be able to do the
same thing **without kontainy** afterwards.

<p align="center">
</p>

This runs through the whole application:

- **Create Container** — the preview grows as you tick boxes, syntax
  highlighted, and the same definition renders as a `docker run` command, a
  systemd Quadlet unit, or a compose service
- **Config Catalog** — every key shows its CLI equivalent, which file it lives in,
  and whether a restart is needed
- **Diagnostics** — every finding ends in a command, and says whether it runs
  in user scope or needs root
- **Learn** — every snippet is a command you can actually type, with a Copy
  button
- **History & Log** — every command this session, filterable, exportable

---

## 📦 Install

```bash
pip install kontainy
kontainy          # or the short name:  ky
```

The same program answers to three names: **`ky`** to type, **`kontainy`** to
read, and `kty` kept from the first release. On Windows, `kontainy-gui`
opens the window without a console.

<details>
<summary><b>🐧 On Linux, pip may refuse to install</b></summary>
<br>

Most current distributions mark the system Python as *externally managed*
(PEP 668), so a plain `pip install` stops with
`error: externally-managed-environment`. Two ways around it:

```bash
# Isolated — recommended, no system packages touched
pipx install kontainy

# Into the system Python — needs the override flag
sudo pip install kontainy --break-system-packages --no-cache-dir -U
```

The same flag applies when upgrading a system-wide install later on.

</details>

### Upgrading

```bash
pip install -U kontainy --no-cache-dir
```

**Help → Check for Updates** asks PyPI — the same place `pip` looks — and
shows the command above, with the `--break-system-packages` flag added when
a system-wide install needs it. It runs in the background, so the window
stays usable while the network is slow, and says so plainly when there is no
network rather than hanging.

Or download the standalone binary — **no Python required:**

| Platform | File | Notes |
|:--------:|:-----|:------|
| 🐧 **Linux** | [`kontainy-x86_64.AppImage`](https://github.com/bayramkotan/kontainy/releases/latest) | `chmod +x` then run — the fully supported target |
| 🪟 **Windows** | [`kontainy.exe`](https://github.com/bayramkotan/kontainy/releases/latest) | Portable. Docker Desktop and `podman machine` only |
| 🍎 **macOS** | [`kontainy-macOS-arm64`](https://github.com/bayramkotan/kontainy/releases/latest) | Apple Silicon |

> **Linux is the first-class target.** Rootless Podman, Quadlet, systemd units,
> subuid mapping and linger only exist there, and roughly half the diagnostic
> rules are Linux-specific. The Windows and macOS builds work against Docker
> Desktop and `podman machine`, and disable what does not apply.

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🔌 Engine discovery
- Connects to **every socket found**, never just the active context
- Docker local daemon, Docker Desktop for Linux, Rancher Desktop, Colima
- Podman **rootful and rootless** sockets
- Resolved CLI target chain, with the winning layer marked
- Detects the `podman-docker` shim (`docker` that is really Podman)
- **No external dependencies** — talks the Docker Engine API over the UNIX
  socket directly, no `docker-py`, no `requests`

### 📦 Containers
- Every engine in **one table**, with an Engine column
- Start, stop, restart, remove
- Summary, port map and raw JSON inspection
- Create with the **full run surface** (see below)
- 17 ready-made templates

</td>
<td width="50%" valign="top">

### ⚙️ Settings
- **152 keys** across Docker and Podman
- Declared value, **effective value**, and the file it came from
- The full override chain: `/usr/share` → `/etc` → `~/.config`
- Red flag when declared and effective disagree — the setting is being ignored
- **65 keys editable** without elevation; the rest read-only with a command
- Comment-preserving TOML writes, atomic, with a `.bak` backup

### 🔬 Diagnostics
- **19 rules**: detect → explain → fix command
- Each links to a catalogue key and a Learn topic
- Detection never requires root

### 📚 Learn
- 16 categories, from namespaces to Kubernetes, KVM and LXC
- Syntax-highlighted, copyable snippets

### ℹ️ Help and updates
- **About** in one box: version, licence, platform, Python and Qt versions
- **Check for Updates** against PyPI, in the background
- Straight to the **GitHub repository**, the **PyPI page** and **Report a Bug**
- A **Documentation** submenu: Docker, Podman, Quadlet, Kubernetes, libvirt

</td>
</tr>
</table>

---

## ⚙️ The settings catalogue

This is what kontainy is for. Docker Desktop and Podman Desktop were designed
for ease of use, and hide most of the configuration surface as a result —
`daemon.json` gets a raw JSON box with no explanation, `containers.conf` gets
nothing at all.

|  | Docker Desktop | Podman Desktop | **kontainy** |
|---|:---:|:---:|:---:|
| Start / stop containers | ✅ | ✅ | ✅ |
| `daemon.json` editing | raw JSON box | ✗ | **structured, explained, validated** |
| `containers.conf` / `storage.conf` | ✗ | ✗ | **full catalogue** |
| `registries.conf`, `short-name-mode` | ✗ | ✗ | **full catalogue** |
| Which file a value came from | ✗ | ✗ | **override chain shown** |
| Declared vs effective value | ✗ | ✗ | **compared, mismatch flagged** |
| All engines in one table | ✗ | ✗ | **✅ with Engine column** |
| Where your terminal points | ✗ | ✗ | **✅ resolved chain** |
| "What goes wrong" note per setting | ✗ | ✗ | **✅ 66 of 152** |

**152 settings** — 56 Docker, 67 Podman, 29 shared — spread across ten
surfaces:

| Surface | Keys | Covers |
|:---|:---:|:---|
| 🌐 Networking | 25 | address pools, bridge, MTU, DNS, iptables/nftables, netavark, pasta |
| 🔐 Security | 23 | capabilities, seccomp, AppArmor, SELinux, user namespaces |
| 📊 Resource limits | 23 | memory, CPU, PIDs, ulimits, block I/O, OOM |
| ⚙️ Engine / Daemon | 19 | runtimes, cgroup manager, live restore, events |
| 📦 Registry | 18 | mirrors, insecure registries, short-name mode, pull policy |
| 🧱 Container | 14 | restart policy, healthcheck, mounts, init, timezone |
| 💾 Storage | 13 | drivers, graphroot, overlay options, quotas |
| 🔧 systemd / Quadlet | 8 | `.container` unit keys, auto-update, linger |
| 📝 Logging | 6 | drivers and rotation |
| 🏗️ Build | 3 | BuildKit and cache garbage collection |

Every entry carries: the key, the file it lives in, its type and valid choices,
the default, the **CLI equivalent**, whether a restart is needed, user or root
scope, a risk level, a description — and for 66 of them, **what goes wrong**: what
breaks when the setting is misunderstood.

> Listing a setting is easy. Writing down what happens when it is wrong is not,
> and no rival tool does it.

---

## 🔬 Diagnostics

The equivalent of a linter for your container setup. Every rule says three
things: what was found, why it happens, and the command that fixes it.

<p align="center">
</p>

**19 rules**, none of which need root to detect:

| Group | Rules | Examples |
|:---|:---:|:---|
| **CTX** context | 6 | `DOCKER_HOST` overriding the context · Desktop leftovers (`credsStore`) · CLI plugins shadowing the distribution's · the `podman-docker` shim |
| **POD** Podman / rootless | 4 | socket not enabled · linger off, so containers die at logout · missing `subuid` range · auto-update timer inactive |
| **NET** networking | 3 | Docker address pool clashing with the local network or VPN · rootless ports below 1024 · nftables without the iptables layer |
| **DSK** disk | 2 | unlimited `json-file` logs filling the root disk · BuildKit cache that `image prune` does not touch |
| **RES** resources | 1 | cgroupfs on rootless cgroup v2, where limits are silently ignored |
| **SVC** systemd | 1 | `docker.socket` restarting the daemon you just stopped |
| **DKR** Docker Desktop | 1 | `/dev/kvm` missing or not readable |
| **PER** permissions | 1 | socket permission denied, group membership not yet applied |

---

## 📦 Templates

*You should not have to hunt for example code.* Seventeen ready-made
definitions, each carrying the details people get wrong when copying from a
blog post: the named volume that keeps the data, the environment variable the
image will not start without, a health start period long enough for the service
to come up, and a capability set that is not simply `--privileged`.

| Category | Templates |
|:---|:---|
| **Databases** | PostgreSQL 16 · MariaDB 11 · Redis 7 · MongoDB 7 |
| **Web** | nginx · Caddy 2 · Traefik 3 |
| **Tooling** | MinIO · Gitea · Vaultwarden · n8n · Pi-hole |
| **Monitoring** | Grafana · Prometheus |
| **Development** | JupyterLab · code-server · Ollama |

Each renders three ways from the same definition:

<details>
<summary><b>📋 PostgreSQL, all three formats</b></summary>
<br>

```bash
podman run -d \
  --name postgres \
  --restart=unless-stopped \
  -p 5432:5432 \
  -v pgdata:/var/lib/postgresql/data \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=<CHANGE_ME> \
  --cap-drop=ALL \
  --cap-add=CHOWN --cap-add=DAC_OVERRIDE --cap-add=FOWNER \
  --cap-add=SETGID --cap-add=SETUID \
  --memory=1g \
  --health-cmd='pg_isready -U postgres' \
  --health-start-period=30s \
  docker.io/library/postgres:16
```

```ini
[Unit]
Description=PostgreSQL 16

[Container]
Image=docker.io/library/postgres:16
PublishPort=5432:5432
Volume=pgdata:/var/lib/postgresql/data
Environment=POSTGRES_PASSWORD=CHANGE_ME
DropCapability=ALL
AddCapability=CHOWN
AutoUpdate=registry

[Service]
Restart=always

[Install]
WantedBy=default.target
```

```yaml
services:
  postgres:
    image: docker.io/library/postgres:16
    restart: unless-stopped
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    cap_drop:
      - ALL

volumes:
  pgdata:
```

</details>

**Quadlet generation is the part no other GUI has.** `podman generate systemd`
is deprecated; Quadlet replaced it, and nothing but a text editor writes those
units today.

---

## 🧱 Create Container

Rival tools give you image, name, ports and volumes. kontainy gives you the
whole surface, across seven tabs, with a live command preview underneath:

| Tab | Covers |
|:---|:---|
| **Basics** | image, name, command, entrypoint, working dir, user, restart policy, environment, labels |
| **Network** | network mode, published ports, hostname, DNS, extra hosts |
| **Storage** | volumes and bind mounts with `:ro` `:z` `:Z` propagation, tmpfs, read-only root, shm size |
| **Resources** | memory, swap, CPUs, cpuset, shares, PID limit, ulimits, OOM score |
| **Security** | privileged, no-new-privileges, user namespace, seccomp, AppArmor, SELinux, **18 capability checkboxes** |
| **Health** | command, interval, timeout, retries, start period |
| **Advanced** | init, TTY, log driver and options, sysctls, devices, pod, passthrough flags |

---

## 📚 Learn

kontainy teaches container management, not kontainy. **16 categories**,
target 204 topics, each with explanation, diagram, table and runnable snippet.

| Category | Topics | Covers |
|:---|:---:|:---|
| ⚡ Quick Start | 8 | first container, ports, volumes, cleanup |
| 📦 Container Internals | 14 | namespaces, cgroups v1/v2, capabilities, overlayfs, OCI specs |
| 🐳 Docker | 18 | architecture, run flags, contexts, `daemon.json`, BuildKit |
| 🦭 Podman | 18 | daemonless design, rootless, pods, `containers.conf` |
| ⚙️ systemd & Quadlet | 10 | units, linger, socket activation, `.container` files |
| ☸️ Kubernetes | 20 | pods, deployments, services, kubeconfig, probes, RBAC |
| 🖥️ KVM / QEMU / libvirt | 12 | domain XML, qcow2, virtio, snapshots, VFIO passthrough |
| 🧱 LXC / LXD / Incus | 10 | system containers, idmap, storage pools, clustering |
| 🌐 Networking | 14 | bridges, macvlan, DNS, nftables, MTU, subnet clashes |
| 💾 Storage | 12 | volumes, bind mounts, overlay2, quotas, SELinux labels |
| 🔐 Security | 14 | rootless, capabilities, seccomp, signing, scanning, SBOM |
| 🏗️ Images & Registries | 12 | manifests, digests, multi-arch, buildah, skopeo, mirrors |
| 🎼 Compose & Orchestration | 10 | compose schema, profiles, healthchecks |
| 🔍 Troubleshooting | 14 | lost containers, permissions, full disks, exit codes |
| 🚀 Performance | 10 | crun vs runc, overlay vs fuse, cache strategy |
| 🔄 Migration & Interop | 8 | Docker to Podman, the shim, Desktop leftovers, WSL2, CI |

Diagnostic rules link into Learn: the rule tells you *what to do*, the topic
explains *why*.

---

## 🔐 Privilege model

**kontainy never elevates privileges.** No `pkexec`, no `sudo`, no `runas`.

| File | Scope | What kontainy does |
|:---|:---:|:---|
| `~/.config/containers/containers.conf` | 👤 user | **writes** |
| `~/.config/containers/storage.conf` | 👤 user | **writes** |
| `~/.config/containers/registries.conf` | 👤 user | **writes** |
| `~/.config/containers/systemd/*` (Quadlet) | 👤 user | **writes** |
| `~/.docker/config.json` | 👤 user | **writes** |
| `/etc/docker/daemon.json` | 🖥 root | read-only + copyable command |
| `/etc/containers/*` | 🖥 root | read-only + copyable command |
| `/etc/subuid`, `/etc/subgid` | 🖥 root | read-only + copyable command |
| `/usr/share/containers/*` | 📦 distribution | read-only, shown in the override chain |

Writes take a `.bak` backup, land atomically through `os.replace` — a
half-written `daemon.json` stops the daemon from starting at all — and preserve
existing comments in TOML files, including the ones explaining the very setting
being changed.

Rootless Podman keeps its entire configuration under `~/.config`, which is why
this model costs so little: **65 of the 152 settings are directly editable.**

---

## 🚀 Quick Start

### From PyPI

```bash
pip install kontainy
ky
```

### From source

```bash
git clone https://github.com/bayramkotan/kontainy.git
cd kontainy
python main.py
```

That is the whole thing. With no PySide6 installed, kontainy shows the
commands it would run, asks, and — if you agree — creates `.venv` beside the
checkout, installs itself into it in editable mode, and starts the window
from there. Nothing is installed into your system Python, and refusing is a
normal answer: the commands are printed either way.

`python main.py --setup` does it without asking, for a script;
`python main.py --no-setup` never does, and prints the commands instead.

Or do it by hand:

```bash
git clone https://github.com/bayramkotan/kontainy.git
cd kontainy
python -m venv .venv
.venv/bin/pip install -e .
```

The last line installs the repository in *editable* mode, which puts the
`kontainy`, `ky` and `kty` commands into the virtual environment and points
them at the checked-out code — edit a file and `ky` runs the new version.
Activate the environment (`source .venv/bin/activate`, or
`.venv\Scripts\activate` on Windows) and run:

```bash
ky
```

Running `python main.py` also works, but installs no commands.

### Linux — system dependencies

PySide6 needs the XCB platform libraries. On a minimal install:

```bash
# Arch / CachyOS
sudo pacman -S --needed libxcb xcb-util-cursor xcb-util-keysyms \
  xcb-util-wm xcb-util-image xcb-util-renderutil libxkbcommon-x11

# Debian / Ubuntu
sudo apt install libxcb-cursor0 libxcb-xinerama0 libxcb-icccm4 \
  libxkbcommon-x11-0 libxcb-keysyms1 libxcb-image0 libxcb-render-util0

# Fedora
sudo dnf install xcb-util-cursor xcb-util-keysyms xcb-util-wm \
  xcb-util-image xcb-util-renderutil libxkbcommon-x11
```

For Podman support, enable the API socket:

```bash
systemctl --user enable --now podman.socket
loginctl enable-linger $USER    # so containers survive logout
```

### CLI

kontainy is a GUI, and **everything the GUI does also works headless** — on a
server with no display, over SSH, or in a script. The command line drives
the same code as the window, never loads Qt, and prints the exact command
it will run before running it.

Installing gives you the same tool under three names: **`ky`** to type,
**`kontainy`** to read, and `kty` kept from the first release. On Windows,
`kontainy-gui` opens the window without a console.

| Short | Full | What it does |
|:------|:-----|:-------------|
| `ky` | `kontainy` | Open the window |
| `ky overview` | `kontainy overview` | Every technology here: installed, version, active target, object count |
| `ky tech` | `kontainy tech` | The technologies available on this system, and where they run |
| `ky docker targets` | `kontainy docker targets` | List contexts, the active one marked, with *rootful* / *rootless* / *remote* |
| `ky docker use NAME` | `kontainy docker use NAME` | Switch the active context (asks first) |
| `ky docker add NAME host=ssh://u@h` | `kontainy docker add …` | Add a context — `ky docker add` alone lists the fields |
| `ky docker rm-target NAME` | `kontainy docker rm-target NAME` | Remove a context |
| `ky docker test [NAME]` | `kontainy docker test` | Check a context answers |
| `ky docker ls` | `kontainy docker ls` | List containers on the active context |
| `ky docker stop web db` | `kontainy docker stop web db` | Act on containers by name: `start`, `stop`, `restart`, `logs`, `rm` |
| `ky docker start-all` | `kontainy docker start-all` | Start every stopped container (`stop-all` too) |
| `ky docker ports web 8080:80` | `kontainy docker ports web 8080:80` | Change a container's ports safely (recreates, keeps the original) |
| `ky podman services` | `kontainy podman services` | The systemd units it depends on |
| `ky podman service enable podman.socket` | `kontainy podman service …` | Start, stop, enable, disable a unit |
| `ky docker shell` | `kontainy docker shell` | `DOCKER_CONTEXT` / `DOCKER_HOST` in your shell profile |
| `ky docker shell set DOCKER_CONTEXT build` | `kontainy docker shell set …` | Pin new terminals to a target |
| `ky kvm ls` | `kontainy libvirt ls` | Virtual machines; `start`, `shutdown`, `reboot`, `force-off`, `autostart` |
| `ky kvm networks` | `kontainy libvirt networks` | Virtual networks; `start`, `stop`, `autostart`, `leases NAME` |
| `ky kvm networks create name=lab bridge=virbr10 address=192.168.110.1 prefix=24` | … | Create a NAT network |
| `ky hyperv ls` | `kontainy hyperv ls` | Hyper-V machines; `start`, `shutdown`, `save-state`, `turn-off`, `checkpoint` |
| `ky hyperv switches` | `kontainy hyperv switches` | Hyper-V virtual switches |
| `ky k8s targets` · `ky k8s ls` | `kontainy kubernetes …` | Kubeconfig contexts; pods with `logs`, `describe`, `delete` |
| `ky incus ls` · `ky lxd ls` | `kontainy incus ls` | Instances; `start`, `stop`, `restart`, `delete` |
| `ky TECH verbs` | `kontainy TECH verbs` | Everything one technology accepts |
| `ky tools` | `kontainy tools` | Every installable tool, installed or not |
| `ky install qemu` | `kontainy install qemu` | Install a tool with this system's package manager |
| `ky uninstall qemu` | `kontainy uninstall qemu` | Remove it |
| `ky catalog log-driver` | `kontainy catalog log-driver` | One configuration key, explained |
| `ky catalog --search dns` | `kontainy catalog --search dns` | Search the 152 keys |
| `ky doctor` | `kontainy doctor` | Run every diagnostic rule |
| `ky scan` | `kontainy scan` | The context chain and every engine found |
| `ky wsl` · `ky wsl use NAME` | `kontainy wsl …` | *(Windows)* Which WSL distribution carries the Linux tools |
| `ky -V` | `kontainy -V` | Show the version (also `version`) |
| `ky -h` | `kontainy -h` | Show help |

Flags that work with every action, anywhere on the line:

| Flag | Meaning |
|:-----|:--------|
| `-y`, `--yes` | Run without asking. Without a terminal, an action that would ask **refuses** unless `-y` is given — a script never runs something by accident |
| `--dry-run` | Show the command, run nothing |
| `--json` | Print lists as JSON |
| `--target NAME` | Act on this target instead of the active one |
| `-q`, `--quiet` | Don't print explanations |

```console
$ ky docker stop web
■  Stop
  $ docker --context default stop web
  Sends SIGTERM to web, then SIGKILL after the stop timeout if it has not exited.

Run this? [y/N] y
web
```

---

## 🏗️ Build from source

Builds are made in CI, on each platform's own runner — there is no
cross-compilation. Pushing a `v*` tag runs the whole pipeline: tests, then
Windows, macOS ARM64 and Linux AppImage builds, then a GitHub release with a
categorised changelog, then PyPI.

```bash
python build.py            # one file, windowed   -> dist/kontainy[.exe]
python build.py --debug    # one file, console
python build.py --onedir   # a directory          -> dist/kontainy/
```

Run the test suite — 245 tests in under four seconds, because PySide6 is
stubbed and the suite covers decisions rather than widgets:

```bash
pip install pytest
python -m pytest -q
```

---

## 🌍 Translations

The interface is English. A translation layer covering eleven languages is
planned; see the project roadmap.

---

## 📝 License

MIT — see [LICENSE](https://github.com/bayramkotan/kontainy/blob/main/LICENSE).

<div align="center">

⭐ **If kontainy helps you, consider [giving it a star](https://github.com/bayramkotan/kontainy)!** ⭐

[🐛 Report Bug](https://github.com/bayramkotan/kontainy/issues) · [💡 Request Feature](https://github.com/bayramkotan/kontainy/issues)

</div>

---

<div align="center">

**Made with ❤️ by [Bayram Kotan](https://github.com/bayramkotan)**

[GitHub](https://github.com/bayramkotan/kontainy) · [Releases](https://github.com/bayramkotan/kontainy/releases) · [Issues](https://github.com/bayramkotan/kontainy/issues) · [Screenshots](https://github.com/bayramkotan/kontainy#-screenshots)

⭐ **If kontainy helps you, give it a star!** ⭐

</div>
