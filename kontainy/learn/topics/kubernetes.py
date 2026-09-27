"""Kubernetes — the objects, and the parts that bite on the first cluster."""

TOPICS = [
    {
        "title": "Desired state, not commands",
        "body": (
            "You do not tell Kubernetes to start a container. You declare "
            "what should exist, and controllers work continuously to make "
            "reality match. Delete a pod a Deployment owns and another "
            "appears — that is not a bug, it is the entire idea.\n\n"
            "This is why `kubectl apply` on a file beats `kubectl run`: the "
            "file is the truth, and it can be reviewed, versioned and "
            "applied again."),
        "snippet": (
            "kubectl apply -f deployment.yaml\n"
            "kubectl diff -f deployment.yaml     # what would change\n"
            "kubectl get deploy web -o yaml | head -30"),
        "language": "bash",
    },
    {
        "title": "Pods: the unit that is not a container",
        "body": (
            "A pod is one or more containers that share a network "
            "namespace and can share volumes. They are scheduled together, "
            "live together and die together, and they reach each other on "
            "localhost.\n\n"
            "Most pods hold one container. The second is usually a sidecar: "
            "a log shipper, a proxy, or something that prepares state in an "
            "init container before the main one starts."),
        "snippet": (
            "kubectl get pods -o wide\n"
            "kubectl describe pod web-7d4f8-abc12\n"
            "kubectl logs web-7d4f8-abc12 -c sidecar\n"
            "kubectl exec -it web-7d4f8-abc12 -- sh"),
        "language": "bash",
    },
    {
        "title": "Deployments, ReplicaSets and rollouts",
        "body": (
            "A Deployment owns a ReplicaSet, and the ReplicaSet owns the "
            "pods. Changing the pod template creates a NEW ReplicaSet and "
            "moves pods across gradually — that is a rolling update.\n\n"
            "The old ReplicaSet is kept, which is what makes `rollout undo` "
            "instant."),
        "snippet": (
            "kubectl set image deploy/web web=myapp:1.5\n"
            "kubectl rollout status deploy/web\n"
            "kubectl rollout history deploy/web\n"
            "kubectl rollout undo deploy/web --to-revision=3"),
        "language": "bash",
    },
    {
        "title": "Services: a stable name in front of moving pods",
        "body": (
            "Pods come and go with new addresses. A Service is a stable "
            "name and address in front of whichever pods match its "
            "selector.\n\n"
            "ClusterIP is internal only. NodePort opens a high port on "
            "every node. LoadBalancer asks the cloud for one; on a bare "
            "cluster it stays `pending` forever unless something like "
            "MetalLB provides it."),
        "snippet": (
            "kubectl expose deploy web --port 80 --target-port 8080\n"
            "kubectl get svc web -o wide\n"
            "kubectl get endpoints web        # the pods actually behind it\n\n"
            "# from another pod\n"
            "curl http://web.default.svc.cluster.local"),
        "language": "bash",
        "warning": (
            "An empty Endpoints list means the selector matches nothing — "
            "usually a label typo, and the reason a Service returns nothing "
            "while the pods are healthy."),
    },
    {
        "title": "Labels and selectors hold everything together",
        "body": (
            "Kubernetes has no pointers between objects. A Service finds "
            "pods by matching labels; a Deployment owns pods the same way. "
            "Get a label wrong and the objects simply do not know about "
            "each other, with no error anywhere.\n\n"
            "This is the single most common cause of \"it is running but "
            "nothing reaches it\"."),
        "snippet": (
            "kubectl get pods --show-labels\n"
            "kubectl get pods -l app=web,tier=frontend\n"
            "kubectl label pod web-abc environment=staging\n\n"
            "kubectl get svc web -o jsonpath='{.spec.selector}'"),
        "language": "bash",
    },
    {
        "title": "Namespaces, and the context that decides where you are",
        "body": (
            "A namespace is a scope for names and a boundary for quotas and "
            "policies. Nothing stops traffic between namespaces by default "
            "— that needs a NetworkPolicy.\n\n"
            "Your kubeconfig context carries both the cluster and the "
            "current namespace, which is why the same command can act on "
            "two different clusters depending on nothing you typed."),
        "snippet": (
            "kubectl config get-contexts\n"
            "kubectl config current-context\n"
            "kubectl config set-context --current --namespace=staging\n\n"
            "kubectl get pods -A     # every namespace, when lost"),
        "language": "bash",
        "rule_id": "K8S01",
    },
    {
        "title": "kubeconfig: several clusters, one file",
        "body": (
            "~/.kube/config holds clusters, users and contexts — a context "
            "being a pairing of the three. KUBECONFIG can list several "
            "files, merged left to right.\n\n"
            "The dangerous habit is a single context named `default` "
            "pointing at production. Name contexts after what they are, and "
            "check before a destructive command."),
        "snippet": (
            "export KUBECONFIG=~/.kube/config:~/.kube/work.yaml\n"
            "kubectl config view --flatten > merged.yaml\n\n"
            "kubectl config use-context prod-eu\n"
            "kubectl cluster-info"),
        "language": "bash",
    },
    {
        "title": "ConfigMaps and Secrets",
        "body": (
            "Both hold key/value data and are mounted as files or injected "
            "as environment variables. A Secret is base64-encoded, which is "
            "encoding, not encryption: anyone who can read the object can "
            "read the value.\n\n"
            "Encryption at rest is a cluster setting, and secrets in git "
            "need sealing or an external store."),
        "snippet": (
            "kubectl create configmap app-config --from-file=app.conf\n"
            "kubectl create secret generic db --from-literal=password=s3cr3t\n\n"
            "kubectl get secret db -o jsonpath='{.data.password}' | base64 -d\n"
            "kubectl describe configmap app-config"),
        "language": "bash",
        "warning": (
            "A mounted ConfigMap updates in the pod within a minute or two; "
            "one injected as an environment variable does not update at "
            "all until the pod restarts."),
    },
    {
        "title": "Probes: liveness, readiness, startup",
        "body": (
            "Readiness decides whether traffic is sent. Liveness decides "
            "whether the container is restarted. Startup gives a slow "
            "application time before the other two begin.\n\n"
            "A liveness probe that is really a readiness probe is a "
            "restart loop waiting to happen: the application is fine, it is "
            "just busy, and Kubernetes keeps killing it."),
        "snippet": (
            "readinessProbe:\n"
            "  httpGet: {path: /ready, port: 8080}\n"
            "  periodSeconds: 5\n"
            "livenessProbe:\n"
            "  httpGet: {path: /healthz, port: 8080}\n"
            "  periodSeconds: 10\n"
            "  failureThreshold: 3\n"
            "startupProbe:\n"
            "  httpGet: {path: /healthz, port: 8080}\n"
            "  failureThreshold: 30\n"
            "  periodSeconds: 5"),
        "language": "yaml",
    },
    {
        "title": "Requests and limits, and the QoS class they decide",
        "body": (
            "A request is what the scheduler reserves; a limit is what the "
            "kernel enforces. Requests decide where a pod fits, limits "
            "decide when it is throttled or killed.\n\n"
            "The pair also sets the QoS class: equal requests and limits "
            "give Guaranteed, request-only gives Burstable, neither gives "
            "BestEffort — and BestEffort pods are evicted first when a node "
            "runs out of memory."),
        "snippet": (
            "resources:\n"
            "  requests: {memory: 256Mi, cpu: 250m}\n"
            "  limits:   {memory: 512Mi, cpu: '1'}\n\n"
            "# kubectl get pod web -o jsonpath='{.status.qosClass}'\n"
            "# kubectl top pods"),
        "language": "yaml",
        "warning": (
            "A CPU limit throttles; a memory limit kills. OOMKilled in a "
            "pod's status is the memory limit, not the node running out."),
    },
    {
        "title": "Storage: PV, PVC and StorageClass",
        "body": (
            "A PersistentVolumeClaim is what a pod asks for; a "
            "PersistentVolume is what it gets; a StorageClass is the "
            "recipe that creates one on demand.\n\n"
            "A claim that stays `Pending` usually means no default "
            "StorageClass, or an access mode the backend cannot provide — "
            "ReadWriteMany is not available on most block storage."),
        "snippet": (
            "kubectl get sc\n"
            "kubectl get pvc,pv\n"
            "kubectl describe pvc data-web-0     # the events say why\n\n"
            "# accessModes: ReadWriteOnce | ReadOnlyMany | ReadWriteMany"),
        "language": "bash",
    },
    {
        "title": "StatefulSets, and why a database is not a Deployment",
        "body": (
            "A StatefulSet gives each pod a stable name, a stable network "
            "identity and its own volume that follows it. Pods start and "
            "stop in order.\n\n"
            "That is what a database cluster needs and what a Deployment "
            "cannot offer: Deployment pods are interchangeable by design "
            "and share nothing."),
        "snippet": (
            "kubectl get statefulset,pods -l app=postgres\n"
            "# pods: postgres-0, postgres-1 — names that persist\n\n"
            "kubectl get pvc -l app=postgres    # one volume per pod\n"
            "kubectl delete pod postgres-0      # returns with the same "
            "name and disk"),
        "language": "bash",
    },
    {
        "title": "DaemonSets, Jobs and CronJobs",
        "body": (
            "A DaemonSet runs one pod per node — log collectors, network "
            "agents, node exporters. A Job runs something to completion and "
            "stops. A CronJob creates Jobs on a schedule.\n\n"
            "Jobs keep their pods after finishing, on purpose, so the logs "
            "can be read; `ttlSecondsAfterFinished` cleans them up when "
            "that is not wanted."),
        "snippet": (
            "kubectl get ds -A\n"
            "kubectl create job --from=cronjob/backup backup-now\n"
            "kubectl get jobs --watch\n"
            "kubectl logs job/backup-now"),
        "language": "bash",
    },
    {
        "title": "Ingress and the controller that has to exist",
        "body": (
            "An Ingress object is a rule: this host and path goes to that "
            "Service. It does nothing on its own — a controller must be "
            "installed to read it and configure a real proxy.\n\n"
            "An Ingress that \"does not work\" on a fresh cluster is usually "
            "a cluster with no ingress controller at all."),
        "snippet": (
            "kubectl get ingressclass\n"
            "kubectl get pods -n ingress-nginx\n"
            "kubectl describe ingress web\n\n"
            "# the newer, more capable alternative: the Gateway API"),
        "language": "bash",
    },
    {
        "title": "RBAC: who may do what",
        "body": (
            "A Role grants verbs on resources inside one namespace; a "
            "ClusterRole does it cluster-wide. A binding attaches one to a "
            "user, a group or a ServiceAccount.\n\n"
            "Every pod runs as a ServiceAccount, `default` if you do not "
            "say otherwise — and in an old cluster that account may have "
            "more rights than the application needs."),
        "snippet": (
            "kubectl auth can-i delete pods\n"
            "kubectl auth can-i list secrets --as system:serviceaccount:"
            "default:myapp\n\n"
            "kubectl create role reader --verb=get,list "
            "--resource=pods\n"
            "kubectl create rolebinding me --role=reader --user=bayram"),
        "language": "bash",
    },
    {
        "title": "NetworkPolicies: nothing is closed by default",
        "body": (
            "Without a policy, every pod can reach every other pod in the "
            "cluster. A NetworkPolicy selects pods and describes what is "
            "allowed; once one policy selects a pod, everything else to "
            "that pod is denied.\n\n"
            "They also need a CNI plugin that implements them. On a plugin "
            "that does not, the object is accepted and quietly does "
            "nothing."),
        "snippet": (
            "apiVersion: networking.k8s.io/v1\n"
            "kind: NetworkPolicy\n"
            "metadata: {name: db-only-from-api}\n"
            "spec:\n"
            "  podSelector: {matchLabels: {app: db}}\n"
            "  policyTypes: [Ingress]\n"
            "  ingress:\n"
            "    - from: [{podSelector: {matchLabels: {app: api}}}]\n"
            "      ports: [{port: 5432}]"),
        "language": "yaml",
    },
    {
        "title": "Reading a broken pod",
        "body": (
            "The order is always the same: the pod's events, then its "
            "previous logs, then the node. `describe` ends with events, and "
            "they name the cause — image pull failures, failing probes, "
            "unschedulable pods, mount errors.\n\n"
            "`--previous` gets the logs of the container that just crashed, "
            "which is the one that knows why."),
        "snippet": (
            "kubectl describe pod web-abc | tail -20\n"
            "kubectl logs web-abc --previous\n"
            "kubectl get events --sort-by=.lastTimestamp | tail -20\n"
            "kubectl describe node <node> | grep -A8 Conditions"),
        "language": "bash",
        "table": {
            "headers": ["Status", "Usually means"],
            "rows": [
                ["ImagePullBackOff", "wrong name, tag, or no credentials"],
                ["CrashLoopBackOff", "it starts and exits; read the logs"],
                ["Pending", "nothing can schedule it: resources, taints, PVC"],
                ["CreateContainerConfigError", "a missing ConfigMap or Secret"],
                ["OOMKilled", "the memory limit was hit"],
            ]},
    },
    {
        "title": "Getting to a service without exposing it",
        "body": (
            "`port-forward` tunnels a local port to a pod or a Service "
            "through the API server. It needs no Ingress, no NodePort and "
            "no change to the cluster, which makes it the right tool for "
            "looking at something.\n\n"
            "It is a debugging tool: it dies with your terminal and handles "
            "one connection path only."),
        "snippet": (
            "kubectl port-forward svc/web 8080:80\n"
            "kubectl port-forward pod/db-0 5432:5432\n\n"
            "kubectl run -it --rm debug --image=nicolaka/netshoot --restart="
            "Never -- bash"),
        "language": "bash",
    },
    {
        "title": "Helm, and what a chart is",
        "body": (
            "A chart is templated YAML plus default values. `helm install` "
            "renders the templates with your values and applies the "
            "result; the release is tracked so it can be upgraded or rolled "
            "back.\n\n"
            "The habit worth keeping is `helm template` first: read what "
            "will be applied before applying it."),
        "snippet": (
            "helm repo add bitnami https://charts.bitnami.com/bitnami\n"
            "helm template myapp bitnami/postgresql -f values.yaml | less\n"
            "helm install myapp bitnami/postgresql -f values.yaml\n"
            "helm list\n"
            "helm rollback myapp 1"),
        "language": "bash",
    },
    {
        "title": "A local cluster: kind, minikube, k3s",
        "body": (
            "kind runs the cluster in containers and starts in seconds — "
            "the right choice for CI and for testing manifests. minikube "
            "runs a VM and bundles addons like ingress and the dashboard. "
            "k3s is a real, small cluster for a machine you keep.\n\n"
            "Docker Desktop's Kubernetes is a fourth: convenient, one node, "
            "and tied to Desktop's lifecycle."),
        "snippet": (
            "kind create cluster --name dev\n"
            "minikube start --driver=docker --addons=ingress\n"
            "curl -sfL https://get.k3s.io | sh -\n\n"
            "kubectl config get-contexts"),
        "language": "bash",
        "tip": (
            "kontainy's Kubernetes page says which of these produced the "
            "current context, and says \"no cluster configured\" rather than "
            "\"not installed\" when kubectl is there without one."),
    },
]
