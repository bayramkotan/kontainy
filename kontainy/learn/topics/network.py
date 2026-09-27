"""Networking — where containers actually reach each other, and where not."""

TOPICS = [
    {
        "title": "The default bridge does not resolve names",
        "body": (
            "On the default bridge, containers get addresses and outbound "
            "NAT, and that is all. There is no DNS between them: `ping db` "
            "fails, and the application that wanted the database reports "
            "\"connection refused\" or \"host not found\".\n\n"
            "A user-defined network adds an embedded DNS server, so every "
            "container on it resolves the others by name and by alias. This "
            "one difference is behind most first-day networking trouble."),
        "snippet": (
            "docker network create app\n"
            "docker run -d --network app --name db postgres:16\n"
            "docker run --network app --rm alpine getent hosts db\n\n"
            "# the old way, deprecated and worth forgetting\n"
            "# docker run --link db:db ..."),
        "language": "bash",
        "rule_id": "NET01",
    },
    {
        "title": "localhost inside a container is the container",
        "body": (
            "Every container has its own network namespace, so 127.0.0.1 "
            "there means itself — not the host, not the container next to "
            "it. A service on the host is reached by the host's address on "
            "the bridge, or by a name the engine provides.\n\n"
            "Docker Desktop and recent Docker on Linux provide "
            "`host.docker.internal`; Podman provides `host.containers."
            "internal`."),
        "snippet": (
            "docker run --rm --add-host host.docker.internal:host-gateway "
            "alpine \\\n"
            "  getent hosts host.docker.internal\n\n"
            "podman run --rm alpine getent hosts host.containers.internal\n\n"
            "ip -4 addr show docker0 | grep inet     # the bridge address"),
        "language": "bash",
        "note": (
            "Containers in the same pod (Podman) or sharing a network "
            "namespace do reach each other on localhost — that is what "
            "sharing the namespace means."),
    },
    {
        "title": "Published ports, and what is listening where",
        "body": (
            "Publishing binds a host port and forwards it. A container "
            "whose service listens on 127.0.0.1 INSIDE the container "
            "publishes nothing useful: the forward arrives on the "
            "container's external address and finds nothing there.\n\n"
            "Applications must listen on 0.0.0.0 inside a container. This "
            "is the second most common \"it works locally\" failure."),
        "snippet": (
            "docker exec web ss -tulpn          # what is listening inside\n"
            "sudo ss -tulpn | grep docker-proxy # what was published outside\n\n"
            "# in the application's own config\n"
            "# bind 0.0.0.0 rather than 127.0.0.1"),
        "language": "bash",
        "rule_id": "NET02",
    },
    {
        "title": "How outbound traffic leaves: NAT and masquerading",
        "body": (
            "A bridge network is a private subnet. Traffic leaving it is "
            "masqueraded behind the host's address by a rule the engine "
            "writes, which is why a container can reach the internet "
            "without any configuration and why the server on the other end "
            "sees the host.\n\n"
            "If outbound traffic suddenly stops after a firewall reload, "
            "the rules were flushed and the engine needs to write them "
            "again."),
        "snippet": (
            "sudo iptables -t nat -L DOCKER-USER -n\n"
            "sudo nft list table ip filter | head -30\n\n"
            "sudo systemctl restart docker    # rewrites the rules\n"
            "docker run --rm alpine ping -c1 1.1.1.1"),
        "language": "bash",
        "warning": (
            "Docker inserts its rules ahead of most firewall front ends, so "
            "a published port can be reachable even though ufw or firewalld "
            "says it is closed. Bind to 127.0.0.1 when a port should stay "
            "local."),
    },
    {
        "title": "DNS inside a container",
        "body": (
            "The engine writes /etc/resolv.conf in the container. On a "
            "user-defined network it points at the engine's own resolver, "
            "which answers container names and forwards everything else.\n\n"
            "On a laptop with systemd-resolved, the host's resolv.conf "
            "points at 127.0.0.53, which means nothing inside a container — "
            "engines work around it, and when the workaround fails, "
            "external names stop resolving while container names still do."),
        "snippet": (
            "docker run --rm alpine cat /etc/resolv.conf\n"
            "docker run --rm --dns 1.1.1.1 alpine nslookup example.com\n\n"
            "# for every container, in daemon.json\n"
            "{\"dns\": [\"1.1.1.1\", \"9.9.9.9\"]}"),
        "language": "json",
        "setting_key": "dns",
    },
    {
        "title": "Network aliases and several names for one container",
        "body": (
            "A container can answer to more than one name on a network. "
            "This is how you point an application at `db` while the "
            "container is called `postgres-16-primary`, without changing "
            "either.\n\n"
            "It is also how a blue/green switch is done locally: move the "
            "alias, not the configuration."),
        "snippet": (
            "docker run -d --network app --name postgres-16-primary \\\n"
            "  --network-alias db postgres:16\n\n"
            "docker network connect --alias cache app redis-container\n"
            "docker run --rm --network app alpine getent hosts db"),
        "language": "bash",
    },
    {
        "title": "A container on several networks",
        "body": (
            "A container can join more than one network, and this is the "
            "usual way to keep a database off the network that faces the "
            "world: the application joins both, the database only the "
            "private one.\n\n"
            "Each network gives its own interface and its own address, and "
            "the container resolves names on all of them."),
        "snippet": (
            "docker network create frontend\n"
            "docker network create backend\n\n"
            "docker run -d --name db --network backend postgres:16\n"
            "docker run -d --name api --network backend myapi\n"
            "docker network connect frontend api\n\n"
            "docker inspect api --format "
            "'{{range $n,$v := .NetworkSettings.Networks}}{{$n}} {{end}}'"),
        "language": "bash",
    },
    {
        "title": "macvlan and ipvlan: an address on the real network",
        "body": (
            "macvlan gives the container its own MAC address and an IP on "
            "your LAN. To the rest of the network it is another machine — "
            "which is what you want for something that must be discoverable "
            "by other devices, like a DHCP or mDNS service.\n\n"
            "The catch is deliberate and confusing: the host cannot talk to "
            "its own macvlan containers without an extra interface, and "
            "most wireless adapters refuse macvlan entirely."),
        "snippet": (
            "docker network create -d macvlan \\\n"
            "  --subnet 192.168.1.0/24 --gateway 192.168.1.1 \\\n"
            "  --ip-range 192.168.1.240/28 -o parent=eth0 lan\n\n"
            "docker run -d --network lan --ip 192.168.1.241 nginx"),
        "language": "bash",
        "warning": (
            "Reserve the range in your router's DHCP settings first, or the "
            "router will hand the same addresses to something else."),
    },
    {
        "title": "Subnet clashes with the office or the VPN",
        "body": (
            "Docker allocates networks from 172.17.0.0/16 upward. If your "
            "company network or VPN uses the same range, routes disappear "
            "the moment a network is created — and the symptom is that the "
            "VPN works until you start a container.\n\n"
            "The fix is to move Docker's pools somewhere nobody else uses."),
        "snippet": (
            "{\n"
            "  \"default-address-pools\": [\n"
            "    {\"base\": \"10.200.0.0/16\", \"size\": 24},\n"
            "    {\"base\": \"10.201.0.0/16\", \"size\": 24}\n"
            "  ]\n"
            "}"),
        "language": "json",
        "note": (
            "Existing networks keep their old subnets: remove and recreate "
            "them after changing the pools, with the daemon restarted in "
            "between."),
        "setting_key": "default-address-pools",
        "rule_id": "NET03",
    },
    {
        "title": "MTU: the transfer that stops at 1.4 MB",
        "body": (
            "On a VPN or some cloud networks the path MTU is below 1500. A "
            "bridge created with 1500 then sends packets that cannot get "
            "through, and the result is not an error: small requests work, "
            "large transfers hang. `apt update` stalling inside a container "
            "while ping works is the classic sign.\n\n"
            "Set the engine's MTU to match the interface it leaves by."),
        "snippet": (
            "ip link show | grep -E 'mtu [0-9]+' | head\n"
            "docker run --rm alpine ping -M do -s 1472 -c1 1.1.1.1  # 1500?\n\n"
            "# daemon.json\n"
            "{\"mtu\": 1400}\n\n"
            "docker network create -o com.docker.network.driver.mtu=1400 app"),
        "language": "bash",
        "setting_key": "mtu",
    },
    {
        "title": "Rootless networking: pasta, slirp4netns and ports",
        "body": (
            "A rootless container cannot create a bridge on the host, so "
            "traffic goes through a userspace network stack instead. "
            "slirp4netns was the long-standing one; pasta is the current "
            "default in Podman and is faster and keeps source addresses.\n\n"
            "Two consequences: ports below 1024 need a sysctl change, and "
            "the container's outgoing address is not the host's by default "
            "unless pasta is in use."),
        "snippet": (
            "podman info --format '{{.Host.NetworkBackend}}'\n"
            "podman run --network pasta:--map-gw alpine ip addr\n\n"
            "sudo sysctl net.ipv4.ip_unprivileged_port_start=80\n"
            "echo 'net.ipv4.ip_unprivileged_port_start=80' | "
            "sudo tee /etc/sysctl.d/99-rootless.conf"),
        "language": "bash",
        "rule_id": "NET02",
    },
    {
        "title": "Debugging from inside: a container with the tools",
        "body": (
            "Most images have no `ping`, `dig`, `ss` or `curl`, and "
            "installing them into a running container is the wrong "
            "instinct. Start a second container in the FIRST one's network "
            "namespace instead: same addresses, same routes, full toolbox, "
            "and nothing added to the image.\n\n"
            "This works for stopped-network debugging too: attach to the "
            "network rather than the container."),
        "snippet": (
            "docker run --rm -it --network container:web nicolaka/netshoot\n"
            "# inside: ss -tulpn; dig db; curl -v http://api:3000; "
            "tcpdump -i any port 5432\n\n"
            "docker run --rm -it --network app nicolaka/netshoot nslookup db"),
        "language": "bash",
        "tip": (
            "nicolaka/netshoot is the usual choice; alpine plus "
            "`apk add curl bind-tools iproute2` is the same idea if you "
            "would rather not pull an unfamiliar image."),
    },
    {
        "title": "Reaching a service on the host from a container",
        "body": (
            "The host is not localhost. Three ways in, in order of "
            "preference: the gateway name the engine provides, the bridge "
            "gateway address, or `--network=host` when isolation is not the "
            "point.\n\n"
            "On Linux, `host.docker.internal` needs the `--add-host "
            "host-gateway` mapping unless a recent Docker adds it for you."),
        "snippet": (
            "docker run --rm --add-host host.docker.internal:host-gateway "
            "alpine \\\n"
            "  wget -qO- http://host.docker.internal:5432\n\n"
            "ip route | awk '/default/ {print $3}'   # the gateway address\n"
            "docker run --rm --network host alpine ss -tulpn | head"),
        "language": "bash",
        "warning": (
            "A database on the host that listens only on 127.0.0.1 is "
            "unreachable from a container whatever you do — it must listen "
            "on the bridge address as well."),
    },
    {
        "title": "IPv6, and why it is off until you turn it on",
        "body": (
            "Docker does not give containers IPv6 addresses by default. On "
            "a network that is IPv6-first, the symptom is an application "
            "that resolves an AAAA record and then cannot connect.\n\n"
            "Enabling it means giving the daemon a ULA subnet and, if those "
            "addresses should leave the machine, arranging NAT or routing "
            "for them."),
        "snippet": (
            "{\n"
            "  \"ipv6\": true,\n"
            "  \"fixed-cidr-v6\": \"fd00:dead:beef::/64\",\n"
            "  \"experimental\": true,\n"
            "  \"ip6tables\": true\n"
            "}"),
        "language": "json",
        "note": (
            "Podman enables IPv6 per network: `podman network create --ipv6 "
            "app`, which is easier to reason about than a daemon-wide "
            "switch."),
    },
]
