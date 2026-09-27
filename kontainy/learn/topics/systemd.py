"""systemd & Quadlet — containers as ordinary services."""

TOPICS = [
    {
        "title": "Why a container should be a systemd unit",
        "body": (
            "`--restart=always` is the engine's own idea of persistence: it "
            "works while the engine runs, and under rootless Podman it does "
            "not survive a reboot at all.\n\n"
            "A systemd unit gives you what the rest of the machine already "
            "has — start at boot, ordering against other services, restart "
            "policy, resource limits, and logs in the journal next to "
            "everything else."),
        "snippet": (
            "systemctl --user status web.service\n"
            "journalctl --user -u web.service -f\n"
            "systemctl --user list-units '*.service' | grep -i container"),
        "language": "bash",
        "rule_id": "POD02",
    },
    {
        "title": "Quadlet: the .container file",
        "body": (
            "Quadlet is a systemd generator. You write a small declarative "
            "file, and systemd turns it into a unit at boot — no generated "
            "unit to keep in sync, no `podman generate systemd`, which is "
            "deprecated.\n\n"
            "User files live in ~/.config/containers/systemd/, system files "
            "in /etc/containers/systemd/."),
        "snippet": (
            "# ~/.config/containers/systemd/web.container\n"
            "[Unit]\n"
            "Description=nginx\n"
            "After=network-online.target\n\n"
            "[Container]\n"
            "Image=docker.io/library/nginx:alpine\n"
            "PublishPort=8080:80\n"
            "Volume=web-data:/usr/share/nginx/html:Z\n"
            "Environment=TZ=Europe/Istanbul\n\n"
            "[Service]\n"
            "Restart=always\n\n"
            "[Install]\n"
            "WantedBy=default.target"),
        "language": "ini",
        "tip": (
            "After writing it: `systemctl --user daemon-reload`, then "
            "`systemctl --user start web`. The unit name is the file name "
            "without the extension."),
    },
    {
        "title": "Lingering: what happens when you log out",
        "body": (
            "A user's services stop when the last session ends, unless "
            "lingering is enabled for that user. Without it, a rootless "
            "container that works perfectly in your terminal disappears the "
            "moment you close the SSH connection.\n\n"
            "It is one command, and it is the single most common reason a "
            "Quadlet unit \"does not survive a reboot\"."),
        "snippet": (
            "loginctl enable-linger $USER\n"
            "loginctl show-user $USER --property=Linger\n\n"
            "systemctl --user enable web.service"),
        "language": "bash",
        "rule_id": "POD02",
    },
    {
        "title": "Volumes, networks and pods as Quadlet files",
        "body": (
            "Quadlet has a file type per object: .volume, .network, .pod, "
            ".kube and .image. A container refers to them by file name, and "
            "systemd works out the order.\n\n"
            "This is how a pod with three containers becomes four small "
            "files rather than one script that has to run in the right "
            "sequence."),
        "snippet": (
            "# app.network\n"
            "[Network]\n"
            "Subnet=10.89.0.0/24\n\n"
            "# db.volume\n"
            "[Volume]\n\n"
            "# api.container\n"
            "[Container]\n"
            "Image=myapi:1.4\n"
            "Network=app.network\n"
            "Volume=db.volume:/data"),
        "language": "ini",
    },
    {
        "title": "Socket activation",
        "body": (
            "systemd can hold the listening socket and start the service "
            "only when the first connection arrives. Podman's own API "
            "socket works this way, which is why nothing is running until a "
            "tool connects.\n\n"
            "For your own services it means a container that costs nothing "
            "while idle, at the price of a first request that waits for "
            "startup."),
        "snippet": (
            "systemctl --user enable --now podman.socket\n"
            "systemctl --user status podman.socket podman.service\n\n"
            "ss -lx | grep podman"),
        "language": "bash",
        "rule_id": "POD01",
    },
    {
        "title": "Ordering: After=, Requires=, Wants=",
        "body": (
            "`After=` is order only; `Requires=` is a hard dependency that "
            "takes this unit down with the other one; `Wants=` is a soft "
            "one that does not.\n\n"
            "For a container that needs the network to be genuinely up, "
            "`After=network-online.target` together with "
            "`Wants=network-online.target` is the pair that works — "
            "network.target alone means \"the stack is configured\", not "
            "\"there is a route\"."),
        "snippet": (
            "[Unit]\n"
            "Description=api\n"
            "Wants=network-online.target\n"
            "After=network-online.target\n"
            "Requires=db.service\n"
            "After=db.service"),
        "language": "ini",
    },
    {
        "title": "Restart, RestartSec and the start limit",
        "body": (
            "systemd restarts a failing service, and then stops doing so: "
            "after StartLimitBurst failures within StartLimitIntervalSec it "
            "gives up and marks the unit failed.\n\n"
            "This is a feature — a service that cannot start should stop "
            "trying — but it surprises people who expect infinite retries "
            "and find the unit dead after five attempts."),
        "snippet": (
            "[Service]\n"
            "Restart=always\n"
            "RestartSec=5\n"
            "StartLimitBurst=5\n"
            "StartLimitIntervalSec=60\n\n"
            "# systemctl --user reset-failed web.service"),
        "language": "ini",
    },
    {
        "title": "Limits that systemd applies, not the engine",
        "body": (
            "A unit can carry its own cgroup limits, and for a rootless "
            "container these are often the ones that actually work, because "
            "systemd owns the delegated cgroup.\n\n"
            "MemoryMax is the hard ceiling, MemoryHigh the point where the "
            "kernel starts reclaiming aggressively — a softer signal that "
            "is usually the better first move."),
        "snippet": (
            "[Service]\n"
            "MemoryHigh=400M\n"
            "MemoryMax=512M\n"
            "CPUQuota=150%\n"
            "TasksMax=256\n\n"
            "# systemd-cgtop -1"),
        "language": "ini",
        "rule_id": "RES01",
    },
    {
        "title": "Logs: journald instead of files",
        "body": (
            "With the journald log driver, container output goes to the "
            "journal, gets rotated with everything else, and is searchable "
            "with the same commands as the rest of the system.\n\n"
            "`docker logs` and `podman logs` still work; the difference is "
            "that the disk cannot silently fill with a single unbounded "
            "json file."),
        "snippet": (
            "journalctl --user -u web.service --since '1 hour ago'\n"
            "journalctl CONTAINER_NAME=web -f\n"
            "journalctl --disk-usage\n\n"
            "podman run --log-driver journald nginx"),
        "language": "bash",
        "setting_key": "containers.log_driver",
    },
    {
        "title": "Timers instead of cron",
        "body": (
            "A systemd timer runs a unit on a schedule, with the logs, "
            "dependencies and limits of any other service — and, unlike "
            "cron, it can catch up a run that was missed while the machine "
            "was off.\n\n"
            "For a nightly backup container, this is the difference between "
            "a job you can inspect and a line in a crontab nobody reads."),
        "snippet": (
            "# backup.timer\n"
            "[Timer]\n"
            "OnCalendar=daily\n"
            "Persistent=true\n"
            "RandomizedDelaySec=15m\n\n"
            "[Install]\n"
            "WantedBy=timers.target\n\n"
            "# systemctl --user list-timers"),
        "language": "ini",
    },
]
