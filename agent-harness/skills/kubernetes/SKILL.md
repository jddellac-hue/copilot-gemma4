# Kubernetes

Expertise Kubernetes pour le diagnostic, l'investigation et le monitoring de clusters.

## Architecture conceptuelle

### Objets fondamentaux

- **Pod** : plus petite unite deployable. Contient un ou plusieurs conteneurs.
- **Deployment** : gere un ReplicaSet, rolling updates, rollbacks.
- **StatefulSet** : pods avec identite stable et stockage persistant.
- **DaemonSet** : un pod par noeud (monitoring, logging, CNI).
- **Service** : abstraction reseau stable devant des pods.
  - ClusterIP (defaut), NodePort, LoadBalancer, ExternalName.
- **Ingress** : routage HTTP/HTTPS externe vers les Services.
- **ConfigMap / Secret** : configuration et donnees sensibles injectees dans les pods.
- **PersistentVolume (PV) / PersistentVolumeClaim (PVC)** : stockage persistant.
- **Job / CronJob** : taches ponctuelles ou planifiees.
- **HorizontalPodAutoscaler (HPA)** : autoscaling sur CPU/memoire/metriques custom.
- **NetworkPolicy** : regles de filtrage reseau entre pods.

### Namespaces

Isolation logique. Bonnes pratiques :
- `kube-system` : composants systeme (coredns, kube-proxy, CNI).
- `monitoring` : Prometheus, Grafana, Dynatrace OneAgent.
- Un namespace par application ou par equipe.
- ResourceQuota et LimitRange par namespace en production.

## Diagnostic courant

### Pod en CrashLoopBackOff

1. `kubectl describe pod <name>` : lire la section Events et le Last State.
2. `kubectl logs <pod> --previous` : logs du conteneur qui a crashe.
3. Causes frequentes :
   - OOMKilled : le conteneur depasse sa limite memoire. Augmenter `resources.limits.memory`.
   - Exit code 1 : erreur applicative. Lire les logs.
   - Exit code 137 : SIGKILL (OOM ou preemption). Verifier les metriques memoire.
   - Exit code 143 : SIGTERM gracieux mais le process n'a pas fini dans le `terminationGracePeriodSeconds`.
4. Liveness probe trop agressive : le pod redemarrage avant d'etre pret. Augmenter `initialDelaySeconds`.

### Pod en Pending

1. `kubectl describe pod <name>` : section Events.
2. Causes :
   - Insufficient CPU/memory : le scheduler ne trouve pas de noeud. Verifier `kubectl describe nodes` (Allocatable vs Allocated).
   - PVC en Pending : le StorageClass ne provisionne pas. Verifier `kubectl get pvc` et `kubectl get pv`.
   - Taints/tolerations : le noeud a un taint que le pod ne tolere pas.
   - NodeSelector/affinity : aucun noeud ne matche.

### Pod en ImagePullBackOff

1. Image introuvable ou tag inexistant.
2. Credentials manquants : `imagePullSecrets` absent ou expire.
3. Registry inaccessible (reseau, proxy, DNS).

### Service ne repond pas

1. Verifier les endpoints : `kubectl get endpoints <service>`.
   - Vide = aucun pod ne matche le selector du Service.
2. Verifier le selector du Service vs les labels des pods.
3. Tester la connectivite depuis un pod : `kubectl exec -it <pod> -- curl <service>:<port>`.
4. Pour NodePort/LoadBalancer : verifier le firewall et les security groups.

## Patterns de deploiement

### Rolling Update (defaut)

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 25%
      maxUnavailable: 25%
```

- Deploie progressivement les nouveaux pods avant de supprimer les anciens.
- `maxSurge` : combien de pods en plus pendant la transition.
- `maxUnavailable` : combien de pods indisponibles pendant la transition.

### Blue-Green

- Deux Deployments (blue et green) avec un Service qui pointe sur un seul.
- Switcher le selector du Service apres validation.
- Rollback instantane : re-switcher le selector.

### Canary

- Deployer une petite portion de trafic sur la nouvelle version.
- Avec Ingress nginx : annotation `canary-weight`.
- Avec Istio/Linkerd : VirtualService avec weight-based routing.

## Probes

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5

startupProbe:
  httpGet:
    path: /health/started
    port: 8080
  failureThreshold: 30
  periodSeconds: 10
```

- **Liveness** : le conteneur est-il vivant ? Echec = restart.
- **Readiness** : le conteneur accepte-t-il du trafic ? Echec = retire des endpoints.
- **Startup** : pour les demarrages lents. Desactive liveness/readiness pendant le startup.

## Gestion des ressources

```yaml
resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 512Mi
```

- `requests` : minimum garanti. Utilise par le scheduler.
- `limits` : maximum. Depassement memoire = OOMKilled. Depassement CPU = throttle.
- **Bonne pratique** : toujours definir les deux. Ratio limits/requests de 2:1 a 4:1.

## Observabilite

### Metriques

- **Metrics Server** : `kubectl top pods`, `kubectl top nodes`.
- **Prometheus** : scrape `/metrics` via ServiceMonitor.
- **Dynatrace OneAgent** : injection automatique dans les pods (operator).
- **HPA** : autoscaling sur `cpu`, `memory`, ou metriques custom via Prometheus Adapter.

### Logs

- `kubectl logs <pod>` : stdout/stderr du conteneur.
- `kubectl logs <pod> -c <container>` : conteneur specifique dans un pod multi-conteneurs.
- `kubectl logs <pod> --previous` : logs du conteneur precedent (apres crash).
- `kubectl logs -l app=myapp` : logs de tous les pods avec le label.
- **Centralisation** : Loki + Promtail, ELK (Filebeat), Dynatrace Log Monitoring.

### Events

- `kubectl get events --sort-by=.lastTimestamp` : tous les evenements du namespace.
- `kubectl get events --field-selector involvedObject.name=<pod>` : evenements d'un pod.
- Les events expirent apres 1h (defaut). Pour du long-terme, configurer un event exporter.

## Kustomize

Structure standard pour les overlays multi-environnement :

```
deployments/
  base/
    deployment.yaml
    service.yaml
    kustomization.yaml
  overlays/
    dev/
      kustomization.yaml      # patches dev
    preprod/
      kustomization.yaml
    prod/
      kustomization.yaml
```

- `kustomize build overlays/dev | kubectl apply -f -`
- Patches : strategic merge, JSON patches, ou `patchesStrategicMerge`.
- Remplacements : `images`, `namePrefix`, `nameSuffix`, `commonLabels`.

## Helm

- `helm install <release> <chart>` : installer.
- `helm upgrade <release> <chart> -f values-prod.yaml` : mettre a jour.
- `helm rollback <release> <revision>` : revenir en arriere.
- `helm list` : releases installees.
- `helm template` : generer les manifests sans installer (utile pour debug).
- Toujours utiliser `--atomic` en CI pour rollback automatique en cas d'echec.

## Securite

### RBAC

- **Role/ClusterRole** : definit les permissions (verbs sur resources).
- **RoleBinding/ClusterRoleBinding** : associe un Role a un User/Group/ServiceAccount.
- Principe du moindre privilege : un ServiceAccount par application, pas de `cluster-admin`.

### Pod Security

- `securityContext.runAsNonRoot: true` : interdire root.
- `securityContext.readOnlyRootFilesystem: true` : filesystem en lecture seule.
- `securityContext.allowPrivilegeEscalation: false` : pas d'escalade.
- Pod Security Standards (PSS) : Privileged, Baseline, Restricted.

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

- Deny-all par defaut, puis ouvrir ce qui est necessaire.
- Necessite un CNI compatible (Calico, Cilium, Weave).

## Troubleshooting avance

### DNS

- Tester depuis un pod : `kubectl exec -it <pod> -- nslookup <service>`.
- CoreDNS logs : `kubectl logs -n kube-system -l k8s-app=kube-dns`.
- Service FQDN : `<service>.<namespace>.svc.cluster.local`.

### Stockage

- PVC en Pending : verifier StorageClass, provisioner, quotas.
- Pod en ContainerCreating avec volume : `kubectl describe pod` pour les events de montage.
- Multi-attach error : le PV est deja monte sur un autre noeud (ReadWriteOnce).

### Performance

- CPU throttling : `kubectl top pod` vs limits. Si `throttled_time` eleve, augmenter les limits CPU.
- OOMKilled frequent : augmenter limits memory ou investiguer les fuites memoire.
- Slow scheduling : verifier les ResourceQuotas et le nombre de pods pending.

## Integration avec le harness

L'agent dispose de 3 outils Kubernetes read-only :
- `kubectl_get(kind, namespace?, selector?)` : lister des ressources.
- `kubectl_describe(kind, name, namespace?)` : detail d'une ressource.
- `kubectl_logs(pod, container?, namespace?, tail?, since?, previous?)` : logs.

Contraintes de securite :
- Le contexte est **verrouille** dans le profil (pas de switch accidentel).
- Les namespaces sont **restreints** a une liste autorisee.
- Les kinds sont **filtres** : seules les ressources read-only sont permises.
- Aucune commande mutante (apply, delete, create, scale, exec) n'est disponible.
